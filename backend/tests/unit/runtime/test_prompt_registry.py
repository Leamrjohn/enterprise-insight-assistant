"""G1: prompts come from versioned files, and moving them changed no byte."""

import hashlib
import json

import pytest
from app.core.settings import get_settings
from app.modules.analysis.data.sql_candidate import SQLCandidate
from app.modules.analysis.planner.planning import build_planning_system_prompt
from app.modules.knowledge import tool_agent
from app.modules.knowledge.rag import support
from app.modules.knowledge.rag.engine import build_prompt
from app.modules.reporting.semantic_review_service import SemanticReviewService
from app.modules.runtime.prompts import (
    PROMPTS_DIR,
    PromptRegistry,
    PromptRegistryError,
    get_prompt_registry,
)

# sha256 of each system prompt rendered by the code before G1 moved it into
# app/prompts/ (extracted from commit eec2f6f).  A changed prompt needs a new
# version in manifest.json, not a new value here.
BEFORE_G1 = {
    "planner": "7a5d73565d75919e7672ed9a5629f5e5034631a68007433c4792a03e33379502",
    "knowledge_tool": "ec4ba6ad6f22fd41d9893660986ecb0ae32e293576e3a2c96b4ccc065e9e8f4c",
    "support_with_facts": "a58971ef1996f3e7493707d5b34309b35a406463d0b00cabefe1de3e112b84ec",
    "support_without_facts": "174f25831b32acef989d1144526528c5ffb3916c4c320ad04012484df6217dfe",
    "answer": "834ce729fc5b02852a9b32a441e7c51b3ff2dd5c79b97c8ea87d37b8b81517a8",
    "review_plan": "33058b5165064711940dd2bba68bdd26094e2220811d9f33c6b150261b386b94",
    "review_sql": "ee56307d94373ae1610ea810a48ffc703e8ff58f91909f5624d90014d8196835",
    "review_evidence_sentence_ref": "2b8e136ae399f0d3dd8762661020be9ff79f9af28ff1c3a5d66772c7bef6470f",
    "review_evidence_text": "fa40304609948cf8cb842e4502987eb1edc71b09da0e503e25d282bf0bd2e106",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Captured(Exception):
    pass


def _review_system_prompt(monkeypatch, method: str, **kwargs) -> str:
    service = SemanticReviewService(gateway=object())  # type: ignore[arg-type]
    seen = {}

    def capture(*, system_prompt, payload):
        seen["system_prompt"] = system_prompt
        raise _Captured

    monkeypatch.setattr(service, "_chat", capture)
    with pytest.raises(_Captured):
        getattr(service, method)(**kwargs)
    return seen["system_prompt"]


def test_node_prompts_are_byte_identical_to_before_g1(monkeypatch):
    plan = {"action": "analyze", "route": "data_only"}
    candidate = SQLCandidate(sql="SELECT 1", purpose="test")
    rendered = {
        "planner": build_planning_system_prompt(),
        "knowledge_tool": tool_agent.SYSTEM_PROMPT,
        "support_with_facts": support._system_prompt(True),
        "support_without_facts": support._system_prompt(False),
        "answer": build_prompt("问题", [])[0],
        "review_plan": _review_system_prompt(
            monkeypatch, "review_plan", question="q", proposed_plan=plan, catalog=None
        ),
        "review_sql": _review_system_prompt(
            monkeypatch,
            "review_sql",
            question="q",
            plan=plan,
            candidate=candidate,
            catalog=None,
        ),
    }
    for mode in ("sentence_ref", "text"):
        monkeypatch.setattr(get_settings(), "review_qualification_mode", mode)
        rendered[f"review_evidence_{mode}"] = _review_system_prompt(
            monkeypatch,
            "review_evidence",
            question="q",
            plan=plan,
            data_result={},
            knowledge_result={},
            report={},
        )

    assert {name: _sha(text) for name, text in rendered.items()} == BEFORE_G1


def test_every_task_records_the_prompt_set_version():
    version = get_prompt_registry().prompt_set_version

    assert version.startswith("prompts@")
    assert len(version) <= 64  # model_call_records.prompt_version is String(64)


def _copy_prompts(tmp_path):
    manifest = json.loads((PROMPTS_DIR / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest.values():
        target = tmp_path / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((PROMPTS_DIR / item["file"]).read_bytes())
    return manifest


def _write_manifest(tmp_path, manifest):
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_edited_prompt_without_manifest_update_fails_to_load(tmp_path):
    manifest = _copy_prompts(tmp_path)
    _write_manifest(tmp_path, manifest)
    path = tmp_path / manifest["planner.system"]["file"]
    path.write_text(path.read_text(encoding="utf-8") + "多一句。\n", encoding="utf-8")

    with pytest.raises(PromptRegistryError, match="planner.system"):
        PromptRegistry.load(tmp_path)


def test_undeclared_variable_fails_to_load(tmp_path):
    manifest = _copy_prompts(tmp_path)
    manifest["review.sql_system"]["variables"] = []
    _write_manifest(tmp_path, manifest)

    with pytest.raises(PromptRegistryError, match="other_tables_note"):
        PromptRegistry.load(tmp_path)


def test_render_refuses_missing_or_extra_variables():
    registry = get_prompt_registry()

    with pytest.raises(PromptRegistryError):
        registry.render("review.sql_system")
    with pytest.raises(PromptRegistryError):
        registry.render("planner.system", extra="x")


def test_windows_line_endings_do_not_change_the_hash(tmp_path):
    manifest = _copy_prompts(tmp_path)
    _write_manifest(tmp_path, manifest)
    path = tmp_path / manifest["planner.system"]["file"]
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    loaded = PromptRegistry.load(tmp_path)

    assert loaded.text("planner.system") == get_prompt_registry().text("planner.system")
    assert loaded.prompt_set_version == get_prompt_registry().prompt_set_version
