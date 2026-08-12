"""A release must not merge to ``main`` unless CI passed. Pinned as tests.

The operator's ruling, 2026-08-11::

    リリースのワークフローということですけれど、CI が通らないとマージ
    しちゃだめですよね。明らかに

    — a release workflow must not merge unless CI passes. Obviously.

WHAT THIS REPLACES, measured across scitex-ai on 2026-08-12: 68 repos inline
their own tag-triggered release workflow and **zero** of them read check
state. 45 of those run ``gh pr merge --admin`` on a ``develop -> main`` sync
at tag push — merging to ``main`` with branch protection bypassed and no
greenness test at all. 23 release workflows do mention ``pytest-matrix``, and
every one of those mentions is a COMMENT; not one is a gate.

So the load-bearing artifact of this whole change is a single DAG edge —
``promote: needs: ci`` — plus the caller's ``publish: needs: promote``. A
comment claiming the gate exists is worth nothing (23 repos prove exactly
that), and a reviewer cannot see a *missing* ``needs:`` by reading prose.
These tests pin the edge AS STRUCTURE.

Mutation-checked: deleting ``needs: ci`` from ``promote``, pointing ``ci`` at
something other than the org pytest-matrix reusable, moving the
``gh pr merge --admin`` call into an ungated job, or dropping
``needs: promote`` from the caller's ``publish`` job each turn at least one
test red.

File-only — parses the YAML and asserts on structure and shell text. No
network, no ``gh``, cannot flake.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_PROMOTE = _REPO / ".github" / "workflows" / "promote-develop-to-main-on-tag.yml"
_CALLER = _REPO / "workflow-templates" / "release.yml"

_PYTEST_MATRIX = "scitex-ai/.github/.github/workflows/pytest-matrix.yml@main"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _needs(job: dict) -> list[str]:
    """``needs`` is a string or a list in the schema; normalise to a list."""
    n = job.get("needs", [])
    return [n] if isinstance(n, str) else list(n)


def _shell(job: dict) -> str:
    """Every ``run:`` body in a job, concatenated."""
    return "\n".join(s.get("run", "") for s in job.get("steps", []))


def _merge_invocations(job: dict) -> list[str]:
    """The actual ``gh pr merge`` command lines — not prose that mentions them.

    Written the naive way first (substring search over the whole shell body)
    this reported ``--squash`` present in a job whose only ``--squash`` is the
    comment ``# MERGE commit (NOT --squash, NOT --rebase)`` and an error
    message reading "a squash/rebase merge policy likely rewrote the sha". That
    is the same text-vs-behaviour mistake this file exists to catch in the
    workflows, so it is not repeated here: select the command lines, ignoring
    comments, then assert on those.
    """
    lines = []
    for raw in _shell(job).splitlines():
        line = raw.strip()
        if line.startswith("#") or "gh pr merge" not in line:
            continue
        lines.append(line)
    return lines


@pytest.fixture(scope="module")
def promote() -> dict:
    return _load(_PROMOTE)


@pytest.fixture(scope="module")
def caller() -> dict:
    return _load(_CALLER)


@pytest.fixture(scope="module")
def admin_merging_jobs(promote: dict) -> list[str]:
    """Jobs that admin-merge, found by BEHAVIOUR rather than by job name."""
    return [
        jid
        for jid, job in promote["jobs"].items()
        if "gh pr merge" in _shell(job) and "--admin" in _shell(job)
    ]


# ---------------------------------------------------------------------------
# THE RULING. The merge job must not be reachable while CI is red.
# ---------------------------------------------------------------------------


def test_promote_is_gated_on_ci(promote: dict) -> None:
    """``promote`` cannot start until ``ci`` succeeded. THE ruling, as an edge."""
    # Arrange
    job = promote["jobs"]["promote"]
    # Act
    needs = _needs(job)
    # Assert
    assert "ci" in needs, (
        "promote must declare `needs: ci` — without this edge the merge runs "
        "regardless of CI, which is exactly the 45-repo hazard this replaces"
    )


def test_ci_job_runs_the_org_pytest_matrix(promote: dict) -> None:
    """The gate must be real CI, not a placeholder job that trivially passes."""
    # Arrange
    job = promote["jobs"]["ci"]
    # Act
    called = job.get("uses")
    # Assert
    assert called == _PYTEST_MATRIX


def test_a_job_admin_merges_the_promotion_pr(admin_merging_jobs: list[str]) -> None:
    """Guards the next test: if nothing admin-merges, that test passes vacuously."""
    # Arrange
    expected_minimum = 1
    # Act
    found = len(admin_merging_jobs)
    # Assert
    assert found >= expected_minimum, "expected a job that admin-merges the PR"


def test_admin_merge_lives_only_in_ci_gated_jobs(
    promote: dict, admin_merging_jobs: list[str]
) -> None:
    """``--admin`` bypasses required REVIEW, so it must sit behind the CI edge."""
    # Arrange
    jobs = promote["jobs"]
    # Act
    ungated = [jid for jid in admin_merging_jobs if "ci" not in _needs(jobs[jid])]
    # Assert
    assert ungated == [], (
        f"{ungated} run `gh pr merge --admin` without `needs: ci`"
    )


def test_promotion_merges_with_a_merge_commit(promote: dict) -> None:
    """A merge commit keeps the tag's sha an ancestor of main."""
    # Arrange
    job = promote["jobs"]["promote"]
    # Act
    merging = [line for line in _merge_invocations(job) if "--merge" in line]
    # Assert
    assert len(merging) == len(_merge_invocations(job))


def test_promotion_never_squashes_or_rebases(promote: dict) -> None:
    """Squash mints a new sha, dropping the tag from main — the guard aborts."""
    # Arrange
    job = promote["jobs"]["promote"]
    # Act
    bad = [
        line
        for line in _merge_invocations(job)
        if "--squash" in line or "--rebase" in line
    ]
    # Assert
    assert bad == []


# ---------------------------------------------------------------------------
# Secret blast radius. pytest-matrix.yml's own header WITHDRAWS `secrets:
# inherit`; a release pipeline is the worst place to ignore that.
# ---------------------------------------------------------------------------


def test_ci_job_does_not_inherit_every_secret(promote: dict) -> None:
    """`inherit` would forward CLAUDE_CODE_CREDENTIALS_JSON into CI. It must not."""
    # Arrange
    job = promote["jobs"]["ci"]
    # Act
    secrets = job.get("secrets")
    # Assert
    assert secrets != "inherit", (
        "`secrets: inherit` forwards EVERY secret the calling repo holds into "
        "CI — including credentials nothing here touches. Pass only what the "
        "CI leg consumes."
    )


def test_ci_job_passes_secrets_explicitly(promote: dict) -> None:
    """The narrowed form is a mapping of named secrets."""
    # Arrange
    job = promote["jobs"]["ci"]
    # Act
    secrets = job.get("secrets")
    # Assert
    assert isinstance(secrets, dict)


# ---------------------------------------------------------------------------
# The caller template is what leaf repos copy — its edges matter as much as
# ours, and one of them is the reason the publish job is not centralised.
# ---------------------------------------------------------------------------


def test_caller_builds_only_after_promotion(caller: dict) -> None:
    """The gate reaches the leaf repo through exactly this edge."""
    # Arrange
    job = caller["jobs"]["build"]
    # Act
    needs = _needs(job)
    # Assert
    assert "promote" in needs


def test_caller_calls_the_promote_reusable(caller: dict) -> None:
    # Arrange
    job = caller["jobs"]["promote"]
    # Act
    called = job.get("uses", "")
    # Assert
    assert "promote-develop-to-main-on-tag.yml@main" in called


def test_caller_publish_job_is_not_a_reusable_call(caller: dict) -> None:
    """OIDC forbids centralising this job. The test states WHY, so it survives.

    PyPI Trusted Publishing validates the `job_workflow_ref` claim, which for
    a job inside a reusable workflow names the REUSABLE's repo and path — not
    this repo's. PyPI's expectation is built from the CALLER's repo plus the
    registered filename, so the repo component can never match and the publish
    fails `invalid-publisher`. There is no configuration that fixes it
    (pypi/warehouse#11096, open since 2022).

    Measured 2026-08-12: all 69 tag-triggered publish workflows in this org
    use OIDC and none uses a token secret, so this applies to every repo.

    A future reader WILL see this inline job and think it should be delegated
    like `promote` is. It is a `uses:`-shaped hole on purpose.
    """
    # Arrange
    job = caller["jobs"]["publish"]
    # Act
    called = job.get("uses")
    # Assert
    assert called is None, (
        "the publish job must stay inline in the top-level caller; delegating "
        "it to a cross-repo reusable breaks PyPI trusted publishing for every "
        "repo — see .old/2026-08-12/WHY-THIS-IS-HERE.md"
    )


def test_caller_publish_job_requests_an_oidc_token(caller: dict) -> None:
    """Trusted publishing needs `id-token: write` on the publishing job."""
    # Arrange
    job = caller["jobs"]["publish"]
    # Act
    permissions = job.get("permissions", {})
    # Assert
    assert permissions.get("id-token") == "write"


def test_caller_asserts_tag_is_contained_in_main(caller: dict) -> None:
    """The containment guard is what makes a silent squash loud."""
    # Arrange
    job = caller["jobs"]["publish"]
    # Act
    body = _shell(job)
    # Assert
    assert "merge-base --is-ancestor" in body


def test_caller_containment_guard_loud_fails(caller: dict) -> None:
    """A guard that warns instead of exiting is not a guard."""
    # Arrange
    job = caller["jobs"]["publish"]
    # Act
    body = _shell(job)
    # Assert
    assert "exit 1" in body


def test_caller_release_is_gated_on_a_successful_publish(caller: dict) -> None:
    """No Release tag-page for a version that never reached the index."""
    # Arrange
    job = caller["jobs"]["release"]
    # Act
    needs = _needs(job)
    # Assert
    assert "publish" in needs


def test_caller_triggers_on_version_tags(caller: dict) -> None:
    # Arrange: `on` parses as the YAML boolean True unless quoted.
    on = caller.get("on", caller.get(True))
    # Act
    tags = on["push"]["tags"]
    # Assert
    assert tags == ["v*"]


def test_caller_triggers_on_nothing_but_a_push(caller: dict) -> None:
    """A branch push must not be able to fire a release."""
    # Arrange
    on = caller.get("on", caller.get(True))
    # Act
    events = list(on)
    # Assert
    assert events == ["push"]
