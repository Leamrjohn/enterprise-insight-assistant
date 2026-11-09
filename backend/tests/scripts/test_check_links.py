"""E11: relative Markdown links must point at files that exist."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/docs"))

from check_links import broken_links, links, main, tracked_markdown


def test_links_skip_code_and_find_images():
    text = (
        "[plan](plan.md) and `[not](code.md)`\n"
        "```\n"
        "[inside](fence.md)\n"
        "```\n"
        "![chart](img/chart.png)\n"
    )

    assert links(text) == [(1, "plan.md"), (5, "img/chart.png")]


def test_broken_links_reports_missing_targets_only(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/plan.md").write_text("# plan\n", encoding="utf-8")
    (tmp_path / "docs/README.md").write_text(
        "[ok](plan.md#step) [web](https://x.test) [here](#top)\n"
        "[gone](old/plan.md) [root](/docs/plan.md) [中文](%E8%AE%A1%E5%88%92.md)\n",
        encoding="utf-8",
    )

    assert broken_links(tmp_path, ["docs/README.md"]) == [
        "docs/README.md:2: missing link target old/plan.md",
        "docs/README.md:2: missing link target %E8%AE%A1%E5%88%92.md",
    ]


def test_frozen_history_is_skipped(tmp_path):
    (tmp_path / "docs/history").mkdir(parents=True)
    (tmp_path / "docs/history/old.md").write_text("[x](gone.md)\n", encoding="utf-8")

    assert broken_links(tmp_path, ["docs/history/old.md"]) == []


def test_repository_links_resolve():
    root = Path(__file__).resolve().parents[3]

    assert broken_links(root, tracked_markdown(root)) == []
    assert main(["--root", str(root)]) == 0
