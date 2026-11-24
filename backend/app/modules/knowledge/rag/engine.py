"""可靠RAG引擎

核心流程：检索证据 → 组装Prompt → 调用模型 → 校验引用 → 判断是否充分
"""

from dataclasses import dataclass, replace

from app.modules.runtime.context.compressors import excerpt
from app.modules.runtime.prompts import get_prompt_registry


@dataclass
class EvidenceRef:
    """一条证据引用"""

    chunk_id: int
    document_id: int
    content: str
    score: float = 0.0  # 向量召回分数
    rerank_score: float | None = None  # CrossEncoder 相关性分数
    document_name: str | None = None
    document_type: str | None = None
    page_number: int | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    chunk_strategy: str | None = None
    retrieval_strategies: tuple[str, ...] = ()
    effective_from: str | None = None
    effective_to: str | None = None
    applies_to: str | None = None


@dataclass
class RAGResult:
    """RAG 处理结果"""

    answer: str
    evidence_used: list[EvidenceRef]
    is_sufficient: bool
    rejection_reason: str | None = None


def _validity_attributes(evidence: EvidenceRef) -> str:
    """Registered validity for the model; absent when nothing was registered."""
    attributes = ""
    if evidence.effective_from is not None:
        attributes += f' valid_from="{evidence.effective_from}"'
        attributes += f' valid_to="{evidence.effective_to or "至今"}"'
    if evidence.applies_to:
        attributes += f' applies_to="{evidence.applies_to}"'
    return attributes


EVIDENCE_MAX_CHARS = 3000
# Less room than this is not worth an excerpt.
MIN_EXCERPT_CHARS = 40


def fit_evidences(
    question: str, evidences: list[EvidenceRef], max_chars: int = EVIDENCE_MAX_CHARS
) -> list[EvidenceRef]:
    """The evidences the answer reads, best first, within ``max_chars``.

    The best one is always whole.  C7: one that no longer fits is cut to the
    sentences about the question (compressors.excerpt) instead of being
    dropped with everything after it.  Fitting the result again changes
    nothing, so build_prompt can be given it.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    sorted_evidences = sorted(
        evidences,
        key=lambda evidence: (
            evidence.rerank_score
            if evidence.rerank_score is not None
            else evidence.score
        ),
        reverse=True,
    )
    selected: list[EvidenceRef] = []
    total_chars = 0
    for evidence in sorted_evidences:
        if not selected or total_chars + len(evidence.content) <= max_chars:
            selected.append(evidence)
            total_chars += len(evidence.content)
            continue
        room = max_chars - total_chars
        if room < MIN_EXCERPT_CHARS:
            break
        text = excerpt(evidence.content, question, room)
        if text is not None:
            selected.append(replace(evidence, content=text))
            total_chars += len(text)
    return selected


def build_prompt(
    question: str, evidences: list[EvidenceRef], max_chars: int = EVIDENCE_MAX_CHARS
) -> tuple[str, str, set[int]]:
    """返回 (system_prompt, user_prompt, allowed_chunk_ids)。"""
    selected = fit_evidences(question, evidences, max_chars)
    context = "\n\n".join(
        (
            f'<evidence chunk_id="{evidence.chunk_id}" '
            f'document="{evidence.document_name or "unknown"}" '
            f'type="{evidence.document_type or "unknown"}" '
            f'page="{evidence.page_number or "unknown"}" '
            f'paragraphs="{evidence.paragraph_start or "unknown"}-{evidence.paragraph_end or "unknown"}"'
            f"{_validity_attributes(evidence)}>\n"
            f"{evidence.content}\n</evidence>"
        )
        for evidence in selected
    )
    system_prompt = get_prompt_registry().text("knowledge.answer_system")
    user_prompt = f"""资料：
{context}
问题：{question}
要求：
1. answer 只能基于提供的资料回答。
2. citations 必须列出支撑答案的 chunk_id。
3. citations 只能使用资料中出现的 chunk_id。"""
    return system_prompt, user_prompt, {e.chunk_id for e in selected}


def keep_relevant(evidences: list[EvidenceRef], min_score: float) -> list[EvidenceRef]:
    """Drop chunks the reranker considers irrelevant.

    Its scores are close to 0 or 1, so one good chunk among unrelated ones is a
    normal result; averaging them would refuse a question that has its answer.
    """
    return [e for e in evidences if (e.rerank_score or 0.0) >= min_score]


def check_sufficiency(
    evidences: list[EvidenceRef],
    question: str = "",
    min_evidences: int = 1,
    min_avg_score: float = 0.5,
) -> bool:
    """判断证据是否充分

    参数：
        evidences: 检索到的证据列表
        min_evidences: 最少需要几条证据
        min_avg_score: 证据的平均重排相关性最低门槛
    """
    if len(evidences) < min_evidences:
        return False
    avg_score = sum(
        evidence.rerank_score if evidence.rerank_score is not None else evidence.score
        for evidence in evidences
    ) / len(evidences)
    return not avg_score < min_avg_score
