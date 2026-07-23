"""Knowledge Agent —— 基于文档知识回答问题的 Agent"""

from app.agents.protocol import Agent, AgentInput, AgentOutput
from app.core.gateway.base import ModelGateway
from app.tools.protocol import Tool, ToolInput
from app.tools.rag import RAGTool
from app.core.gateway.factory import get_model_gateway
from app.core.rag.result_parser import parse_analysis_result


class KnowledgeAgent(Agent):
    """只使用文档知识工具的 Agent"""

    def __init__(
        self,
        rag_tool: RAGTool | None = None,
        gateway: ModelGateway | None = None,
    ) -> None:
        self._rag_tool = rag_tool or RAGTool()
        self._gateway = gateway

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
            return AgentOutput(
                success=False,
                error=result.error or "RAGTool failed",
            )
        data = result.data or {}

        if data.get("status") == "insufficient_evidence":
            return AgentOutput(
                success=True,
                answer=data["answer"],
                evidence=[],
            )

        if data.get("status") != "ready":
            return AgentOutput(
                success=False,
                error="RAGTool returned an unexpected result status",
            )

        gateway = self._gateway or get_model_gateway()
        raw_output = gateway.chat(
            prompt=data["user_prompt"],
            system_prompt=data["system_prompt"],
            json_mode=True,
        )
        parsed_result = parse_analysis_result(
            raw_output,
            set(data["allowed_chunk_ids"]),
        )

        retrieved_evidences = {
            evidence["chunk_id"]: evidence for evidence in data["evidences"]
        }
        cited_evidences = []
        for citation in parsed_result.citations:
            evidence = retrieved_evidences[citation.chunk_id]
            cited_evidence = {
                "chunk_id": citation.chunk_id,
                "document_id": evidence["document_id"],
                "content": evidence["content"],
                "score": evidence["score"],
            }
            if "rerank_score" in evidence:
                cited_evidence["rerank_score"] = evidence["rerank_score"]
            cited_evidences.append(cited_evidence)

        return AgentOutput(
            success=True,
            answer=parsed_result.answer,
            evidence=cited_evidences,
        )
