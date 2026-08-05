"""主题聚类"""

from typing import List, Dict, Tuple
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation

from analysis.keywords import segment_text


def cluster_topics(
    events: list,
    n_clusters: int = 5,
    method: str = "kmeans",
) -> Dict[int, List[dict]]:
    """
    对事件进行主题聚类

    Args:
        events: Event 对象列表
        n_clusters: 聚类数量
        method: 聚类方法 (kmeans / lda)

    Returns:
        {cluster_id: [event_dict, ...]}
    """
    if len(events) < n_clusters:
        return {0: events}

    # 准备文本数据
    texts = []
    for event in events:
        text = event.title or ""
        if event.description:
            text += " " + event.description
        # 分词后重新组合
        texts.append(" ".join(segment_text(text)))

    # TF-IDF 向量化
    vectorizer = TfidfVectorizer(max_features=1000, max_df=0.8, min_df=2)
    try:
        tfidf_matrix = vectorizer.fit_transform(texts)
    except ValueError:
        # 文档太少或词汇太少
        return {0: events}

    # 聚类
    if method == "kmeans":
        n_clusters = min(n_clusters, len(events))
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init=5)
        labels = model.fit_predict(tfidf_matrix)
    elif method == "lda":
        n_clusters = min(n_clusters, len(events))
        model = LatentDirichletAllocation(
            n_components=n_clusters, random_state=42
        )
        transformed = model.fit_transform(tfidf_matrix)
        labels = transformed.argmax(axis=1)
    else:
        return {0: events}

    # 按聚类分组
    clusters = defaultdict(list)
    for idx, label in enumerate(labels):
        clusters[label].append(events[idx])

    return dict(clusters)


def get_cluster_keywords(
    events: list,
    vectorizer: TfidfVectorizer = None,
    top_n: int = 5,
) -> List[Tuple[str, float]]:
    """
    获取事件集合的主题关键词

    Args:
        events: Event 对象列表
        vectorizer: 已拟合的 TF-IDF 向量化器
        top_n: 返回前 N 个关键词

    Returns:
        [(关键词, 权重), ...]
    """
    texts = []
    for event in events:
        text = event.title or ""
        if event.description:
            text += " " + event.description
        texts.append(" ".join(segment_text(text)))

    combined = " ".join(texts)
    words = segment_text(combined)

    # 简单的词频统计作为主题词
    from collections import Counter
    counter = Counter(words)
    return counter.most_common(top_n)


def compute_cluster_similarity(cluster_events: List[list]) -> float:
    """
    计算多个聚类之间的相似度

    Returns:
        0-1 之间的相似度值
    """
    if len(cluster_events) < 2:
        return 0.0

    # 计算每个聚类的关键词集合
    cluster_keywords = []
    for events in cluster_events:
        keywords = set()
        for event in events:
            if event.title:
                keywords.update(segment_text(event.title))
        cluster_keywords.append(keywords)

    # 计算 Jaccard 相似度
    total_similarity = 0.0
    count = 0
    for i in range(len(cluster_keywords)):
        for j in range(i + 1, len(cluster_keywords)):
            if cluster_keywords[i] and cluster_keywords[j]:
                intersection = cluster_keywords[i] & cluster_keywords[j]
                union = cluster_keywords[i] | cluster_keywords[j]
                similarity = len(intersection) / len(union) if union else 0
                total_similarity += similarity
                count += 1

    return total_similarity / count if count > 0 else 0.0
