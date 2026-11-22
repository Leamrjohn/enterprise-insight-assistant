"""C9b: code keeps only summary items that cite messages outside the window."""

from dataclasses import dataclass

import pytest
from app.modules.conversations.summary import MAX_SUMMARY_ITEMS, empty_summary
from app.modules.conversations.summary_update import (
    BAD_TEXT,
    MAX_ITEM_CHARS,
    MESSAGE_IN_WINDOW,
    NO_SOURCE,
    OVER_ITEM_LIMIT,
    UNKNOWN_MESSAGE,
    apply_summary,
)


@dataclass
class Msg:
    id: int
    role: str
    content: str | None


# Messages 1-4 have left the window; 5 and 6 are still in it.
MESSAGES = [
    Msg(1, "user", "我负责华东区的战略客户。"),
    Msg(2, "assistant", "好的。"),
    Msg(3, "user", "华东区8月销售额是多少？"),
    Msg(4, "assistant", "华东区8月销售额比7月下降12%。"),
    Msg(5, "user", "好的。"),
    Msg(6, "assistant", "还有其他问题吗？"),
]
WINDOW_START = 5


def item(text="用户说自己负责华东区的战略客户", ids=(1,)) -> dict:
    return {"text": text, "source_message_ids": list(ids)}


def apply(items, summary=None):
    return apply_summary(
        summary or empty_summary(), items, MESSAGES, window_start_id=WINDOW_START
    )


def test_items_citing_messages_outside_the_window_are_kept():
    conclusion = item("助手分析得出华东区8月销售额比7月下降12%", (4, 3, 3))
    summary, rejected = apply([item(), conclusion])

    assert rejected == []
    assert summary["items"] == [
        item(),
        {"text": conclusion["text"], "source_message_ids": [3, 4]},
    ]
    assert summary["covered_through"] == 4


@pytest.mark.parametrize(
    "bad, reason",
    [
        ({"source_message_ids": [1]}, BAD_TEXT),
        (item(text="   "), BAD_TEXT),
        (item(text=123), BAD_TEXT),
        (item(text="华" * (MAX_ITEM_CHARS + 1)), BAD_TEXT),
        ({"text": "用户负责华东区"}, NO_SOURCE),
        (item(ids=()), NO_SOURCE),
        ({"text": "用户负责华东区", "source_message_ids": 1}, NO_SOURCE),
        (item(ids=(1, "2")), NO_SOURCE),
        (item(ids=(True,)), NO_SOURCE),
        (item(ids=(1, 99)), UNKNOWN_MESSAGE),
        (item(ids=(4, 5)), MESSAGE_IN_WINDOW),
    ],
)
def test_a_bad_item_is_rejected_with_its_first_failing_check(bad, reason):
    summary, rejected = apply([item(), bad])

    assert summary["items"] == [item()]
    assert rejected == [{"index": 1, "reason": reason}]


def test_an_item_of_exactly_the_limit_is_kept():
    summary, rejected = apply([item(text="华" * MAX_ITEM_CHARS)])
    assert (len(summary["items"]), rejected) == (1, [])


def test_only_the_first_items_up_to_the_cap_are_kept():
    items = [item(f"第{i}条要点") for i in range(MAX_SUMMARY_ITEMS + 2)]
    summary, rejected = apply(items)

    assert len(summary["items"]) == MAX_SUMMARY_ITEMS
    assert rejected == [
        {"index": MAX_SUMMARY_ITEMS, "reason": OVER_ITEM_LIMIT},
        {"index": MAX_SUMMARY_ITEMS + 1, "reason": OVER_ITEM_LIMIT},
    ]


def test_the_old_summary_is_not_changed_and_its_counter_is_kept():
    old = empty_summary()
    old["items"] = [item("旧要点")]
    old["incremental_count"] = 3
    summary, _ = apply([item()], summary=old)

    assert old["items"] == [item("旧要点")]
    assert summary["items"] == [item()]
    assert summary["incremental_count"] == 3
