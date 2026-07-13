"""可靠RAG引擎

核心流程：检索证据 → 组装Prompt → 调用模型 → 校验引用 → 判断是否充分
"""

from dataclasses import dataclass
from app.core.model_gateway import ModelGateway


@dataclass
class EvidenceRef:
    """一条证据引用"""
    chunk_id: int
    document_id: int
    content: str
    score: float = 0.0


@dataclass
class RAGResult:
    """RAG 处理结果"""
    answer: str
    evidence_used: list[EvidenceRef]
    is_sufficient: bool
    rejection_reason: str | None = None


def build_prompt(question: str, evidences: list[EvidenceRef],max_chars: int = 3000) -> tuple[str, str]:
    """把问题和证据组装成Prompt，返回(system_prompt, user_prompt)"""
    sorted_evidences = sorted(evidences, key=lambda e: e.score, reverse=True)
    # 按字数上限截断
    selected = []
    total_chars = 0
    for e in sorted_evidences:
        total_chars += len(e.content)
        if total_chars < max_chars:
            selected.append(e)
        else:
            break
    if not selected and sorted_evidences:
        selected = [sorted_evidences[0]]  # 至少保留一条

    context = "\n\n".join(
        f"[引用 {e.chunk_id}] {e.content}" for e in selected
    )
    system_prompt = "你是一个数据分析助手。只能基于提供的资料回答问题。如果资料不足以回答问题，请明确说明。"
    user_prompt = f"""资料：
{context}
问题：{question}
要求：
1. 只基于提供的资料回答
2. 在引用处标注 [来源: chunk_id]
3. 如果资料不足以回答问题，请说明"""
    return system_prompt, user_prompt


def check_sufficiency(
    evidences: list[EvidenceRef],
    question: str ="",
    min_evidences: int = 1,
    min_avg_score: float = 0.4,

) -> bool:
    """判断证据是否充分

    参数：
        evidences: 检索到的证据列表
        min_evidences: 最少需要几条证据
        min_avg_score: 证据的平均相似度最低门槛
    """
    if len(evidences) < min_evidences:
        return False
    avg_score = sum(e.score for e in evidences) / len(evidences)
    if avg_score < min_avg_score:
        return False
    if question:
        keywords = _extract_keywords(question)
        if keywords:
            matched = [
                e for e in evidences
                if any(kw in e.content for kw in keywords)
            ]
            if len(matched) < min_evidences:
                return False
    return True


def _extract_keywords(question:str) ->list[str]:
    """从问题中提取关键词，用于实体匹配兜底"""
    # 常见的停用词（对问题语义贡献不大的词）
    stop_words = {
        "什么", "为什么", "怎么", "如何", "的", "是", "了", "在", "和",
        "对", "原因", "怎样", "吗", "呢", "吗", "可以", "能", "会",
        "有", "不", "都", "要", "还", "也", "就", "\u3001", "\uff0c",
    }
    # 用这些停用词把问题拆成片段
    # 简单做法：逐个停用词替换成空格，再按空格切分
    text = question
    for word in stop_words:
        text = text.replace(word, " ")
    keywords = [w.strip() for w in text.split() if len(w.strip()) >= 2]
    return list(dict.fromkeys(keywords))  # 去重，保留原始顺序
