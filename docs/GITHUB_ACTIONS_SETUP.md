# GitHub Actions CI/CD 設定指南

本專案使用 **GitHub Actions + Self-hosted Runner**（跑在部署機 192.168.1.11）建置 3 條 pipeline：

| Workflow | 觸發 | 用途 |
|----------|------|------|
| `docs-deploy.yml` | push 改動 `docs/**/*.html` | 複製 HTML 到 `/mnt/disk3/shared/aikm-*` |
| `ci-test.yml` | push 到非 main branch / PR | backend pytest + e2e chromium |
| `main-deploy.yml` | push 到 main / 手動 | 拉 main、build、rolling update、health check、失敗 rollback |

---

## 為何用 Self-hosted Runner？

- 直接在部署機上跑，可以 `docker exec aikm-backend ...` / `docker compose up -d`，不用 SSH
- 內網拉 image、訪問 DB 都不繞路，速度快
- 不計入 GitHub Free 配額（無限免費）
- GitHub 會自動處理：private repo 不接外部 PR 的 self-hosted 任務（安全）

---

## 一次性設定（使用者手動）

### 步驟 1：在 GitHub 註冊 Runner（拿 token）

1. 開啟 `https://github.com/nick0918964388/ai-km-platform`
2. **Settings** → **Actions** → **Runners** → **New self-hosted runner**
3. Image 選 **Linux**，Architecture 選 **x64**
4. 頁面會顯示安裝指令，**只要複製 `./config.sh --url ... --token XXXXXXX` 中那段 token**（格式類似 `A3DS...`，**有效時間 1 小時**）

### 步驟 2：在部署機 .env 放入 token

```bash
ssh root@192.168.1.11
cd /root/ai-km-platform
echo "GITHUB_RUNNER_TOKEN=<剛複製的 token>" >> .env
```

### 步驟 3：啟動 Runner container

```bash
# 先 pull 最新程式（此 PR merged 後）
git pull origin main

# 啟動 runner
docker compose up -d github-runner

# 確認啟動
docker logs -f aikm-github-runner
```

看到以下訊息代表成功：
```
√ Connected to GitHub
√ Runner successfully added
√ Runner connection is good
...
Listening for Jobs
```

回到 GitHub Repo → Settings → Actions → Runners 頁面，應看到 `aikm-runner-01` 狀態為 **Idle**。

### 步驟 4：驗證首次觸發

Push 任何 branch（例如當前 `feat/dashboard-domain-e2e`）即觸發 `ci-test.yml`。  
到 GitHub Repo → **Actions** 標籤頁查看 pipeline 跑綠燈。

---

## 驗收清單

- [ ] Runner 顯示 **Idle** 於 GitHub Settings → Actions → Runners
- [ ] 改一個 `docs/*.html` push → `docs-deploy` 綠燈 + `/mnt/disk3/shared/aikm-*.html` 已更新
- [ ] 改一個 backend 程式 push → `ci-test` 綠燈（pytest + e2e chromium）
- [ ] Merge PR 到 `main` → `main-deploy` 跑 build + health check，成功；若失敗應自動 rollback 到上一 commit

---

## Troubleshooting

### Runner 顯示 Offline

```bash
docker logs aikm-github-runner --tail 80
```

**最常見**：token 過期（1 小時限制），runner 第一次註冊後會轉為長期憑證，但**重新建立 container** 時需新 token。做法：

1. 到 GitHub Repo → Settings → Actions → Runners，若 `aikm-runner-01` 仍存在，先按右側 **Remove** → **Force remove this runner**
2. 重新點 **New self-hosted runner** 拿新 token
3. 更新 `.env` 的 `GITHUB_RUNNER_TOKEN`
4. `docker compose up -d --force-recreate github-runner`

### Playwright 首次執行過慢

E2E 首次會下載 chromium（~170MB），若想預熱：

```bash
docker exec aikm-github-runner bash -c 'cd /tmp/runner/work && npx playwright install chromium'
```

`ci-test.yml` 內已用 `npx playwright install chromium --with-deps`（冪等，第二次幾乎不耗時）。

### Deploy 失敗自動 rollback

`main-deploy.yml` 會在 build/healthcheck 任一步失敗時：
1. `git reset --hard <previous-commit>`
2. `docker compose up -d --build backend frontend` 重建回舊版本
3. 在 job log 顯示 `::warning::Rolling back to <sha>`

**若 rollback 也失敗**（例如舊 commit 也壞），手動上機：

```bash
ssh root@192.168.1.11
cd /root/ai-km-platform
git log --oneline -10                  # 找近期確定可用的 commit
git reset --hard <good-commit-sha>
docker compose up -d --build backend frontend
curl -sS http://localhost:8000/health  # 驗證
```

### Runner 權限問題

Runner container 以 root 身份掛載 `/var/run/docker.sock` 和 `/root/ai-km-platform`，已有足夠權限。  
若遇到 `permission denied`，檢查 `.env` 的 UID/GID 設定或直接 `chmod` 專案目錄。

### Secrets 管理

所有敏感資訊（API keys、DB 密碼等）走部署機 `/root/ai-km-platform/.env`，**不要**放 GitHub Secrets（因為 workflows 不在 GitHub cloud 跑，是 self-hosted，取 secret 會增加複雜度）。

例外：**未來若要發 Discord/Slack 通知**，可加入 `DISCORD_WEBHOOK_URL` 至 GitHub Repo Secrets，在 workflow 用 `${{ secrets.DISCORD_WEBHOOK_URL }}` 引用。

---

## 架構概念圖

```
GitHub Cloud                          部署機 192.168.1.11 (Ubuntu)
┌─────────────────────┐               ┌──────────────────────────────────┐
│ push / PR event     │──webhook─────▶│ aikm-github-runner (container)   │
│ Actions scheduler   │               │   │                              │
└─────────────────────┘               │   ├──▶ docker exec aikm-backend  │
                                      │   │                              │
                                      │   ├──▶ docker compose up         │
                                      │   │                              │
                                      │   ├──▶ cp to /mnt/disk3/shared   │
                                      │   │                              │
                                      │   └──▶ curl localhost:8000/health│
                                      └──────────────────────────────────┘
```
