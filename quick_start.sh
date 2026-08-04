#!/bin/bash
# 个人认知画像系统 - 快速开始脚本

set -e

echo "🧠 个人认知画像系统 - 快速开始"
echo "=================================================="

# 1. 运行环境安装
echo ""
echo "📦 步骤 1/4: 安装环境..."
bash setup.sh

# 2. 初始化数据库
echo ""
echo "🗄️ 步骤 2/4: 初始化数据库..."
python3 scripts/init_db.py

# 3. 获取 Cookie
echo ""
echo "🍪 步骤 3/4: 获取 B站 Cookie..."
echo "请按照提示输入 B站 Cookie"
python3 scripts/get_bilibili_cookie.py

# 4. 同步数据
echo ""
echo "📥 步骤 4/4: 同步 B站数据..."
python3 scripts/sync.py --source bilibili

echo ""
echo "=================================================="
echo "🎉 安装完成！"
echo "=================================================="
echo ""
echo "启动前端："
echo "  streamlit run frontend/app.py"
echo ""
echo "然后访问: http://localhost:8501"
echo ""
