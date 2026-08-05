"""兴趣图谱构建（分词 → 词频 → 事件内 top5 共现）"""

from collections import Counter
from typing import Any, Dict, List, Optional

from analysis.keywords import segment_text


def build_interest_graph(
    events: list,
    min_freq: int = 1,
    min_co: int = 1,
    max_nodes: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """从事件列表构建兴趣共现图。

    Returns:
        {"nodes": [{"id", "label", "freq"}], "edges": [{"source", "target", "weight"}]}
    """
    event_keywords: List[Counter] = []
    for event in events:
        text = event.title or ""
        if event.description:
            text += " " + event.description
        if event.tags:
            text += " " + " ".join(event.tags)
        keywords = Counter(segment_text(text))
        if keywords:
            event_keywords.append(keywords)

    keyword_freq: Counter = Counter()
    co_occurrence: Counter = Counter()

    for keywords in event_keywords:
        for word in keywords:
            keyword_freq[word] += 1
        # 取该事件内词频最高的 5 个关键词
        top = [word for word, _ in keywords.most_common(5)]
        for i, w1 in enumerate(top):
            for w2 in top[i + 1:]:
                if w1 != w2:
                    co_occurrence[(w1, w2)] += 1

    nodes = [
        {"id": word, "label": word, "freq": freq}
        for word, freq in keyword_freq.items()
        if freq >= min_freq
    ]
    if max_nodes and len(nodes) > max_nodes:
        nodes = sorted(nodes, key=lambda n: n["freq"], reverse=True)[:max_nodes]
    node_ids = {n["id"] for n in nodes}
    edges = [
        {"source": s, "target": t, "weight": count}
        for (s, t), count in co_occurrence.items()
        if s in node_ids and t in node_ids and count >= min_co
    ]
    return {"nodes": nodes, "edges": edges}
