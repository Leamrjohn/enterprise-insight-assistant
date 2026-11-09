"""E10a: download the local retrieval models at pinned revisions into HF_HOME.

The application loads models by name, which resolves the cache's ``main`` ref.
After downloading a pinned revision this points ``main`` at it, so an offline
run (HF_HUB_OFFLINE=1) uses exactly these files and never a newer upload.
CI caches HF_HOME keyed on this file, so changing a revision downloads again.

    HF_HOME=/path/to/cache python scripts/evaluation/prefetch_models.py
"""

from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download

# Revisions match the models the local Worker cache has been evaluated with.
MODELS = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": (
        "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
    ),
    "BAAI/bge-reranker-base": "2cfc18c9415c912f9d8155881c133215df768a70",
}
# Weights in safetensors only; skip the duplicate PyTorch, ONNX and TF exports.
IGNORE = ["*.bin", "*.h5", "*.msgpack", "*.onnx", "onnx/*", "openvino/*", "*.ot"]


def main() -> None:
    for repo, revision in MODELS.items():
        path = Path(snapshot_download(repo, revision=revision, ignore_patterns=IGNORE))
        main_ref = path.parents[1] / "refs" / "main"
        main_ref.parent.mkdir(parents=True, exist_ok=True)
        main_ref.write_text(revision, encoding="utf-8")
        print(f"{repo}@{revision[:12]} ready")


if __name__ == "__main__":
    main()
