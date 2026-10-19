from app.modules.analysis.facts import build_confirmed_facts, build_data_evidence


def test_fact_builder_derives_bounded_fact_from_controlled_row() -> None:
    evidence = build_data_evidence(
        {
            "evidence": [
                {
                    "purpose": "区域销售比较",
                    "columns": ["region_name", "total_sales"],
                    "rows": [["华东", 100]],
                }
            ]
        }
    )

    facts = build_confirmed_facts(evidence)

    assert evidence[0].purpose == "已授权经营数据"
    assert facts[0].data_evidence_ids == ["data-1"]
    assert facts[0].statement == "已授权经营数据：区域为华东，销售额为100。"


def test_fact_builder_skips_rows_without_a_reliable_column_contract() -> None:
    evidence = build_data_evidence(
        {"evidence": [{"columns": ["sales"], "rows": [[1, 2]]}]}
    )

    assert build_confirmed_facts(evidence) == []


def test_fact_builder_does_not_promote_refuted_claim_to_confirmed_fact() -> None:
    evidence = build_data_evidence(
        {
            "evidence": [
                {
                    "columns": ["销售额"],
                    "rows": [[100]],
                    "metric_assessment": {
                        "status": "supported",
                        "reason": "指标已验证。",
                    },
                    "claim_assessment": {
                        "status": "refuted",
                        "reason": "断言不成立。",
                    },
                }
            ]
        }
    )

    assert build_confirmed_facts(evidence) == []
