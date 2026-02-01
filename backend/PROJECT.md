# AI KM Platform - Backend (Multimodal RAG)

## 架構設計

### 技術棧
- **Framework:** FastAPI (Python)
- **Vector DB:** Qdrant (輕量、支援多模態)
- **Embedding:** 
  - 文字: sentence-transformers
  - 圖片: CLIP (openai/clip-vit-base-patch32)
- **LLM:** OpenAI GPT-4o (支援圖片理解)
- **文件處理:** PyMuPDF, pdf2image, Pillow

### API 端點

#### 知識庫管理
- POST /api/kb/upload - 上傳文件（PDF/圖片）
- GET /api/kb/documents - 列出所有文件
- DELETE /api/kb/documents/{id} - 刪除文件
- GET /api/kb/stats - 知識庫統計

#### RAG 查詢
- POST /api/chat - 對話查詢（支援圖片）
- POST /api/search - 純搜尋（不生成回答）

#### 權限管理
- GET /api/permissions/kb - 知識庫權限設定
- PUT /api/permissions/kb - 更新權限

### 文件處理流程
```
上傳文件 → 解析 → 分割(文字+圖片) → 嵌入 → 存入 Qdrant
         ↓
      [PDF] → PyMuPDF 提取文字 + 圖片
      [圖片] → CLIP 嵌入 + 描述生成
```

### 權限矩陣
| 權限 | Admin | User | Guest |
|------|-------|------|-------|
| 上傳文件 | ✓ | ✓ | ✗ |
| 刪除文件 | ✓ | ✗ | ✗ |
| 查詢知識庫 | ✓ | ✓ | ✓ |
| 管理權限 | ✓ | ✗ | ✗ |
