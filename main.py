"""个人认知画像系统 - 主入口"""

import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from core.database import Database
from core.plugin_loader import PluginManager
from core.utils import load_config


def main():
    """主函数"""
    print("🧠 个人认知画像系统")
    print("=" * 50)

    # 1. 加载配置
    print("📄 加载配置...")
    config = load_config()
    print(f"  ✅ 配置已加载")

    # 2. 初始化数据库
    print("🗄️ 初始化数据库...")
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]

    db = Database(db_path)
    db.init_tables()
    print(f"  ✅ 数据库已初始化: {db_path}")

    # 3. 加载插件
    print("🔌 加载插件...")
    plugin_manager = PluginManager(config["system"]["plugins_dir"], config)
    discovered = plugin_manager.discover()
    print(f"  ✅ 发现插件: {discovered}")

    # 4. 显示统计
    stats = db.get_stats()
    print(f"\n📊 数据库统计:")
    print(f"  总事件数: {stats['total']}")
    for source, count in stats.get("by_source", {}).items():
        print(f"  - {source}: {count} 条")

    # 5. 显示已启用的数据源
    print(f"\n📦 已启用的数据源:")
    for plugin in plugin_manager.get_enabled_plugins():
        print(f"  - {plugin.icon} {plugin.display_name}")

    db.close()
    print("\n✅ 系统就绪！")
    print("\n下一步:")
    print("  1. 配置数据源: 编辑 config.yaml")
    print("  2. 同步数据: python scripts/sync.py")
    print("  3. 生成报告: python scripts/generate_report.py")
    print("  4. 启动前端: streamlit run frontend/app.py")


if __name__ == "__main__":
    main()
