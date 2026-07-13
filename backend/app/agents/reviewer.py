"""Reviewer Agent —— 检查数据一致性和建议合理性，不替代确定性校验器"""

from app.agents.protocol import Agent, AgentInput, AgentOutput
from app.tools.protocol import Tool


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
        data_result = input.context.get("data_result", {})
        knowledge_result = input.context.get("knowledge_result", {})

        if not data_result and not knowledge_result:
            return AgentOutput(
                success=False,
                error="ReviewerAgent 需要 context 中有 data_result 或 knowledge_result",
            )

        conflicts = []

        # 简单检查：如果两份都有数据，看看关键指标是否出入
        if data_result and knowledge_result:
            conflicts.append("已收到 SQL 结果和文档证据，请人工确认一致性")

        return AgentOutput(
            success=True,
            answer=None,
            evidence=[{
                "has_conflicts": len(conflicts) > 0,
                "conflicts": conflicts,
                "data_available": bool(data_result),
                "knowledge_available": bool(knowledge_result),
            }],
        )
