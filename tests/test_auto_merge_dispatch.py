"""The org auto-merge sweep must DISPATCH develop's post-merge gates itself.

GitHub SUPPRESSES workflow triggers for pushes made with the default
``github.token`` (recursive-run protection), and auto-merge-to-develop.yml
merges with exactly that token — so every commit the sweep lands arrives on
develop with ZERO check runs. Measured across the scitex-ai org on
2026-07-22: 58 of 74 enumerated repos carry at least one bot-merged develop
head with ``check-runs total_count: 0`` while their user-pushed neighbours on
the same branch carry 5-19 each (figrecipe 3ebb01c0 -> 0 vs b33a8ed3 -> 19;
scitex-io 49d709be -> 0 vs f9fe3dd5 -> 8; scitex-app 0e69dfd5 -> 0 vs
827b75c9 -> 16), with runners online and idle.

A downstream develop-health gate then reads "no checks" as "no red signal"
and keeps merging — green-by-absence. ``workflow_dispatch`` IS exempt from
the suppression, so the merge step must explicitly dispatch the gates after
a successful merge.

These tests pin that wiring AS TEXT — no network, no gh, cannot flake.
Mutation-checked: reverting the workflow to its pre-fix body, neutering the
``gh workflow run`` line, or flipping ``--ref develop`` to ``--ref main``
each turn at least one test red.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_AUTO_MERGE = _REPO / ".github" / "workflows" / "auto-merge-to-develop.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(_AUTO_MERGE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def merge_step(workflow: dict) -> dict:
    """The step that performs the merges (found by behaviour, not by name)."""
    steps = workflow["jobs"]["automerge"]["steps"]
    merging = [s for s in steps if "gh pr merge" in s.get("run", "")]
    assert len(merging) == 1, "expected exactly one merging step"
    return merging[0]


def _dispatch_lines(merge_step: dict) -> list[str]:
    return [
        line for line in merge_step["run"].splitlines() if "gh workflow run" in line
    ]


# ---------------------------------------------------------------------------
# The dispatch exists at all.
# ---------------------------------------------------------------------------


def test_merge_step_runs_workflow_dispatch(merge_step: dict) -> None:
    # Arrange
    run = merge_step["run"]
    # Act
    lines = [line for line in run.splitlines() if "gh workflow run" in line]
    # Assert
    assert lines, (
        "the merge step never runs `gh workflow run` — a github.token merge "
        "fires no triggers, so develop's new head would sit un-checked"
    )


# ---------------------------------------------------------------------------
# THE WRONG-REF HOLE. `--ref main` is a dispatch that exists but checks the
# wrong branch — it would satisfy a naive "is there a dispatch?" test while
# leaving the merged develop head just as un-verified as before.
# ---------------------------------------------------------------------------


def test_every_dispatch_targets_develop(merge_step: dict) -> None:
    # Arrange: non-emptiness is pinned by test_merge_step_runs_workflow_dispatch.
    lines = _dispatch_lines(merge_step)
    # Act
    off_ref = [line for line in lines if "--ref develop" not in line]
    # Assert
    assert off_ref == [], (
        "a dispatch without `--ref develop` runs the gate against another "
        f"branch, not the head the merge just produced: {off_ref}"
    )


def test_no_dispatch_targets_a_non_develop_ref(merge_step: dict) -> None:
    # Arrange
    lines = _dispatch_lines(merge_step)
    # Act: catch the mutation from the other side — `--ref main` must never
    # appear even alongside a correct `--ref develop` on some other line.
    wrong = [line for line in lines if "--ref main" in line or "--ref master" in line]
    # Assert
    assert wrong == [], f"dispatch targets a non-develop ref: {wrong}"


def _discovery_lines(merge_step: dict) -> list[str]:
    return [
        line
        for line in merge_step["run"].splitlines()
        if "contents/.github/workflows/" in line and "ref=" in line
    ]


def test_gate_discovery_reads_workflow_files(merge_step: dict) -> None:
    # Arrange
    step = merge_step
    # Act
    discovery = _discovery_lines(step)
    # Assert
    assert discovery, "no gate-discovery read of .github/workflows found"


def test_gate_discovery_reads_the_develop_ref(merge_step: dict) -> None:
    # Arrange: non-emptiness is pinned by the previous test.
    discovery = _discovery_lines(merge_step)
    # Act: auto-discovery must inspect workflow files as they exist ON
    # develop. Discovering from main would happily "find" a gate that does
    # not exist on the branch being merged into.
    off_ref = [line for line in discovery if "ref=develop" not in line]
    # Assert
    assert off_ref == [], f"gate discovery reads a non-develop ref: {off_ref}"


# ---------------------------------------------------------------------------
# Reachable only AFTER a merge — once per call, never per PR, never dry.
# ---------------------------------------------------------------------------


def test_dispatch_is_guarded_by_the_merge_count(merge_step: dict) -> None:
    # Arrange
    run = merge_step["run"]
    # Act: locate the end of the per-PR merge loop (the first column-0 `done`
    # after `gh pr merge`), the merge-count guard, and the dispatch.
    loop_end_at = run.index("\ndone\n", run.index("gh pr merge"))
    guard_at = run.index('[ "$merges" -gt 0 ]')
    dispatch_at = run.index("gh workflow run")
    # Assert: the guard opens after the merge loop and before the dispatch,
    # so N merges fan out to ONE dispatch round, not N.
    assert loop_end_at < guard_at < dispatch_at, (
        "the dispatch must be guarded on `merges > 0` after the merge loop — "
        "a per-PR or unconditional dispatch is the wrong shape"
    )


def test_dry_run_does_not_dispatch(merge_step: dict) -> None:
    # Arrange
    run = merge_step["run"]
    # Act: the dry-run branch must be decided between the guard and the
    # dispatch — a dry run merges nothing, so firing real CI from it would be
    # dispatching gates for a merge that never happened.
    guarded_block = run[run.index('[ "$merges" -gt 0 ]') : run.index("gh workflow run")]
    # Assert
    assert '"$DRY_RUN" = "true"' in guarded_block


def test_dispatch_failure_is_loud(merge_step: dict) -> None:
    # Arrange
    run = merge_step["run"]
    # Act
    after_guard = run[run.index('[ "$merges" -gt 0 ]') :]
    # Assert: a failed dispatch leaves develop's new head UN-CHECKED — the
    # precise silence this wiring exists to end — so it must go ::error::
    # loud, not vanish into an `|| true`.
    assert "::error::" in after_guard, (
        "a failed gate dispatch must be loud (::error::), not silently "
        "swallowed"
    )


def test_dispatch_failure_reds_the_run(merge_step: dict) -> None:
    # Arrange
    run = merge_step["run"]
    # Act
    after_guard = run[run.index('[ "$merges" -gt 0 ]') :]
    # Assert
    assert "exit 1" in after_guard, "a failed dispatch must red the run"


def test_empty_gate_set_is_an_error_not_a_pass(merge_step: dict) -> None:
    # Arrange
    run = merge_step["run"]
    after_guard = run[run.index('[ "$merges" -gt 0 ]') :]
    # Act: "we merged and found nothing to dispatch" IS the green-by-absence
    # state. A check that could not run must never report what a check that
    # passed reports.
    empty_branch = [
        line
        for line in after_guard.splitlines()
        if "::error::" in line and "NO dispatchable" in line
    ]
    # Assert
    assert empty_branch, (
        "an empty gate set must be a loud error — silently dispatching "
        "nothing reproduces the exact hole this fix closes"
    )


# ---------------------------------------------------------------------------
# The token can actually honour the dispatch.
# ---------------------------------------------------------------------------


def test_workflow_token_may_dispatch(workflow: dict) -> None:
    # Arrange
    permissions = workflow.get("permissions", {})
    # Act: `gh workflow run` needs actions:write; without it every dispatch
    # 403s and the sweep is back to landing un-CI'd commits.
    granted = permissions.get("actions")
    # Assert
    assert granted == "write"


def _call_inputs(workflow: dict) -> dict:
    # YAML 1.1 parses a bare `on:` key as boolean True — read both.
    triggers = workflow.get("on", workflow.get(True, {}))
    return (triggers.get("workflow_call") or {}).get("inputs") or {}


def test_dry_run_input_is_declared(workflow: dict) -> None:
    # Arrange
    doc = workflow
    # Act
    inputs = _call_inputs(doc)
    # Assert
    assert "dry_run" in inputs, "callers cannot request a dry run"


def test_post_merge_gates_input_is_declared(workflow: dict) -> None:
    # Arrange
    doc = workflow
    # Act
    inputs = _call_inputs(doc)
    # Assert
    assert "post_merge_gates" in inputs, (
        "callers cannot override auto-discovery — a repo whose gate names "
        "the deny-list misjudges would have no escape hatch"
    )
