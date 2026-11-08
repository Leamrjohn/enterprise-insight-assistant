"""Pick the part of a schema snapshot worth showing the model for one question.

This narrows what the prompt shows and nothing else: the SQL validator always
checks against the full snapshot, so a table left out here is never a permission
decision.  When unsure, show everything; a missing table costs far more than a
few hundred tokens.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog

# Business words that point at a table.  A table not listed here is only shown
# when the question names it, or when nothing matched at all.
TABLE_TERMS: dict[str, tuple[str, ...]] = {
    "sales_orders": (
        "订单",
        "销售额",
        "销售",
        "下单",
        "交付",
        "收入",
        "营收",
        "毛利",
        "折扣",
    ),
    "sales_order_items": ("毛利", "明细", "单价", "销量", "折扣", "成本"),
    "customers": (
        "客户",
        "区域",
        "区",
        "华东",
        "华南",
        "华北",
        "华中",
        "西部",
        "行业",
        "合同",
        "信用",
    ),
    "regions": ("区域", "大区"),
    "employees": ("销售代表", "员工", "经理", "负责人", "人员", "入职"),
    "products": ("产品", "sku", "物料", "品类"),
    "product_categories": ("品类",),
    "suppliers": ("供应商",),
    "purchase_orders": ("采购",),
    "purchase_order_items": ("采购",),
    "invoices": ("发票", "应收", "账龄", "回款", "逾期", "开票"),
    "payments": ("回款", "付款", "收款"),
    "service_tickets": ("客诉", "工单", "售后", "投诉"),
    "returns": ("退货", "退款"),
    "shipments": ("发货", "物流", "配送", "送达", "运输"),
    "inventory_movements": ("库存", "入库", "出库", "仓库"),
    "expense_entries": ("费用", "支出", "差旅", "报销"),
    "monthly_budgets": ("预算", "目标"),
    "cost_centers": ("成本中心", "部门"),
    "crm_notes": ("跟进", "拜访", "crm"),
}


def _join_neighbours(catalog: SnapshotCatalog) -> dict[str, set[str]]:
    neighbours: dict[str, set[str]] = {}
    for left, _, right, _ in catalog.joins:
        neighbours.setdefault(left, set()).add(right)
        neighbours.setdefault(right, set()).add(left)
    return neighbours


def _path_between(
    start: str, targets: set[str], neighbours: dict[str, set[str]]
) -> list[str]:
    """Shortest join path from start to any target, excluding both ends."""
    previous: dict[str, str] = {}
    queue = deque([start])
    seen = {start}
    while queue:
        table = queue.popleft()
        if table in targets and table != start:
            path = []
            while table != start:
                table = previous[table]
                if table != start:
                    path.append(table)
            return path
        for neighbour in sorted(neighbours.get(table, ())):
            if neighbour not in seen:
                seen.add(neighbour)
                previous[neighbour] = table
                queue.append(neighbour)
    return []


def select_tables(catalog: SnapshotCatalog, texts: Iterable[str]) -> set[str]:
    """Tables the question points at, plus those needed to join them; empty if unsure."""
    text = " ".join(texts).lower()
    selected = {
        table
        for table in catalog.tables
        if table.lower() in text
        or any(term in text for term in TABLE_TERMS.get(table, ()))
    }
    if not selected:
        return set()
    neighbours = _join_neighbours(catalog)
    for table in sorted(selected):
        selected |= set(_path_between(table, selected - {table}, neighbours))
    return selected


def narrow_catalog(
    catalog: SnapshotCatalog, tables: set[str]
) -> SnapshotCatalog | None:
    """The catalog limited to these tables; None when that would not narrow it."""
    kept = tables & set(catalog.tables)
    if not kept or kept == set(catalog.tables):
        return None
    return SnapshotCatalog(
        tables={table: catalog.tables[table] for table in kept},
        joins=frozenset(
            join for join in catalog.joins if join[0] in kept and join[2] in kept
        ),
    )
