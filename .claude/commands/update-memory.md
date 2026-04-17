# /update-memory — 每日開發日誌彙整

執行此指令，自動產生今日開發日誌並更新近期摘要。

## 執行流程（依序完成，不需使用者確認）

### Step 1 — 收集今日資訊
執行以下指令收集資料：
```bash
git log --since="midnight" --format="%h %s" 
git diff main...HEAD --stat
```

### Step 2 — 寫入每日日誌
將今日開發重點寫入 `memory/daily/YYYY-MM-DD.md`（日期用今天實際日期）：

```markdown
# YYYY-MM-DD 開發日誌

## 分支
`branch-name`

## 完成事項
- 條列今日完成的功能、修復、調整

## Commits
（貼上 git log 輸出）

## 遇到的問題與解法
- 問題：...
  解法：...

## 重要決策
- ...

## 明日待續
- ...
```

### Step 3 — 更新 `memory/MEMORY.md`
在「近期功能進展」區塊**最頂端**插入今日摘要（格式如下），保留既有內容：

```markdown
### YYYY-MM-DD | branch-name
- 重點一
- 重點二
```

### Step 4 — 回報結果
完成後告知：
- ✅ 已寫入 `memory/daily/YYYY-MM-DD.md`
- ✅ 已更新 `memory/MEMORY.md`
- 並列出今日摘要三到五條重點
