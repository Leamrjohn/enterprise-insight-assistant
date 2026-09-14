"""Model-backed semantic checks; they never grant permissions or execute SQL."""

from __future__ import annotations

import json
from time import sleep
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import RetryableModelError, StructuredOutputError
from app.core.gateway.base import ModelGateway
from app.core.gateway.factory import get_model_gateway
from app.modules.analysis.planner_decision import PlannerDecision
from app.modules.reporting.semantic_review import EvidenceSemanticReview, SQLSemanticReview
from app.modules.analysis.sql_candidate import SQLCandidate
from app.modules.analysis.snapshot_catalog import SnapshotCatalog


def _catalog_payload(catalog: SnapshotCatalog | None) -> dict[str, Any]:
    if catalog is None:
        return {"tables": {}, "joins": []}
    return {
        "tables": {
            table: sorted(columns) for table, columns in sorted(catalog.tables.items())
        },
        "joins": [list(join) for join in sorted(catalog.joins)],
    }


class SemanticReviewService:
    """Use a model as a semantic critic over already-scoped inputs."""

    def __init__(
        self,
        gateway: ModelGateway | None = None,
        *,
        sleeper=sleep,
    ) -> None:
        self._gateway = gateway or get_model_gateway()
        self._sleeper = sleeper
        self.model_attempts = 0

    def review_plan(
        self,
        *,
        question: str,
        proposed_plan: dict[str, Any],
        catalog: SnapshotCatalog | None,
    ) -> PlannerDecision:
        system_prompt = (
            "你是企业经营助手的 Planner 语义复核器。只返回一个完整的 "
            "PlannerDecision JSON，不回答用户问题。复核初始计划是否与用户问题、"
            "当前公司已授权范围和契约快照一致。若指标或关键条件不能由快照支持，"
            "选择 needs_clarification；若明确要求其他公司、未授权资料、系统内部数据、"
            "写入或危险行为，选择 refuse。不得因为缺少时间而忽略跨公司或越权意图。"
            "scope_exit 不得实际完成翻译、写诗、推荐等无关任务。"
            "action 只能是 analyze、direct_response、scope_exit、needs_clarification、refuse；"
            "若初始计划正确，必须原样保留它的 action 和其他字段，不能使用 proceed、accept、keep 等词。"
            "必须只输出以下八字段 JSON："
            '{"action":"...","route":null,"reason":"...",'
            '"clarification_question":null,"response_message":null,'
            '"resolved_question":null,"clarification":null,"intent":null}。'
        )
        payload = {
            "question": question,
            "proposed_plan": proposed_plan,
            "current_scope": "仅当前登录公司的已授权数据源和文档",
            "schema_snapshot": _catalog_payload(catalog),
        }
        raw_output = self._chat(system_prompt=system_prompt, payload=payload)
        preserved_plan = self._preserved_plan_from_review(raw_output, proposed_plan)
        if preserved_plan is not None:
            return preserved_plan
        return self._parse_with_repair(
            PlannerDecision,
            raw_output,
            "Planner 语义复核结果不符合 JSON 契约",
            system_prompt,
            payload,
        )

    @staticmethod
    def _preserved_plan_from_review(
        raw_output: str,
        proposed_plan: dict[str, Any],
    ) -> PlannerDecision | None:
        """Accept common critic vocabulary as an explicit keep-plan decision."""
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError:
            return None
        action = payload.get("action") if isinstance(payload, dict) else None
        if isinstance(action, str) and action.lower() in {"accept", "keep", "proceed"}:
            return PlannerDecision.model_validate(proposed_plan)
        return None

    def review_sql(
        self,
        *,
        question: str,
        plan: dict[str, Any],
        candidate: SQLCandidate,
        catalog: SnapshotCatalog | None,
    ) -> SQLSemanticReview:
        system_prompt = (
            "你是受控 SQL 的执行前语义复核器。只返回 JSON。判断候选 SQL 是否真正"
            "回答用户问题和 Planner 计划。你不能授权表、字段、关联或权限；这些由后续"
            "SQLTool 决定。若快照缺少所需指标、枚举含义、比较期或关键条件，返回"
            "insufficient_schema，绝不允许用无关表或近似指标替代。若快照足够但 SQL "
            "遗漏可修复条件，返回 repair；只有关键业务条件、指标与范围都被表达时返回 execute。"
            "必须只输出 JSON："
            '{"decision":"execute|repair|insufficient_schema","reason":"...",'
            '"missing_requirements":["..."]}。'
        )
        payload = {
            "question": question,
            "plan": plan,
            "candidate": candidate.model_dump(),
            "schema_snapshot": _catalog_payload(catalog),
        }
        raw_output = self._chat(system_prompt=system_prompt, payload=payload)
        return self._parse_with_repair(
            SQLSemanticReview,
            raw_output,
            "SQL 语义复核结果不符合 JSON 契约",
            system_prompt,
            payload,
        )

    def review_evidence(
        self,
        *,
        question: str,
        plan: dict[str, Any],
        data_result: dict[str, Any],
        knowledge_result: dict[str, Any],
        report: dict[str, Any],
    ) -> EvidenceSemanticReview:
        system_prompt = (
            "你是企业经营报告的证据语义复核器。只返回 JSON，不生成新事实、数字、"
            "引用或建议。判断现有数据和文档证据是否支持回答原问题：supported 表示"
            "支持，partial 表示只支持部分事实，unsupported 表示不能回答核心问题。"
            "当数据只是无关记录、缺少关键筛选/比较条件，或原因没有文档引用时，不能"
            "判为 supported。"
            "必须只输出 JSON："
            '{"verdict":"supported|partial|unsupported","reason":"...",'
            '"limitations":["..."]}。'
        )
        payload = {
            "question": question,
            "plan": plan,
            "data_result": data_result,
            "knowledge_result": knowledge_result,
            "deterministic_report": report,
        }
        raw_output = self._chat(system_prompt=system_prompt, payload=payload)
        return self._parse_with_repair(
            EvidenceSemanticReview,
            raw_output,
            "证据语义复核结果不符合 JSON 契约",
            system_prompt,
            payload,
        )

    def _parse_with_repair(
        self,
        model,
        raw_output: str,
        error_message: str,
        system_prompt: str,
        payload: dict[str, Any],
    ):
        try:
            return model.model_validate_json(raw_output)
        except ValidationError:
            repaired_output = self._chat(
                system_prompt=(
                    f"{system_prompt} 上一次输出不符合 JSON 契约。"
                    "现在只能输出一个完整 JSON 对象，不要解释或 Markdown。"
                ),
                payload=payload,
            )
            try:
                return model.model_validate_json(repaired_output)
            except ValidationError as error:
                raise StructuredOutputError(error_message) from error

    def _chat(self, *, system_prompt: str, payload: dict[str, Any]) -> str:
        for attempt_index in range(2):
            self.model_attempts += 1
            try:
                return self._gateway.chat(
                    prompt=json.dumps(payload, ensure_ascii=False),
                    system_prompt=system_prompt,
                    json_mode=True,
                )
            except RetryableModelError:
                if attempt_index == 1:
                    raise
                self._sleeper(1.0)
        raise RuntimeError("语义复核调用未返回结果")
