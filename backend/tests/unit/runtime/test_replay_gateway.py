import json

import pytest
from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import (
    RecordReplayGateway,
    ReplayMissError,
    request_key,
)


class _CountingGateway(ModelGateway):
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls += 1
        return f'{{"echo": "{prompt}", "n": {self.calls}}}'

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_record_then_replay_returns_identical_output_without_calling_model(
    tmp_path,
) -> None:
    inner = _CountingGateway()
    recorder = RecordReplayGateway(tmp_path, mode="record", inner=inner)
    first = recorder.chat("q1", "sys", json_mode=True)

    replayer = RecordReplayGateway(tmp_path, mode="replay")
    assert replayer.chat("q1", "sys", json_mode=True) == first
    assert inner.calls == 1
    saved = json.loads(
        (tmp_path / f"{request_key('q1', 'sys', json_mode=True)}.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["response"] == first


def test_replay_miss_fails_closed_and_never_calls_a_model(tmp_path) -> None:
    replayer = RecordReplayGateway(tmp_path, mode="replay")

    with pytest.raises(ReplayMissError):
        replayer.chat("never recorded", "sys")


def test_request_key_changes_with_prompt_system_prompt_and_json_mode() -> None:
    keys = {
        request_key("q", "s", json_mode=False),
        request_key("q2", "s", json_mode=False),
        request_key("q", "s2", json_mode=False),
        request_key("q", "s", json_mode=True),
    }
    assert len(keys) == 4


def test_record_mode_requires_inner_gateway(tmp_path) -> None:
    with pytest.raises(ValueError):
        RecordReplayGateway(tmp_path, mode="record")
