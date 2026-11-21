"""How the long-conversation evaluation builds each case, and the v2 case set."""

import hashlib
import json
from types import SimpleNamespace

from app.core.gateway.replay import RecordReplayGateway
from scripts.evaluation.run_long_conversation_evaluation import (
    FILLER_ANSWER,
    FILLER_QUESTION,
    FIXTURE,
    FIXTURE_V1,
    ResumingGateway,
    build_messages,
    score_case,
)

CONSTRAINT = "后面都只看华东区。"
NOTED = "好的，已记下。"
F = [FILLER_QUESTION, FILLER_ANSWER]


def contents(case: dict, filler_turns: int = 10) -> list[str]:
    return [m.content for m in build_messages(case, filler_turns)]


def test_v1_cases_build_the_same_messages_as_before():
    fixture = json.loads(FIXTURE_V1.read_text(encoding="utf-8"))
    built = [
        [(m.id, m.role, m.content) for m in build_messages(c, fixture["filler_turns"])]
        for c in fixture["cases"]
    ]
    digest = hashlib.sha256(json.dumps(built, ensure_ascii=False).encode()).hexdigest()
    assert digest == "af466d28699176870508c5096bf92e0fd623949c1931f7a33b1868e4fad6ad07"


def test_a_case_can_set_its_own_number_of_filler_turns():
    built = contents({"constraint": CONSTRAINT, "filler_turns": 30})
    assert len(built) == 2 + 30 * 2
    assert built[:2] == [CONSTRAINT, NOTED]


def test_a_case_without_constraint_is_only_filler():
    assert contents({"filler_turns": 3}) == F * 3


def test_an_insert_goes_after_the_given_pair():
    case = {
        "constraint": CONSTRAINT,
        "filler_turns": 3,
        "inserts": [{"after_pair": 2, "user": "U", "assistant": "A"}],
    }
    assert contents(case) == [CONSTRAINT, NOTED, *F, "U", "A", *F, *F]


def test_after_pair_zero_puts_the_insert_first():
    case = {
        "constraint": CONSTRAINT,
        "filler_turns": 1,
        "inserts": [{"after_pair": 0, "user": "U", "assistant": "A"}],
    }
    assert contents(case) == ["U", "A", CONSTRAINT, NOTED, *F]


def test_inserts_at_the_same_place_keep_their_order():
    case = {
        "constraint": CONSTRAINT,
        "filler_turns": 1,
        "inserts": [
            {"after_pair": 1, "user": "U1", "assistant": "A1"},
            {"after_pair": 1, "user": "U2", "assistant": "A2"},
        ],
    }
    assert contents(case) == [CONSTRAINT, NOTED, "U1", "A1", "U2", "A2", *F]


def test_inserts_count_pairs_of_the_recent_layout_too():
    # recent: 2 filler pairs, the constraint, then 2 more (RECENT_TURNS_AFTER).
    case = {
        "constraint": CONSTRAINT,
        "constraint_position": "recent",
        "filler_turns": 2,
        "inserts": [{"after_pair": 3, "user": "U", "assistant": "A"}],
    }
    assert contents(case) == [*F, *F, CONSTRAINT, NOTED, "U", "A", *F, *F]


def test_the_override_stays_last_and_ids_count_from_one():
    case = {
        "constraint": CONSTRAINT,
        "filler_turns": 1,
        "inserts": [{"after_pair": 2, "user": "U", "assistant": "A"}],
        "override": "改看华南区。",
    }
    messages = build_messages(case, 10)
    assert [m.content for m in messages][-2:] == ["改看华南区。", "好的。"]
    assert [m.id for m in messages] == list(range(1, len(messages) + 1))
    assert [m.role for m in messages] == ["user", "assistant"] * (len(messages) // 2)


def decision(text: str, action: str = "analyze") -> SimpleNamespace:
    return SimpleNamespace(action=action, resolved_question=text, evaluation_scope=None)


def test_must_contain_all_needs_one_word_from_every_group():
    case = {
        "case_id": "c",
        "split": "development",
        "must_contain_all": [["华东"], ["已交付", "delivered"]],
    }
    assert score_case(case, decision("华东区已交付订单"))["passed"] is True
    assert score_case(case, decision("华东区 delivered 订单"))["passed"] is True
    assert score_case(case, decision("华东区订单"))["passed"] is False


class CountingGateway:
    def __init__(self):
        self.calls = 0

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.calls += 1
        return f"live {self.calls}"


def test_resume_reads_what_is_recorded_and_pays_only_for_the_rest(tmp_path):
    inner = CountingGateway()
    RecordReplayGateway(tmp_path, mode="record", inner=inner).chat("a")  # type: ignore[arg-type]
    resuming = ResumingGateway(tmp_path, mode="record", inner=inner)  # type: ignore[arg-type]
    assert resuming.chat("a") == "live 1"
    assert resuming.chat("b") == "live 2"
    assert inner.calls == 2


def pairs_in(case: dict, default_turns: int) -> int:
    turns = case.get("filler_turns", default_turns)
    if case.get("constraint"):
        turns += 1 + (2 if case.get("constraint_position") == "recent" else 0)
    return turns


def test_v2_keeps_v1_and_covers_every_kind_of_case():
    v1 = json.loads(FIXTURE_V1.read_text(encoding="utf-8"))
    v2 = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = v2["cases"]
    assert cases[: len(v1["cases"])] == v1["cases"]
    assert v2["filler_turns"] == v1["filler_turns"]
    assert len(cases) >= 40
    assert len({c["case_id"] for c in cases}) == len(cases)

    long_cases = [c for c in cases if pairs_in(c, v2["filler_turns"]) >= 30]
    injection = [c for c in cases if c.get("category") == "injection"]
    assert len(long_cases) >= 8
    assert len(injection) >= 6
    assert all(c.get("must_not_contain") for c in injection)

    heldout = sum(c["split"] == "heldout" for c in cases)
    assert {c["split"] for c in cases} == {"development", "heldout"}
    assert 0.25 <= heldout / len(cases) <= 0.4


def test_every_v2_case_is_well_formed():
    v2 = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in v2["cases"]:
        cid = case["case_id"]
        assert case["question"], cid
        assert (
            case.get("must_contain")
            or case.get("must_contain_all")
            or case.get("must_not_contain")
        ), cid
        pairs = pairs_in(case, v2["filler_turns"])
        for insert in case.get("inserts", []):
            assert 0 <= insert["after_pair"] <= pairs, cid
            assert insert["user"] and insert["assistant"], cid
