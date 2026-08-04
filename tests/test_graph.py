"""兴趣图谱构建测试（pytest 兼容，也可直接运行）"""

import sys
from datetime import datetime
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.models import Event, EventType
from analysis.graph import build_interest_graph


def _event(i: int, title: str, tags=()):
    return Event(
        id=f"g-{i}",
        timestamp=datetime(2026, 8, 1, 10, 0, i),
        source="test",
        event_type=EventType.VIEW,
        title=title,
        tags=list(tags),
    )


def test_empty_events():
    assert build_interest_graph([]) == {"nodes": [], "edges": []}


def test_nodes_and_edges():
    events = [
        _event(1, "Python 编程 教程", tags=["编程"]),
        _event(2, "Python FastAPI 实战", tags=["编程", "后端"]),
    ]
    graph = build_interest_graph(events)
    freq = {n["id"]: n["freq"] for n in graph["nodes"]}
    assert freq.get("Python", 0) >= 2
    pairs = {(e["source"], e["target"]) for e in graph["edges"]}
    assert ("Python", "编程") in pairs or ("编程", "Python") in pairs


def test_filter_thresholds():
    events = [_event(i, "Python 编程 教程") for i in range(5)]
    graph = build_interest_graph(events, min_freq=4, min_co=2)
    freq = {n["id"]: n["freq"] for n in graph["nodes"]}
    assert freq, "过滤后仍应有节点"
    assert all(f >= 4 for f in freq.values())
    assert all(e["weight"] >= 2 for e in graph["edges"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 图谱测试通过！")
