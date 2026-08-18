"""An unpinned toolchain makes a CI result a function of wall-clock time.

With ``setup-uv`` unpinned, the uv binary is whatever was newest when the job
started, and whatever each runner happens to have cached. The same commit then
passes on one node and fails on another, and a run that was green yesterday
goes red overnight with no diff of its own. That is the worst shape a gate can
fail in, because the evidence points at the change under test rather than at
the toolchain underneath it. scitex-agent-container hit exactly this and pinned
deliberately (sac-ci-pin-uv-version-*).

WHY AN INPUT RATHER THAN A PIN IN THIS FILE. Pinning centrally would freeze uv
for all 17+ consumers at once and turn every bump into a coordinated migration.
Leaving it unpinned forces any repo that needs determinism to keep a LOCAL COPY
of this whole workflow — which is precisely the PS-231 duplication this file
exists to remove. An input lets one repo pin without touching the others, the
same shape as ``runs_on``.

THE CONCRETE CASE THIS UNBLOCKS, and the reason it is not hypothetical:
scitex-agent-container's local import-smoke carries ``version: "0.11.29"``.
Converting it to call this reusable — required by PS-231 — would have SILENTLY
UN-PINNED uv. The consolidation would have looked clean, the diff would have
been a deletion, and the determinism would have left with it. That is the same
failure #39 was written to prevent for the console-script assertion: a caller
that drops behaviour is worse than the duplication it removes.

WHAT THIS TEST DOES NOT CLAIM. It pins the WIRING — that the input exists, is
optional, defaults to setup-uv's own default, and is actually threaded into the
step. It does not install uv, and it makes no claim about which version any
consumer should choose.

Mutation-checked: removing the input, changing its default away from "latest",
making it required, or dropping the ``version:`` line from the setup-uv step
each turn at least one test red.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPO / ".github" / "workflows" / "import-smoke.yml"

#: setup-uv's own default. Threading the input with THIS default is what makes
#: the change a no-op for every caller that passes nothing.
_SETUP_UV_DEFAULT = "latest"

_EXPECTED_VERSION_EXPR = "${{ inputs.uv_version }}"

_FORK_GUARD_NAME = "Refuse to run fork-authored code on self-hosted infrastructure"


def _workflow() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _call_inputs(wf: dict) -> dict:
    # PyYAML parses a bare `on:` key as the boolean True, so accept both.
    trigger = wf.get("on", wf.get(True))
    return trigger["workflow_call"]["inputs"]


def _steps(wf: dict) -> list[dict]:
    return wf["jobs"]["import-smoke"]["steps"]


def _setup_uv_step(wf: dict) -> dict:
    return next(s for s in _steps(wf) if "setup-uv" in (s.get("uses") or ""))


def test_the_uv_version_input_is_declared() -> None:
    # Arrange
    wf = _workflow()
    # Act
    inputs = _call_inputs(wf)
    # Assert
    assert "uv_version" in inputs


def test_the_uv_version_input_is_optional() -> None:
    # Arrange
    wf = _workflow()
    # Act
    required = _call_inputs(wf)["uv_version"]["required"]
    # Assert — a required input would break all 17+ existing callers at once,
    # none of which pass it.
    assert required is False


def test_the_uv_version_input_defaults_to_setup_uv_s_own_default() -> None:
    # Arrange
    wf = _workflow()
    # Act
    default = _call_inputs(wf)["uv_version"]["default"]
    # Assert — this exact value is what makes the change a NO-OP for every
    # silent caller. Any other default changes the toolchain under repos that
    # made no decision, which is the thing an unpinned `latest` already does
    # to them once a day.
    assert default == _SETUP_UV_DEFAULT


def test_the_setup_uv_step_actually_consumes_the_input() -> None:
    # Arrange
    wf = _workflow()
    # Act
    version = _setup_uv_step(wf)["with"]["version"]
    # Assert — declaring an input nothing reads is the failure mode that looks
    # exactly like success: a caller pins, CI reports green, and uv is still
    # whatever was newest that morning.
    assert version == _EXPECTED_VERSION_EXPR


def test_the_setup_uv_step_still_caches_on_pyproject() -> None:
    # Arrange
    wf = _workflow()
    # Act
    glob = _setup_uv_step(wf)["with"]["cache-dependency-glob"]
    # Assert — adding a key to `with:` must not displace the existing one.
    assert glob == "pyproject.toml"


def test_adding_the_input_did_not_displace_the_fork_guard() -> None:
    # Arrange
    wf = _workflow()
    steps = _steps(wf)
    # Act
    first = steps[0]
    # Assert — the fork guard MUST remain the first step, ahead of
    # actions/checkout, which is what first puts fork-authored content on the
    # node.
    assert first.get("name") == _FORK_GUARD_NAME
