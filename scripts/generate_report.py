"""生成报告脚本"""

import logging
import sys
import argparse
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import Database, database_url
from core.utils import load_config, setup_logging
from analysis.profile import ProfileGenerator
from report.generator import ReportGenerator

logger = logging.getLogger("generate_report")


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

    setup_logging()

    # 加载配置
    config = load_config(args.config)

    # 初始化数据库
    db_url = database_url(config)
    db = Database(db_url)
    db.init_tables()

    # 生成画像
    logger.info("📊 生成 %s 报告...", args.period)
    generator = ProfileGenerator(db, config.get("analysis", {}))
    profile = generator.generate(period=args.period)

    # 生成报告
    report_gen = ReportGenerator()

    if args.format in ["html", "both"]:
        report_path = report_gen.generate_html(profile)
        logger.info("📄 HTML 报告已生成: %s", report_path)

    if args.format in ["text", "both"]:
        text_report = report_gen.generate_summary(profile)
        text_path = f"./data/reports/{profile.id}_{profile.period}.txt"
        Path(text_path).parent.mkdir(parents=True, exist_ok=True)
        Path(text_path).write_text(text_report, encoding="utf-8")
        logger.info("📄 文本报告已生成: %s", text_path)

    # 打印摘要
    logger.info("\n" + "=" * 50 + "\n%s\n" + "=" * 50, report_gen.generate_summary(profile))

    db.close()


if __name__ == "__main__":
    main()
