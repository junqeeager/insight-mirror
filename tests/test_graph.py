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


def test_cooccurrence_uses_event_local_top5():
    # 音乐在事件 0 内词频最高（5 次），但全局只在事件 0 出现；
    # 其他词全局高频（每个 21 次），按全局排序会被挤出 Top5。
    events = [
        _event(0, "音乐 音乐 音乐 音乐 音乐 科技 财经 教育 体育 游戏", tags=[]),
    ]
    for i in range(1, 21):
        events.append(_event(i, "科技 财经 教育 体育 游戏", tags=[]))

    graph = build_interest_graph(events)
    edges = {(e["source"], e["target"]) for e in graph["edges"]}
    assert any("音乐" in pair for pair in edges), "事件内高频词应进入共现 Top5"


def test_filter_thresholds():
    events = [_event(i, "Python 编程 教程") for i in range(5)]
    graph = build_interest_graph(events, min_freq=4, min_co=2)
    freq = {n["id"]: n["freq"] for n in graph["nodes"]}
    assert freq, "过滤后仍应有节点"
    assert all(f >= 4 for f in freq.values())
    assert all(e["weight"] >= 2 for e in graph["edges"])


def test_max_nodes_prunes_graph():
    events = [
        _event(i, f"主题{i} 通用词 热门词", tags=["编程"])
        for i in range(10)
    ]
    graph = build_interest_graph(events, max_nodes=3)
    assert len(graph["nodes"]) == 3
    for edge in graph["edges"]:
        assert edge["source"] in {n["id"] for n in graph["nodes"]}
        assert edge["target"] in {n["id"] for n in graph["nodes"]}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 图谱测试通过！")
