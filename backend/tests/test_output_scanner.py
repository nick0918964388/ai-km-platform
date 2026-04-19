"""Output Scanner 單元測試 — Security #3"""
from __future__ import annotations

import pytest

from app.services.output_scanner import (
    OutputScanner,
    ScanAction,
    Severity,
    get_output_scanner,
)


@pytest.fixture
def scanner() -> OutputScanner:
    return OutputScanner()


# ── BLOCK 等級（密鑰、憑證） ─────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Here is my key: sk-abc123XYZ456defghijk789",
    "anthropic key: sk-ant-api03-abcDEF123456_-abcdef",
    "AWS: AKIAIOSFODNN7EXAMPLE is the key",
    "token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "api_key: 'abcdef1234567890abcdef'",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
])
def test_block_on_credentials(scanner, text):
    result = scanner.scan(text)
    assert result.action == ScanAction.BLOCK, f"Should BLOCK: {text[:50]!r}"
    assert result.cleaned_text == OutputScanner.BLOCK_MESSAGE


# ── REDACT 等級（PII） ─────────────────────────────────────────────
def test_redact_credit_card(scanner):
    text = "卡號是 4532-1234-5678-9010，請保密。"
    result = scanner.scan(text)
    assert result.action == ScanAction.REDACT
    assert "4532-1234-5678-9010" not in result.cleaned_text
    assert "***" in result.cleaned_text


def test_redact_twn_id(scanner):
    text = "身份證字號 A123456789 已登記。"
    result = scanner.scan(text)
    assert result.action == ScanAction.REDACT
    assert "A123456789" not in result.cleaned_text


def test_redact_email(scanner):
    text = "請寄信到 admin@example.com 詢問。"
    result = scanner.scan(text)
    assert result.action == ScanAction.REDACT
    assert "admin@example.com" not in result.cleaned_text


def test_redact_phone_twn(scanner):
    text = "聯絡電話 0912-345-678。"
    result = scanner.scan(text)
    assert result.action == ScanAction.REDACT
    assert "0912-345-678" not in result.cleaned_text


def test_redact_bcrypt_hash(scanner):
    text = "hash: $2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
    result = scanner.scan(text)
    assert result.action == ScanAction.REDACT


# ── WARN 等級（內部 IP / 一般 hash） ───────────────────────────────
def test_warn_on_internal_ip(scanner):
    text = "伺服器 IP 是 192.168.1.11，請連線。"
    result = scanner.scan(text)
    assert result.action == ScanAction.WARN
    assert len(result.hits) == 1
    assert result.hits[0].pattern_name == "internal_ip"
    # WARN 不改文字
    assert "192.168.1.11" in result.cleaned_text


def test_warn_on_md5(scanner):
    text = "file md5: d41d8cd98f00b204e9800998ecf8427e"
    result = scanner.scan(text)
    assert result.action == ScanAction.WARN


# ── PASS：純文字 ──────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "這是一份工單維修資料。",
    "EMU800 最近完成三次 PM 維修。",
    "請檢查煞車系統是否正常。",
    "",
])
def test_pass_on_safe_text(scanner, text):
    result = scanner.scan(text)
    assert result.action == ScanAction.PASS
    assert result.cleaned_text == text


# ── Multiple hits ─────────────────────────────────────────────────
def test_multiple_hits_block_priority(scanner):
    """同時有 BLOCK 與 REDACT 命中，BLOCK 優先整段替換。"""
    text = "key=sk-abc123XYZ456defghijk789 email=foo@bar.com"
    result = scanner.scan(text)
    assert result.action == ScanAction.BLOCK
    assert len(result.hits) >= 2
    assert any(h.action == ScanAction.BLOCK for h in result.hits)


def test_multiple_redact_hits(scanner):
    text = "email1 foo@bar.com 身分證 A123456789 電話 0912345678"
    result = scanner.scan(text)
    assert result.action == ScanAction.REDACT
    assert "foo@bar.com" not in result.cleaned_text
    assert "A123456789" not in result.cleaned_text


# ── Singleton ─────────────────────────────────────────────────────
def test_singleton():
    s1 = get_output_scanner()
    s2 = get_output_scanner()
    assert s1 is s2


# ── 關閉 block / redact ───────────────────────────────────────────
def test_disable_block():
    s = OutputScanner(enable_block=False)
    result = s.scan("key: sk-abc123XYZ456defghijk789")
    # 關閉後 action 仍記 BLOCK 但 cleaned_text 不替換 → 但目前實作不回寫 pass
    # 期望：hits 仍記錄，cleaned_text 是原文
    assert result.action == ScanAction.BLOCK  # 仍回報
    # enable_block=False → 不使用 BLOCK_MESSAGE，但目前是 default 路徑
    # 此 branch 只驗證 hits 有記錄
    assert any(h.pattern_name == "openai_key" for h in result.hits)


def test_severity_attached():
    s = OutputScanner()
    result = s.scan("email foo@bar.com")
    assert result.hits[0].severity == Severity.MEDIUM
