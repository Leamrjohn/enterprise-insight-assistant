"""Knowledge Agent —— 基于文档知识回答问题的 Agent"""

from app.services.agent_protocol import Agent, AgentInput, AgentOutput
from app.services.tool_protocol import Tool, ToolInput
from app.services.rag_tool import RAGTool


class KnowledgeAgent(Agent):
    """只使用文档知识工具的 Agent"""

    def __init__(self):
        self._rag_tool = RAGTool()

    @property
    def name(self) -> str:
        return "knowledge"

    @property
    def description(self) -> str:
        return "在已上传的文档中搜索相关内容，回答需要文档支撑的问题"

    @property
    def allowed_tools(self) -> list[Tool]:
        return [self._rag_tool]

    def run(self, input: AgentInput) -> AgentOutput:
        """执行知识检索"""
        tool_input = ToolInput(
            parameters={
                "question": input.question,
                "user_id": input.user_id,
            }
        )
        result = self._rag_tool.execute(tool_input)

        if not result.success:
            return AgentOutput(success=False, error=result.error)

        return AgentOutput(
            success=True,
            answer=result.data.get("answer") if result.data else None,
            evidence=result.data.get("evidences") if result.data else [],
        )
