#!/bin/bash
# 启动 Cloudflare Tunnel 和 React SPA + FastAPI

echo "🚀 启动服务..."

# 检查 uvicorn 是否运行
if ! pgrep -f "uvicorn api.main" > /dev/null; then
    echo "  启动 React SPA + API..."
    cd /home/junqeeager/aicode
    nohup /usr/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8501 > /tmp/personal-profile-web.log 2>&1 &
    sleep 3
fi

# 检查隧道是否运行
if ! pgrep -f "cloudflared tunnel" > /dev/null; then
    echo "  启动 Cloudflare Tunnel..."
    nohup cloudflared tunnel run personal-profile > /tmp/cloudflared.log 2>&1 &
    sleep 3
fi

echo ""
echo "✅ 服务已启动"
echo ""
echo "Web/API: http://localhost:8501"
echo "外网访问: https://t.506ikun.space"
echo ""
