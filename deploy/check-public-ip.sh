#!/bin/bash
# 检查公网 IP 和端口可达性

echo "===================================="
echo "  网络诊断工具"
echo "===================================="

# 获取公网 IP
echo ""
echo "📡 获取公网 IP..."
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null)
echo "  公网 IP: $PUBLIC_IP"

# 获取 WSL IP
WSL_IP=$(hostname -I | awk '{print $1}')
echo "  WSL2 IP: $WSL_IP"

# 检查 Streamlit 状态
echo ""
echo "🔍 检查 Streamlit 状态..."
if pgrep -f "streamlit run" > /dev/null; then
    echo "  ✅ Streamlit 正在运行"
else
    echo "  ❌ Streamlit 未运行"
    echo "  启动命令: streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true"
fi

# 检查端口监听
echo ""
echo "🔌 检查端口 8501..."
if ss -tlnp | grep -q ":8501"; then
    echo "  ✅ 端口 8501 已监听"
else
    echo "  ❌ 端口 8501 未监听"
fi

# 测试本地访问
echo ""
echo "🌐 测试本地访问..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 | grep -q "200\|302"; then
    echo "  ✅ 本地访问正常"
else
    echo "  ⚠️ 本地访问异常"
fi

echo ""
echo "===================================="
echo "  配置步骤"
echo "===================================="
echo ""
echo "1. 在 Windows PowerShell (管理员) 运行:"
echo "   powershell -ExecutionPolicy Bypass -File deploy/windows-setup.ps1"
echo ""
echo "2. 将域名 506ikun.space 解析到: $PUBLIC_IP"
echo ""
echo "3. 访问: http://506ikun.space:8501"
echo ""
