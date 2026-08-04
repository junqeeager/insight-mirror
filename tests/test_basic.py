"""基础测试"""

import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 测试核心模块导入
from core.models import Event, EventType, Depth, Topic, Profile
from core.database import Database
from core.plugin_loader import DataSourcePlugin, PluginManager

# 测试分析模块导入
from analysis.keywords import extract_keywords, segment_text
from analysis.trends import analyze_time_distribution, analyze_source_distribution

# 测试报告模块导入
from report.generator import ReportGenerator

# 测试工具模块
from core.utils import load_config, format_duration

print("✅ 所有模块导入成功！")

# 测试数据库初始化
db = Database(":memory:")
db.init_tables()
print("✅ 内存数据库初始化成功！")

# 测试事件创建和插入
from datetime import datetime
event = Event(
    id="test-1",
    timestamp=datetime(2024, 1, 1, 12, 0, 0),
    source="test",
    event_type=EventType.VIEW,
    title="测试视频",
)
db.insert_event(event)
assert db.get_event_count() == 1
print("✅ 事件插入成功！")

# 测试关键词提取
texts = ["Python 编程", "机器学习 深度学习", "数据分析 可视化"]
keywords = extract_keywords(texts, top_n=5)
print(f"✅ 关键词提取: {keywords}")

# 测试格式化
duration = format_duration(3661)
assert duration == "1小时1分钟"
print(f"✅ 时长格式化: {duration}")

db.close()
print("\n🎉 所有基础测试通过！")
