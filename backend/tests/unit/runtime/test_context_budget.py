"""What a model call may see, and how long context is shortened."""

import json
from types import SimpleNamespace

from app.modules.conversations.service import (
    build_conversation_context,
    find_standing_constraints,
)
from app.modules.runtime.context_budget import (
    EVIDENCE_REVIEW,
    MAX_ROWS_WHEN_COMPRESSED,
    ContextManifest,
    Section,
    assemble,
    cap_chunk_text,
    cap_data_rows,
    count_tokens,
)
from scripts.evaluation.run_long_conversation_evaluation import (
    FIXTURE,
    build_messages,
    context_for,
)


def _message(index, role, content):
    return SimpleNamespace(id=index, role=role, content=content)


def test_undeclared_sections_and_fields_do_not_get_in():
    manifest = ContextManifest(
        node="n", budget_tokens=1000, sections={"plan": Section(fields=("route",))}
    )
    payload, decision = assemble(
        manifest, {"plan": {"route": "x", "reason": "y"}, "secret": "z"}
    )
    assert payload == {"plan": {"route": "x"}}
    assert decision.left_out == ["secret"]


def test_nothing_is_compressed_below_the_threshold():
    rows = [[i] for i in range(MAX_ROWS_WHEN_COMPRESSED + 5)]
    payload, decision = assemble(
        EVIDENCE_REVIEW,
        {"data_result": {"status": "ready", "evidence": [{"rows": rows}]}},
    )
    assert payload["data_result"]["evidence"][0]["rows"] == rows
    assert decision.compressed == []


def test_compression_starts_at_eighty_percent_and_says_what_it_left_out():
    rows = [["客户名称很长很长很长", i] for i in range(400)]
    payload, decision = assemble(
        EVIDENCE_REVIEW,
        {
            "question": "q",
            "data_result": {"status": "ready", "evidence": [{"rows": rows}]},
        },
    )
    item = payload["data_result"]["evidence"][0]
    assert decision.compressed == ["data_result"]
    assert len(item["rows"]) == MAX_ROWS_WHEN_COMPRESSED
    assert item["rows_left_out"] == 400 - MAX_ROWS_WHEN_COMPRESSED


def test_a_section_without_compressor_is_never_shortened():
    question = "问" * 20000
    payload, decision = assemble(EVIDENCE_REVIEW, {"question": question})
    assert payload["question"] == question
    assert decision.over_budget


def test_cheaper_sections_are_compressed_only_as_far_as_needed():
    manifest = ContextManifest(
        node="n",
        budget_tokens=500,
        sections={
            "data_result": Section(compress=cap_data_rows),
            "knowledge_result": Section(compress=cap_chunk_text),
        },
    )
    rows = [["客户名称很长很长很长", i] for i in range(300)]
    long_chunk = "片段内容" * 150
    _, decision = assemble(
        manifest,
        {
            "data_result": {"evidence": [{"rows": rows}]},
            "knowledge_result": {"evidences": [{"content": long_chunk}]},
        },
    )
    assert decision.compressed[0] == "data_result"


def test_chunk_text_is_marked_when_shortened():
    long_chunk = "片" * 2000
    result = cap_chunk_text({"evidences": [{"content": long_chunk, "chunk_id": 1}]})
    item = result["evidences"][0]
    assert item["content_truncated"] is True and item["chunk_id"] == 1
    assert len(item["content"]) < len(long_chunk)


def test_evidence_review_drops_what_the_report_repeats():
    payload, _ = assemble(
        EVIDENCE_REVIEW,
        {
            "plan": {"route": "hybrid", "reason": "internal"},
            "deterministic_report": {
                "status": "completed",
                "data_evidence": [{"sql": "SELECT 1"}],
                "document_citations": [{"chunk_id": 1}],
                "limitations": [],
            },
        },
    )
    assert "reason" not in payload["plan"]
    assert "data_evidence" not in payload["deterministic_report"]
    assert "document_citations" not in payload["deterministic_report"]
    assert count_tokens(payload) > 0


def test_assistant_text_is_shortened_first_and_user_text_stays():
    user_text = "这是用户的要求，要完整保留。"
    messages = [
        _message(1, "user", user_text),
        _message(2, "assistant", "很长的报告内容。" * 500),
        _message(3, "user", user_text),
    ]
    context = build_conversation_context(messages)
    by_id = {m["id"]: m for m in context["messages"]}
    assert len(by_id[2]["content"]) <= 400
    assert by_id[2]["content_truncated"] is True
    assert by_id[1]["content"] == user_text and by_id[3]["content"] == user_text


def test_short_history_is_not_compressed():
    messages = [_message(1, "user", "问题"), _message(2, "assistant", "回答" * 50)]
    context = build_conversation_context(messages)
    assert context["messages"][1]["content"] == "回答" * 50


def test_standing_constraints_keep_the_users_exact_words():
    found = find_standing_constraints(
        [
            _message(1, "user", "后面都只看华东区。"),
            _message(2, "assistant", "只看华东，好的。"),
            _message(3, "user", "报告在哪里看？"),
        ]
    )
    assert found == [{"id": 1, "content": "后面都只看华东区。"}]


def test_standing_constraints_are_bounded_and_keep_the_newest():
    messages = [_message(i, "user", f"只看第{i}个区域") for i in range(1, 9)]
    found = find_standing_constraints(messages)
    assert [item["id"] for item in found] == [4, 5, 6, 7, 8]


def test_long_conversation_fixture_loses_the_constraint_without_the_feature():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        messages = build_messages(case, fixture["filler_turns"])
        without = context_for(case, fixture["filler_turns"], with_constraints=False)
        recent = {m["content"] for m in without["messages"]}
        assert case["constraint"] not in recent, case["case_id"]
        assert without["history_truncated"] is True
        assert len(messages) > 8
        with_feature = context_for(case, fixture["filler_turns"], with_constraints=True)
        assert case["constraint"] in {
            c["content"] for c in with_feature["standing_constraints"]
        }, case["case_id"]
