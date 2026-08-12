"""Every self-hosted job that checks out a pull request must refuse fork code.

These jobs run BARE on shared University of Melbourne HPC nodes — no
container, no overlay, two concurrent jobs sharing one ``$HOME`` (measured by
scitex-hpc on the CI supervisor allocation, job 28161762, spartan-bm062). So
``actions/checkout`` followed by ``uv pip install -e .`` executes a pull
request's own build-backend hooks on university hardware, and for
``rtd-sphinx-build`` the fork's ``conf.py`` is executed as plain Python.

Two operator mandates constrain the fix and they point in opposite
directions:

    2026-07-14  「PR用のテストとgithub側のランナーというのは本当にもう一切
                  使わないでください…強制です、例外なしです」
                — never use GitHub-hosted runners, no exceptions (PS-169).
    2026-07-30  「大学の資源を外部の人にも使わせる形になったら一発でアウト」
                — external people using university resources is unacceptable.

Together they leave no runner for fork-authored code, so a fork PR is not
re-routed anywhere: it is REFUSED, before checkout.

WHICH WORKFLOWS ARE COVERED IS DERIVED, NOT LISTED. The suite reads every
workflow, selects the jobs that (a) resolve to a self-hosted runner and
(b) contain an ``actions/checkout`` step, and requires the guard on exactly
those. A new self-hosted workflow that checks out a PR therefore fails these
tests on the change that introduces it, which is the point — a hardcoded
list would go stale silently and this file would keep passing.

``cla.yml`` is excluded by that predicate rather than by an exemption: its
jobs are self-hosted but check out nothing (measured 2026-07-30 on
scitex-app), so no fork code runs there.

WHAT THESE TESTS DO NOT CLAIM. For ``pull_request``, GitHub runs the
workflow definition from the PR's own head, so a hostile fork can edit a
CALLER's ci.yml to bypass these reusable workflows entirely and declare its
own self-hosted job. The guard closes the DEFAULT path; the actual boundary
is the fork-PR approval policy (``all_external_contributors``, measured on
74/74 public scitex-ai repos, 2026-07-30) — a human click. Do not read a
green run here as "forks cannot reach the pool".

Mutation-checked: moving the guard after ``actions/checkout``, deleting it
from any one workflow, dropping the ``exit 1``, or relaxing the predicate to
``head.repo.fork`` each turn at least one test red.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOW_DIR = _REPO / ".github" / "workflows"

#: The one sanctioned predicate. Folded from the workflows' ``if: >-`` block,
#: so newlines have already become single spaces by the time yaml hands it
#: over. Pinned as one string on purpose: five copies of a predicate that
#: drift apart is five different answers to "is this a fork?".
_GUARD_IF = (
    "github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name != github.repository"
)

_GUARD_NAME = "Refuse to run fork-authored code on self-hosted infrastructure"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _runs_on_labels(job: dict) -> list[str]:
    """Flatten the two ``runs-on`` spellings this repo uses into labels."""
    runs_on = job.get("runs-on", "")
    if isinstance(runs_on, dict):  # {labels: [...]} form
        runs_on = runs_on.get("labels", [])
    if isinstance(runs_on, str):
        runs_on = [runs_on]
    return [str(label) for label in runs_on]


def _may_run_self_hosted(job: dict) -> bool:
    """True when this job CAN land on a self-hosted runner.

    A literal ``self-hosted`` label is the easy case. The hard case is a
    parameterised ``runs-on: ${{ fromJSON(inputs.runs_on) }}``, whose value is
    not knowable until a caller supplies it — and whose DEFAULT here is the
    Spartan pool. Statically it could be either, so this answers YES.

    ERRING TOWARDS GUARDED IS THE ONLY SAFE DIRECTION. A false yes costs one
    unnecessary guard step on a hosted runner, where it is harmless. A false NO
    silently drops the job out of :func:`_guarded_jobs`, so the fork guard
    becomes unenforced AND untested at the same moment — the check keeps
    passing while the protection is gone. Parameterising ``runs-on`` did
    exactly that on 2026-07-31, and these tests caught it.
    """
    labels = _runs_on_labels(job)
    if "self-hosted" in labels:
        return True
    return any("${{" in label for label in labels)


def _checks_out(job: dict) -> bool:
    return any(
        "actions/checkout" in str(step.get("uses", "")) for step in job.get("steps", [])
    )


def _guarded_jobs() -> list[tuple[str, str, dict]]:
    """(workflow filename, job id, job) for every job that needs the guard.

    Selected by behaviour — self-hosted AND checks out — so the set tracks
    the workflows instead of being asserted alongside them.
    """
    found: list[tuple[str, str, dict]] = []
    for path in sorted(_WORKFLOW_DIR.glob("*.yml")):
        for job_id, job in (_load(path).get("jobs") or {}).items():
            if _may_run_self_hosted(job) and _checks_out(job):
                found.append((path.name, job_id, job))
    return found


_TARGETS = _guarded_jobs()
_IDS = [f"{workflow}:{job_id}" for workflow, job_id, _ in _TARGETS]


# ---------------------------------------------------------------------------
# The selector itself has to be right, or every test below vacuously passes.
# An empty parametrize list reports SKIPPED, and a suite of skips reads as a
# pass in CI. This is the positive control for the whole file.
# ---------------------------------------------------------------------------


def test_selector_finds_the_known_self_hosted_checkout_jobs() -> None:
    # Arrange
    minimum_known_today = 5
    # Act
    found = len(_TARGETS)
    # Assert
    assert found >= minimum_known_today, (
        f"selector found only {_IDS} — it is broken, not the fleet"
    )


def test_selector_includes_the_pytest_matrix_job() -> None:
    # Arrange
    expected = "pytest-matrix.yml:pytest-matrix"
    # Act
    selected = _IDS
    # Assert
    assert expected in selected


def test_selector_excludes_cla_which_checks_out_nothing() -> None:
    # Arrange
    excluded_prefix = "cla.yml"
    # Act
    cla_jobs = [i for i in _IDS if i.startswith(excluded_prefix)]
    # Assert
    assert not cla_jobs


# ---------------------------------------------------------------------------
# The guard is present, first, and fails closed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("workflow", "job_id", "job"), _TARGETS, ids=_IDS)
def test_guard_step_is_present(workflow: str, job_id: str, job: dict) -> None:
    # Arrange
    steps = job["steps"]
    # Act
    names = [step.get("name") for step in steps]
    # Assert
    assert _GUARD_NAME in names, f"{workflow}:{job_id} has no fork guard"


@pytest.mark.parametrize(("workflow", "job_id", "job"), _TARGETS, ids=_IDS)
def test_guard_step_precedes_every_checkout(
    workflow: str, job_id: str, job: dict
) -> None:
    # Arrange
    steps = job["steps"]
    # Act
    guard_at = next(
        i for i, step in enumerate(steps) if step.get("name") == _GUARD_NAME
    )
    first_checkout_at = next(
        i
        for i, step in enumerate(steps)
        if "actions/checkout" in str(step.get("uses", ""))
    )
    # Assert
    assert guard_at < first_checkout_at, (
        f"{workflow}:{job_id} guards AFTER checkout — fork content is already "
        "on the node by then, so the step is a report, not a barrier"
    )


@pytest.mark.parametrize(("workflow", "job_id", "job"), _TARGETS, ids=_IDS)
def test_guard_predicate_is_the_sanctioned_one(
    workflow: str, job_id: str, job: dict
) -> None:
    # Arrange
    guard = next(s for s in job["steps"] if s.get("name") == _GUARD_NAME)
    # Act
    normalised = " ".join(str(guard.get("if", "")).split())
    # Assert
    assert normalised == _GUARD_IF, f"{workflow}:{job_id} predicate drifted"


@pytest.mark.parametrize(("workflow", "job_id", "job"), _TARGETS, ids=_IDS)
def test_guard_exits_nonzero_rather_than_skipping(
    workflow: str, job_id: str, job: dict
) -> None:
    # Arrange
    guard = next(s for s in job["steps"] if s.get("name") == _GUARD_NAME)
    # Act
    body = guard.get("run", "")
    # Assert
    assert "exit 1" in body, (
        f"{workflow}:{job_id} guard does not fail. A skipped job's check can be "
        "reported as successful to branch protection — a red that looks green"
    )


@pytest.mark.parametrize(("workflow", "job_id", "job"), _TARGETS, ids=_IDS)
def test_guard_tells_the_reviewer_what_to_do_instead(
    workflow: str, job_id: str, job: dict
) -> None:
    # Arrange
    guard = next(s for s in job["steps"] if s.get("name") == _GUARD_NAME)
    # Act
    body = guard.get("run", "")
    # Assert
    assert "gh pr checkout" in body, (
        f"{workflow}:{job_id} guard states the refusal without the remedy; "
        "an error that only says what broke is half-written"
    )


# ---------------------------------------------------------------------------
# The mandate the guard exists to honour: no job here may resolve to a
# GitHub-hosted image. Asserted locally so a future 'just route forks to
# ubuntu-latest' cannot land quietly in this repo.
# ---------------------------------------------------------------------------


_HOSTED_PREFIXES = ("ubuntu-", "macos-", "windows-")
_ALL_JOBS = [
    (path.name, job_id, job)
    for path in sorted(_WORKFLOW_DIR.glob("*.yml"))
    for job_id, job in (_load(path).get("jobs") or {}).items()
]


@pytest.mark.parametrize(
    ("workflow", "job_id", "job"),
    _ALL_JOBS,
    ids=[f"{w}:{j}" for w, j, _ in _ALL_JOBS],
)
def test_no_job_targets_a_github_hosted_image(
    workflow: str, job_id: str, job: dict
) -> None:
    # Arrange
    labels = _runs_on_labels(job)
    # Act
    hosted = [label for label in labels if label.startswith(_HOSTED_PREFIXES)]
    # Assert
    assert not hosted, (
        f"{workflow}:{job_id} targets {hosted}. Operator mandate 2026-07-14 "
        "(PS-169) forbids GitHub-hosted runners with no exceptions; if the "
        "self-hosted pool cannot run it, fix the pool"
    )
