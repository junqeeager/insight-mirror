"""关键词提取"""

from collections import Counter
from typing import List, Tuple

try:
    import jieba
    import jieba.analyse
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    # 提供简单的 fallback 实现
    def _simple_segment(text: str) -> List[str]:
        """简单的中文分词（按字符切分）"""
        import re
        # 按空格和标点分词
        words = re.split(r'[\s,.!?，。！？、；：""''（）\[\]【】]+', text)
        return [w.strip() for w in words if len(w.strip()) > 1]

    class _SimpleAnalyse:
        @staticmethod
        def extract_tags(text: str, topK: int = 20, withWeight: bool = False):
            """简单的关键词提取"""
            words = _simple_segment(text)
            counter = Counter(words)
            if withWeight:
                return [(word, count/len(words)) for word, count in counter.most_common(topK)]
            return [word for word, count in counter.most_common(topK)]

    # 创建兼容对象
    jieba = type('jieba', (), {'cut': lambda self, text: _simple_segment(text)})()
    jieba.analyse = _SimpleAnalyse()


# 中文停用词（精简版）
STOP_WORDS = set(
    "的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 "
    "自己 这 他 她 它 们 那 被 从 把 让 用 为 以 但 可 这个 那个 什么 怎么 如何 "
    "可以 这样 那样 个 种 之 而 与 及 或 虽然 因为 所以 如果 但是 然后 其实 "
    "可能 应该 已经 还是 还 只是 就是 只 不过 一些 这些 那些 之 内 以 外 "
    "http https www com cn org net html htm".split()
)


def extract_keywords(texts: List[str], top_n: int = 20) -> List[Tuple[str, float]]:
    """
    从文本列表中提取关键词

    Args:
        texts: 文本列表
        top_n: 返回前 N 个关键词

    Returns:
        [(关键词, 权重), ...]
    """
    # 合并所有文本
    combined_text = " ".join(texts)

    # 使用 TF-IDF 提取关键词
    keywords = jieba.analyse.extract_tags(
        combined_text,
        topK=top_n,
        withWeight=True,
    )

    # 过滤停用词
    filtered = [
        (word, weight)
        for word, weight in keywords
        if word not in STOP_WORDS and len(word) > 1
    ]

    return filtered


def extract_keywords_from_events(events: list, top_n: int = 20) -> List[Tuple[str, float]]:
    """
    从事件列表中提取关键词

    Args:
        events: Event 对象列表
        top_n: 返回前 N 个关键词

    Returns:
        [(关键词, 权重), ...]
    """
    texts = []
    for event in events:
        # 组合标题和描述
        text = event.title or ""
        if event.description:
            text += " " + event.description
        if event.tags:
            text += " " + " ".join(event.tags)
        texts.append(text)

    return extract_keywords(texts, top_n)


def segment_text(text: str) -> List[str]:
    """中文分词"""
    words = jieba.cut(text)
    return [w.strip() for w in words if w.strip() and w not in STOP_WORDS and len(w.strip()) > 1]


def word_frequency(texts: List[str]) -> Counter:
    """统计词频"""
    counter = Counter()
    for text in texts:
        words = segment_text(text)
        counter.update(words)
    return counter
