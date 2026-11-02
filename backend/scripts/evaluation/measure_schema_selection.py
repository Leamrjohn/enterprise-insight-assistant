"""How well schema selection covers the tables each reference SQL needs.

Free: no model is called.  A missed table is the failure that matters, because
the model would then have to retry with the full schema.

Needs ACME_DEMO_DATABASE_PASSWORD.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.analysis.catalog.schema_selection import select_tables
from app.modules.analysis.data.sql_generation import (
    build_sql_generation_system_prompt,
    hidden_table_names,
)
from scripts.evaluation.measure_context_baseline import count_tokens, tables_used
from scripts.evaluation.run_sql_result_evaluation import demo_source, load_catalog

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "evaluation_sql"
    / "sql_results_v1.json"
)


def main() -> None:
    catalog = load_catalog(demo_source())
    full_tokens = count_tokens(build_sql_generation_system_prompt(catalog))
    rows = []
    for case in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]:
        selected = select_tables(catalog, [case["question"], *case.get("entities", [])])
        needed = (
            tables_used(case["reference_sql"]) if case.get("reference_sql") else set()
        )
        tokens = count_tokens(
            build_sql_generation_system_prompt(catalog, shown_tables=selected or None)
        )
        rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "selected": len(selected) or len(catalog.tables),
                "needed": sorted(needed),
                "missed": sorted(needed - selected) if selected else [],
                "fell_back_to_full": not selected,
                "prompt_tokens": tokens,
                "hidden": len(hidden_table_names(catalog, selected)),
            }
        )
    print(
        json.dumps(
            {
                "cases": len(rows),
                "full_prompt_tokens": full_tokens,
                "average_prompt_tokens": round(
                    sum(r["prompt_tokens"] for r in rows) / len(rows)
                ),
                "average_tables_shown": round(
                    sum(r["selected"] for r in rows) / len(rows), 2
                ),
                "cases_missing_a_table": [r["case_id"] for r in rows if r["missed"]],
                "fell_back_to_full": [
                    r["case_id"] for r in rows if r["fell_back_to_full"]
                ],
                "rows": rows,
            },
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
