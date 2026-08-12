"""The reusable nightly must be able to tell someone it failed.

WHY THIS EXISTS. Measured 2026-08-12 across the 22 repos carrying the SIF CI
shim: **20 of them had at least one nightly whose latest run failed**, 52
failing repo/workflow pairs, 2 fully green. The case that forced it was
``scitex-agent-container``, whose ``main`` failed its nightly on seven
consecutive nights (Aug 5-11) — every leg, zero tests executed, each time at
``mkdir: cannot create directory '/data': Permission denied`` — and told
nobody, because that workflow had no failure reporting of any kind.

Seven days of silence was evidence about the DETECTOR, not about the code.

THE SHARP EDGE THIS FILE POLICES. A called workflow's token can never exceed
the CALLER's grant. ``pytest-matrix.yml`` declares ``issues: write`` on its
alarm job, but only RECEIVES it if the caller stub passes it down. A stub
without that grant produces the worst possible failure shape: an alarm that
looks configured, probes green every night, and cannot file on the one night it
is needed. So the grant is asserted here, mechanically, on the stub every repo
copies.

MUTATION CONTROLS. ``test_mutant_*`` strip the alarm or the grant out of an
in-memory copy and assert the rule notices. A rule that cannot be shown to fail
proves nothing about the green.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_REUSABLE = _ROOT / ".github" / "workflows" / "pytest-matrix.yml"
_STUB = _ROOT / "workflow-templates" / "pytest-matrix.yml"

# The job that runs the suite inside the reusable workflow, and the job id the
# caller stub must not rename (it is the branch-protection context prefix).
_SUITE_JOB = "pytest-matrix"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _jobs(wf: dict) -> dict:
    return wf.get("jobs") or {}


def _needs(job: dict) -> list[str]:
    n = job.get("needs")
    return [n] if isinstance(n, str) else list(n or [])


def _can_report(job: dict) -> bool:
    perms = job.get("permissions") or {}
    return isinstance(perms, dict) and perms.get("issues") == "write"


def alarm_violations(reusable: dict, stub: dict) -> list[str]:
    """THE RULE. Empty list == a red night reaches a human."""
    problems: list[str] = []

    alarms = [
        jid
        for jid, job in _jobs(reusable).items()
        if jid != _SUITE_JOB and _can_report(job) and _SUITE_JOB in _needs(job)
    ]
    if not alarms:
        problems.append(
            f"reusable workflow has no job depending on `{_SUITE_JOB}` with "
            "`issues: write` — a failed nightly reports to nobody"
        )

    # The grant the caller must pass down; without it the alarm above is inert.
    granted = (_jobs(stub).get(_SUITE_JOB) or {}).get("permissions") or {}
    if granted.get("issues") != "write":
        problems.append(
            "caller stub does not grant `issues: write`, so the alarm inside the "
            f"reusable workflow cannot file (got {granted!r})"
        )
    return problems


@pytest.fixture(scope="module")
def reusable() -> dict:
    return _load(_REUSABLE)


@pytest.fixture(scope="module")
def stub() -> dict:
    return _load(_STUB)


@pytest.fixture(scope="module")
def alarm(reusable) -> dict:
    return _jobs(reusable)["notify"]


# --------------------------------------------------------------------------
# The rule.
# --------------------------------------------------------------------------


def test_a_red_night_reaches_a_human(reusable, stub):
    # Arrange
    pair = (reusable, stub)
    # Act
    problems = alarm_violations(*pair)
    # Assert
    assert not problems, f"nightly cannot report its own failure: {problems}"


# --------------------------------------------------------------------------
# The alarm job inside the reusable workflow.
# --------------------------------------------------------------------------


def test_alarm_observes_the_suite(alarm):
    # Arrange
    job = alarm
    # Act
    needs = _needs(job)
    # Assert
    assert _SUITE_JOB in needs, f"alarm does not observe the suite job: {needs}"


def test_alarm_fires_for_the_nightly_cron(alarm):
    """A cron failure is the case with no human already looking at it."""
    # Arrange
    cond = " ".join(str(alarm.get("if") or "").split())
    # Act
    covers_cron = "schedule" in cond
    # Assert
    assert covers_cron, f"alarm never fires for the nightly cron: {cond!r}"


def test_alarm_also_runs_on_green_nights(alarm):
    """`always()`, so a dead alarm surfaces on a quiet night rather than via the
    first regression that goes unreported. This is what makes silence mean green."""
    # Arrange
    cond = " ".join(str(alarm.get("if") or "").split())
    # Act
    unconditional = cond.startswith("always()")
    # Assert
    assert unconditional, f"alarm only runs when already failing: {cond!r}"


def test_alarm_runner_is_separately_configurable(alarm):
    """An alarm ideally does not share fate with what it reports on: a wholly
    wedged pool silences it exactly when it is needed.

    This asserts the CAPABILITY, not a hosted default. The default deliberately
    matches the suite's pool — `tests/test_fork_guard.py` here forbids hosted
    images citing 2026-07-14, while the `runs_on` input cites a later
    (2026-07-31) ruling making hosted the default for new work, and that
    contradiction is an operator's to resolve rather than something to settle by
    editing the guard that blocks you. It is also not urgent: across the seven
    silent nights that motivated this alarm the runner was ALIVE every time and
    the job failed inside it, so a same-pool alarm would have fired on all seven.
    """
    # Arrange
    runs_on = str(alarm.get("runs-on") or "")
    # Act
    configurable = "inputs.alarm_runs_on" in runs_on
    # Assert
    assert configurable, (
        f"alarm runner is hardcoded, so a caller cannot decouple it: {runs_on!r}"
    )


def test_alarm_aborts_on_a_failed_report(alarm):
    """`set -e`. Without it a failing `gh issue comment` is masked by the next
    command's exit 0 and the step goes green having reported nothing."""
    # Arrange
    script = "\n".join(str(s.get("run") or "") for s in alarm["steps"])
    # Act
    strict = "set -euo pipefail" in script
    # Assert
    assert strict, "alarm script does not use `set -euo pipefail`"


def test_alarm_verifies_an_open_issue_exists_afterwards(alarm):
    """"exited 0" and "an open issue now exists" are different claims, and only
    the second one is the alarm having worked."""
    # Arrange
    script = "\n".join(str(s.get("run") or "") for s in alarm["steps"])
    # Act
    checks = "--state open" in script and "ALARM FAILED SILENTLY" in script
    # Assert
    assert checks, "alarm never confirms an open issue exists after reporting"


def test_alarm_files_one_issue_per_fault_not_one_per_night(alarm):
    """30 identical issues a month teaches everyone to filter it, which is the
    same as not reporting."""
    # Arrange
    script = "\n".join(str(s.get("run") or "") for s in alarm["steps"])
    # Act
    dedupes = "gh issue reopen" in script and "gh issue comment" in script
    # Assert
    assert dedupes, "alarm does not reuse an existing issue"


# --------------------------------------------------------------------------
# The caller stub — where the permission has to come from.
# --------------------------------------------------------------------------


def test_stub_grants_the_permission_the_alarm_needs(stub):
    # Arrange
    job = _jobs(stub).get(_SUITE_JOB) or {}
    # Act
    perms = job.get("permissions") or {}
    # Assert
    assert perms.get("issues") == "write", (
        f"stub must pass `issues: write` down or the alarm cannot file: {perms!r}"
    )


def test_stub_keeps_contents_read_after_naming_a_permission(stub):
    """Naming ANY permission drops every unnamed one to `none`, so the checkout
    inside the reusable workflow needs `contents: read` restored explicitly."""
    # Arrange
    job = _jobs(stub).get(_SUITE_JOB) or {}
    # Act
    perms = job.get("permissions") or {}
    # Assert
    assert perms.get("contents") == "read", (
        f"stub names permissions but drops `contents: read`: {perms!r}"
    )


def test_stub_still_calls_the_reusable_workflow(stub):
    """Guards the fixture: a stub that stopped calling it would pass the
    permission assertions above while testing nothing."""
    # Arrange
    job = _jobs(stub).get(_SUITE_JOB) or {}
    # Act
    uses = str(job.get("uses") or "")
    # Assert
    assert uses.startswith("scitex-ai/.github/.github/workflows/pytest-matrix.yml"), (
        f"stub no longer calls the reusable workflow: {uses!r}"
    )


# --------------------------------------------------------------------------
# Mutation controls.
# --------------------------------------------------------------------------


def test_mutant_reusable_without_an_alarm_is_reported(reusable, stub):
    # Arrange
    mutant = copy.deepcopy(reusable)
    # Act
    del mutant["jobs"]["notify"]
    # Assert
    assert alarm_violations(mutant, stub), (
        "removing the alarm produced NO violation — the rule is not what makes "
        "the passing tests above pass"
    )


def test_mutant_alarm_without_report_permission_is_reported(reusable, stub):
    """A job named `notify` that cannot open an issue is decoration."""
    # Arrange
    mutant = copy.deepcopy(reusable)
    # Act
    mutant["jobs"]["notify"]["permissions"] = {"contents": "read"}
    # Assert
    assert alarm_violations(mutant, stub), (
        "an alarm stripped of `issues: write` was still accepted"
    )


def test_mutant_alarm_not_wired_to_the_suite_is_reported(reusable, stub):
    # Arrange
    mutant = copy.deepcopy(reusable)
    # Act
    mutant["jobs"]["notify"]["needs"] = []
    # Assert
    assert alarm_violations(mutant, stub), (
        "an alarm observing nothing was still accepted"
    )


def test_mutant_stub_without_the_grant_is_reported(reusable, stub):
    """THE failure shape this file exists for: the alarm is present and correct,
    and inert, because the caller never passed the permission down."""
    # Arrange
    mutant = copy.deepcopy(stub)
    # Act
    del mutant["jobs"][_SUITE_JOB]["permissions"]
    # Assert
    assert alarm_violations(reusable, mutant), (
        "a stub that grants nothing was accepted — the alarm would probe green "
        "every night and fail on the one night it was needed"
    )
