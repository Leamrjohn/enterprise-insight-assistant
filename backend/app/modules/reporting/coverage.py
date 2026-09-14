"""覆盖率计算器 —— 检查证据是否覆盖了问题的关键实体"""

import re


def _extract_keywords(question: str) -> list[str]:
    """Small local extractor so coverage is independent from RAG internals."""
    stop_words = {
        "为什么",
        "怎么",
        "如何",
        "请问",
        "分析",
        "是否",
        "当前",
        "这个",
        "哪些",
    }
    tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", question)
    return [token for token in dict.fromkeys(tokens) if token not in stop_words]


def calculate_coverage(
    question: str, evidences: list, answer: str = ""
) -> tuple[float, list[str]]:
    """计算证据对问题关键实体的覆盖率。返回(覆盖率, 未覆盖实体列表)"""
    if not evidences or not question:
        return (0.0, [])

    keywords = _extract_keywords(question)
    if not keywords:
        return (1.0, [])

    covered = []
    uncovered = []
    for kw in keywords:
        found = False
        for ev in evidences:
            content = (
                ev.get("content", "")
                if isinstance(ev, dict)
                else getattr(ev, "content", "")
            )
            if kw in content:
                found = True
                break
        if found:
            covered.append(kw)
        else:
            uncovered.append(kw)

    coverage = len(covered) / len(keywords)
    return (coverage, uncovered)
