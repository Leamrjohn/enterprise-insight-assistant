"""Render a versioned evaluation artifact from real Worker observations.

This script deliberately does not invoke an Agent.  A future E2E adapter must
first normalize a persisted task into ``EvaluationObservation``; keeping that
boundary explicit prevents test fixtures from being mistaken for live results.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.modules.evaluation.business_schemas import (
    EvaluationFixture,
    EvaluationObservation,
    EvaluationRun,
)
from app.modules.evaluation.business import evaluate_run


def _git_revision(workspace: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=workspace, text=True
    ).strip()


def _render_markdown(run: EvaluationRun) -> str:
    metrics = run.metrics
    lines = [
        f"# Business evaluation: {run.run_id}",
        "",
        f"- Comparison: `{run.comparison_label}`",
        f"- Git: `{run.git_revision}`",
        f"- Dataset: `{run.dataset_version}`",
        f"- Model: `{run.model_version}`",
        f"- Trusted business analysis success rate: `{metrics.trusted_business_analysis_success_rate:.2%}`",
        f"- Hard security gate: `{'passed' if metrics.hard_gate_passed else 'FAILED'}` ({metrics.security_incident_count} incidents)",
        "",
        "| Case | Passed | Violations |",
        "|---|---:|---|",
    ]
    for result in run.results:
        lines.append(
            f"| {result.case_id} | {'yes' if result.passed else 'no'} | {', '.join(result.violations) or '-'} |"
        )
    lines.extend(
        [
            "",
            "This artifact evaluates normalized real-execution observations. It does not by itself prove that an LLM, Redis, Celery Worker, or business database was invoked.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--comparison", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    args = parser.parse_args()

    fixture = EvaluationFixture.model_validate_json(args.fixture.read_text(encoding="utf-8"))
    raw_observations = json.loads(args.observations.read_text(encoding="utf-8"))
    observations = [EvaluationObservation.model_validate(item) for item in raw_observations]
    results, metrics = evaluate_run(fixture.cases, observations)
    now = datetime.now(UTC)
    workspace = Path(__file__).resolve().parents[2]
    environment = json.loads(args.environment.read_text(encoding="utf-8"))
    run = EvaluationRun(
        run_id=f"{args.comparison}-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}",
        started_at=now,
        completed_at=now,
        comparison_label=args.comparison,
        git_revision=_git_revision(workspace),
        dataset_version=fixture.dataset_version,
        model_version=args.model_version,
        environment=environment,
        parameters={"fixture": str(args.fixture), "observation_count": len(observations)},
        results=results,
        metrics=metrics,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "run.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    (args.output_dir / "report.md").write_text(_render_markdown(run), encoding="utf-8")
    print(args.output_dir)


if __name__ == "__main__":
    main()
