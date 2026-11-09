"""Knowledge Agent whose model may search again before it answers.

Code runs the first search, so a question the first search already answers costs
no extra model round.  Company, documents and validity window are set by code on
every search; the model only writes the words to look for.  Citations are checked
against what was really retrieved, and the support check runs as on the fixed route.
"""

from __future__ import annotations

import json

from app.core.gateway.base import ModelGateway
from app.core.gateway.factory import get_model_gateway
from app.modules.analysis.agent_protocol import AgentInput, AgentOutput
from app.modules.analysis.tool_protocol import ToolInput, ToolOutput
from app.modules.knowledge.agent import (
    CONFIRMED_FACTS_DATA_NOTE,
    CONFIRMED_FACTS_RULES,
    KnowledgeAgent,
)
from app.modules.knowledge.analysis_result import AnalysisCitation
from app.modules.runtime.prompts import get_prompt_registry
from app.modules.runtime.tool_guard import outcome_of_failure
from app.modules.runtime.tool_loop import (
    LoopLimits,
    ToolReply,
    ToolSpec,
    run_tool_loop,
)
from pydantic import BaseModel, ConfigDict, Field

MAX_SEARCHES = 3
INSUFFICIENT_ANSWER = "无法回答：资料不足"


class SearchDocumentsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=300, description="要检索的中文关键词")


class SubmitAnswerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, description="只基于资料的回答")
    citations: list[AnalysisCitation] = Field(
        min_length=1, description="支撑答案的 chunk_id"
    )


class ReportNoEvidenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=300)


KNOWLEDGE_TOOL_CATALOG_VERSION = "knowledge-tools/v1"
KNOWLEDGE_TOOL_SPECS = [
    ToolSpec(
        name="search_documents",
        version="search_documents/v1",
        purpose="用另一组关键词再检索一次公司文档。范围和有效期由系统决定。",
        when_to_use="已有资料不足以回答，而且换一种说法可能找到时。",
        when_not_to_use="已有资料够回答时；不要重复相同的关键词。",
        example={"query": "退货 审批 流程"},
        common_errors=("把整段问题原样再搜一次",),
        input_model=SearchDocumentsArgs,
    ),
    ToolSpec(
        name="submit_answer",
        version="submit_answer/v1",
        purpose="提交基于资料的回答和它引用的 chunk_id，结束检索。",
        when_to_use="资料能支持回答时。",
        when_not_to_use="资料不足时，不要凭常识作答。",
        example={"answer": "退货需要主管审批。", "citations": [{"chunk_id": 123}]},
        common_errors=("引用了没有出现过的 chunk_id",),
        input_model=SubmitAnswerArgs,
    ),
    ToolSpec(
        name="report_no_evidence",
        version="report_no_evidence/v1",
        purpose="说明文档里找不到答案，结束检索。",
        when_to_use="换过关键词后资料仍然不足时。",
        when_not_to_use="资料已能回答问题的一部分时，应回答这一部分。",
        example={"reason": "文档没有提到库存周转天数"},
        common_errors=(),
        input_model=ReportNoEvidenceArgs,
    ),
]
SYSTEM_PROMPT = get_prompt_registry().text("knowledge.tool_system")


def _shown(evidence: dict) -> dict:
    """Only what answering needs: scores and internal fields stay on the server."""
    return {
        "chunk_id": evidence["chunk_id"],
        "document": evidence.get("document_name"),
        "page": evidence.get("page_number"),
        "effective_from": evidence.get("effective_from"),
        "effective_to": evidence.get("effective_to"),
        "applies_to": evidence.get("applies_to"),
        "content": evidence["content"],
    }


class _KnowledgeToolSession:
    def __init__(
        self, agent: ToolCallingKnowledgeAgent, input: AgentInput, gateway: ModelGateway
    ) -> None:
        self._agent = agent
        self._input = input
        self._gateway = gateway
        self.brief, self.facts = agent._retrieval_brief(input)
        self.parameters = agent._search_parameters(input)
        self.retrieved: dict[int, dict] = {}
        self.searches = 0
        self.seen_queries: set[str] = set()
        self.degraded = False
        self.switched_from: str | None = None
        self.attempts: dict = {}
        self.final: AgentOutput | None = None
        self.failure: ToolOutput | None = None

    @property
    def handlers(self) -> dict:
        return {
            "search_documents": self.search_documents,
            "submit_answer": self.submit_answer,
            "report_no_evidence": self.report_no_evidence,
        }

    def search(self, query: str) -> ToolOutput:
        self.searches += 1
        self.seen_queries.add(query)
        result = self._agent._rag_tool.execute(
            ToolInput(parameters={**self.parameters, "question": query})
        )
        if not result.success:
            self.failure = result
            return result
        data = result.data or {}
        self.degraded = self.degraded or bool(data.get("degraded"))
        self.switched_from = self.switched_from or data.get("switched_from")
        for evidence in data.get("evidences") or []:
            self.retrieved[evidence["chunk_id"]] = evidence
        return result

    def render(self, result: ToolOutput) -> dict:
        evidences = (result.data or {}).get("evidences") or []
        if not evidences:
            return {"status": "insufficient_evidence", "evidences": []}
        return {"status": "ready", "evidences": [_shown(e) for e in evidences]}

    def search_documents(self, args: SearchDocumentsArgs) -> ToolReply:
        if self.searches >= MAX_SEARCHES:
            return ToolReply(
                {"error": "检索次数已用完，请基于已有资料回答或说明资料不足。"},
                "repairable",
                "search_limit_reached",
            )
        if args.query in self.seen_queries:
            return ToolReply(
                {"error": "这组关键词已经查过，请换一种说法或结束检索。"},
                "repairable",
                "search_repeated",
            )
        result = self.search(args.query)
        if not result.success:
            return ToolReply(
                {"error": result.error},
                outcome_of_failure(result),
                result.error_code,
            )
        return ToolReply(self.render(result))

    def submit_answer(self, args: SubmitAnswerArgs) -> ToolReply:
        cited = [citation.chunk_id for citation in args.citations]
        unknown = sorted(set(cited) - set(self.retrieved))
        if unknown:
            return ToolReply(
                {"error": "这些 chunk_id 没有在检索结果里出现。", "unknown": unknown},
                "repairable",
                "citation_unknown",
            )
        self.final = self._agent._cited_output(
            input=self._input,
            gateway=self._gateway,
            answer=args.answer,
            cited_chunk_ids=cited,
            evidences=list(self.retrieved.values()),
            validity_window=self.parameters["validity_window"],
            brief=self.brief,
            attempts=self.attempts,
        )
        return ToolReply({"accepted": True}, "finish")

    def report_no_evidence(self, _args: ReportNoEvidenceArgs) -> ToolReply:
        self.final = AgentOutput(
            success=True,
            answer=INSUFFICIENT_ANSWER,
            evidence=[],
            error_code="insufficient_evidence",
            attempts=self.attempts,
        )
        return ToolReply({"accepted": True}, "finish")


class ToolCallingKnowledgeAgent(KnowledgeAgent):
    """Same output contract as KnowledgeAgent, so the workflow cannot tell."""

    def __init__(self, *args, limits: LoopLimits | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._limits = limits or LoopLimits(max_rounds=4, max_tool_calls=5)

    def _user_prompt(
        self, input: AgentInput, session: _KnowledgeToolSession, first: ToolOutput
    ) -> str:
        prompt = (
            f"<question>\n{input.question}\n</question>\n"
            "系统已按问题检索一次，结果如下：\n"
            f"<search_result>\n{json.dumps(session.render(first), ensure_ascii=False)}\n"
            "</search_result>\n"
        )
        if session.brief.confirmed_fact_statements:
            prompt += (
                "<confirmed_data_facts>\n- "
                + "\n- ".join(session.brief.confirmed_fact_statements)
                + f"\n</confirmed_data_facts>\n{CONFIRMED_FACTS_DATA_NOTE}"
            )
        return prompt

    def run(self, input: AgentInput) -> AgentOutput:
        if input.context.get("feedback"):
            return super().run(input)
        gateway = self._gateway or get_model_gateway()
        session = _KnowledgeToolSession(self, input, gateway)
        first = session.search(session.brief.render_query())
        if not first.success:
            return AgentOutput(
                success=False,
                error=first.error or "RAGTool failed",
                error_code=first.error_code,
            )
        loop = run_tool_loop(
            gateway,
            system_prompt=SYSTEM_PROMPT
            + (CONFIRMED_FACTS_RULES if session.facts else ""),
            user_prompt=self._user_prompt(input, session, first),
            specs=KNOWLEDGE_TOOL_SPECS,
            handlers=session.handlers,
            limits=self._limits,
        )
        tool_loop = {
            "catalog_version": KNOWLEDGE_TOOL_CATALOG_VERSION,
            "stop_reason": loop.stop_reason,
            "rounds": loop.rounds,
            "searches": session.searches,
            "trace": loop.trace,
        }
        session.attempts["tool_loop"] = tool_loop
        if session.degraded:
            session.attempts["degraded"] = ["rerank"]
        if session.switched_from:
            session.attempts["switched_from"] = session.switched_from
        if session.final is not None:
            return session.final
        if loop.stop_reason in ("denied", "exhausted", "unavailable"):
            failure = session.failure
            return AgentOutput(
                success=False,
                error=(failure.error if failure else None) or "文档检索未能完成。",
                error_code=failure.error_code if failure else loop.stop_reason,
                attempts=session.attempts,
            )
        # Lost its way without an answer: the fixed route takes this question.
        output = super().run(input)
        output.attempts = {
            **(output.attempts or {}),
            "tool_loop": tool_loop,
            "switched_to_fixed": loop.stop_reason,
        }
        return output
