"""Record-once, replay-offline model gateway for component evaluation.

Record mode forwards to a real gateway and stores each response under a hash of
the exact request.  Replay mode only reads stored responses and fails closed on
a miss, so an evaluation can never silently fall through to a paid call.

Cassettes contain business data: keep them under the git-ignored
``evaluation-runs/`` directory and never in the database.  The only exception is
the reviewed CI gate recordings under ``tests/fixtures`` (E10a), which cover the
synthetic acme demo data and the frozen held-out questions only.
"""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Literal

from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse

ReplayMode = Literal["record", "replay"]


class ReplayMissError(RuntimeError):
    """Raised when replay mode has no recording for the exact request."""


def request_key(prompt: str, system_prompt: str | None, *, json_mode: bool) -> str:
    material = f"{system_prompt or ''}\0{prompt}\0json_mode={json_mode}"
    return sha256(material.encode("utf-8")).hexdigest()


class RecordReplayGateway(ModelGateway):
    def __init__(
        self,
        cassette_dir: Path,
        *,
        mode: ReplayMode,
        inner: ModelGateway | None = None,
    ) -> None:
        if mode == "record" and inner is None:
            raise ValueError("record mode needs a real gateway to forward to")
        self._dir = Path(cassette_dir)
        self._mode = mode
        self._inner = inner
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_mode: bool = False,
    ) -> str:
        key = request_key(prompt, system_prompt, json_mode=json_mode)
        path = self._path(key)
        if self._mode == "replay":
            if not path.exists():
                raise ReplayMissError(f"no recording for request {key[:12]}")
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        assert self._inner is not None
        response = self._inner.chat(prompt, system_prompt, json_mode=json_mode)
        # Write then rename so an interrupted run never leaves a half cassette.
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"key": key, "json_mode": json_mode, "response": response},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return response

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        tool_choice: str | dict = "auto",
    ) -> ToolChatResponse:
        material = json.dumps(
            [messages, tools, tool_choice], ensure_ascii=False, sort_keys=True
        )
        key = "tools-" + sha256(material.encode("utf-8")).hexdigest()
        path = self._path(key)
        if self._mode == "replay":
            if not path.exists():
                raise ReplayMissError(f"no recording for request {key[:18]}")
            stored = json.loads(path.read_text(encoding="utf-8"))
            return ToolChatResponse(
                text=stored["text"],
                tool_calls=tuple(ToolCall(**call) for call in stored["tool_calls"]),
            )
        assert self._inner is not None
        response = self._inner.chat_with_tools(messages, tools, tool_choice=tool_choice)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "key": key,
                    "text": response.text,
                    "tool_calls": [
                        {"id": c.id, "name": c.name, "arguments": c.arguments}
                        for c in response.tool_calls
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return response

    def count_tokens(self, text: str) -> int:
        if self._inner is not None:
            return self._inner.count_tokens(text)
        # Replay has no tokenizer dependency; a character count is a safe upper bound.
        return len(text)
