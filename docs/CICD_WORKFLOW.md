# CI/CD 工作流程

> 本文件為 ai-km-platform 的 CI/CD 完整參考。任何新功能/修復都走此流程。
> 建立於 2026-04-19，commit `e8cc2dd` 起正式啟用。

---

## 平台與架構

- **CI 平台**：GitHub Actions
- **Runner**：self-hosted，跑在部署機 192.168.1.11 上（container `aikm-github-runner`）
- **Workflows**：`.github/workflows/*.yml`（3 條）
- **Repo**：private，`nick0918964388/ai-km-platform`

---

## 三條 Pipeline

### 1. `docs-deploy.yml`
- **觸發**：push 到任何 branch 且 diff 含 `docs/**/*.html`
- **動作**：把 `docs/*.html` cp 到 `/mnt/disk3/shared/aikm-<檔名>`
- **結果**：立即可在 `http://192.168.1.11:9999/aikm-<檔名>` 看到最新版

### 2. `ci-test.yml`
- **觸發**：push 到非 main branch + 任何 PR
- **步驟**：
  1. `docker exec aikm-backend pytest /app/tests/` —— backend 單元測試
  2. `npx playwright test --project=chromium` —— E2E 迴歸測試
- **結果**：失敗時 upload playwright-report 為 artifact；不 gate 部署（只是 visibility）
- **Concurrency**：同 branch 新 push 會 cancel 舊的

### 3. `main-deploy.yml`
- **觸發**：push 到 `main` 或手動 `workflow_dispatch`
- **步驟**：
  1. Snapshot 目前 HEAD（作為 rollback 基準）
  2. `git pull origin main`
  3. `docker compose build backend frontend`
  4. Rolling update backend → 5 retry 健康檢查 `http://localhost:8000/health`
  5. Rolling update frontend → 健康檢查 `http://localhost:3000/`
  6. **任一步失敗 → 自動 `git reset --hard <prev>` + rebuild**
  7. 寫 Deploy summary 到 GitHub Actions step summary

---

## 新增功能的完整 7 步流程

### Step 1：從 main 開分支
```bash
git checkout main
git pull
git checkout -b feat/<short-name>
```

### Step 2：本機開發 + commit
```bash
# 寫 code
git add <files>
git commit -m "feat(<scope>): 中文說明"
```

### Step 3：Push（觸發 ci-test + docs-deploy）
```bash
git push origin feat/<short-name>
```
去 https://github.com/nick0918964388/ai-km-platform/actions 看 CI 結果：
- 綠燈 → 繼續
- 紅燈 → 修 bug 再 push（Concurrency 會 cancel 舊 run）

### Step 4：開 PR
```bash
gh pr create --base main --head feat/<short-name> \
  --title "..." --body "..."
```
或去 GitHub UI 開。PR 開啟會**再跑一次 ci-test** 確保 merge 前是安全的。

### Step 5：Review（可選）
自我 review diff 或找人 review。繼續 push 到同 branch 會自動觸發 CI 重跑。

### Step 6：Merge to main
PR 頁面點 **Merge pull request**（等 ci-test 綠燈）

### Step 7：自動部署 🚀
merge 後 `main-deploy` 立刻跑 → 完整 rolling update + 健康檢查 + 失敗 rollback。
**完全不需要 SSH 部署機**。

---

## 重要連結

| 用途 | URL |
|------|-----|
| Actions | https://github.com/nick0918964388/ai-km-platform/actions |
| Runner 狀態 | https://github.com/nick0918964388/ai-km-platform/settings/actions/runners |
| Branch 保護設定 | https://github.com/nick0918964388/ai-km-platform/settings/branches |
| Secrets | https://github.com/nick0918964388/ai-km-platform/settings/secrets/actions |

---

## 強制建議：Main Branch Protection

**立刻做**：GitHub Settings → Branches → Add rule for `main`：
- ✅ Require a pull request before merging
- ✅ Require status checks to pass before merging → 勾 `ci-test / backend-tests` 和 `ci-test / e2e-chromium`
- ✅ Require branches to be up to date before merging
- ✅ Do not allow bypassing the above settings

沒有這個保護，有人直接 push main 就會繞過所有測試觸發 deploy。

---

## Troubleshooting

### Runner 顯示 Offline
```bash
ssh root@192.168.1.11
docker logs aikm-github-runner --tail 50
```
若 token 過期（container recreate 後），需重拿 token：
1. GitHub → Settings → Actions → Runners → New self-hosted runner → 複製 token
2. `echo "GITHUB_RUNNER_TOKEN=<新 token>" >> /root/ai-km-platform/.env`（覆蓋舊的）
3. `docker compose restart github-runner`

### Push 被擋：PAT workflow scope
錯誤訊息 `refusing to allow a Personal Access Token to create or update workflow`

原因：git 用的 PAT 沒 `workflow` scope。**踩過的大地雷**：remote URL 可能嵌入了舊 PAT 繞過 `gh auth`：
```bash
git remote -v
# 若 URL 含 https://ghp_xxx@github.com/... 就是地雷

# 修：
git remote set-url origin https://github.com/nick0918964388/ai-km-platform.git

# 確認 gh 登入有 workflow scope
gh auth status
# 應看到 Token scopes 含 'workflow'

git push origin <branch>
```

或直接 `gh auth login` 走 OAuth（自動有完整 scope）。

### Deploy 失敗自動 rollback 的日誌
GitHub Actions `main-deploy` 頁面會看到 `::warning:: Rolling back to <prev-commit>`。
若 rollback 也失敗（例如舊 commit 本身壞），手動上部署機：
```bash
ssh root@192.168.1.11
cd /root/ai-km-platform
git log --oneline -10
git reset --hard <known-good-commit>
docker compose up -d --build backend frontend
```

### E2E chromium 首次跑很慢
Runner 首次跑 E2E 需下載 chromium（~170MB）。workflow 用 `--with-deps` 冪等安裝。
要預熱：
```bash
docker exec aikm-github-runner npx playwright install chromium
```

### CI Test 跑但失敗說套件缺失
Backend pytest 需 `pytest pytest-asyncio fakeredis`，workflow 會 `pip install --quiet` 補裝。
若仍失敗，可能 backend image 改了 Python 版本，可手動進 container 修：
```bash
docker exec aikm-backend pip install pytest pytest-asyncio fakeredis
```

---

## 相關文件

- `docs/GITHUB_ACTIONS_SETUP.md` — Runner 首次註冊指南（已完成）
- `.github/workflows/` — 三個 workflow YAML 檔
- `docker-compose.yml` — `github-runner` service 定義
- `CLAUDE.md` — Claude 工作手冊（含部署原則）
