# Review Report: W1-T1 Neo4j Container Deploy

Commit: `5618752` — `feat(phase3): 加入 Neo4j 容器服務 (W1-T1)`
Files: `docker-compose.yml` (+34) / `.env.example` (+8)
Review date: 2026-04-18
Reviewer: Review Agent

---

## 摘要

- **CRITICAL**: 2 個（.env 已被 git 追蹤含真實 API key、Neo4j port 0.0.0.0 全開 + UFW 關閉）
- **HIGH**: 4 個（compose 預設密碼 fallback、APOC import/export 全開、procedures 全部 unrestricted、健康檢查只測 HTTP）
- **NICE-TO-HAVE**: 3 個（cypher-shell healthcheck、Prometheus metrics、backup 策略）

**本 commit 自身變更**：無敏感資訊外洩，`.env.example` 乾淨。結構大致合理，但安全預設偏寬鬆，且遺留了一個既存的 `.env` 已追蹤問題（不是這個 commit 造成，但在部署時等於繼續暴露）。

---

## CRITICAL

### C1. `.env` 已被 commit 進 git（非本 commit 造成，但必須處理）
**事實：**
- `git ls-files` 顯示 `.env` 被追蹤。
- `git show HEAD:.env` 內容：
  ```
  # API Security
  AIKM_API_KEY=_lAWtCn29ETEomZjfz1Xa9SvVsrjOaCMvqt0htX3Shw
  ```
- 首次進入歷史是 `f5cc226 feat(rwd): ...`（2026-02-02）。
- 本機 `.env` 內容和 git HEAD 版本相同（僅一行 AIKM_API_KEY）——換句話說**本機的 NEO4J_PASSWORD 目前沒被追蹤**，但這不是因為 `.gitignore` 保護，而是單純沒被 `git add` 進去。只要下次有人不小心 `git add .env`，就會把 Neo4j 密碼 commit 進去。

**風險：** AIKM_API_KEY 已在公開（或任何能 clone repo 的人）歷史中。遠端如果是 GitHub public 就已經外洩。

**修正：**
1. **立刻 revoke/rotate 現有 `AIKM_API_KEY`**（backend 與 frontend 都要換）。
2. 從 git 歷史移除 `.env`：
   ```bash
   git rm --cached .env
   echo ".env" >> .gitignore   # 目前 .gitignore 只 ignore .env*.local，不含 .env
   git commit -m "chore: stop tracking .env and ignore it"
   ```
3. 歷史清除可用 `git filter-repo --path .env --invert-paths` 或 BFG（屬後續工作，但 key rotate 是當務之急）。
4. `.gitignore` 目前第 25 行是 `.env*.local`，需要加一行單純 `.env` 與 `.env.production`。

### C2. Neo4j port 7474/7687 綁 0.0.0.0 + 防火牆未啟用
**事實：**
```
LISTEN  0.0.0.0:7474  docker-proxy
LISTEN  0.0.0.0:7687  docker-proxy
狀態：不活動  (UFW)
iptables: ACCEPT 0.0.0.0/0 → 172.18.0.7 tcp dpt:7687
```
- 部署機有外部 IP `114.32.141.218`。雖然從 server 本身 curl 該外部 IP 不通（上游 NAT/firewall 應該擋了），但這個前提**不可依賴**——它只要有一天把 port forward 打開、或內網有一台中毒機器，Neo4j 就全裸了。
- LAN（192.168.1.0/24）上的任何機器（含 Drone CI、Maximo Liberty 共存機）現在都能直接連 Bolt / Browser。

**修正（擇一或兼用）：**
1. **最好**：改 port 綁定 loopback 或 Docker 內部，不對 host 開：
   ```yaml
   ports:
     - "127.0.0.1:7474:7474"
     - "127.0.0.1:7687:7687"
   ```
   後端從 `bolt://neo4j:7687`（Docker 網路）連，不需對 host 暴露。Browser UI 可透過 SSH tunnel。
2. **次選**：啟用 UFW，只允許 192.168.1.0/24：
   ```bash
   ufw allow from 192.168.1.0/24 to any port 7474,7687
   ufw enable
   ```
3. 確認路由器/上游防火牆確實沒 port-forward 7474/7687（目前看起來沒，但應寫進 runbook）。

---

## HIGH

### H1. `docker-compose.yml` 有弱密碼預設 fallback
```yaml
NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-aikm_neo4j_change_me}
```
若 `.env` 漏帶 `NEO4J_PASSWORD`，container 會自動吃 `aikm_neo4j_change_me` 並靜默起來——這是 hard-coded weak default。

目前部署機實測：強密碼版生效（用 `aikm_neo4j_change_me` cypher-shell 登入失敗），所以現況安全。但這只是運氣好。

**修正：** 把 fallback 拿掉，讓缺失時**啟動失敗**才是正確行為：
```yaml
NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}
```

### H2. APOC import/export 全開
```yaml
NEO4J_apoc_export_file_enabled: "true"
NEO4J_apoc_import_file_enabled: "true"
NEO4J_apoc_import_file_use__neo4j__config: "true"
```
- `apoc.import.file.use_neo4j_config=true` 會限制只讀 `/var/lib/neo4j/import`，所以還算可控。
- 但 `apoc.export.file.enabled=true` 意味著任何有 Cypher 執行權限的人可以 `CALL apoc.export.csv.query(...)` 寫檔到 container `/var/lib/neo4j/import`（或其他可寫路徑），會導致磁碟耗盡、暫存敏感資料到 volume 等。
- Phase 3 當下若只需做圖查詢，import/export **先關掉**比較安全。

**修正建議：**
- 若 Phase 3 目前不需 CSV I/O，改成 `"false"`；之後需要再開。
- 若需要，至少把 export 關掉、import 保留；並在 app 層驗證 Cypher（已有 W2-T3 cypher validator）。

### H3. `dbms.security.procedures.unrestricted: apoc.*,gds.*` 過寬
- `unrestricted` 等於授予 APOC/GDS 所有 procedure **不受安全沙盒限制**。只要 Bolt 帳號密碼洩漏，攻擊者可透過 `apoc.cypher.doIt` / `apoc.trigger.install` 等做任意操作，包括讀 container 檔案、內網探測。
- Community 版沒 role-based auth，只有 neo4j superuser，因此等於「密碼 = root」。

**修正：**
- 把 `unrestricted` 收斂到實際用到的 package，例如：`apoc.meta.*,apoc.coll.*,gds.graph.*`。
- 允許清單 `allowlist` 已設同樣寬度，亦可收斂。
- 原則：**先 allowlist 很小範圍，缺再加**。

### H4. Healthcheck 只測 HTTP 200
```yaml
test: ["CMD-SHELL", "wget -q --spider http://localhost:7474 || exit 1"]
```
7474 HTTP 起來 ≠ Bolt DB 可用。更穩的是：
```yaml
test: ["CMD-SHELL", "cypher-shell -u neo4j -p $${NEO4J_PASSWORD} 'RETURN 1;' || exit 1"]
```
需要把 `NEO4J_PASSWORD` 也 pass 給 container（目前只用在 `NEO4J_AUTH`，compose 不會自動再加 env key）。

---

## NICE-TO-HAVE

### N1. Volumes — 已持久化，bind mount 位置 OK
部署機 `docker inspect` 顯示 volumes 掛在 `/mnt/disk2/docker/volumes/...`（named volume，非敏感 host 路徑 bind），所以沒有 C 級風險。四個 volumes 都有建立（data/logs/plugins/import）。

### N2. 記憶體設定 OK
- 部署機：62 GiB total、目前 used 7.4 GiB、available 55 GiB。
- Neo4j 配置 heap 2G + pagecache 1G = 3G，完全沒壓力。
- 實測 `docker stats aikm-neo4j` = 1.148 GiB，正常。
- 同機有 Maximo Liberty 與 Drone CI，也無擠壓。

### N3. Backup / Metrics 尚未納入
- 沒看到 `neo4j-admin database dump` 的 cron / scheduled task。Phase 3 資料開始寫入後建議納入 daily backup + 送到非同機的儲存。
- 沒啟用 Prometheus metrics（Neo4j 5.x 支援 `metrics.prometheus.enabled=true` + endpoint `:2004`）。

---

## 修正建議優先序

1. **立即（部署前/部署後 1 小時內）**
   - **rotate `AIKM_API_KEY`**（C1） — 已洩漏。
   - `git rm --cached .env` + 更新 `.gitignore`（C1） — 防止 NEO4J_PASSWORD 未來被誤 commit。
2. **今日**
   - 把 Neo4j ports 改 `127.0.0.1:7474/7687`，後端走 Docker 內網連（C2）。
   - 把 compose fallback 密碼改成 `:?` 強制（H1）。
3. **本週**
   - 收斂 `procedures.unrestricted` / `allowlist` 到實際用到的 package（H3）。
   - 若 Phase 3 目前不需要 CSV import/export，先關掉（H2）。
   - Healthcheck 改 cypher-shell 版本（H4）。
4. **本月（Phase 3 寫入資料開始後）**
   - 排定 `neo4j-admin database dump` daily backup（N3）。
   - 啟 UFW 白名單（C2 次選）。
   - 啟用 Prometheus metrics（N3）。

---

## GO/NO-GO

- [ ] GO — 本 commit **單就 diff 本身**沒有致命錯誤，容器已在部署機健康運行且用強密碼保護。
- [x] **NO-GO（有條件）** — 本次變更雖然**容器本身能跑**，但：
  - C1（.env 已 tracked 含真 API key）是整個 repo 等級的機密洩漏，雖然不是本 commit 引入，但**本 commit 推上部署 = 整個 repo 等級繼續放著不管**，必須同步修。
  - C2（port 0.0.0.0 + 無防火牆）風險高、修正極低成本（改 ports binding 一行）。

**建議：** 開一個 hotfix commit 同時處理 C1 + C2，再判定 GO。若老闆願意接受 C1 非本 commit 造成、另外獨立 ticket 處理，則本 commit 可條件 GO（但 C2 仍須先修）。

---

## 附錄：驗證指令記錄

```bash
# 本 commit diff
git show 5618752

# .env 歷史
git log --all --oneline -- .env
# → f5cc226 feat(rwd): implement responsive web design support (P1+P2)

git show HEAD:.env
# → AIKM_API_KEY=_lAWtCn29ETEomZjfz1Xa9SvVsrjOaCMvqt0htX3Shw

# 部署機記憶體 / 容器
ssh root@192.168.1.11 "free -h"
# → 62Gi total / 55Gi avail

ssh root@192.168.1.11 "docker stats aikm-neo4j --no-stream"
# → 1.148GiB / 62.65GiB

# 部署機 port binding
ssh root@192.168.1.11 "ss -tlnp | grep -E '7474|7687'"
# → LISTEN 0.0.0.0:7474 / 0.0.0.0:7687

ssh root@192.168.1.11 "ufw status"
# → 狀態：不活動

# 預設密碼無效驗證
ssh root@192.168.1.11 "docker exec aikm-neo4j cypher-shell -u neo4j -p 'aikm_neo4j_change_me' 'RETURN 1;'"
# → The client is unauthorized due to authentication failure.

# volume mount
ssh root@192.168.1.11 "docker inspect aikm-neo4j | grep Source"
# → /mnt/disk2/docker/volumes/ai-km-platform_aikm-neo4j-{data,logs,plugins,import}
```
