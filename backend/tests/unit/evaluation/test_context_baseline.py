"""The baseline tool must attribute tokens and tables correctly."""

from scripts.evaluation.measure_context_baseline import (
    count_tokens,
    schema_usage,
    split_sections,
    tables_used,
)


def test_sections_add_up_to_about_the_whole_prompt():
    prompt = "前面的规则\n表：\na, b, c\nJoin：\na = b"

    sections = split_sections(prompt, ("表：", "Join：", "不存在："))

    assert set(sections) == {"规则", "表", "Join"}
    assert abs(sum(sections.values()) - count_tokens(prompt)) <= 2


def test_prompt_without_headers_counts_as_rules():
    assert set(split_sections("只有规则", ("表：",))) == {"规则"}


def test_tables_used_finds_joined_and_subquery_tables():
    sql = (
        "SELECT 1 FROM a JOIN b ON a.id = b.id "
        "WHERE EXISTS (SELECT 1 FROM c WHERE c.id = a.id)"
    )
    assert tables_used(sql) == {"a", "b", "c"}


def test_schema_usage_skips_cases_without_sql():
    usage = schema_usage(
        {
            "results": [
                {"sql": "SELECT 1 FROM a"},
                {"sql": "SELECT 1 FROM a JOIN b ON a.id = b.id"},
                {"sql": None},
            ]
        },
        total_tables=22,
    )
    assert usage == {
        "cases_with_sql": 2,
        "total_tables_offered": 22,
        "average_tables_used": 1.5,
        "max_tables_used": 2,
    }
