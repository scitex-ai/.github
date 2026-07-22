"""The org rtd-sphinx-build reusable must actually FIND the org's docs.

The shipped version probed only ``docs/conf.py``, ``docs/source/conf.py`` and
``docs/src/conf.py``, then ``exit 0``d when it found none. Measured across
scitex-ai on 2026-07-22 (74 repos enumerated via the git-trees API, every
``conf.py`` path in every default branch): 66 repos keep conf.py at
``docs/sphinx/conf.py``, 1 at ``docs/sphinx/source/conf.py``, 8 ship none, and
ZERO use any of the three probed paths. 15 repos already call the reusable, so
in 15 of 15 the gate matched nothing and exited 0 — green while building no
documentation at all. scitex-agent-container's own workflow documents its
refusal to adopt the reusable for exactly this reason.

Two properties close it and both are pinned here: the org path is found, and a
miss is a HARD FAILURE unless the caller explicitly opts out.

The discovery block is EXECUTED, not just grepped — these tests slice the real
shell body out of the real workflow file and run it under bash against a real
temp tree. No stubs, no network, no gh; the slice stops before the uv/sphinx
steps so nothing needs installing.

Mutation-checked — each of these turns at least one test red:
  * drop ``docs/sphinx/conf.py`` from CANDIDATES
  * drop ``$DOCS_DIR/conf.py`` from CANDIDATES
  * revert the miss branch to ``exit 0``
  * flip the ``required`` input default to false
  * make the opt-out silent (drop the ::warning::)
  * drop the searched-paths / opt-out remediation echoes
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_RTD = _REPO / ".github" / "workflows" / "rtd-sphinx-build.yml"

# The discovery block runs from the top of the step body up to and including
# the line that reports a hit. Everything after it is the uv/sphinx install,
# which needs a network and a runner.
_END_MARKER = 'echo "found sphinx conf.py at $CONF"'


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(_RTD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def build_step(workflow: dict) -> dict:
    """The step that discovers conf.py (found by behaviour, not by name)."""
    steps = workflow["jobs"]["docs-sphinx"]["steps"]
    building = [s for s in steps if "sphinx-build" in s.get("run", "")]
    assert len(building) == 1, "expected exactly one sphinx-building step"
    return building[0]


@pytest.fixture(scope="module")
def discovery_script(build_step: dict) -> str:
    run = build_step["run"]
    assert _END_MARKER in run, (
        "cannot locate the end of the discovery block — if the workflow was "
        "restructured, update _END_MARKER so these tests keep executing the "
        "real shell rather than silently testing nothing"
    )
    return run[: run.index(_END_MARKER) + len(_END_MARKER)]


@pytest.fixture(scope="module")
def call_inputs(workflow: dict) -> dict:
    # YAML 1.1 parses a bare `on:` key as boolean True — read both.
    triggers = workflow.get("on", workflow.get(True, {}))
    return (triggers.get("workflow_call") or {}).get("inputs") or {}


def _run(
    script: str, cwd: Path, docs_dir: str, required: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin", "DOCS_DIR": docs_dir, "DOCS_REQUIRED": required},
        capture_output=True,
        text=True,
    )


def _tree(factory: pytest.TempPathFactory, name: str, *relpaths: str) -> Path:
    root = factory.mktemp(name)
    for rel in relpaths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("project = 'x'\n", encoding="utf-8")
    return root


def _output(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# Scenario fixtures. Each runs the REAL discovery shell once against a real
# tree; the tests below assert one property each on the result.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def org_layout(
    discovery_script: str, tmp_path_factory: pytest.TempPathFactory
) -> subprocess.CompletedProcess:
    """The layout 66 of 74 scitex-ai repos actually use."""
    root = _tree(tmp_path_factory, "org", "docs/sphinx/conf.py")
    return _run(discovery_script, root, "docs/sphinx", "true")


@pytest.fixture(scope="module")
def org_layout_via_fallback(
    discovery_script: str, tmp_path_factory: pytest.TempPathFactory
) -> subprocess.CompletedProcess:
    """The org layout, reached WITHOUT docs_dir pointing at it.

    ``docs_dir`` here names a directory that does not exist, so a hit can only
    come from ``docs/sphinx/conf.py`` being in the hardcoded fallback list.
    Without this case the org path is masked by the default value of the
    input, and deleting it from CANDIDATES leaves the suite green — which is
    precisely the mutation that survived the first run of the harness.
    """
    root = _tree(tmp_path_factory, "fallback", "docs/sphinx/conf.py")
    return _run(discovery_script, root, "no/such/dir", "true")


@pytest.fixture(scope="module")
def legacy_layout(
    discovery_script: str, tmp_path_factory: pytest.TempPathFactory
) -> subprocess.CompletedProcess:
    """An old-layout repo must not break when the default moves."""
    root = _tree(tmp_path_factory, "legacy", "docs/source/conf.py")
    return _run(discovery_script, root, "docs/sphinx", "true")


@pytest.fixture(scope="module")
def custom_layout(
    discovery_script: str, tmp_path_factory: pytest.TempPathFactory
) -> subprocess.CompletedProcess:
    """A layout NO built-in candidate matches — only the input can find it."""
    root = _tree(tmp_path_factory, "custom", "documentation/manual/conf.py")
    return _run(discovery_script, root, "documentation/manual", "true")


@pytest.fixture(scope="module")
def custom_over_legacy(
    discovery_script: str, tmp_path_factory: pytest.TempPathFactory
) -> subprocess.CompletedProcess:
    """Both present — the caller's explicit choice must win."""
    root = _tree(
        tmp_path_factory, "both", "docs/sphinx/source/conf.py", "docs/sphinx/conf.py"
    )
    return _run(discovery_script, root, "docs/sphinx/source", "true")


@pytest.fixture(scope="module")
def missing_required(
    discovery_script: str, tmp_path_factory: pytest.TempPathFactory
) -> subprocess.CompletedProcess:
    """An empty tree — exactly what all 40 calling repos presented."""
    root = _tree(tmp_path_factory, "missing")
    return _run(discovery_script, root, "docs/sphinx", "true")


@pytest.fixture(scope="module")
def missing_opted_out(
    discovery_script: str, tmp_path_factory: pytest.TempPathFactory
) -> subprocess.CompletedProcess:
    """No docs anywhere, and the caller declared it ships none."""
    root = _tree(tmp_path_factory, "optout")
    return _run(discovery_script, root, "docs/sphinx", "false")


# ---------------------------------------------------------------------------
# PROPERTY 1 — the org's actual layout is found. 66 of 74 repos depend on it.
# ---------------------------------------------------------------------------


def test_org_layout_succeeds(org_layout: subprocess.CompletedProcess) -> None:
    # Arrange
    proc = org_layout
    # Act
    rc = proc.returncode
    # Assert
    assert rc == 0, _output(proc)


def test_docs_sphinx_conf_py_is_the_path_found(
    org_layout: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = org_layout
    # Act
    out = _output(proc)
    # Assert
    assert "found sphinx conf.py at docs/sphinx/conf.py" in out, out


def test_org_layout_is_found_without_docs_dir_pointing_at_it(
    org_layout_via_fallback: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = org_layout_via_fallback
    # Act
    out = _output(proc)
    # Assert: docs/sphinx/conf.py must be a hardcoded fallback in its own
    # right, not merely the value the docs_dir input happens to default to.
    assert "found sphinx conf.py at docs/sphinx/conf.py" in out, out


def test_org_layout_via_fallback_succeeds(
    org_layout_via_fallback: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = org_layout_via_fallback
    # Act
    rc = proc.returncode
    # Assert
    assert rc == 0, _output(proc)


def test_legacy_layout_still_succeeds(
    legacy_layout: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = legacy_layout
    # Act
    rc = proc.returncode
    # Assert
    assert rc == 0, _output(proc)


def test_legacy_layout_resolves_to_its_own_path(
    legacy_layout: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = legacy_layout
    # Act
    out = _output(proc)
    # Assert
    assert "found sphinx conf.py at docs/source/conf.py" in out, out


# ---------------------------------------------------------------------------
# PROPERTY 2 — a caller can point the gate at its own layout instead of
# forking the workflow. Zero-input reusables are the documented cause of the
# 75-variant rtd-sphinx sprawl.
# ---------------------------------------------------------------------------


def test_docs_dir_input_is_declared(call_inputs: dict) -> None:
    # Arrange
    inputs = call_inputs
    # Act
    spec = inputs.get("docs_dir")
    # Assert
    assert spec is not None, "callers cannot override the docs directory"


def test_docs_dir_defaults_to_the_org_convention(call_inputs: dict) -> None:
    # Arrange
    spec = call_inputs.get("docs_dir") or {}
    # Act
    default = spec.get("default")
    # Assert: the 66 repos on the convention must need no `with:` block at all.
    assert default == "docs/sphinx"


def test_custom_docs_dir_succeeds(custom_layout: subprocess.CompletedProcess) -> None:
    # Arrange
    proc = custom_layout
    # Act
    rc = proc.returncode
    # Assert
    assert rc == 0, _output(proc)


def test_custom_docs_dir_is_the_path_found(
    custom_layout: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = custom_layout
    # Act
    out = _output(proc)
    # Assert: only the input could have produced this hit.
    assert "found sphinx conf.py at documentation/manual/conf.py" in out, out


def test_custom_docs_dir_wins_over_the_legacy_fallbacks(
    custom_over_legacy: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = custom_over_legacy
    # Act
    out = _output(proc)
    # Assert: otherwise the input is decorative whenever a legacy dir exists.
    assert "found sphinx conf.py at docs/sphinx/source/conf.py" in out, out


# ---------------------------------------------------------------------------
# PROPERTY 3 — a missing conf.py FAILS. This is the whole defect: a gate that
# cannot fail is not a gate, and a skip must never be reported as a pass.
# ---------------------------------------------------------------------------


def test_required_input_is_declared(call_inputs: dict) -> None:
    # Arrange
    inputs = call_inputs
    # Act
    spec = inputs.get("required")
    # Assert
    assert spec is not None, "no opt-out input declared"


def test_required_defaults_to_true(call_inputs: dict) -> None:
    # Arrange
    spec = call_inputs.get("required") or {}
    # Act
    default = spec.get("default")
    # Assert: defaulting to false would ship the green no-op under a new name.
    assert default is True


def test_missing_conf_py_fails_by_default(
    missing_required: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = missing_required
    # Act
    rc = proc.returncode
    # Assert
    assert rc != 0, (
        "a missing conf.py exited 0 — this is the green-no-op defect: the job "
        "reports success having built no documentation whatsoever"
    )


@pytest.mark.parametrize(
    "searched",
    [
        "docs/sphinx/conf.py",
        "docs/conf.py",
        "docs/source/conf.py",
        "docs/src/conf.py",
    ],
)
def test_failure_names_every_path_it_searched(
    missing_required: subprocess.CompletedProcess, searched: str
) -> None:
    # Arrange
    proc = missing_required
    # Act
    out = _output(proc)
    # Assert: "not found" without WHERE IT LOOKED is unactionable.
    assert searched in out, f"failure message never names {searched}: {out}"


@pytest.mark.parametrize(
    "fragment",
    [
        "docs_dir:",
        "required: false",
        "rtd-sphinx-build.yml@main",
    ],
)
def test_failure_hint_is_executable_as_printed(
    missing_required: subprocess.CompletedProcess, fragment: str
) -> None:
    # Arrange
    proc = missing_required
    # Act
    out = _output(proc)
    # Assert: both escape hatches, under a pasteable `uses:` line.
    assert fragment in out, f"remediation hint never mentions {fragment}: {out}"


# ---------------------------------------------------------------------------
# PROPERTY 4 — the opt-out works, and is LOUD. A repo that genuinely ships no
# docs may pass, but its log must never look like a real build.
# ---------------------------------------------------------------------------


def test_opt_out_allows_the_skip(
    missing_opted_out: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = missing_opted_out
    # Act
    rc = proc.returncode
    # Assert
    assert rc == 0, _output(proc)


def test_opt_out_is_annotated(missing_opted_out: subprocess.CompletedProcess) -> None:
    # Arrange
    proc = missing_opted_out
    # Act
    out = _output(proc)
    # Assert: an unannotated skip is indistinguishable from a successful build
    # in the checks UI, which is the defect restated.
    assert "::warning::" in out, out


def test_opt_out_states_that_nothing_was_built(
    missing_opted_out: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = missing_opted_out
    # Act
    out = _output(proc)
    # Assert: prose that refuses to let the green read as "the docs compile".
    assert "NO DOCUMENTATION WAS BUILT" in out, out


def test_default_run_never_reaches_the_skip_branch(
    missing_required: subprocess.CompletedProcess,
) -> None:
    # Arrange
    proc = missing_required
    # Act
    out = _output(proc)
    # Assert: the truthy default must not fall through to the opt-out.
    assert "NO DOCUMENTATION WAS BUILT" not in out, out
