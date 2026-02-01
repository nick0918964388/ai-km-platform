#!/bin/bash
# AI-KM Platform Quick Start Script

set -e

echo "🚀 AI-KM Platform 啟動腳本"
echo "=========================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未運行，請先啟動 Docker Desktop"
    exit 1
fi

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，從 .env.example 複製..."
    cp .env.example .env
fi

# Build and start services
echo ""
echo "📦 建置並啟動服務..."
docker compose up -d --build

# Wait for services to be healthy
echo ""
echo "⏳ 等待服務啟動..."
sleep 10

# Check service status
echo ""
echo "📊 服務狀態："
docker compose ps

echo ""
echo "✅ 啟動完成！"
echo ""
echo "🌐 前端: http://localhost:3000"
echo "🔧 後端 API: http://localhost:8000"
echo "📚 API 文檔: http://localhost:8000/docs"
echo "🔍 Qdrant UI: http://localhost:6333/dashboard"
echo ""
echo "📝 管理員帳號: admin@example.com / admin"
echo ""
echo "停止服務: docker compose down"
echo "查看日誌: docker compose logs -f"
