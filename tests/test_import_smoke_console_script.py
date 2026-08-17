"""``import <pkg>`` passing does not mean the package's COMMAND works.

Entry-point drift — a renamed module or callable behind ``[project.scripts]``
— leaves the import green and breaks every caller that invokes the command.
For containerised packages that command IS the runtime surface, so the failure
lands in production while CI stays green.

``import-smoke`` is the only job in the org that installs into a venv, and a
venv install DOES materialise entry-point scripts in ``.venv/bin`` (unlike
``pip install --target``, which does not). So it is the only place the
assertion is even possible, which is why it belongs here rather than in a
consumer's own workflow.

WHY THIS TEST EXISTS AND NOT JUST THE STEP. scitex-agent-container carried this
assertion in a LOCAL copy of import-smoke, and that copy was one of five
workflows flagged by PS-231 as re-implementing an org reusable. Deleting the
local copy to satisfy PS-231 would have silently dropped the coverage — the
consolidation would have looked clean and removed a real gate. The capability
moved upstream instead, and this file is what stops it being "simplified" back
out by someone who reads the step as redundant with the import above it.

WHAT THIS TEST DOES NOT CLAIM. It pins the WIRING — that the input exists,
defaults to off, and that the step is gated on it. It does not run the step;
whether a given package's console script actually resolves is that package's
CI result, not this repo's.

Mutation-checked: removing the input, changing its default to a non-empty
string, dropping the ``if:`` gate, or moving the step ahead of the install
each turn at least one test red.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPO / ".github" / "workflows" / "import-smoke.yml"

#: Pinned as one string: the gate and the input name must agree, and two
#: spellings that drift apart is a step that silently never runs.
_GATE_IF = "inputs.console_script != ''"

_FORK_GUARD_NAME = "Refuse to run fork-authored code on self-hosted infrastructure"


def _workflow() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _call_inputs(wf: dict) -> dict:
    # PyYAML parses a bare `on:` key as the boolean True, so accept both.
    trigger = wf.get("on", wf.get(True))
    return trigger["workflow_call"]["inputs"]


def _steps(wf: dict) -> list[dict]:
    return wf["jobs"]["import-smoke"]["steps"]


def test_the_console_script_input_is_declared() -> None:
    # Arrange
    wf = _workflow()
    # Act
    inputs = _call_inputs(wf)
    # Assert
    assert "console_script" in inputs


def test_the_console_script_input_defaults_to_off() -> None:
    # Arrange
    wf = _workflow()
    # Act
    default = _call_inputs(wf)["console_script"]["default"]
    # Assert — MUST be empty. A non-empty default would assert something about
    # every package in the org, including those that ship no console script,
    # and they would go red on a change they did not make.
    assert default == ""


def test_the_console_script_input_is_optional() -> None:
    # Arrange
    wf = _workflow()
    # Act
    required = _call_inputs(wf)["console_script"]["required"]
    # Assert
    assert required is False


def test_exactly_one_step_is_gated_on_the_console_script_input() -> None:
    # Arrange
    wf = _workflow()
    # Act
    gated = [s for s in _steps(wf) if s.get("if") == _GATE_IF]
    # Assert — zero means the step runs for every caller, breaking packages
    # with no console script; more than one means the gate has been copied and
    # the copies can drift apart.
    assert len(gated) == 1, [s.get("name") for s in _steps(wf)]


def test_the_gated_step_is_the_console_script_step() -> None:
    # Arrange
    wf = _workflow()
    # Act
    gated = [s for s in _steps(wf) if s.get("if") == _GATE_IF]
    # Assert — guards against the gate migrating onto some unrelated step,
    # which would leave the console-script assertion running unconditionally.
    assert "console_script" in (gated[0].get("name") or "")


def test_the_console_script_step_runs_after_the_install() -> None:
    # Arrange
    wf = _workflow()
    steps = _steps(wf)
    # Act
    install_at = next(
        i for i, s in enumerate(steps) if "import" in (s.get("name") or "").lower()
    )
    script_at = next(i for i, s in enumerate(steps) if s.get("if") == _GATE_IF)
    # Assert — the venv must exist before .venv/bin/<name> can be executed, so
    # ordering here is correctness and not style.
    assert script_at > install_at


def test_adding_the_step_did_not_displace_the_fork_guard() -> None:
    # Arrange
    wf = _workflow()
    steps = _steps(wf)
    # Act
    first = steps[0]
    # Assert — the fork guard MUST remain the first step, ahead of
    # actions/checkout, which is what first puts fork-authored content on the
    # node. Appending a step is safe; this asserts that a future edit which
    # reorders the list to accommodate one is not.
    assert first.get("name") == _FORK_GUARD_NAME
