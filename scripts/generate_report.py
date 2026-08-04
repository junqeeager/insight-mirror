"""生成报告脚本"""

import sys
import argparse
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import Database
from core.utils import load_config
from analysis.profile import ProfileGenerator
from report.generator import ReportGenerator


def main():
    parser = argparse.ArgumentParser(description="生成个人认知画像报告")
    parser.add_argument(
        "--period",
        type=str,
        choices=["weekly", "monthly", "yearly"],
        default="weekly",
        help="报告周期",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["html", "text", "both"],
        default="both",
        help="输出格式",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径",
    )

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 初始化数据库
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]

    db = Database(db_path)
    db.init_tables()

    # 生成画像
    print(f"📊 生成 {args.period} 报告...")
    generator = ProfileGenerator(db, config.get("analysis", {}))
    profile = generator.generate(period=args.period)

    # 生成报告
    report_gen = ReportGenerator()

    if args.format in ["html", "both"]:
        report_path = report_gen.generate_html(profile)
        print(f"📄 HTML 报告已生成: {report_path}")

    if args.format in ["text", "both"]:
        text_report = report_gen.generate_summary(profile)
        text_path = f"./data/reports/{profile.id}_{profile.period}.txt"
        Path(text_path).parent.mkdir(parents=True, exist_ok=True)
        Path(text_path).write_text(text_report, encoding="utf-8")
        print(f"📄 文本报告已生成: {text_path}")

    # 打印摘要
    print("\n" + "=" * 50)
    print(report_gen.generate_summary(profile))
    print("=" * 50)

    db.close()


if __name__ == "__main__":
    main()
