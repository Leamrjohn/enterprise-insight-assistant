"""C2: per-section token counts, and no section text in what is stored."""

from app.core.tokenizer import count_tokens
from app.modules.runtime.context_measurement import (
    measure_sections,
    measurement_details,
)

SECTIONS = {
    "system": "你是企业经营洞察助手的规划器。",
    "question": "华东区2025年8月销售额是多少？",
    "history": "",
}
SECTIONSQ = {
    "system": "你是企业经营洞察助手的规划器。",
    "question": "华东区2025年8月销售额是多少？",
    "history": "用户：上个月华东卖了多少？\n助手：华东区2025年7月销售额为 128.5 万元。",
}


def test_each_section_and_the_total_are_counted():
    counts = measure_sections(SECTIONS)

    assert counts["system"] == count_tokens(SECTIONS["system"])
    assert counts["question"] == count_tokens(SECTIONS["question"])
    assert counts["history"] == 0
    assert counts["total"] == counts["system"] + counts["question"]


def test_event_details_carry_counts_but_no_text():
    details = measurement_details("planner", SECTIONS)

    assert details["node"] == "planner"
    assert details["tokens"]["total"] > 0
    assert "华东" not in str(details) and "规划器" not in str(details)


def test_event_details_have_only_node_and_integer_counts():
    counts = measurement_details("planner", SECTIONS)
    assert set(counts) == {"node", "tokens"}
    assert all(isinstance(value, int) for value in counts["tokens"].values())


def test_total_includes_every_section():
    counts = measure_sections(SECTIONSQ)

    assert counts["system"] == count_tokens(SECTIONSQ["system"])
    assert counts["question"] == count_tokens(SECTIONSQ["question"])
    assert counts["history"] == count_tokens(SECTIONSQ["history"])
    assert counts["total"] == counts["system"] + counts["question"] + counts["history"]
