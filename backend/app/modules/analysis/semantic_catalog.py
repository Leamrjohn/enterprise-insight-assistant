from dataclasses import dataclass


@dataclass(frozen=True)
class TableDefinition:
    description: str
    columns: frozenset[str]


@dataclass(frozen=True)
class JoinDefinition:
    left_table: str
    left_column: str
    right_table: str
    right_column: str


BUSINESS_TABLES = {
    "customers": TableDefinition(
        description="客户主数据，用于区域、行业、等级和合同到期分析。",
        columns=frozenset(
            {
                "id",
                "customer_code",
                "name",
                "region_code",
                "industry",
                "tier",
                "contract_end_date",
                "status",
            }
        ),
    ),
    "sales_orders": TableDefinition(
        description=(
            "销售订单事实表。销售额使用 total_amount，"
            "只统计 status = 'delivered' 的订单。"
        ),
        columns=frozenset(
            {
                "id",
                "order_no",
                "customer_id",
                "order_date",
                "status",
                "subtotal",
                "discount_amount",
                "total_amount",
            }
        ),
    ),
    "sales_order_items": TableDefinition(
        description="销售订单明细。毛利使用 line_amount - unit_cost * quantity。",
        columns=frozenset(
            {
                "id",
                "order_id",
                "product_id",
                "quantity",
                "unit_price",
                "unit_cost",
                "discount_rate",
                "line_amount",
            }
        ),
    ),
    "products": TableDefinition(
        description="产品主数据，用于 SKU、产品名称、品类和供应商分析。",
        columns=frozenset(
            {
                "id",
                "sku",
                "name",
                "category_id",
                "supplier_id",
                "list_price",
                "standard_cost",
                "active",
            }
        ),
    ),
    "product_categories": TableDefinition(
        description="产品品类维度表。",
        columns=frozenset({"id", "name"}),
    ),
    "service_tickets": TableDefinition(
        description="售后工单，用于客诉数量、类别、严重度和处理时长分析。",
        columns=frozenset(
            {
                "id",
                "ticket_no",
                "customer_id",
                "order_id",
                "product_id",
                "opened_date",
                "category",
                "severity",
                "status",
                "resolution_days",
            }
        ),
    ),
    "invoices": TableDefinition(
        description="应收发票，用于发票金额、到期日和应收账龄分析。",
        columns=frozenset(
            {
                "id",
                "invoice_no",
                "order_id",
                "invoice_date",
                "due_date",
                "invoice_amount",
                "status",
            }
        ),
    ),
    "payments": TableDefinition(
        description="回款记录，用于已回款、未回款和回款时效分析。",
        columns=frozenset(
            {
                "id",
                "payment_no",
                "invoice_id",
                "payment_date",
                "amount",
                "method",
            }
        ),
    ),
}


BUSINESS_JOINS = frozenset(
    {
        JoinDefinition("sales_orders", "customer_id", "customers", "id"),
        JoinDefinition("sales_order_items", "order_id", "sales_orders", "id"),
        JoinDefinition("sales_order_items", "product_id", "products", "id"),
        JoinDefinition("products", "category_id", "product_categories", "id"),
        JoinDefinition("service_tickets", "customer_id", "customers", "id"),
        JoinDefinition("service_tickets", "order_id", "sales_orders", "id"),
        JoinDefinition("service_tickets", "product_id", "products", "id"),
        JoinDefinition("invoices", "order_id", "sales_orders", "id"),
        JoinDefinition("payments", "invoice_id", "invoices", "id"),
    }
)


METRIC_DEFINITIONS = {
    "revenue": (
        "销售额 = SUM(sales_orders.total_amount)，"
        "且 sales_orders.status = 'delivered'。"
    ),
    "gross_profit": (
        "毛利 = SUM(sales_order_items.line_amount "
        "- sales_order_items.unit_cost * sales_order_items.quantity)。"
    ),
    "open_receivable": ("未回款余额 = 发票金额减去该发票已关联的回款金额。"),
    "ticket_count": "客诉数量 = COUNT(service_tickets.id)。",
}
FILTER_VALUE_DEFINITIONS = {
    "customers.region_code": {
        "EAST": "华东",
        "NORTH": "华北",
        "SOUTH": "华南",
        "WEST": "西部",
    },
    "customers.tier": {
        "key": "重点客户",
        "standard": "标准客户",
        "strategic": "战略客户",
    },
    "sales_orders.status": {
        "delivered": "已交付订单；销售额指标必须使用该状态。",
    },
    "service_tickets.category": {
        "产品质量": "产品质量类售后工单。",
    },
    "service_tickets.severity": {
        "high": "高严重度",
        "medium": "中严重度",
    },
    "invoices.status": {
        "open": "未结清发票。",
    },
}


def is_allowed_table(table: str) -> bool:
    return table in BUSINESS_TABLES


def allowed_columns(table: str) -> frozenset[str]:
    definition = BUSINESS_TABLES.get(table)
    return definition.columns if definition else frozenset()


def is_allowed_join(
    left_table: str,
    left_column: str,
    right_table: str,
    right_column: str,
) -> bool:
    requested = JoinDefinition(
        left_table,
        left_column,
        right_table,
        right_column,
    )
    reversed_requested = JoinDefinition(
        right_table,
        right_column,
        left_table,
        left_column,
    )
    return requested in BUSINESS_JOINS or reversed_requested in BUSINESS_JOINS
