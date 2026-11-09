"""Versioned system prompts read from app/prompts/ (G1).

Each prompt is a file listed in ``app/prompts/manifest.json`` with a version,
the variables it takes and the sha256 of its text.  Loading checks all three,
so a file edited without updating the manifest fails at startup instead of
reaching a model.  Rendering uses ``string.Template`` (``${name}``; a literal
dollar sign is ``$$``) and refuses missing or extra variables.

Task-level ``prompt_set_version`` goes into every model call record, so a
metric change can be traced to the prompt set that produced it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


class PromptRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptEntry:
    prompt_id: str
    version: str
    variables: frozenset[str]
    sha256: str
    template: Template


def _read_text(path: Path) -> str:
    # Files end with one newline that is not part of the prompt; a Windows
    # checkout may also turn LF into CRLF.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return text.removesuffix("\n")


class PromptRegistry:
    def __init__(self, entries: dict[str, PromptEntry]) -> None:
        self._entries = entries
        lines = sorted(
            f"{entry.prompt_id}@{entry.version}:{entry.sha256}"
            for entry in entries.values()
        )
        digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
        self.prompt_set_version = f"prompts@{digest[:16]}"

    @classmethod
    def load(cls, directory: Path = PROMPTS_DIR) -> PromptRegistry:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        entries = {}
        for prompt_id, item in manifest.items():
            path = directory / item["file"]
            if not path.is_file():
                raise PromptRegistryError(f"{prompt_id}: missing file {item['file']}")
            text = _read_text(path)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest != item["sha256"]:
                raise PromptRegistryError(
                    f"{prompt_id}: {item['file']} changed without updating the "
                    "manifest sha256 and version"
                )
            template = Template(text)
            if not template.is_valid():
                raise PromptRegistryError(f"{prompt_id}: invalid placeholder")
            declared = frozenset(item["variables"])
            found = frozenset(template.get_identifiers())
            if declared != found:
                raise PromptRegistryError(
                    f"{prompt_id}: declares {sorted(declared)} but uses {sorted(found)}"
                )
            entries[prompt_id] = PromptEntry(
                prompt_id, item["version"], declared, digest, template
            )
        return cls(entries)

    def render(self, prompt_id: str, **variables: str) -> str:
        entry = self._entries[prompt_id]
        if set(variables) != entry.variables:
            raise PromptRegistryError(
                f"{prompt_id}: needs {sorted(entry.variables)}, got {sorted(variables)}"
            )
        return entry.template.substitute(variables)

    def text(self, prompt_id: str) -> str:
        return self.render(prompt_id)

    def version_of(self, prompt_id: str) -> str:
        return f"{prompt_id}@{self._entries[prompt_id].version}"


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    return PromptRegistry.load()
