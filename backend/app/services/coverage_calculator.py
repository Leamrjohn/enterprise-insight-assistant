"""覆盖率计算器 —— 检查证据是否覆盖了问题的关键实体"""

from app.core.rag.engine import _extract_keywords


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
            if kw in ev.content:
                found = True
                break
        if found:
            covered.append(kw)
        else:
            uncovered.append(kw)

    coverage = len(covered) / len(keywords)
    return (coverage, uncovered)
