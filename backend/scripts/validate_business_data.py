"""Validate invariants and known scenarios in the synthetic business dataset."""

from __future__ import annotations

import hashlib
import json

from generate_business_data import CORPUS_DIR, db_connection


def scalar(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.fetchone()[0]


def require_zero(cur, label: str, sql: str) -> None:
    value = scalar(cur, sql)
    if value:
        raise RuntimeError(f"{label}: found {value} invalid rows")


def validate_document_corpus(cur) -> int:
    """Check that generated files exist, are unchanged, and track database facts."""
    manifest_path = CORPUS_DIR / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(
            "business knowledge-base manifest is missing; run the generator"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    if manifest["artifact_count"] != len(artifacts) or len(artifacts) != 30:
        raise RuntimeError("business knowledge-base artifact count is invalid")
    if "evaluation.scenario_truth" in json.dumps(manifest, ensure_ascii=False):
        raise RuntimeError(
            "evaluation answer key must never be part of the knowledge base"
        )
    for artifact in artifacts:
        path = CORPUS_DIR / artifact["path"]
        if not path.exists():
            raise RuntimeError(f"knowledge-base file is missing: {artifact['path']}")
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha256 != artifact["sha256"]:
            raise RuntimeError(f"knowledge-base file drifted: {artifact['path']}")
    expected_coverage = {
        "regions",
        "cost_centers",
        "employees",
        "customers",
        "suppliers",
        "product_categories",
        "products",
        "sales_orders",
        "sales_order_items",
        "invoices",
        "payments",
        "shipments",
        "purchase_orders",
        "purchase_order_items",
        "inventory_movements",
        "service_tickets",
        "returns",
        "expense_entries",
        "monthly_budgets",
        "crm_notes",
        "business_documents",
    }
    actual_coverage = {
        table for artifact in artifacts for table in artifact["source_tables"]
    }
    missing_coverage = expected_coverage - actual_coverage
    if missing_coverage:
        raise RuntimeError(
            f"knowledge-base does not cover business tables: {sorted(missing_coverage)}"
        )
    for month in ("2024-01", "2025-08", "2025-12"):
        revenue = scalar(
            cur,
            "SELECT COALESCE(SUM(total_amount),0) FROM sales_orders WHERE order_date >= %s::date AND order_date < (%s::date + INTERVAL '1 month')"
            % (f"'{month}-01'", f"'{month}-01'"),
        )
        expected = f"销售额：¥{revenue:,.2f}"
        content = (CORPUS_DIR / "monthly" / f"{month}.md").read_text(encoding="utf-8")
        if expected not in content:
            raise RuntimeError(f"monthly report does not match sales data: {month}")
    category_revenue = scalar(
        cur,
        """
        SELECT COALESCE(SUM(oi.line_amount), 0)
        FROM sales_order_items oi
        JOIN sales_orders o ON o.id=oi.order_id
        JOIN products p ON p.id=oi.product_id
        JOIN product_categories pc ON pc.id=p.category_id
        WHERE pc.name='传动控制' AND o.order_date >= DATE '2025-08-01' AND o.order_date < DATE '2025-09-01'
        """,
    )
    august_content = (CORPUS_DIR / "monthly" / "2025-08.md").read_text(encoding="utf-8")
    if f"| 传动控制 | ¥{category_revenue:,.2f} |" not in august_content:
        raise RuntimeError("monthly category report does not match sales-line data")
    for profile, paths in manifest["test_profiles"].items():
        if profile != "full_regression" and len(paths) > 3:
            raise RuntimeError(
                f"test profile {profile} is too large for focused RAG tests"
            )
    return len(artifacts)


def main() -> None:
    with db_connection() as conn, conn.cursor() as cur:
        counts = {
            table: scalar(cur, f"SELECT COUNT(*) FROM {table}")
            for table in (
                "customers",
                "products",
                "sales_orders",
                "sales_order_items",
                "invoices",
                "payments",
                "service_tickets",
                "business_documents",
            )
        }
        minimums = {
            "customers": 300,
            "products": 100,
            "sales_orders": 3000,
            "sales_order_items": 6000,
            "invoices": 3000,
            "payments": 2000,
            "service_tickets": 40,
            "business_documents": 25,
        }
        for table, minimum in minimums.items():
            if counts[table] < minimum:
                raise RuntimeError(
                    f"{table}: {counts[table]} rows, expected at least {minimum}"
                )
        require_zero(
            cur,
            "order totals",
            "SELECT COUNT(*) FROM sales_orders o WHERE o.total_amount <> (SELECT ROUND(SUM(line_amount), 2) FROM sales_order_items i WHERE i.order_id=o.id)",
        )
        require_zero(
            cur,
            "overpaid invoices",
            "SELECT COUNT(*) FROM invoices i WHERE i.invoice_amount < COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.invoice_id=i.id), 0)",
        )
        require_zero(
            cur,
            "orphaned shipment",
            "SELECT COUNT(*) FROM shipments s LEFT JOIN sales_orders o ON o.id=s.order_id WHERE o.id IS NULL",
        )
        require_zero(
            cur,
            "post-contract strategic orders",
            "SELECT COUNT(*) FROM sales_orders WHERE customer_id=1 AND order_date >= DATE '2025-08-01'",
        )
        complaint_signal = scalar(
            cur,
            "SELECT COUNT(*) FROM service_tickets WHERE opened_date BETWEEN DATE '2025-05-01' AND DATE '2025-06-30' AND category='产品质量' AND severity='high'",
        )
        if complaint_signal < 30:
            raise RuntimeError("quality-event signal is too weak for evaluation")
        truth_count = scalar(cur, "SELECT COUNT(*) FROM evaluation.scenario_truth")
        if truth_count != 5:
            raise RuntimeError(f"expected 5 evaluation scenarios, found {truth_count}")
        corpus_count = validate_document_corpus(cur)
    print("Business dataset validation passed.")
    for table, count in counts.items():
        print(f"  {table}: {count}")
    print(f"  quality-event high-severity tickets: {complaint_signal}")
    print(f"  generated knowledge-base artifacts: {corpus_count}")


if __name__ == "__main__":
    main()
