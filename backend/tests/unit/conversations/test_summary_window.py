"""C9c: which messages have left the window, and which to summarize next."""

from dataclasses import dataclass

import pytest
from app.modules.conversations.summary_update import (
    messages_to_summarize,
    planner_summary,
    window_start,
)


@dataclass
class Msg:
    id: int
    role: str
    content: str | None


def conversation(count: int, blank: tuple[int, ...] = ()) -> list[Msg]:
    """Messages 1..count; the ids in ``blank`` have no content."""
    return [
        Msg(i, "user" if i % 2 else "assistant", None if i in blank else f"第{i}条")
        for i in range(1, count + 1)
    ]


@pytest.mark.parametrize("count", [0, 3, 8])
def test_nothing_has_left_a_window_that_holds_every_message(count):
    assert window_start(conversation(count), window_size=8) is None


def test_the_window_starts_at_the_oldest_of_the_last_messages():
    assert window_start(conversation(12), window_size=8) == 5


def test_messages_without_content_do_not_take_a_window_place():
    # 10 and 12 are blank, so the last eight with content are 3-9 and 11.
    messages = conversation(12, blank=(10, 12))
    assert window_start(messages, window_size=8) == 3


def test_whitespace_only_counts_as_no_content():
    messages = conversation(9)
    messages[-1].content = "  \n"
    assert window_start(messages, window_size=8) is None


def ids(messages) -> list[int]:
    return [m.id for m in messages]


def test_the_messages_between_covered_and_the_window_are_picked():
    picked = messages_to_summarize(
        conversation(20), covered_through=4, window_start_id=13, limit=12
    )
    assert ids(picked) == [5, 6, 7, 8, 9, 10, 11, 12]


def test_only_the_oldest_up_to_the_limit_are_picked():
    picked = messages_to_summarize(
        conversation(20), covered_through=0, window_start_id=13, limit=3
    )
    assert ids(picked) == [1, 2, 3]


def test_blank_messages_are_not_picked():
    picked = messages_to_summarize(
        conversation(10, blank=(2, 3)), covered_through=0, window_start_id=6, limit=12
    )
    assert ids(picked) == [1, 4, 5]


def test_nothing_is_picked_once_covered_reaches_the_window():
    picked = messages_to_summarize(
        conversation(20), covered_through=12, window_start_id=13, limit=12
    )
    assert picked == []


def _summary(*sources: list[int]) -> dict:
    return {
        "items": [
            {"text": f"要点{i}", "source_message_ids": ids}
            for i, ids in enumerate(sources)
        ]
    }


def test_the_planner_reads_items_older_than_its_history():
    summary = _summary([1], [2, 4], [3])
    assert planner_summary(summary, window_start_id=5) == ["要点0", "要点1", "要点2"]


def test_an_item_citing_a_message_still_in_the_history_is_left_out():
    # 要点1 cites message 5, which the Planner already sees in its history.
    summary = _summary([1], [4, 5], [3])
    assert planner_summary(summary, window_start_id=5) == ["要点0", "要点2"]


def test_an_empty_summary_gives_nothing():
    assert planner_summary({"items": []}, window_start_id=5) == []
