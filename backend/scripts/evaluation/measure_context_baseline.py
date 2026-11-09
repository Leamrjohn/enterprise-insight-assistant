"""Free context baseline: where prompt tokens go, and how much schema is used.

Builds the real SQL and planner prompts against the acme demo schema and counts
tokens per section.  With --sql-report it also counts which tables the generated
SQL of a recorded evaluation actually touched.  No model is called.

Needs ACME_DEMO_DATABASE_PASSWORD.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sqlglot
from app.core.tokenizer import count_tokens as count_text_tokens
from app.modules.analysis.data.sql_generation import build_sql_generation_system_prompt
from app.modules.analysis.planner.planning import build_planning_system_prompt
from scripts.evaluation.run_sql_result_evaluation import demo_source, load_catalog
from sqlglot import exp

SQL_SECTION_HEADERS = (
    "可验证指标契约：",
    "当前公司允许的表：",
    "当前公司允许的 Join：",
    "当前公司允许的筛选值：",
)


def count_tokens(text: str) -> int:
    return count_text_tokens(text)


def split_sections(prompt: str, headers: tuple[str, ...]) -> dict[str, int]:
    """Token count of each headed section; text before the first header is rules."""
    positions = sorted((prompt.index(h), h) for h in headers if h in prompt)
    if not positions:
        return {"规则": count_tokens(prompt)}
    sections = {"规则": count_tokens(prompt[: positions[0][0]])}
    for (start, header), (end, _) in zip(
        positions, [*positions[1:], (len(prompt), "")], strict=True
    ):
        sections[header.rstrip("：")] = count_tokens(prompt[start:end])
    return sections


def tables_used(sql: str) -> set[str]:
    return {
        table.name
        for table in sqlglot.parse_one(sql, read="postgres").find_all(exp.Table)
    }


def schema_usage(report: dict, *, total_tables: int) -> dict:
    per_case = [
        len(tables_used(row["sql"])) for row in report["results"] if row.get("sql")
    ]
    return {
        "cases_with_sql": len(per_case),
        "total_tables_offered": total_tables,
        "average_tables_used": round(sum(per_case) / len(per_case), 2)
        if per_case
        else None,
        "max_tables_used": max(per_case, default=None),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql-report", type=Path)
    args = parser.parse_args()

    catalog = load_catalog(demo_source())
    sql_prompt = build_sql_generation_system_prompt(catalog)
    result: dict = {
        "sql_system_prompt": {
            "total": count_tokens(sql_prompt),
            "sections": split_sections(sql_prompt, SQL_SECTION_HEADERS),
        },
        "planner_system_prompt": {
            "total": count_tokens(build_planning_system_prompt())
        },
    }
    if args.sql_report:
        report = json.loads(args.sql_report.read_text(encoding="utf-8"))
        result["schema_usage"] = schema_usage(report, total_tables=len(catalog.tables))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
