"""Planner Agent —— 分析问题，拆解任务，决定调用哪些 Agent"""

from app.agents.protocol import Agent, AgentInput, AgentOutput
from app.tools.protocol import Tool


class PlannerAgent(Agent):
    """拆解用户问题，生成执行计划，但不直接生成最终结论"""

    @property
    def name(self) -> str:
        return "planner"

    @property
    def description(self) -> str:
        return "分析用户问题，拆解为子任务，决定需要调用哪些 Agent"

    @property
    def allowed_tools(self) -> list[Tool]:
        return []  # Planner 不调任何工具

    def run(self, input: AgentInput) -> AgentOutput:
        question = input.question

        # 简单规则：根据关键词决定需要哪些 Agent
        data_keywords = [
            "销售额", "订单", "客诉", "毛利", "收入", "成本",
            "多少", "统计", "占比", "趋势", "对比", "数据",
        ]
        doc_keywords = [
            "文档", "报告", "资料", "季度", "年度", "总结",
            "原因", "分析", "建议", "方案", "根据资料",
        ]

        need_data = any(kw in question for kw in data_keywords)
        need_knowledge = any(kw in question for kw in doc_keywords)

        if not need_data and not need_knowledge:
            return AgentOutput(
                success=False,
                error="无法判断需要哪种 Agent，请提供更具体的业务问题",
            )

        return AgentOutput(
            success=True,
            answer=None,
            evidence=[{
                "plan": {
                    "need_data": need_data,
                    "need_knowledge": need_knowledge,
                    "steps": self._build_steps(need_data, need_knowledge),
                }
            }],
        )

    def _build_steps(self, need_data: bool, need_knowledge: bool) -> list[str]:
        steps = []
        if need_data:
            steps.append("调用 DataAgent 查询经营数据")
        if need_knowledge:
            steps.append("调用 KnowledgeAgent 检索文档")
        return steps
