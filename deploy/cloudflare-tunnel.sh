#!/bin/bash
# Cloudflare Tunnel 配置脚本

set -e

echo "===================================="
echo "  Cloudflare Tunnel 配置"
echo "===================================="

# 检查 cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared 未安装"
    echo "安装命令: curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared"
    exit 1
fi

echo "✅ cloudflared 已安装: $(cloudflared --version)"

# 检查是否已登录
if [ ! -f ~/.cloudflared/cert.pem ]; then
    echo ""
    echo "⚠️ 需要先登录 Cloudflare"
    echo ""
    echo "请运行以下命令："
    echo "  cloudflared login"
    echo ""
    echo "然后在浏览器中打开提供的 URL 并授权"
    echo "授权完成后重新运行此脚本"
    exit 0
fi

echo "✅ 已登录 Cloudflare"

# 创建隧道（如果不存在）
TUNNEL_NAME="personal-profile"
echo ""
echo "🔍 检查隧道 '$TUNNEL_NAME'..."

if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
    echo "  ✅ 隧道已存在"
else
    echo "  📝 创建隧道..."
    cloudflared tunnel create "$TUNNEL_NAME"
    echo "  ✅ 隧道创建成功"
fi

# 获取隧道 ID
TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
echo "  隧道 ID: $TUNNEL_ID"

# 配置隧道
echo ""
echo "📝 配置隧道..."

mkdir -p ~/.cloudflared

cat > ~/.cloudflared/config.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: /home/junqeeager/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: 506ikun.space
    service: http://localhost:8501
  - hostname: www.506ikun.space
    service: http://localhost:8501
  - service: http_status:404
EOF

echo "  ✅ 配置文件已生成: ~/.cloudflared/config.yml"

# 路由域名到隧道
echo ""
echo "🌐 配置域名路由..."

cloudflared tunnel route dns "$TUNNEL_NAME" "506ikun.space" 2>/dev/null || echo "  ⚠️ 域名路由可能已存在"
cloudflared tunnel route dns "$TUNNEL_NAME" "www.506ikun.space" 2>/dev/null || echo "  ⚠️ www 路由可能已存在"

echo ""
echo "===================================="
echo "  ✅ 配置完成！"
echo "===================================="
echo ""
echo "启动隧道："
echo "  cloudflared tunnel run $TUNNEL_NAME"
echo ""
echo "访问地址："
echo "  https://506ikun.space"
echo ""
