import json

import pytest
from scripts.evaluation import smoke_runtime_identity as identity


def test_dump_guard_tokens_do_not_hide_data_changes():
    first = b"\\restrict random1\nCOPY x;\nrow1\n\\unrestrict random1\n"
    second = first.replace(b"random1", b"random2")
    assert identity.dump_hash(first) == identity.dump_hash(second)
    assert identity.dump_hash(first) != identity.dump_hash(
        first.replace(b"row1", b"row2")
    )


@pytest.mark.parametrize("mismatch", ["owner", "source", "model", None])
def test_capture_is_read_only_and_rejects_runtime_mismatch(
    monkeypatch, tmp_path, mismatch
):
    root = tmp_path
    manifest = root / "data/business_knowledge_base/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"version":"v1","seed":7}')
    monkeypatch.setattr(identity, "source_hash", lambda _: "expected")
    # Keep the real probe function's source available when substituting its hash.
    monkeypatch.setattr(
        identity.inspect,
        "getsource",
        lambda _: "def source_hash(root): return 'expected'\n",
    )
    calls = []

    def read(*args):
        calls.append(args)
        if args[0] == "inspect":
            if args[2] == "{{.Image}}":
                return b"image-sha"
            return f"true|{'other' if mismatch == 'owner' else 'agent'}|{root}".encode()
        if "pg_dump" in args:
            assert "PGOPTIONS=-c default_transaction_read_only=on" in args
            assert "--no-owner" in args and "--no-privileges" in args
            return b"COPY table;\nrow\n"
        return json.dumps(
            {
                "source": "old" if mismatch == "source" else "expected",
                "model": {
                    "llm_model": "other"
                    if mismatch == "model" and args[1] == "agent-worker-1"
                    else "model"
                },
            }
        ).encode()

    monkeypatch.setattr(identity, "docker_read", read)
    if mismatch:
        with pytest.raises(ValueError):
            identity.collect_runtime_identity(root)
        assert not any("pg_dump" in c for c in calls)
    else:
        result = identity.collect_runtime_identity(root)
        assert len(result["containers"]) == 3
        assert result["corpus_seed"] == 7
        assert len(result["business_dump_sha256"]) == 64
        assert "row" not in json.dumps(result)


def test_source_hash_changes_with_code_but_not_windows_line_endings(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    file = app / "main.py"
    prepare = tmp_path / "scripts/evaluation/prepare_business_evaluation.py"
    prepare.parent.mkdir(parents=True)
    prepare.write_bytes(b"pass\n")
    file.write_bytes(b"x = 1\r\n")
    first = identity.source_hash(tmp_path)
    file.write_bytes(b"x = 1\n")
    assert identity.source_hash(tmp_path) == first
    file.write_bytes(b"x = 2\n")
    assert identity.source_hash(tmp_path) != first
