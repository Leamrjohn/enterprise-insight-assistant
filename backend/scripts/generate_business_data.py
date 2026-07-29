"""Seed a reproducible synthetic B2B industrial-distribution dataset.

This script only manages tables in the dedicated ``business_data`` database.
It is deliberately deterministic: the same seed produces the same business
events, so the Agent evaluation set has a stable ground truth.
"""

from __future__ import annotations

import os
import random
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import psycopg


SEED = 20260718
RNG = random.Random(SEED)
PUBLIC_TABLES = (
    "payments, returns, service_tickets, shipments, inventory_movements, "
    "purchase_order_items, purchase_orders, sales_order_items, invoices, "
    "sales_orders, expense_entries, monthly_budgets, crm_notes, "
    "business_documents, products, product_categories, suppliers, customers, "
    "employees, cost_centers, regions"
)
CORPUS_VERSION = "1.0"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = WORKSPACE_ROOT / "docs" / "business_knowledge_base"


def currency(value: Decimal | int | float | None) -> str:
    """Render database values consistently in generated Chinese documents."""
    return f"¥{Decimal(value or 0):,.2f}"


def write_artifact(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def money(value: Decimal | float) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_starts() -> list[date]:
    return [date(year, month, 1) for year in (2024, 2025) for month in range(1, 13)]


def db_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("BUSINESS_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("BUSINESS_DB_PORT", "5434")),
        user=os.getenv("BUSINESS_DB_USER", "business_app"),
        password=os.getenv("BUSINESS_DB_PASSWORD", "business_password"),
        dbname=os.getenv("BUSINESS_DB_NAME", "business_data"),
    )


def recreate_schema(cur: psycopg.Cursor) -> None:
    cur.execute(f"DROP TABLE IF EXISTS {PUBLIC_TABLES} CASCADE")
    cur.execute("CREATE SCHEMA IF NOT EXISTS evaluation")
    cur.execute("DROP TABLE IF EXISTS evaluation.scenario_truth")
    cur.execute(
        """
        CREATE TABLE regions (code TEXT PRIMARY KEY, name TEXT NOT NULL, manager_name TEXT NOT NULL);
        CREATE TABLE cost_centers (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, department TEXT NOT NULL);
        CREATE TABLE employees (id INTEGER PRIMARY KEY, employee_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, department TEXT NOT NULL, region_code TEXT REFERENCES regions(code), cost_center_id INTEGER REFERENCES cost_centers(id), hire_date DATE NOT NULL, active BOOLEAN NOT NULL);
        CREATE TABLE customers (id INTEGER PRIMARY KEY, customer_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, region_code TEXT REFERENCES regions(code), industry TEXT NOT NULL, tier TEXT NOT NULL CHECK (tier IN ('strategic','key','standard')), account_manager_id INTEGER REFERENCES employees(id), credit_limit NUMERIC(14,2) NOT NULL, contract_end_date DATE, status TEXT NOT NULL);
        CREATE TABLE suppliers (id INTEGER PRIMARY KEY, supplier_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, region TEXT NOT NULL, payment_terms_days INTEGER NOT NULL, quality_rating NUMERIC(3,2) NOT NULL);
        CREATE TABLE product_categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE products (id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category_id INTEGER REFERENCES product_categories(id), supplier_id INTEGER REFERENCES suppliers(id), list_price NUMERIC(12,2) NOT NULL, standard_cost NUMERIC(12,2) NOT NULL, reorder_point INTEGER NOT NULL, active BOOLEAN NOT NULL);
        CREATE TABLE sales_orders (id INTEGER PRIMARY KEY, order_no TEXT UNIQUE NOT NULL, customer_id INTEGER REFERENCES customers(id), sales_rep_id INTEGER REFERENCES employees(id), order_date DATE NOT NULL, status TEXT NOT NULL, subtotal NUMERIC(14,2) NOT NULL, discount_amount NUMERIC(14,2) NOT NULL, total_amount NUMERIC(14,2) NOT NULL);
        CREATE TABLE sales_order_items (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES sales_orders(id), product_id INTEGER REFERENCES products(id), quantity INTEGER NOT NULL, unit_price NUMERIC(12,2) NOT NULL, unit_cost NUMERIC(12,2) NOT NULL, discount_rate NUMERIC(5,4) NOT NULL, line_amount NUMERIC(14,2) NOT NULL);
        CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT UNIQUE NOT NULL, order_id INTEGER UNIQUE REFERENCES sales_orders(id), invoice_date DATE NOT NULL, due_date DATE NOT NULL, invoice_amount NUMERIC(14,2) NOT NULL, status TEXT NOT NULL);
        CREATE TABLE payments (id INTEGER PRIMARY KEY, payment_no TEXT UNIQUE NOT NULL, invoice_id INTEGER REFERENCES invoices(id), payment_date DATE NOT NULL, amount NUMERIC(14,2) NOT NULL, method TEXT NOT NULL);
        CREATE TABLE shipments (id INTEGER PRIMARY KEY, shipment_no TEXT UNIQUE NOT NULL, order_id INTEGER UNIQUE REFERENCES sales_orders(id), warehouse_code TEXT NOT NULL, shipped_date DATE NOT NULL, delivered_date DATE, status TEXT NOT NULL, logistics_provider TEXT NOT NULL);
        CREATE TABLE purchase_orders (id INTEGER PRIMARY KEY, po_no TEXT UNIQUE NOT NULL, supplier_id INTEGER REFERENCES suppliers(id), order_date DATE NOT NULL, expected_date DATE NOT NULL, received_date DATE, status TEXT NOT NULL, total_cost NUMERIC(14,2) NOT NULL);
        CREATE TABLE purchase_order_items (id INTEGER PRIMARY KEY, purchase_order_id INTEGER REFERENCES purchase_orders(id), product_id INTEGER REFERENCES products(id), quantity INTEGER NOT NULL, unit_cost NUMERIC(12,2) NOT NULL, line_cost NUMERIC(14,2) NOT NULL);
        CREATE TABLE inventory_movements (id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), movement_date DATE NOT NULL, movement_type TEXT NOT NULL, quantity INTEGER NOT NULL, reference_type TEXT NOT NULL, reference_id INTEGER NOT NULL, warehouse_code TEXT NOT NULL);
        CREATE TABLE service_tickets (id INTEGER PRIMARY KEY, ticket_no TEXT UNIQUE NOT NULL, customer_id INTEGER REFERENCES customers(id), order_id INTEGER REFERENCES sales_orders(id), product_id INTEGER REFERENCES products(id), opened_date DATE NOT NULL, category TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL, resolution_days INTEGER);
        CREATE TABLE returns (id INTEGER PRIMARY KEY, return_no TEXT UNIQUE NOT NULL, order_item_id INTEGER REFERENCES sales_order_items(id), return_date DATE NOT NULL, quantity INTEGER NOT NULL, reason TEXT NOT NULL, refund_amount NUMERIC(14,2) NOT NULL, status TEXT NOT NULL);
        CREATE TABLE expense_entries (id INTEGER PRIMARY KEY, expense_date DATE NOT NULL, cost_center_id INTEGER REFERENCES cost_centers(id), category TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, vendor_name TEXT NOT NULL, description TEXT NOT NULL);
        CREATE TABLE monthly_budgets (id INTEGER PRIMARY KEY, month DATE NOT NULL, cost_center_id INTEGER REFERENCES cost_centers(id), revenue_target NUMERIC(14,2), expense_budget NUMERIC(14,2) NOT NULL, UNIQUE(month, cost_center_id));
        CREATE TABLE crm_notes (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), employee_id INTEGER REFERENCES employees(id), note_date DATE NOT NULL, note_type TEXT NOT NULL, content TEXT NOT NULL);
        CREATE TABLE business_documents (id INTEGER PRIMARY KEY, document_code TEXT UNIQUE NOT NULL, document_type TEXT NOT NULL, title TEXT NOT NULL, effective_date DATE NOT NULL, department TEXT NOT NULL, related_customer_id INTEGER REFERENCES customers(id), related_supplier_id INTEGER REFERENCES suppliers(id), related_product_id INTEGER REFERENCES products(id), content TEXT NOT NULL, access_level TEXT NOT NULL);
        CREATE TABLE evaluation.scenario_truth (scenario_code TEXT PRIMARY KEY, question TEXT NOT NULL, factual_cause TEXT NOT NULL, expected_data_signals TEXT NOT NULL, expected_document_codes TEXT NOT NULL, conclusion_policy TEXT NOT NULL);
        """
    )


def seed_dimensions(
    cur: psycopg.Cursor,
) -> tuple[list[tuple], list[tuple], list[tuple], list[tuple]]:
    regions = [
        ("EAST", "华东", "周晓岚"),
        ("SOUTH", "华南", "陈凯"),
        ("NORTH", "华北", "李文博"),
        ("WEST", "西部", "王宁"),
    ]
    centers = [
        (1, "CC-SALES", "销售中心", "销售"),
        (2, "CC-OPS", "供应链与运营", "运营"),
        (3, "CC-CS", "客户成功", "客户服务"),
        (4, "CC-FIN", "财务中心", "财务"),
        (5, "CC-MKT", "市场部", "市场"),
    ]
    cur.executemany("INSERT INTO regions VALUES (%s,%s,%s)", regions)
    cur.executemany("INSERT INTO cost_centers VALUES (%s,%s,%s,%s)", centers)
    employees = []
    names = [
        "林涛",
        "沈悦",
        "顾晨",
        "韩雪",
        "贺阳",
        "孟琳",
        "罗嘉",
        "高宇",
        "苏然",
        "叶青",
        "许峰",
        "唐蕾",
        "郭航",
        "莫言",
        "杜鹏",
        "方敏",
        "乔安",
        "程皓",
        "魏然",
        "宋佳",
        "何晨",
        "任静",
        "蒋涛",
        "陆颖",
        "白岩",
        "姜雪",
        "卓航",
        "于敏",
        "彭博",
        "袁静",
        "冯凯",
        "吴丹",
    ]
    for idx, name in enumerate(names, 1):
        dept, center = (
            ("销售", 1)
            if idx <= 16
            else (
                ("运营", 2)
                if idx <= 22
                else (("客户服务", 3) if idx <= 27 else ("财务", 4))
            )
        )
        region = regions[(idx - 1) % len(regions)][0] if dept == "销售" else None
        employees.append(
            (
                idx,
                f"EMP-{idx:03d}",
                name,
                dept,
                region,
                center,
                date(2020 + idx % 4, 1 + idx % 12, 1),
                True,
            )
        )
    cur.executemany("INSERT INTO employees VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", employees)
    categories = [
        (1, "工业自动化"),
        (2, "传动控制"),
        (3, "流体系统"),
        (4, "检测仪表"),
        (5, "安全防护"),
    ]
    cur.executemany("INSERT INTO product_categories VALUES (%s,%s)", categories)
    suppliers = []
    supplier_regions = ["苏州", "宁波", "深圳", "天津", "成都"]
    for idx in range(1, 25):
        category = categories[(idx - 1) % len(categories)][1]
        suppliers.append(
            (
                idx,
                f"SUP-{idx:03d}",
                f"{supplier_regions[idx % 5]}{category}供应有限公司",
                category,
                supplier_regions[idx % 5],
                30 if idx % 3 else 45,
                Decimal("4.2") - Decimal(idx % 4) / 10,
            )
        )
    cur.executemany("INSERT INTO suppliers VALUES (%s,%s,%s,%s,%s,%s,%s)", suppliers)
    products = []
    for idx in range(1, 121):
        category_id = (idx - 1) % 5 + 1
        base_cost = Decimal(500 + (idx % 20) * 180 + category_id * 220)
        products.append(
            (
                idx,
                f"SKU-{category_id}-{idx:04d}",
                f"{categories[category_id - 1][1]}组件 {idx:03d}",
                category_id,
                (idx - 1) % 24 + 1,
                money(base_cost * Decimal("1.38")),
                base_cost,
                20 + idx % 35,
                True,
            )
        )
    cur.executemany(
        "INSERT INTO products VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", products
    )
    customers = []
    industries = [
        "装备制造",
        "汽车零部件",
        "新能源",
        "医疗器械",
        "物流自动化",
        "食品加工",
    ]
    region_prefix = {"EAST": "华东", "SOUTH": "华南", "NORTH": "华北", "WEST": "西部"}
    for idx in range(1, 321):
        region = regions[(idx - 1) % 4][0]
        tier = "strategic" if idx <= 12 else ("key" if idx <= 72 else "standard")
        name = (
            "华东精密制造有限公司"
            if idx == 1
            else f"{region_prefix[region]}{industries[idx % len(industries)]}客户{idx:03d}"
        )
        customers.append(
            (
                idx,
                f"CUST-{idx:04d}",
                name,
                region,
                industries[idx % len(industries)],
                tier,
                (idx - 1) % 16 + 1,
                Decimal("5000000")
                if tier == "strategic"
                else (Decimal("2000000") if tier == "key" else Decimal("500000")),
                date(2025, 7, 31) if idx == 1 else None,
                "active",
            )
        )
    cur.executemany(
        "INSERT INTO customers VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", customers
    )
    return employees, products, customers, suppliers


def seed_transactions(
    cur: psycopg.Cursor,
    employees: list[tuple],
    products: list[tuple],
    customers: list[tuple],
    suppliers: list[tuple],
) -> None:
    product_map = {row[0]: row for row in products}
    order_rows: list[tuple] = []
    item_rows: list[tuple] = []
    invoice_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    shipment_rows: list[tuple] = []
    movements: list[tuple] = []
    order_id = item_id = invoice_id = payment_id = shipment_id = movement_id = 0
    for month in month_starts():
        for customer in customers:
            customer_id, _, _, region, _, tier, rep_id, *_ = customer
            if customer_id == 1 and month >= date(2025, 8, 1):
                continue  # contract-expiry / competitor event is represented by dependent records below
            # A two-year B2B dataset needs enough repeated purchases for
            # month-over-month, customer, and product drill-downs to be useful.
            order_probability = {"strategic": 0.98, "key": 0.72, "standard": 0.33}[tier]
            if RNG.random() > order_probability:
                continue
            count = 2 if tier == "strategic" and RNG.random() < 0.55 else 1
            for _ in range(count):
                order_id += 1
                order_date = month + timedelta(days=RNG.randint(0, 25))
                chosen = RNG.sample(range(1, 121), RNG.randint(2, 4))
                subtotal = Decimal("0")
                discount = Decimal("0")
                lines = []
                for product_id in chosen:
                    item_id += 1
                    product = product_map[product_id]
                    qty = (
                        RNG.randint(2, 14) if tier != "standard" else RNG.randint(1, 6)
                    )
                    unit_price, unit_cost = Decimal(product[5]), Decimal(product[6])
                    # Supplier SUP-003 raises the purchase cost of transmission
                    # products in Q4.  The confirmed sales cost must reflect that
                    # event, otherwise a gross-margin query cannot verify it.
                    if month >= date(2025, 10, 1) and product[3] == 2:
                        unit_cost = money(unit_cost * Decimal("1.12"))
                    discount_rate = (
                        Decimal("0.03") if tier == "strategic" else Decimal("0.01")
                    )
                    if (
                        month >= date(2025, 10, 1)
                        and product[3] == 2
                        and region == "EAST"
                    ):
                        discount_rate += Decimal(
                            "0.05"
                        )  # competitive discount pressure
                    gross = unit_price * qty
                    line_amount = money(gross * (Decimal("1") - discount_rate))
                    subtotal += gross
                    discount += gross - line_amount
                    lines.append(
                        (
                            item_id,
                            order_id,
                            product_id,
                            qty,
                            unit_price,
                            unit_cost,
                            discount_rate,
                            line_amount,
                        )
                    )
                total = money(subtotal - discount)
                order_rows.append(
                    (
                        order_id,
                        f"SO-{order_date:%Y%m}-{order_id:05d}",
                        customer_id,
                        rep_id,
                        order_date,
                        "delivered",
                        money(subtotal),
                        money(discount),
                        total,
                    )
                )
                item_rows.extend(lines)
                invoice_id += 1
                invoice_date = order_date + timedelta(days=RNG.randint(1, 4))
                due_date = invoice_date + timedelta(days=30)
                invoice_rows.append(
                    (
                        invoice_id,
                        f"INV-{invoice_date:%Y%m}-{invoice_id:05d}",
                        order_id,
                        invoice_date,
                        due_date,
                        total,
                        "open",
                    )
                )
                shipment_id += 1
                shipment_rows.append(
                    (
                        shipment_id,
                        f"SHP-{order_date:%Y%m}-{shipment_id:05d}",
                        order_id,
                        "WH-EAST" if region == "EAST" else "WH-CENTRAL",
                        order_date + timedelta(days=1),
                        order_date + timedelta(days=RNG.randint(2, 7)),
                        "delivered",
                        RNG.choice(["顺达物流", "安捷供应链", "中联货运"]),
                    )
                )
                for line in lines:
                    movement_id += 1
                    movements.append(
                        (
                            movement_id,
                            line[2],
                            order_date,
                            "outbound",
                            -line[3],
                            "sales_order",
                            order_id,
                            "WH-EAST" if region == "EAST" else "WH-CENTRAL",
                        )
                    )
                paid_ratio = (
                    Decimal("1")
                    if RNG.random() < 0.82
                    else (Decimal("0.6") if RNG.random() < 0.7 else Decimal("0"))
                )
                if customer_id == 280 and month >= date(2025, 10, 1):
                    paid_ratio = Decimal("0")  # receivable-risk scenario
                if paid_ratio:
                    payment_id += 1
                    payment_rows.append(
                        (
                            payment_id,
                            f"PAY-{invoice_date:%Y%m}-{payment_id:05d}",
                            invoice_id,
                            invoice_date + timedelta(days=RNG.randint(5, 38)),
                            money(total * paid_ratio),
                            RNG.choice(["bank_transfer", "bank_acceptance"]),
                        )
                    )
    cur.executemany(
        "INSERT INTO sales_orders VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", order_rows
    )
    cur.executemany(
        "INSERT INTO sales_order_items VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", item_rows
    )
    cur.executemany("INSERT INTO invoices VALUES (%s,%s,%s,%s,%s,%s,%s)", invoice_rows)
    cur.executemany("INSERT INTO payments VALUES (%s,%s,%s,%s,%s,%s)", payment_rows)
    cur.executemany(
        "INSERT INTO shipments VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", shipment_rows
    )
    cur.executemany(
        "INSERT INTO inventory_movements VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", movements
    )
    seed_procurement_and_operations(cur, products, suppliers, item_rows, order_rows)


def seed_procurement_and_operations(
    cur: psycopg.Cursor,
    products: list[tuple],
    suppliers: list[tuple],
    item_rows: list[tuple],
    order_rows: list[tuple],
) -> None:
    po_rows: list[tuple] = []
    poi_rows: list[tuple] = []
    expenses: list[tuple] = []
    budgets: list[tuple] = []
    tickets: list[tuple] = []
    returns_rows: list[tuple] = []
    notes: list[tuple] = []
    docs: list[tuple] = []
    po_id = poi_id = expense_id = budget_id = ticket_id = return_id = doc_id = 0
    for month in month_starts():
        for center_id in range(1, 6):
            budget_id += 1
            budgets.append(
                (
                    budget_id,
                    month,
                    center_id,
                    Decimal("2800000") if center_id == 1 else None,
                    Decimal(180000 + center_id * 35000),
                )
            )
        for category, center, amount in [
            ("物流仓储", 2, 85000),
            ("销售差旅", 1, 42000),
            ("市场活动", 5, 60000),
            ("人力与行政", 4, 130000),
        ]:
            expense_id += 1
            variance = Decimal(RNG.randint(-12000, 18000))
            expenses.append(
                (
                    expense_id,
                    month + timedelta(days=RNG.randint(1, 26)),
                    center,
                    category,
                    money(amount + variance),
                    f"{category}服务商",
                    f"{month:%Y-%m}常规{category}支出",
                )
            )
        for supplier in suppliers:
            if supplier[0] % 4:
                continue
            po_id += 1
            picked = [p for p in products if p[4] == supplier[0]][:3]
            total = Decimal("0")
            for product in picked:
                poi_id += 1
                qty = RNG.randint(35, 100)
                unit_cost = Decimal(product[6])
                if supplier[0] == 3 and month >= date(2025, 10, 1):
                    unit_cost = money(unit_cost * Decimal("1.12"))
                line = money(unit_cost * qty)
                total += line
                poi_rows.append((poi_id, po_id, product[0], qty, unit_cost, line))
            po_rows.append(
                (
                    po_id,
                    f"PO-{month:%Y%m}-{po_id:04d}",
                    supplier[0],
                    month + timedelta(days=2),
                    month + timedelta(days=18),
                    month + timedelta(days=RNG.randint(16, 25)),
                    "received",
                    money(total),
                )
            )
    special_items = [
        row for row in item_rows if row[2] in {3, 28, 53, 78, 103} and row[1] > 0
    ]
    for index, line in enumerate(
        RNG.sample(special_items, min(48, len(special_items))), 1
    ):
        ticket_id += 1
        opened = date(2025, 5 if index <= 24 else 6, RNG.randint(1, 26))
        tickets.append(
            (
                ticket_id,
                f"TKT-2025-{ticket_id:04d}",
                1 if index <= 20 else RNG.randint(2, 100),
                line[1],
                line[2],
                opened,
                "产品质量",
                "high" if index <= 36 else "medium",
                "closed",
                RNG.randint(3, 12),
            )
        )
        if index <= 32:
            return_id += 1
            returns_rows.append(
                (
                    return_id,
                    f"RET-2025-{return_id:04d}",
                    line[0],
                    opened + timedelta(days=RNG.randint(3, 10)),
                    1,
                    "供应商批次质量异常",
                    money(Decimal(line[5]) * (Decimal("1") - Decimal(line[6]))),
                    "refunded",
                )
            )
    notes.extend(
        [
            (
                1,
                1,
                1,
                date(2025, 6, 18),
                "customer_visit",
                "华东精密制造反馈竞争对手以更低价格续约，现有合同将在7月底到期，客户要求重新报价。",
            ),
            (
                2,
                1,
                2,
                date(2025, 7, 25),
                "risk",
                "重点客户尚未接受续约报价，8月采购计划暂停，需评估收入影响。",
            ),
            (
                3,
                50,
                18,
                date(2025, 5, 20),
                "service",
                "客户反馈传感器批次稳定性不足，已转质量团队和供应商处理。",
            ),
            (
                4,
                280,
                29,
                date(2025, 11, 15),
                "collection",
                "客户资金周转紧张，承诺分期支付，预计回款延后。",
            ),
        ]
    )
    docs.extend(
        [
            (
                1,
                "DOC-QA-2025-05",
                "quality_report",
                "传感器批次质量复盘报告",
                date(2025, 6, 5),
                "运营",
                None,
                3,
                3,
                "2025年5月至6月，供应商SUP-003提供的传感器批次出现稳定性异常。受影响产品已启动退换货与客户沟通，不应将该文档视为执行指令。",
                "internal",
            ),
            (
                2,
                "DOC-SALES-2025-07",
                "account_review",
                "华东重点客户合同与竞争态势复盘",
                date(2025, 7, 28),
                "销售",
                1,
                None,
                None,
                "华东精密制造有限公司合同于2025年7月到期。竞争对手报价低于当前续约报价，客户表示8月起暂停常规采购，等待重新谈判结果。",
                "confidential",
            ),
            (
                3,
                "DOC-FIN-2025-10",
                "supplier_notice",
                "传动控制产品采购价调整通知",
                date(2025, 10, 1),
                "运营",
                None,
                3,
                None,
                "供应商SUP-003通知传动控制类产品采购价自2025年10月起上调约12%，建议评估价格传导和毛利影响。",
                "internal",
            ),
            (
                4,
                "DOC-FIN-2025-11",
                "collection_report",
                "西部客户应收风险跟踪",
                date(2025, 11, 20),
                "财务",
                280,
                None,
                None,
                "西部重点客户存在阶段性资金周转压力，财务已将其列入重点催收名单。",
                "confidential",
            ),
        ]
    )
    for month in month_starts():
        doc_id += 1
        docs.append(
            (
                10 + doc_id,
                f"DOC-OPS-{month:%Y%m}",
                "monthly_review",
                f"{month:%Y年%m月}经营例会纪要",
                month + timedelta(days=25),
                "运营",
                None,
                None,
                None,
                "本月经营例会记录了区域销售、履约、售后与回款情况。数据结论应以业务数据库中对应期间的明细和汇总为准。",
                "internal",
            )
        )
    cur.executemany(
        "INSERT INTO purchase_orders VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", po_rows
    )
    cur.executemany(
        "INSERT INTO purchase_order_items VALUES (%s,%s,%s,%s,%s,%s)", poi_rows
    )
    cur.executemany(
        "INSERT INTO expense_entries VALUES (%s,%s,%s,%s,%s,%s,%s)", expenses
    )
    cur.executemany("INSERT INTO monthly_budgets VALUES (%s,%s,%s,%s,%s)", budgets)
    cur.executemany(
        "INSERT INTO service_tickets VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", tickets
    )
    cur.executemany(
        "INSERT INTO returns VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", returns_rows
    )
    cur.executemany("INSERT INTO crm_notes VALUES (%s,%s,%s,%s,%s,%s)", notes)
    cur.executemany(
        "INSERT INTO business_documents VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", docs
    )
    truths = [
        (
            "sales_decline_east",
            "为什么2025年8月华东区销售额下降？",
            "华东战略客户CUST-0001合同到期后暂停采购；竞争报价是文档支持的背景，不可仅凭相关性断言为唯一原因。",
            "区域月销售额下降；客户下钻显示CUST-0001销售额归零。",
            "DOC-SALES-2025-07",
            "可给出有证据的主要归因，并说明仍需人工确认续约结果。",
        ),
        (
            "quality_spike",
            "2025年6月产品质量投诉为什么上升？",
            "SUP-003传感器批次异常导致售后和退货集中增加。",
            "5-6月产品质量高严重度工单、退货和相关SKU异常。",
            "DOC-QA-2025-05",
            "可给出有证据的批次质量归因。",
        ),
        (
            "margin_pressure",
            "2025年第四季度传动控制产品毛利为什么下降？",
            "SUP-003采购涨价与华东竞争折扣共同压缩毛利。",
            "采购单价上涨、销售折扣扩大、毛利下降。",
            "DOC-FIN-2025-10",
            "应同时呈现两个因素，不能只归因于一个因素。",
        ),
        (
            "collection_risk",
            "西部区域回款风险是否上升？",
            "CUST-0280在2025年第四季度未按期付款。",
            "逾期发票与未回款余额增加。",
            "DOC-FIN-2025-11",
            "可给出风险提示，不能把未付款等同于坏账。",
        ),
        (
            "insufficient_evidence",
            "某新产品在2024年3月销量下降的业务原因是什么？",
            "没有与该问题对应的业务文档证据。",
            "可查询销量，但不存在可靠原因证据。",
            "",
            "必须拒绝给出确定原因，并说明缺少文档证据。",
        ),
    ]
    cur.executemany(
        "INSERT INTO evaluation.scenario_truth VALUES (%s,%s,%s,%s,%s,%s)", truths
    )


def create_indexes(cur: psycopg.Cursor) -> None:
    for statement in (
        "CREATE INDEX idx_orders_date_customer ON sales_orders(order_date, customer_id)",
        "CREATE INDEX idx_order_items_product ON sales_order_items(product_id)",
        "CREATE INDEX idx_invoices_due ON invoices(due_date)",
        "CREATE INDEX idx_tickets_date_product ON service_tickets(opened_date, product_id)",
        "CREATE INDEX idx_documents_effective ON business_documents(effective_date)",
    ):
        cur.execute(statement)


def fetch_one(cur: psycopg.Cursor, query: str, parameters: tuple = ()) -> tuple:
    cur.execute(query, parameters)
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("document corpus query unexpectedly returned no row")
    return row


def build_monthly_report(cur: psycopg.Cursor, month: date) -> str:
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    # Independent aggregate subqueries avoid multiplying values through
    # unrelated joins. The reports must be numerically exact, not illustrative.
    overview = fetch_one(
        cur,
        """
        SELECT
          (SELECT COUNT(*) FROM sales_orders WHERE order_date >= %s AND order_date < %s),
          (SELECT COALESCE(SUM(total_amount), 0) FROM sales_orders WHERE order_date >= %s AND order_date < %s),
          (SELECT COUNT(DISTINCT customer_id) FROM sales_orders WHERE order_date >= %s AND order_date < %s),
          (SELECT COALESCE(SUM(oi.line_amount), 0) FROM sales_order_items oi JOIN sales_orders o ON o.id=oi.order_id WHERE o.order_date >= %s AND o.order_date < %s),
          (SELECT COALESCE(SUM(oi.line_amount - oi.unit_cost * oi.quantity), 0) FROM sales_order_items oi JOIN sales_orders o ON o.id=oi.order_id WHERE o.order_date >= %s AND o.order_date < %s),
          (SELECT COALESCE(SUM(invoice_amount), 0) FROM invoices WHERE invoice_date >= %s AND invoice_date < %s),
          (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE payment_date >= %s AND payment_date < %s),
          (SELECT COUNT(*) FROM service_tickets WHERE opened_date >= %s AND opened_date < %s),
          (SELECT COUNT(*) FROM returns WHERE return_date >= %s AND return_date < %s),
          (SELECT COALESCE(SUM(refund_amount), 0) FROM returns WHERE return_date >= %s AND return_date < %s),
          (SELECT COALESCE(SUM(amount), 0) FROM expense_entries WHERE expense_date >= %s AND expense_date < %s),
          (SELECT COALESCE(SUM(expense_budget), 0) FROM monthly_budgets WHERE month=%s),
          (SELECT COUNT(*) FROM crm_notes WHERE note_date >= %s AND note_date < %s),
          (SELECT COALESCE(SUM(quantity), 0) FROM inventory_movements WHERE movement_date >= %s AND movement_date < %s)
        """,
        (month, next_month) * 11 + (month,) + (month, next_month) * 2,
    )
    regional_rows = cur.execute(
        """
        SELECT r.code, r.name, COUNT(o.id), COALESCE(SUM(o.total_amount), 0)
        FROM regions r LEFT JOIN customers c ON c.region_code=r.code
        LEFT JOIN sales_orders o ON o.customer_id=c.id AND o.order_date >= %s AND o.order_date < %s
        GROUP BY r.code, r.name ORDER BY r.code
        """,
        (month, next_month),
    ).fetchall()
    category_rows = cur.execute(
        """
        SELECT pc.name,
               COALESCE(SUM(oi.line_amount) FILTER (WHERE o.order_date >= %s AND o.order_date < %s), 0),
               COALESCE(SUM(oi.line_amount - oi.unit_cost * oi.quantity) FILTER (WHERE o.order_date >= %s AND o.order_date < %s), 0)
        FROM product_categories pc LEFT JOIN products p ON p.category_id=pc.id
        LEFT JOIN sales_order_items oi ON oi.product_id=p.id
        LEFT JOIN sales_orders o ON o.id=oi.order_id
        GROUP BY pc.name ORDER BY pc.name
        """,
        (month, next_month, month, next_month),
    ).fetchall()
    purchase_count, purchase_cost = fetch_one(
        cur,
        "SELECT COUNT(*), COALESCE(SUM(total_cost), 0) FROM purchase_orders WHERE order_date >= %s AND order_date < %s",
        (month, next_month),
    )
    shipment_count = fetch_one(
        cur,
        "SELECT COUNT(*) FROM shipments WHERE shipped_date >= %s AND shipped_date < %s",
        (month, next_month),
    )[0]
    region_table = "\n".join(
        f"| {code} / {name} | {orders} | {currency(revenue)} |"
        for code, name, orders, revenue in regional_rows
    )
    category_table = "\n".join(
        f"| {name} | {currency(revenue)} | {currency(gross_profit)} |"
        for name, revenue, gross_profit in category_rows
    )
    gross_margin = (
        Decimal(overview[4]) / Decimal(overview[3]) * 100 if overview[3] else 0
    )
    return f"""# {month:%Y年%m月}经营月度事实包

> 文档版本：{CORPUS_VERSION}；数据期间：{month.isoformat()} 至 {(next_month - timedelta(days=1)).isoformat()}；生成方式：固定 seed `{SEED}` 的业务库聚合。\n>
> 使用边界：本文件陈述可复算经营事实，不单独证明因果关系；原因判断必须另有授权业务资料支撑。

## 一、经营总览

- 已交付订单：{overview[0]} 笔；成交客户：{overview[2]} 家；销售额：{currency(overview[1])}。
- 销售明细收入：{currency(overview[3])}；按订单行成本计算的毛利：{currency(overview[4])}；毛利率：{gross_margin:.2f}%。
- 当月开票：{currency(overview[5])}；当月到账：{currency(overview[6])}。
- 采购订单：{purchase_count} 笔、采购金额：{currency(purchase_cost)}；已发运：{shipment_count} 单；库存变动数量合计：{overview[13]}。
- 服务工单：{overview[7]} 件；退货：{overview[8]} 笔、退款：{currency(overview[9])}。
- 费用：{currency(overview[10])}；费用预算：{currency(overview[11])}；CRM 记录：{overview[12]} 条。

## 二、区域销售

| 区域代码 / 名称 | 订单数 | 销售额 |
|---|---:|---:|
{region_table}

## 三、品类收入与毛利

| 产品类别 | 销售明细收入 | 毛利 |
|---|---:|---:|
{category_table}

## 四、数据口径与可追溯范围

- 销售额来自 `sales_orders.total_amount`；订单日期使用 `sales_orders.order_date`。
- 毛利来自 `sales_order_items.line_amount - unit_cost × quantity`；不能用本文件中的自然语言重新计算或覆盖数据库数字。
- 回款为当月 `payments.payment_date` 落账金额；它不等价于当月开票的全部回收，也不等价于坏账。
- 工单、退货、费用、预算、采购、库存和 CRM 指标分别来自其同名事实表，仅用于描述本月发生量。
"""


def build_reference_documents(
    cur: psycopg.Cursor,
) -> dict[str, tuple[str, list[str], str]]:
    master = fetch_one(
        cur,
        "SELECT COUNT(*), (SELECT COUNT(*) FROM employees), (SELECT COUNT(*) FROM products), (SELECT COUNT(*) FROM suppliers), (SELECT COUNT(*) FROM cost_centers) FROM customers",
    )
    regions = cur.execute(
        "SELECT r.code, r.name, r.manager_name, COUNT(c.id) FROM regions r LEFT JOIN customers c ON c.region_code=r.code GROUP BY r.code,r.name,r.manager_name ORDER BY r.code"
    ).fetchall()
    region_table = "\n".join(
        f"| {code} | {name} | {manager} | {count} |"
        for code, name, manager, count in regions
    )
    docs = {
        "reference/master_data_catalog.md": (
            f"""# 经营主数据目录

> 文档版本：{CORPUS_VERSION}；生成于业务固定 seed `{SEED}`。本文件是实体与口径索引，不包含任何评测答案。

## 覆盖范围

- 客户：{master[0]} 家；员工：{master[1]} 人；产品：{master[2]} 个；供应商：{master[3]} 家；成本中心：{master[4]} 个。
- 产品覆盖工业自动化、传动控制、流体系统、检测仪表和安全防护五类；客户按战略、重点、标准分层。

| 区域代码 | 区域名称 | 区域负责人 | 客户数 |
|---|---|---|---:|
{region_table}

## 关联规则

- 客户以 `customers.region_code` 归属区域，订单以 `sales_orders.customer_id` 关联客户。
- 产品以 `products.category_id` 关联品类、以 `products.supplier_id` 关联供应商；订单行与采购订单行均通过产品 ID 关联。
- 主数据说明业务对象的范围，不构成某一月份的经营结论。
""",
            [
                "regions",
                "customers",
                "employees",
                "products",
                "suppliers",
                "cost_centers",
                "product_categories",
            ],
            "reference",
        ),
        "reference/metric_dictionary.md": (
            """# 经营指标口径与使用限制

## 可确认的数值事实

| 指标 | 数据来源 | 计算方式 |
|---|---|---|
| 销售额 | `sales_orders` | 指定期间 `total_amount` 求和，且只统计已交付订单。 |
| 毛利 | `sales_order_items` | `line_amount - unit_cost × quantity` 求和。 |
| 应收余额 | `invoices`、`payments` | 发票金额减截至观察日的已收款。 |
| 逾期 | `invoices.due_date` | 到期日早于观察日且仍有未收余额。 |
| 客诉与退货 | `service_tickets`、`returns` | 按发生日期、类别、严重程度及退款金额汇总。 |
| 采购成本 | `purchase_orders`、`purchase_order_items` | 按采购下单日期及订单行成本汇总。 |

## 禁止的推断

- 订单下降本身不能证明唯一原因。
- 未回款只能证明回款风险或逾期，不能直接认定坏账。
- 同期发生的工单、退货和采购变化只能作为待核验信号，必须结合对应的授权文档形成假设。
""",
            [
                "sales_orders",
                "sales_order_items",
                "invoices",
                "payments",
                "service_tickets",
                "returns",
                "purchase_orders",
                "purchase_order_items",
            ],
            "reference",
        ),
    }
    return docs


def build_event_documents(cur: psycopg.Cursor) -> dict[str, tuple[str, list[str], str]]:
    july, august = fetch_one(
        cur,
        """
        SELECT
          COALESCE(SUM(total_amount) FILTER (WHERE order_date >= DATE '2025-07-01' AND order_date < DATE '2025-08-01'), 0),
          COALESCE(SUM(total_amount) FILTER (WHERE order_date >= DATE '2025-08-01' AND order_date < DATE '2025-09-01'), 0)
        FROM sales_orders o JOIN customers c ON c.id=o.customer_id WHERE c.region_code='EAST'
    """,
    )
    customer_july = fetch_one(
        cur,
        "SELECT COALESCE(SUM(total_amount),0) FROM sales_orders WHERE customer_id=1 AND order_date >= DATE '2025-07-01' AND order_date < DATE '2025-08-01'",
    )[0]
    tickets, high_tickets, returns, refunds = fetch_one(
        cur,
        """
        SELECT COUNT(*), COUNT(*) FILTER (WHERE severity='high'),
               (SELECT COUNT(*) FROM returns WHERE return_date >= DATE '2025-05-01' AND return_date < DATE '2025-07-01'),
               (SELECT COALESCE(SUM(refund_amount),0) FROM returns WHERE return_date >= DATE '2025-05-01' AND return_date < DATE '2025-07-01')
        FROM service_tickets WHERE opened_date >= DATE '2025-05-01' AND opened_date < DATE '2025-07-01'
    """,
    )
    sep_margin, oct_margin = fetch_one(
        cur,
        """
        SELECT
          COALESCE(SUM(oi.line_amount-oi.unit_cost*oi.quantity) FILTER (WHERE o.order_date >= DATE '2025-09-01' AND o.order_date < DATE '2025-10-01') / NULLIF(SUM(oi.line_amount) FILTER (WHERE o.order_date >= DATE '2025-09-01' AND o.order_date < DATE '2025-10-01'),0),0),
          COALESCE(SUM(oi.line_amount-oi.unit_cost*oi.quantity) FILTER (WHERE o.order_date >= DATE '2025-10-01' AND o.order_date < DATE '2025-11-01') / NULLIF(SUM(oi.line_amount) FILTER (WHERE o.order_date >= DATE '2025-10-01' AND o.order_date < DATE '2025-11-01'),0),0)
        FROM sales_order_items oi JOIN sales_orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id WHERE p.category_id=2
    """,
    )
    outstanding = fetch_one(
        cur,
        """
        SELECT COALESCE(SUM(i.invoice_amount-COALESCE(p.paid,0)),0) FROM invoices i
        JOIN sales_orders o ON o.id=i.order_id
        LEFT JOIN (SELECT invoice_id,SUM(amount) AS paid FROM payments WHERE payment_date <= DATE '2025-12-31' GROUP BY invoice_id) p ON p.invoice_id=i.id
        WHERE o.customer_id=280 AND i.due_date < DATE '2026-01-01'
    """,
    )[0]
    return {
        "events/2025-08-east-sales-review.md": (
            f"""# 华东区 2025 年 8 月销售变化复盘

## 数据事实

- 华东区销售额由 2025 年 7 月的 {currency(july)} 变为 8 月的 {currency(august)}。
- 客户 `CUST-0001`（华东精密制造有限公司）7 月销售额为 {currency(customer_july)}，8 月起没有新增订单。

## 已授权业务背景

该客户合同于 2025 年 7 月到期；CRM 与对应业务资料记录了竞争报价及客户暂停常规采购、等待重新谈判的状态。

## 结论边界

合同到期与暂停采购可作为对该客户销售归零的有证据解释；竞争报价是背景信号，不能仅凭同期性断言为华东全部销售下降的唯一原因。
""",
            ["sales_orders", "customers", "crm_notes", "business_documents"],
            "scenario",
        ),
        "events/2025-05-06-quality-review.md": (
            f"""# 2025 年 5–6 月传感器质量事件复盘

## 数据事实

- 该期间记录服务工单 {tickets} 件，其中高严重度 {high_tickets} 件。
- 同期发生退货 {returns} 笔，退款金额 {currency(refunds)}。

## 已授权业务背景

供应商 `SUP-003` 的传感器批次被记录为存在稳定性异常；受影响产品已启动退换货与客户沟通。

## 结论边界

工单和退货是可复算事实，供应商批次异常是文档支持的原因假设。该复盘不是对所有产品或所有客户的质量结论。
""",
            [
                "service_tickets",
                "returns",
                "sales_order_items",
                "products",
                "suppliers",
                "business_documents",
            ],
            "scenario",
        ),
        "events/2025-q4-transmission-margin-review.md": (
            f"""# 2025 年第四季度传动控制产品毛利压力复盘

## 数据事实

- 传动控制品类 2025 年 9 月毛利率为 {Decimal(sep_margin) * 100:.2f}%，10 月为 {Decimal(oct_margin) * 100:.2f}%。
- 采购与销售明细显示，2025 年 10 月起该品类的单位成本和华东竞争性折扣均发生变化。

## 已授权业务背景

供应商 `SUP-003` 通知传动控制类产品采购价自 2025 年 10 月起上调约 12%。

## 结论边界

采购成本上升与折扣扩大应同时作为毛利压力的候选因素；文档不支持只归因于其中任一因素。
""",
            [
                "sales_order_items",
                "sales_orders",
                "products",
                "purchase_order_items",
                "purchase_orders",
                "business_documents",
            ],
            "scenario",
        ),
        "events/2025-q4-west-receivable-risk.md": (
            f"""# 西部客户 CUST-0280 回款风险跟踪

## 数据事实

- 截至 2025-12-31，`CUST-0280` 的已到期未收余额为 {currency(outstanding)}。
- 其 2025 年 10 月开具的发票存在未按期付款记录。

## 已授权业务背景

CRM 和财务资料记录该客户存在阶段性资金周转压力，并已纳入重点催收。

## 结论边界

本报告支持“回款风险上升、需催收跟进”的判断；未付款和逾期不等于坏账，仍需按后续回款及信用政策评估。
""",
            ["customers", "invoices", "payments", "crm_notes", "business_documents"],
            "scenario",
        ),
    }


def generate_business_knowledge_base(cur: psycopg.Cursor) -> None:
    """Generate a complete, deterministic RAG corpus from business-data facts.

    The corpus intentionally excludes ``evaluation.scenario_truth``.  It can
    support retrieval tests, but cannot leak the answer key into retrieval.
    """
    artifacts: list[dict[str, object]] = []
    documents: dict[str, tuple[str, list[str], str]] = {}
    for month in month_starts():
        relative_path = f"monthly/{month:%Y-%m}.md"
        documents[relative_path] = (
            build_monthly_report(cur, month),
            [
                "sales_orders",
                "sales_order_items",
                "customers",
                "invoices",
                "payments",
                "purchase_orders",
                "purchase_order_items",
                "shipments",
                "inventory_movements",
                "service_tickets",
                "returns",
                "expense_entries",
                "monthly_budgets",
                "crm_notes",
                "product_categories",
            ],
            "monthly",
        )
    documents.update(build_reference_documents(cur))
    documents.update(build_event_documents(cur))

    for relative_path, (content, source_tables, kind) in sorted(documents.items()):
        sha256 = write_artifact(CORPUS_DIR / relative_path, content)
        artifacts.append(
            {
                "path": relative_path,
                "sha256": sha256,
                "kind": kind,
                "source_tables": source_tables,
            }
        )

    profiles = {
        "unit_minimal": ["reference/metric_dictionary.md"],
        "sales_decline": [
            "monthly/2025-07.md",
            "monthly/2025-08.md",
            "events/2025-08-east-sales-review.md",
        ],
        "quality_spike": [
            "monthly/2025-05.md",
            "monthly/2025-06.md",
            "events/2025-05-06-quality-review.md",
        ],
        "margin_pressure": [
            "monthly/2025-09.md",
            "monthly/2025-10.md",
            "events/2025-q4-transmission-margin-review.md",
        ],
        "receivable_risk": [
            "monthly/2025-10.md",
            "monthly/2025-11.md",
            "events/2025-q4-west-receivable-risk.md",
        ],
        "full_regression": [artifact["path"] for artifact in artifacts],
    }
    manifest = {
        "version": CORPUS_VERSION,
        "seed": SEED,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "test_profiles": profiles,
    }
    write_artifact(
        CORPUS_DIR / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    write_artifact(
        CORPUS_DIR / "README.md",
        """# 经营知识库生成语料

本目录由 `backend/scripts/generate_business_data.py` 从固定 seed 的业务数据库生成。不要手工修改 Markdown 或 `manifest.json`；数据库重建后重新运行生成器即可同步刷新。

测试默认使用 `manifest.json` 的场景小语料（通常 1–3 篇），避免每次运行都嵌入全量文档。`full_regression` 仅用于少量独立回归或 E2E。

文档只包含可复算事实、明确的业务背景和结论边界；不包含 `evaluation.scenario_truth` 中的答案键。
""",
    )


def main() -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            recreate_schema(cur)
            employees, products, customers, suppliers = seed_dimensions(cur)
            seed_transactions(cur, employees, products, customers, suppliers)
            create_indexes(cur)
            generate_business_knowledge_base(cur)
        conn.commit()
    print(
        f"Synthetic enterprise dataset and document corpus generated successfully (seed={SEED})."
    )


if __name__ == "__main__":
    main()
