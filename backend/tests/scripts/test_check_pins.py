"""E3: images, actions, toolchains and frontend versions must not float."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/deps"))

from check_pins import (
    check_dockerfile,
    check_package_json,
    check_yaml,
    find_problems,
    main,
)

DIGEST = "@sha256:" + "a" * 64
COMMIT = "@" + "b" * 40


def test_dockerfile_needs_a_digest_except_for_earlier_stages():
    text = f"FROM python:3.12-slim{DIGEST} AS build\nFROM build\nFROM redis:7\n"

    assert check_dockerfile("x.Dockerfile", text) == [
        "x.Dockerfile:3: image without digest: redis:7"
    ]


def test_yaml_flags_tags_unpinned_actions_and_loose_toolchains():
    text = "\n".join(
        [
            f"    image: pgvector/pgvector:0.8.0-pg16{DIGEST}",
            "    image: node:22-alpine",
            "  GITLEAKS_IMAGE: ghcr.io/gitleaks/gitleaks:latest",
            f"      - uses: actions/checkout{COMMIT} # v6",
            "      - uses: actions/setup-node@v7",
            "        uses: docker://redis:7",
            "      - uses: ./.github/actions/local",
            "          python-version: '3.12'",
            "          node-version: '22.23.1'",
        ]
    )

    assert check_yaml("ci.yml", text) == [
        "ci.yml:2: image without digest: node:22-alpine",
        "ci.yml:3: image without digest: ghcr.io/gitleaks/gitleaks:latest",
        "ci.yml:5: action not pinned to a commit: actions/setup-node@v7",
        "ci.yml:6: image without digest: docker://redis:7",
        "ci.yml:8: python-version is not exact: 3.12",
    ]


def test_package_json_versions_must_be_exact():
    text = json.dumps(
        {
            "dependencies": {"react": "19.2.8", "vite": "latest"},
            "devDependencies": {"vitest": "^4.1.10"},
        }
    )

    assert check_package_json("package.json", text) == [
        "package.json: dependencies.vite is not exact: latest",
        "package.json: devDependencies.vitest is not exact: ^4.1.10",
    ]


def test_main_fails_on_a_floating_reference(tmp_path, capsys):
    (tmp_path / "docker-compose.yml").write_text(
        "    image: redis:7\n", encoding="utf-8"
    )

    assert main(["--root", str(tmp_path)]) == 1
    assert (
        "docker-compose.yml:1: image without digest: redis:7" in capsys.readouterr().out
    )


def test_repository_has_no_floating_reference():
    assert find_problems(Path(__file__).resolve().parents[3]) == []


def test_untracked_files_in_a_checkout_are_not_checked(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "docker-compose.yml").write_text(
        f"    image: redis:7.4.9{DIGEST}\n", encoding="utf-8"
    )
    git("add", "docker-compose.yml")
    old = tmp_path / "tmp/old-worktree/backend"
    old.mkdir(parents=True)
    (old / "api.Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")

    assert find_problems(tmp_path) == []
