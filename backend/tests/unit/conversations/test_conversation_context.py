from types import SimpleNamespace

import app.modules.conversations.service as conversation_service


def _message(message_id: int, role: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(id=message_id, role=role, content=content)


def test_context_snapshot_records_selected_message_sources_and_budget() -> None:
    snapshot = conversation_service.build_conversation_context(
        [
            _message(101, "user", "分析华东区销售下降"),
            _message(102, "assistant", "华东区销售额出现下降。"),
        ]
    )

    assert snapshot["version"] == "2.0"
    assert snapshot["messages"] == [
        {
            "id": 101,
            "role": "user",
            "content": "分析华东区销售下降",
            "content_truncated": False,
        },
        {
            "id": 102,
            "role": "assistant",
            "content": "华东区销售额出现下降。",
            "content_truncated": False,
        },
    ]
    manifest = snapshot["context_manifest"]
    assert manifest["version"] == "conversation-context/v2"
    assert manifest["selected_content_chars"] == sum(
        len(message["content"]) for message in snapshot["messages"]
    )
    assert manifest["selected_content_tokens"] > 0
    assert [fragment["message_id"] for fragment in manifest["fragments"]] == [
        101,
        102,
    ]
    assert {fragment["decision"] for fragment in manifest["fragments"]} == {"selected"}


def test_context_snapshot_marks_omitted_history_in_its_manifest() -> None:
    snapshot = conversation_service.build_conversation_context(
        [
            _message(101, "user", "older"),
            _message(102, "assistant", "newest"),
        ],
        max_chars=6,
        max_message_chars=6,
        min_fragment_chars=3,
        max_tokens=100,
    )

    assert snapshot["messages"] == [
        {
            "id": 102,
            "role": "assistant",
            "content": "newest",
            "content_truncated": False,
        }
    ]
    assert snapshot["history_truncated"] is True
    omitted = snapshot["context_manifest"]["fragments"][0]
    assert omitted["message_id"] == 101
    assert omitted["decision"] == "omitted"
    assert omitted["reason"] == "context_char_budget_exhausted"


def test_context_snapshot_records_messages_omitted_by_count_limit() -> None:
    snapshot = conversation_service.build_conversation_context(
        [
            _message(101, "user", "oldest"),
            _message(102, "assistant", "newest"),
        ],
        max_chars=100,
        max_message_chars=100,
        min_fragment_chars=3,
        max_tokens=100,
        max_messages=1,
    )

    assert [message["id"] for message in snapshot["messages"]] == [102]
    assert snapshot["history_truncated"] is True
    oldest = snapshot["context_manifest"]["fragments"][0]
    assert oldest["message_id"] == 101
    assert oldest["decision"] == "omitted"
    assert oldest["reason"] == "message_count_limit"


def test_context_snapshot_marks_a_partial_message_as_unsafe_to_complete() -> None:
    snapshot = conversation_service.build_conversation_context(
        [_message(103, "assistant", "newest-message-is-too-long")],
        max_chars=6,
        max_message_chars=6,
        min_fragment_chars=3,
        max_tokens=100,
    )

    assert snapshot["messages"] == [
        {
            "id": 103,
            "role": "assistant",
            "content": "newest",
            "content_truncated": True,
        }
    ]
    assert snapshot["history_truncated"] is True
    fragment = snapshot["context_manifest"]["fragments"][0]
    assert fragment["decision"] == "truncated"
    assert fragment["reason"] == "per_message_char_limit"


def test_context_snapshot_omits_a_message_that_cannot_keep_minimum_fragment() -> None:
    content = "甲乙丙丁"
    token_count = conversation_service.estimate_conversation_tokens(content)
    assert token_count > 1

    snapshot = conversation_service.build_conversation_context(
        [_message(104, "user", content)],
        max_chars=100,
        max_message_chars=100,
        min_fragment_chars=len(content),
        max_tokens=token_count - 1,
    )

    assert snapshot["messages"] == []
    assert snapshot["history_truncated"] is True
    fragment = snapshot["context_manifest"]["fragments"][0]
    assert fragment["decision"] == "omitted"
    assert fragment["reason"] == "token_budget_exhausted"


def test_context_snapshot_rejects_an_invalid_token_budget() -> None:
    try:
        conversation_service.build_conversation_context([], max_tokens=0)
    except ValueError as error:
        assert str(error) == "max_tokens must be greater than 0"
    else:
        raise AssertionError("max_tokens=0 must be rejected")
