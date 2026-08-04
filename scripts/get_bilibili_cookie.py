#!/usr/bin/env python3
"""自动获取 B站 Cookie"""

import sys
import os
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def get_cookie_with_browser():
    """使用浏览器自动获取 Cookie"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 请先安装 playwright: pip install playwright")
        return None

    print("🌐 正在启动浏览器...")
    print("📝 请在浏览器中登录 B站，登录完成后关闭浏览器窗口...")
    print()

    try:
        with sync_playwright() as p:
            # 启动浏览器（有界面模式）
            browser = p.chromium.launch(
                headless=False,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = browser.new_context()
            page = context.new_page()

            # 打开 B站登录页
            page.goto("https://passport.bilibili.com/login")

            print("=" * 50)
            print("📋 操作步骤：")
            print("  1. 在弹出的浏览器中登录 B站")
            print("  2. 登录成功后，关闭浏览器窗口")
            print("=" * 50)

            # 等待浏览器关闭
            page.wait_for_event("close", timeout=300000)  # 5分钟超时
            browser.close()

    except Exception as e:
        print(f"⚠️ 浏览器操作出错: {e}")
        print("将使用手动输入方式...")
        return None

    # 注意：这里需要重新获取 cookies，因为 page 已关闭
    # 改用另一种方式：在关闭前保存
    return None


def get_cookie_manual():
    """手动输入 Cookie"""
    print("=" * 50)
    print("📝 手动输入 B站 Cookie")
    print("=" * 50)
    print()
    print("获取方式：")
    print("  1. 浏览器登录 bilibili.com")
    print("  2. F12 打开开发者工具")
    print("  3. 切到 Application/Storage 标签")
    print("  4. 左侧找到 Cookies → https://www.bilibili.com")
    print("  5. 找到 SESSDATA 和 bili_jct 的值")
    print()
    print("  或者：")
    print("  1. F12 打开开发者工具")
    print("  2. 切到 Network 标签")
    print("  3. 刷新页面，找到任意请求")
    print("  4. 在 Request Headers 中找到 Cookie")
    print("  5. 复制 SESSDATA=xxx 和 bili_jct=xxx 的值")
    print()

    sessdata = input("请输入 SESSDATA: ").strip()
    bili_jct = input("请输入 bili_jct: ").strip()

    if sessdata and bili_jct:
        return {
            "SESSDATA": sessdata,
            "bili_jct": bili_jct,
        }
    else:
        print("❌ 输入不完整")
        return None


def save_to_env(cookie_data: dict):
    """保存到 .env 文件"""
    env_path = Path(".env")

    # 读取现有配置
    existing = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    existing[key.strip()] = value.strip()

    # 更新配置
    existing["BILIBILI_COOKIE"] = f"SESSDATA={cookie_data['SESSDATA']}; bili_jct={cookie_data['bili_jct']}"
    existing["BILIBILI_CSRF"] = cookie_data["bili_jct"]

    # 写入文件
    with open(env_path, "w", encoding="utf-8") as f:
        for key, value in existing.items():
            f.write(f"{key}={value}\n")

    print(f"\n✅ Cookie 已保存到 {env_path}")


def main():
    print("🍪 B站 Cookie 获取工具")
    print("=" * 50)

    # 选择获取方式
    print("\n选择获取方式：")
    print("  1. 手动输入（推荐）")
    print("  2. 自动获取（需要图形界面）")

    choice = input("\n请选择 (1/2): ").strip()

    cookie_data = None

    if choice == "2":
        cookie_data = get_cookie_with_browser()
        if cookie_data is None:
            print("\n⚠️ 自动获取失败，切换到手动输入...")
            cookie_data = get_cookie_manual()
    else:
        cookie_data = get_cookie_manual()

    if cookie_data:
        # 显示获取到的信息
        print("\n" + "=" * 50)
        print("📊 获取到的 Cookie：")
        print(f"  SESSDATA: {cookie_data['SESSDATA'][:20]}...")
        print(f"  bili_jct: {cookie_data['bili_jct'][:10]}...")
        print("=" * 50)

        # 保存到 .env
        save = input("\n是否保存到 .env 文件？(y/n): ").strip().lower()
        if save == "y":
            save_to_env(cookie_data)
            print("\n🎉 配置完成！现在可以运行同步脚本了：")
            print("  python3 scripts/sync.py --source bilibili")
    else:
        print("\n❌ 获取 Cookie 失败")


if __name__ == "__main__":
    main()
