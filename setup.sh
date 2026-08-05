#!/bin/bash
# 个人认知画像系统 - 环境安装脚本

set -e

echo "🧠 个人认知画像系统 - 环境安装"
echo "=================================================="

# 检查 Python 版本
echo "🔍 检查 Python 版本..."
python3 --version

# 安装 pip（如果没有）
echo "📦 检查 pip..."
if ! command -v pip3 &> /dev/null && ! python3 -m pip --version &> /dev/null; then
    echo "  安装 pip..."
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    python3 /tmp/get-pip.py --user --break-system-packages 2>/dev/null || \
    python3 /tmp/get-pip.py --user
    export PATH="$HOME/.local/bin:$PATH"
    echo "  ✅ pip 已安装"
else
    echo "  ✅ pip 已存在"
fi

# 安装依赖
echo "📦 安装 Python 依赖..."
pip3 install --user --break-system-packages -r requirements.txt 2>/dev/null || \
pip3 install --user -r requirements.txt

# 安装 playwright（用于获取 Cookie）
echo "📦 安装 playwright..."
pip3 install --user --break-system-packages playwright 2>/dev/null || \
pip3 install --user playwright

# 安装浏览器
echo "🌐 安装 Chromium 浏览器..."
python3 -m playwright install chromium 2>/dev/null || echo "  ⚠️ 浏览器安装跳过（可能需要系统依赖）"

echo ""
echo "✅ 依赖安装完成！"
echo ""

# 安装 Git 推送密钥扫描钩子（防止真实凭据被推送到公开仓库）
echo "🔒 安装 pre-push 密钥扫描钩子..."
HOOKS_DIR=""
if [ -d .git-data/hooks ]; then
    HOOKS_DIR=".git-data/hooks"
elif [ -d .git/hooks ]; then
    HOOKS_DIR=".git/hooks"
fi

if [ -n "$HOOKS_DIR" ] && [ -f deploy/pre-push ]; then
    cp deploy/pre-push "$HOOKS_DIR/pre-push"
    chmod +x "$HOOKS_DIR/pre-push"
    echo "  ✅ 已安装到 $HOOKS_DIR/pre-push"
else
    echo "  ⚠️ 未找到 Git hooks 目录，跳过钩子安装"
fi

echo ""
echo "下一步:"
echo "  1. 获取 B站 Cookie:"
echo "     python3 scripts/get_bilibili_cookie.py"
echo ""
echo "  2. 初始化数据库:"
echo "     python3 scripts/init_db.py"
echo ""
echo "  3. 同步数据:"
echo "     python3 scripts/sync.py --source bilibili"
echo ""
echo "  4. 启动前端:"
echo "     streamlit run frontend/app.py"
echo ""
