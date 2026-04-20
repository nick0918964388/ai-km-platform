"""
Output Scanner — 掃描 LLM 回應中的敏感資訊 (Security #3)

檢測模式：
- API keys / tokens / JWT
- 信用卡號、台灣身分證字號、email、電話
- 內部 IP（10.* / 172.16-31.* / 192.168.*）
- 密碼 hash（bcrypt / md5 特徵）
- SSH / AWS keys

動作：
- BLOCK：整段回應替換成警告訊息（critical 級別）
- REDACT：命中部分遮蔽（xxx***xx）
- WARN：記 audit，但不修改

預設策略：密鑰類 BLOCK，PII 類 REDACT，弱訊號 WARN。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ScanAction(Enum):
    PASS = "pass"
    WARN = "warn"       # 記 log，不改
    REDACT = "redact"   # 遮蔽命中部分
    BLOCK = "block"     # 整段擋下，回覆 refusal


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScanHit:
    pattern_name: str
    severity: Severity
    action: ScanAction
    matched: str        # 原文（audit 用，log 時 truncate）
    redacted: str       # 遮蔽版本


@dataclass
class ScanResult:
    action: ScanAction
    hits: list[ScanHit] = field(default_factory=list)
    cleaned_text: str = ""  # REDACT 後的文字（或 BLOCK 的 refusal）


class OutputScanner:
    """LLM 回應掃描器。Sync, <5ms/call 對 <10KB 文字。"""

    # (name, regex, severity, action)
    PATTERNS: list[tuple[str, re.Pattern, Severity, ScanAction]] = [
        # ── 密鑰類 → BLOCK ──
        ("openai_key", re.compile(r"sk-[a-zA-Z0-9]{20,}"), Severity.CRITICAL, ScanAction.BLOCK),
        ("anthropic_key", re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}"), Severity.CRITICAL, ScanAction.BLOCK),
        ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), Severity.CRITICAL, ScanAction.BLOCK),
        ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), Severity.HIGH, ScanAction.BLOCK),
        (
            "generic_api_key",
            re.compile(
                r"(?:api[_\-]?key|access[_\-]?token|secret[_\-]?key)[\"'\s:=]+[A-Za-z0-9_\-]{16,}",
                re.IGNORECASE,
            ),
            Severity.HIGH,
            ScanAction.BLOCK,
        ),
        (
            "ssh_private_key",
            re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PRIVATE) PRIVATE KEY-----"),
            Severity.CRITICAL,
            ScanAction.BLOCK,
        ),

        # ── PII → REDACT ──
        ("credit_card", re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), Severity.HIGH, ScanAction.REDACT),
        ("twn_id", re.compile(r"\b[A-Z][12]\d{8}\b"), Severity.HIGH, ScanAction.REDACT),
        (
            "email",
            re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
            Severity.MEDIUM,
            ScanAction.REDACT,
        ),
        ("phone_twn", re.compile(r"\b09\d{2}[-\s]?\d{3}[-\s]?\d{3}\b"), Severity.MEDIUM, ScanAction.REDACT),
        (
            "bcrypt_hash",
            re.compile(r"\$2[abxy]\$\d{2}\$[./A-Za-z0-9]{53}"),
            Severity.HIGH,
            ScanAction.REDACT,
        ),

        # ── 弱訊號 → WARN ──
        (
            "internal_ip",
            re.compile(
                r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
                r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
                r"|192\.168\.\d{1,3}\.\d{1,3})\b"
            ),
            Severity.MEDIUM,
            ScanAction.WARN,
        ),
        ("md5_hash", re.compile(r"\b[a-f0-9]{32}\b"), Severity.LOW, ScanAction.WARN),
    ]

    BLOCK_MESSAGE = (
        "抱歉，回應內容包含敏感資訊（如 API key、憑證等），"
        "已被安全機制攔截。如果您認為這是誤判，請聯絡管理員。"
    )

    def __init__(self, enable_redact: bool = True, enable_block: bool = True):
        self.enable_redact = enable_redact
        self.enable_block = enable_block

    def _redact(self, text: str) -> str:
        """遮蔽中間字元，保留頭尾便於 debug。"""
        if len(text) <= 6:
            return "***"
        if len(text) <= 10:
            return f"{text[:2]}***{text[-2:]}"
        return f"{text[:3]}***{text[-3:]}"

    def scan(self, text: str) -> ScanResult:
        if not text:
            return ScanResult(action=ScanAction.PASS, cleaned_text="")

        hits: list[ScanHit] = []
        cleaned = text
        action_priority = {
            ScanAction.PASS: 0,
            ScanAction.WARN: 1,
            ScanAction.REDACT: 2,
            ScanAction.BLOCK: 3,
        }
        highest_action = ScanAction.PASS

        for name, pat, severity, action in self.PATTERNS:
            for m in pat.finditer(text):
                matched = m.group(0)
                redacted = self._redact(matched)
                hits.append(ScanHit(name, severity, action, matched, redacted))

                if action == ScanAction.REDACT and self.enable_redact:
                    cleaned = cleaned.replace(matched, redacted)

                if action_priority[action] > action_priority[highest_action]:
                    highest_action = action

        # BLOCK 優先：整段替換
        if highest_action == ScanAction.BLOCK and self.enable_block:
            logger.warning(
                "[output_scanner] BLOCK triggered: hits=%s",
                [(h.pattern_name, h.severity.value) for h in hits if h.action == ScanAction.BLOCK],
            )
            return ScanResult(
                action=ScanAction.BLOCK,
                hits=hits,
                cleaned_text=self.BLOCK_MESSAGE,
            )

        if hits:
            logger.info(
                "[output_scanner] hits=%s action=%s",
                [(h.pattern_name, h.severity.value) for h in hits],
                highest_action.value,
            )

        return ScanResult(
            action=highest_action,
            hits=hits,
            cleaned_text=cleaned,
        )


_scanner: OutputScanner | None = None


def get_output_scanner() -> OutputScanner:
    global _scanner
    if _scanner is None:
        _scanner = OutputScanner()
    return _scanner
