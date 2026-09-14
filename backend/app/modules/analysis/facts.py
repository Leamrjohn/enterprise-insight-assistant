"""Deterministically derive facts from controlled data evidence only."""

from app.modules.reporting.schemas import ConfirmedFact, DataEvidence


_COLUMN_DISPLAY_NAMES = {
    "order_count": "订单数量",
    "total_orders": "订单数量",
    "total_sales": "销售额",
    "sales_amount": "销售额",
    "revenue": "销售额",
    "total_amount": "订单金额",
    "average_order_value": "平均订单金额",
    "avg_order_value": "平均订单金额",
    "region_name": "区域",
    "region": "区域",
    "customer_name": "客户",
    "customer": "客户",
    "product_name": "产品",
    "product": "产品",
    "month": "月份",
    "order_date": "下单日期",
    "status": "订单状态",
}


def render_evidence_purpose(purpose: object) -> str:
    """Keep raw SQL and implementation names out of business-facing facts."""
    if not isinstance(purpose, str) or not purpose.strip():
        return "已授权经营数据"
    normalized = purpose.strip()
    lowered = normalized.lower()
    if any(
        token in lowered for token in ("select ", " from ", " join ", " where ", ";")
    ):
        return "已授权经营数据"
    if " 的 " in normalized and any(
        char.isascii() and char.isalpha() for char in normalized
    ):
        return "已授权经营数据"
    if "_" in normalized:
        return "已授权经营数据"
    return normalized


def render_data_fields(columns: list[str], row: list[object]) -> str:
    fields = []
    for column, value in zip(columns, row):
        normalized = str(column).strip().lower()
        label = _COLUMN_DISPLAY_NAMES.get(normalized)
        if label is None:
            label = (
                str(column)
                if any("\u4e00" <= char <= "\u9fff" for char in str(column))
                else "查询结果"
            )
        fields.append(f"{label}{'未返回' if value is None else f'为{value}'}")
    return "，".join(fields)


def build_data_evidence(data_result: dict) -> list[DataEvidence]:
    evidence_list: list[DataEvidence] = []
    for index, evidence in enumerate(data_result.get("evidence") or [], start=1):
        evidence_list.append(
            DataEvidence(
                evidence_id=f"data-{index}",
                purpose=evidence.get("purpose") or "受控经营数据查询",
                sql=evidence.get("sql"),
                columns=[str(column) for column in evidence.get("columns") or []],
                rows=[list(row) for row in evidence.get("rows") or []],
            )
        )
    return evidence_list


def build_confirmed_facts(data_evidence: list[DataEvidence]) -> list[ConfirmedFact]:
    """No LLM is involved: a fact is a bounded rendering of one result row."""
    facts: list[ConfirmedFact] = []
    for evidence in data_evidence:
        for row in evidence.rows[:5]:
            if not evidence.columns or len(row) != len(evidence.columns):
                continue
            facts.append(
                ConfirmedFact(
                    fact_id=f"fact-{len(facts) + 1}",
                    statement=(
                        f"{render_evidence_purpose(evidence.purpose)}："
                        f"{render_data_fields(evidence.columns, row)}。"
                    ),
                    data_evidence_ids=[evidence.evidence_id],
                )
            )
    return facts
