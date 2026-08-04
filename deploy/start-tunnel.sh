#!/bin/bash
# 启动 Cloudflare Tunnel 和 Streamlit

echo "🚀 启动服务..."

# 检查 Streamlit 是否运行
if ! pgrep -f "streamlit run" > /dev/null; then
    echo "  启动 Streamlit..."
    cd /home/junqeeager/aicode
    nohup streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > /tmp/streamlit.log 2>&1 &
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
echo "Streamlit: http://localhost:8501"
echo "外网访问: https://t.506ikun.space"
echo ""
