"""Reviewer Agent —— 检查数据一致性和建议合理性，不替代确定性校验器"""

from app.agents.protocol import Agent, AgentInput, AgentOutput
from app.tools.protocol import Tool


def _format_data_result(data_result: dict) -> str | None:
    evidences = data_result.get("evidence") or []
    if not evidences:
        return None

    first_evidence = evidences[0]
    columns = first_evidence.get("columns") or []
    rows = first_evidence.get("rows") or []
    purpose = first_evidence.get("purpose") or "受控数据查询"

    if not columns or not rows:
        return f"数据查询（{purpose}）未返回可展示的记录。"

    rendered_rows = []
    for row in rows[:5]:
        fields = [f"{column}={value}" for column, value in zip(columns, row)]
        rendered_rows.append(", ".join(fields))

    return f"数据查询（{purpose}）：{'；'.join(rendered_rows)}"


class ReviewerAgent(Agent):
    """检查多个 Agent 的结果是否存在冲突，不直接生成新结论"""

    @property
    def name(self) -> str:
        return "reviewer"

    @property
    def description(self) -> str:
        return "检查 KnowledgeAgent 和 DataAgent 的结果是否一致"

    @property
    def allowed_tools(self) -> list[Tool]:
        return []  # Reviewer 不调任何工具

    def run(self, input: AgentInput) -> AgentOutput:
        """对比 context 中的两份证据，检查一致性"""
        data_result = input.context.get("data_result") or {}
        knowledge_result = input.context.get("knowledge_result") or {}
        plan = input.context.get("plan") or {}
        if not data_result and not knowledge_result:
            return AgentOutput(
                success=False,
                error="ReviewerAgent 需要 context 中有 data_result 或 knowledge_result",
            )

        data_summary = _format_data_result(data_result)
        data_failed = data_result.get("status") == "failed"
        knowledge_failed = knowledge_result.get("status") == "failed"
        knowledge_evidences = knowledge_result.get("evidences") or []
        knowledge_answer = knowledge_result.get("answer")
        citation_chunk_ids = [
            evidence["chunk_id"]
            for evidence in knowledge_evidences
            if isinstance(evidence.get("chunk_id"), int)
        ]
        if data_summary and knowledge_answer and citation_chunk_ids:
            citations_text = ", ".join(
                f"chunk_id={chunk_id}" for chunk_id in citation_chunk_ids
            )

            return AgentOutput(
                success=True,
                answer=(
                    f"{data_summary}\n"
                    f"文档说明：{knowledge_answer}\n"
                    f"文档引用：{citations_text}"
                ),
                evidence=[
                    {
                        "review_status": "complete",
                        "data_available": True,
                        "knowledge_available": True,
                        "citation_chunk_ids": citation_chunk_ids,
                        "limitations": [],
                    }
                ],
            )
        if data_summary and plan.get("route") == "data_only":
            return AgentOutput(
                success=True,
                answer=data_summary,
                evidence=[
                    {
                        "review_status": "completed",
                        "data_available": True,
                        "knowledge_available": False,
                        "citation_chunk_ids": [],
                        "limitations": [],
                    }
                ],
            )
        if data_summary:
            limitation = (
                "文档检索暂时不可用，未对原因作出结论。"
                if knowledge_failed
                else "未检索到足够的文档证据，未对原因作出结论。"
            )
            return AgentOutput(
                success=True,
                answer=f"{data_summary}\n无法根据现有文档说明下降原因。",
                evidence=[
                    {
                        "review_status": "partial",
                        "data_available": True,
                        "knowledge_available": False,
                        "citation_chunk_ids": [],
                        "limitations": [limitation],
                    }
                ],
            )

        if knowledge_answer and citation_chunk_ids:
            citations_text = ", ".join(
                f"chunk_id={chunk_id}" for chunk_id in citation_chunk_ids
            )
            return AgentOutput(
                success=True,
                answer=(
                    "文档线索（尚未由当前经营数据验证）："
                    f"{knowledge_answer}\n文档引用：{citations_text}"
                ),
                evidence=[
                    {
                        "review_status": "partial",
                        "data_available": False,
                        "knowledge_available": True,
                        "citation_chunk_ids": citation_chunk_ids,
                        "limitations": [
                            "经营数据查询未成功，文档线索不能作为已确认事实。"
                        ],
                    }
                ],
            )

        if data_failed and not citation_chunk_ids:
            return AgentOutput(
                success=False,
                error="经营数据与文档检索均未成功，无法形成分析结果",
            )

        if knowledge_answer and not knowledge_failed:
            return AgentOutput(
                success=True,
                answer=knowledge_answer,
                evidence=[
                    {
                        "review_status": "partial",
                        "data_available": False,
                        "knowledge_available": False,
                        "citation_chunk_ids": [],
                        "limitations": [
                            "未检索到足够的文档证据，无法形成可引用的原因判断。"
                        ],
                    }
                ],
            )
        return AgentOutput(
            success=False,
            error="ReviewerAgent 尚未支持当前证据组合",
        )
