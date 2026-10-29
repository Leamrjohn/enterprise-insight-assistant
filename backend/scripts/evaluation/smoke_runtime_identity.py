"""Read-only baseline identity collection; never emits credentials or data rows."""

import hashlib
import inspect
import json
import subprocess


def source_hash(root):
    digest = hashlib.sha256()
    files = sorted(root.glob("app/**/*.py")) + [
        root / "scripts/evaluation/prepare_business_evaluation.py"
    ]
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest()
        )
    return digest.hexdigest()


def dump_hash(data):
    # New pg_dump versions randomize these psql guard tokens, not database data.
    lines = data.splitlines(keepends=True)
    return hashlib.sha256(
        b"".join(
            line
            for line in lines
            if not line.startswith((b"\\restrict ", b"\\unrestrict "))
        )
    ).hexdigest()


def docker_read(*args):
    result = subprocess.run(
        ["docker", *args], capture_output=True, timeout=120, check=False
    )
    if result.returncode:
        raise RuntimeError("Read-only runtime identity collection failed")
    return result.stdout


def collect_runtime_identity(root):
    containers = ("agent-api-1", "agent-worker-1", "agent-report-worker-1")
    database = "agent-demo_business_acme-1"
    for name in (*containers, database):
        owner = (
            docker_read(
                "inspect",
                "--format",
                '{{.State.Running}}|{{index .Config.Labels "com.docker.compose.project"}}|'
                '{{index .Config.Labels "com.docker.compose.project.working_dir"}}',
                name,
            )
            .decode()
            .strip()
            .split("|")
        )
        if owner != ["true", "agent", str(root)]:
            raise ValueError(
                "Runtime identity requires running containers owned by this workspace"
            )
    probe = "import hashlib,json\nfrom pathlib import Path\n" + inspect.getsource(
        source_hash
    )
    probe += """
import os
from app.core.settings import get_settings
fields = {"llm_provider", "llm_model", "llm_temperature", "llm_max_output_tokens",
          "llm_timeout_seconds", "workflow_release_version", "model_price_table_version",
          "model_price_table", "analysis_task_model_max_calls", "analysis_task_model_max_cost",
          "analysis_task_model_max_total_tokens", "reranker_model", "rag_retrieval_top_k"}
settings = get_settings()
model = settings.model_dump(mode="json", include=fields)
endpoint = settings.deepseek_base_url if settings.llm_provider == "deepseek" else os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
model["endpoint_sha256"] = hashlib.sha256(endpoint.encode()).hexdigest()
model["request_seed"] = None  # Current gateways do not send a model seed.
print(json.dumps({"source": source_hash(Path("/app")),
                  "model": model}))
"""
    expected = source_hash(root / "backend")
    snapshots = {}
    for name in containers:
        snapshot = json.loads(docker_read("exec", name, "python", "-c", probe))
        if snapshot["source"] != expected:
            raise ValueError(
                "Container source differs from workspace; align images before running"
            )
        snapshot["image"] = (
            docker_read("inspect", "--format", "{{.Image}}", name).decode().strip()
        )
        snapshots[name] = snapshot
    if any(s["model"] != snapshots[containers[0]]["model"] for s in snapshots.values()):
        raise ValueError("API and Worker model configuration differs")
    dump = docker_read(
        "exec",
        "-e",
        "PGOPTIONS=-c default_transaction_read_only=on",
        database,
        "pg_dump",
        "-U",
        "business_owner",
        "-d",
        "acme_business",
        "--no-owner",
        "--no-privileges",
    )
    manifest = json.loads(
        (root / "data/business_knowledge_base/manifest.json").read_bytes()
    )
    return {
        "containers": snapshots,
        "business_dump_sha256": dump_hash(dump),
        "corpus_version": manifest["version"],
        "corpus_seed": manifest["seed"],
    }
