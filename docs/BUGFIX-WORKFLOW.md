# Bug Fix Workflow

## 流程：Developer → Reviewer → Tester

### 1. 建立 Bug Branch
```bash
# 從 main 分支建立 bugfix branch
git checkout main
git checkout -b bugfix/<issue-id>-<short-description>
# 例如: bugfix/012-dashboard-name-fix
```

### 2. Developer 修復
- 在 bugfix branch 上修復問題
- 每個 bug 一個 commit，清楚描述修改
- commit message 格式: `fix(<scope>): <description>`

### 3. Reviewer 審核
- 建立 Pull Request: `bugfix/xxx` → `main`
- Code Review checklist:
  - [ ] 修復是否正確解決問題
  - [ ] 沒有引入新問題
  - [ ] 符合專案程式碼風格
  - [ ] 環境變數/設定有正確更新

### 4. Tester 測試
- 在測試環境驗證修復
- 使用 Playwright 或瀏覽器手動測試
- 確認修復後才 approve PR

### 5. 合併
- Squash merge 到 main
- 刪除 bugfix branch
- 部署到 production (docker compose up -d --build)

## Bug Branch 命名規範
- `bugfix/<number>-<description>`
- 例如: `bugfix/012-dashboard-display-name`
- 例如: `bugfix/013-rag-ollama-integration`
