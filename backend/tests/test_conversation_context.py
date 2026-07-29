from types import SimpleNamespace

import app.services.conversation_service as conversation_service


def test_build_conversation_context_serializes_messages() -> None:
    build_conversation_context = getattr(
        conversation_service,
        "build_conversation_context",
        None,
    )
    assert callable(build_conversation_context), (
        "conversation_service.build_conversation_context 尚未实现"
    )

    messages = [
        SimpleNamespace(id=101, role="user", content="分析华东区销售下降"),
        SimpleNamespace(id=102, role="assistant", content="华东区销售额出现下降。"),
    ]

    snapshot = build_conversation_context(messages)

    assert snapshot == {
        "version": "1.0",
        "messages": [
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
        ],
        "history_truncated": False,
    }


def test_build_conversation_context_keeps_newest_messages_within_budget() -> None:
    messages = [
        SimpleNamespace(id=101, role="user", content="older"),
        SimpleNamespace(id=102, role="assistant", content="   "),
        SimpleNamespace(id=103, role="user", content="newest"),
    ]

    snapshot = conversation_service.build_conversation_context(
        messages,
        max_chars=6,
        max_message_chars=6,
        min_fragment_chars=3,
    )

    assert snapshot == {
        "version": "1.0",
        "messages": [
            {
                "id": 103,
                "role": "user",
                "content": "newest",
                "content_truncated": False,
            },
        ],
        "history_truncated": True,
    }


def test_build_conversation_context_truncates_oversized_newest_message() -> None:
    messages = [
        SimpleNamespace(
            id=103,
            role="assistant",
            content="newest-message-is-too-long",
        ),
    ]

    snapshot = conversation_service.build_conversation_context(
        messages,
        max_chars=6,
        max_message_chars=6,
        min_fragment_chars=3,
    )

    assert snapshot == {
        "version": "1.0",
        "messages": [
            {
                "id": 103,
                "role": "assistant",
                "content": "newest",
                "content_truncated": True,
            },
        ],
        "history_truncated": False,
    }


def test_build_conversation_context_uses_large_enough_remaining_fragment() -> None:
    messages = [
        SimpleNamespace(id=101, role="assistant", content="older"),
        SimpleNamespace(id=102, role="user", content="newest"),
    ]

    snapshot = conversation_service.build_conversation_context(
        messages,
        max_chars=9,
        max_message_chars=6,
        min_fragment_chars=3,
    )

    assert snapshot == {
        "version": "1.0",
        "messages": [
            {
                "id": 101,
                "role": "assistant",
                "content": "old",
                "content_truncated": True,
            },
            {
                "id": 102,
                "role": "user",
                "content": "newest",
                "content_truncated": False,
            },
        ],
        "history_truncated": False,
    }


def test_build_conversation_context_stops_when_remaining_fragment_is_too_small() -> (
    None
):
    messages = [
        SimpleNamespace(id=100, role="user", content="tiny"),
        SimpleNamespace(id=101, role="assistant", content="older"),
        SimpleNamespace(id=102, role="user", content="newest"),
    ]

    snapshot = conversation_service.build_conversation_context(
        messages,
        max_chars=8,
        max_message_chars=6,
        min_fragment_chars=3,
    )

    assert snapshot == {
        "version": "1.0",
        "messages": [
            {
                "id": 102,
                "role": "user",
                "content": "newest",
                "content_truncated": False,
            },
        ],
        "history_truncated": True,
    }


def test_build_conversation_context_marks_older_messages_omitted_after_fragment() -> (
    None
):
    messages = [
        SimpleNamespace(id=100, role="user", content="first"),
        SimpleNamespace(id=101, role="assistant", content="older"),
        SimpleNamespace(id=102, role="user", content="newest"),
    ]

    snapshot = conversation_service.build_conversation_context(
        messages,
        max_chars=9,
        max_message_chars=6,
        min_fragment_chars=3,
    )

    assert snapshot == {
        "version": "1.0",
        "messages": [
            {
                "id": 101,
                "role": "assistant",
                "content": "old",
                "content_truncated": True,
            },
            {
                "id": 102,
                "role": "user",
                "content": "newest",
                "content_truncated": False,
            },
        ],
        "history_truncated": True,
    }
