"""Knowledge Agent —— 基于文档知识回答问题的 Agent"""

from app.modules.analysis.agent_protocol import Agent, AgentInput, AgentOutput
from app.core.gateway.base import ModelGateway
from app.modules.analysis.tool_protocol import Tool, ToolInput
from app.modules.knowledge.tool import RAGTool
from app.core.gateway.factory import get_model_gateway
from app.core.exceptions import StructuredOutputError
from app.modules.knowledge.rag.result_parser import parse_analysis_result
from app.modules.knowledge.schemas import RetrievalBrief


class KnowledgeAgent(Agent):
    """只使用文档知识工具的 Agent"""

    def __init__(
        self,
        rag_tool: Tool | None = None,
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
        feedback = input.context.get("feedback") or {}
        same_scope_retry = (
            feedback.get("target") == "knowledge"
            and feedback.get("mode") == "retry_same_scope"
        )
        attempts = {"same_scope_retry": 1} if same_scope_retry else {}
        # A retrieval-service retry deliberately keeps the original question and scope.
        # Feedback selects the operation; it must not be mixed into untrusted document text.
        facts = input.context.get("confirmed_facts") or []
        brief = RetrievalBrief(
            question=input.question,
            confirmed_fact_ids=[
                fact["fact_id"]
                for fact in facts
                if isinstance(fact, dict) and isinstance(fact.get("fact_id"), str)
            ],
            confirmed_fact_statements=[
                fact["statement"]
                for fact in facts
                if isinstance(fact, dict)
                and isinstance(fact.get("statement"), str)
                and fact["statement"].strip()
            ],
        )
        parameters = {"question": brief.render_query()}
        company_id = input.context.get("company_id")
        if company_id is not None:
            parameters["company_id"] = company_id
        if input.context.get("document_ids") is not None:
            parameters["document_ids"] = input.context["document_ids"]
        tool_input = ToolInput(parameters=parameters)
        result = self._rag_tool.execute(tool_input)
        if not result.success:
            return AgentOutput(
                success=False,
                error=result.error or "RAGTool failed",
                error_code=result.error_code,
                attempts=attempts,
            )
        data = result.data or {}

        if data.get("status") == "insufficient_evidence":
            return AgentOutput(
                success=True,
                answer=data["answer"],
                evidence=[],
                error_code="insufficient_evidence",
                attempts=attempts,
            )

        if data.get("status") != "ready":
            return AgentOutput(
                success=False,
                error="RAGTool returned an unexpected result status",
                attempts=attempts,
            )

        gateway = self._gateway or get_model_gateway()
        raw_output = gateway.chat(
            prompt=data["user_prompt"],
            system_prompt=data["system_prompt"],
            json_mode=True,
        )
        try:
            parsed_result = parse_analysis_result(
                raw_output,
                set(data["allowed_chunk_ids"]),
            )
        except StructuredOutputError:
            # A malformed model answer or an untrusted citation is not evidence.
            # Preserve any independently verified data result by letting Reviewer
            # produce a partial report instead of aborting the whole workflow.
            return AgentOutput(
                success=True,
                answer="无法根据现有文档形成可引用的原因判断。",
                evidence=[],
                error_code="knowledge_invalid_output",
                attempts=attempts,
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
            attempts=attempts,
        )
