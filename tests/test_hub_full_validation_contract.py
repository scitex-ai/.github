"""Fixed complete Hub bodies, explicit admission and real fail-closed shells."""

import copy
import hashlib
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github/workflows"
ROWS = {
    "hub-pytest-matrix.yml": (
        "pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml",
        "692a23b6b978239cadbf501cb0003845859dff647e176cff153725005f6ba18a",
    ),
    "hub-quality-audit.yml": (
        "scitex-hub-quality-audit-on-ubuntu-latest.yml",
        "f52da9459fb715d796c20ea5630577ae1f7f66590910f927e45a333d78ecc7ca",
    ),
    "hub-command-v-guard.yml": (
        "check-command-v-args.yml",
        "57e99e080388dbea1b5e95930023ce2fcad9f1ee7ae0d45b4cfcaa093891c985",
    ),
    "hub-symlink-guard.yml": (
        "check-absolute-symlinks.yml",
        "e977245a24c25aaea0ba5cfecde794c213624b5b8fe978c34f0b6dc759b44299",
    ),
    "hub-cli-import-smoke.yml": (
        "cli-import-smoke-on-ubuntu-latest.yml",
        "25c481d05cfbec4eed967c4b7aa48d6bac746ba0db3b9bb23e5409dc56736a1c",
    ),
    "hub-sphinx-build.yml": (
        "rtd-sphinx-build-on-ubuntu-latest.yml",
        "51471b38804ee3b2c584f7044466a4ffd18be9650b1e0504e48f8723678f6a19",
    ),
    "hub-custom-tests.yml": (
        "tests.yml",
        "4143a455115acce0c031a488f2858566e026bad9098eda7c8380926f5c540a38",
    ),
}
HOSTED_ONLY = {"terminal-tests", "security-regression", "test-summary"}


def source_case(name):
    original, digest = ROWS[name]
    raw = (ROOT / "tests/fixtures" / ("hub-original-" + original)).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("original whole Git fixture changed")
    return yaml.safe_load(raw), yaml.safe_load((WORKFLOWS / name).read_text())


def restored_jobs(original, candidate, name):
    """Reverse only the declared routing/guard and three install seams."""
    result = copy.deepcopy(candidate["jobs"])
    result.pop("runner-admission")
    for key, job in result.items():
        old = original["jobs"][key]
        if key == "test-summary":
            continue
        if "needs" in old:
            job["needs"] = copy.deepcopy(old["needs"])
        else:
            job.pop("needs", None)
        job["runs-on"] = old["runs-on"]
        if key in HOSTED_ONLY:
            job["steps"].pop(1)
        else:
            job["steps"] = [copy.deepcopy(old["steps"][0])] + job["steps"][3:]
        if name == "hub-cli-import-smoke.yml":
            setup = next(
                index
                for index, step in enumerate(job["steps"])
                if step.get("uses") == "astral-sh/setup-uv@v7"
            )
            job["steps"][setup] = copy.deepcopy(old["steps"][setup])
        install_names = {
            "hub-pytest-matrix.yml": (
                "Install dependencies (py${{ matrix.python-version }})"
            ),
            "hub-cli-import-smoke.yml": "Install with NO extras",
            "hub-sphinx-build.yml": "Install package + docs deps",
        }
        if name in install_names:
            changed = next(
                step for step in job["steps"] if step.get("name") == install_names[name]
            )
            prior = next(
                step for step in old["steps"] if step.get("name") == install_names[name]
            )
            changed["run"] = prior["run"]
    if "runner-admission" in original["jobs"]:
        result["runner-admission"] = copy.deepcopy(original["jobs"]["runner-admission"])
    return result


@pytest.mark.parametrize("name", ROWS)
def test_all_original_jobs_test_commands_env_services_limits_and_permissions_survive(
    name,
):
    # Arrange
    original, candidate = source_case(name)
    # Act
    restored = restored_jobs(original, candidate, name)
    # Assert
    assert restored == original["jobs"]


@pytest.mark.parametrize("name", ROWS)
def test_fixed_callee_has_same_revision_gate_and_no_arbitrary_input_or_secrets(
    name,
):
    # Arrange
    _original, candidate = source_case(name)
    events = candidate.get("on", candidate.get(True))
    # Act
    admission = candidate["jobs"]["runner-admission"]
    # Assert
    assert (
        set(events),
        candidate["permissions"],
        admission["uses"],
        set(admission),
        events["workflow_call"],
    ) == (
        {"workflow_call"},
        {"contents": "write" if name == "hub-sphinx-build.yml" else "read"},
        "./.github/workflows/runner-admission.yml",
        {"uses", "with"},
        {"secrets": {"CODECOV_TOKEN": {"required": False}}}
        if name == "hub-pytest-matrix.yml"
        else None,
    )


@pytest.mark.parametrize("name", ROWS)
def test_all_native_legs_require_gate_repo_and_fork_refusal_before_any_checkout(name):
    # Arrange
    _original, candidate = source_case(name)
    # Act
    observed = []
    for key, job in candidate["jobs"].items():
        if "steps" not in job or key in HOSTED_ONLY:
            continue
        first, second, third = job["steps"][:3]
        observed.append(
            (
                "runner-admission" in job["needs"],
                "fromJSON(needs.runner-admission.outputs.runs_on)" in job["runs-on"],
                first["name"]
                == "Refuse to run fork-authored code on self-hosted infrastructure",
                "runner.environment == 'self-hosted'" in first["if"],
                "native_authorized != 'true'" in second["if"],
                third["env"] == {"EXPECTED_REPOSITORY": "scitex-ai/scitex-hub"},
                third["run"] == 'test "$GITHUB_REPOSITORY" = "$EXPECTED_REPOSITORY"\n',
            )
        )
    # Assert
    assert observed and all(row == (True,) * 7 for row in observed)


def test_terminal_security_and_strict_four_leg_summary_remain_hosted():
    # Arrange
    original, candidate = source_case("hub-custom-tests.yml")
    # Act
    values = [(key, candidate["jobs"][key]["runs-on"]) for key in sorted(HOSTED_ONLY)]
    summary = candidate["jobs"]["test-summary"]
    # Assert
    assert (values, summary) == (
        [(key, "ubuntu-latest") for key in sorted(HOSTED_ONLY)],
        original["jobs"]["test-summary"],
    )


@pytest.mark.parametrize(
    "name,key,step_name",
    [
        (
            "hub-pytest-matrix.yml",
            "test",
            "Install dependencies (py${{ matrix.python-version }})",
        ),
        ("hub-sphinx-build.yml", "sphinx", "Install package + docs deps"),
    ],
)
@pytest.mark.parametrize("full_exit", [0, 23])
def test_real_full_install_shell_fails_loudly_where_original_reduces_dependencies(
    name, key, step_name, full_exit, tmp_path
):
    # Arrange
    original, candidate = source_case(name)
    before = next(
        step["run"]
        for step in original["jobs"][key]["steps"]
        if step.get("name") == step_name
    )
    after = next(
        step["run"]
        for step in candidate["jobs"][key]["steps"]
        if step.get("name") == step_name
    )
    uv = tmp_path / "uv"
    uv.write_text(
        '#!/bin/sh\ncase "$*" in *"pip install"*".[all"*) '
        'exit "$FULL_EXIT";; esac\nexit 0\n'
    )
    uv.chmod(0o700)
    environment = dict(
        os.environ,
        PATH=str(tmp_path) + ":/usr/bin:/bin",
        FULL_EXIT=str(full_exit),
        GITHUB_PATH=str(tmp_path / "github-path"),
    )
    # GitHub expands only this literal version before handing the run script to bash.
    before = before.replace("${{ matrix.python-version }}", "3.12")
    after = after.replace("${{ matrix.python-version }}", "3.12")
    # Act
    original_result = subprocess.run(
        ["/bin/bash", "-c", before],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        timeout=3,
        check=False,
    )
    successor_result = subprocess.run(
        ["/bin/bash", "-c", after],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        timeout=3,
        check=False,
    )
    # Assert
    assert (
        original_result.returncode,
        successor_result.returncode,
        b"not found" in successor_result.stderr,
    ) == (0, full_exit, False)


def test_shipped_cli_gate_keeps_exact_no_extra_import_help_proof_with_uv():
    # Arrange
    original, candidate = source_case("hub-cli-import-smoke.yml")
    # Act
    steps = candidate["jobs"]["cli-import-smoke"]["steps"]
    installation = next(
        step["run"] for step in steps if step.get("name") == "Install with NO extras"
    )
    # Assert
    assert (
        installation,
        steps[-2:],
        candidate["jobs"]["cli-import-smoke"]["timeout-minutes"],
    ) == (
        (
            "set -euo pipefail\nuv venv --python 3.12 .venv\n"
            "uv pip install --python .venv/bin/python -e .\n"
        ),
        original["jobs"]["cli-import-smoke"]["steps"][-2:],
        30,
    )


@pytest.mark.parametrize("name", ROWS)
def test_original_has_no_same_revision_company_gate_before_its_fixed_bodies(name):
    # Arrange
    original, _candidate = source_case(name)
    # Act
    gate = original["jobs"].get("runner-admission", {})
    # Assert
    assert gate.get("uses") != "./.github/workflows/runner-admission.yml"


@pytest.mark.parametrize("name", ROWS)
def test_caller_proposal_preserves_original_events_concurrency_and_fixed_named_route(
    name,
):
    # Arrange
    original, _candidate = source_case(name)
    filename, _digest = ROWS[name]
    caller = yaml.safe_load(
        (ROOT / "tests/fixtures" / ("hub-proposed-caller-" + filename)).read_text()
    )
    # Act
    validation = caller["jobs"]["validation"]
    # Assert
    assert (
        caller["name"],
        caller.get("on", caller.get(True)),
        caller["concurrency"],
        validation,
        caller["permissions"],
    ) == (
        original["name"],
        original.get("on", original.get(True)),
        original["concurrency"],
        {
            "uses": "scitex-ai/.github/.github/workflows/" + name + "@main",
            **(
                {"secrets": {"CODECOV_TOKEN": "${{ secrets.CODECOV_TOKEN }}"}}
                if name == "hub-pytest-matrix.yml"
                else {}
            ),
        },
        {"contents": "write" if name == "hub-sphinx-build.yml" else "read"},
    )


@pytest.mark.parametrize(
    "name,bridge,expected",
    [
        (
            "hub-pytest-matrix.yml",
            "required-pytest",
            "pytest-matrix-on-ubuntu-py${{ matrix.python-version }}",
        ),
        (
            "hub-cli-import-smoke.yml",
            "required-cli",
            "cli-import-smoke-on-ubuntu-latest",
        ),
        ("hub-quality-audit.yml", "required-audit", "audit"),
    ],
)
@pytest.mark.parametrize(
    "result,exit_code",
    [("success", 0), ("failure", 1), ("cancelled", 1), ("skipped", 1), ("", 1)],
)
def test_real_hosted_required_context_bridge_rejects_every_non_success_graph_result(
    name, bridge, expected, result, exit_code
):
    # Arrange
    filename, _digest = ROWS[name]
    caller = yaml.safe_load(
        (ROOT / "tests/fixtures" / ("hub-proposed-caller-" + filename)).read_text()
    )
    job = caller["jobs"][bridge]
    step = job["steps"][0]
    # Act
    actual = subprocess.run(
        ["/bin/bash", "-c", step["run"]],
        capture_output=True,
        timeout=2,
        env={"PATH": "/usr/bin:/bin", "VALIDATION_RESULT": result},
        check=False,
    )
    # Assert
    assert (
        job["name"],
        job["needs"],
        job["if"],
        job["runs-on"],
        job["permissions"],
        step["env"],
        set(step),
        actual.returncode,
    ) == (
        expected,
        "validation",
        "always()",
        "ubuntu-latest",
        {},
        {"VALIDATION_RESULT": "${{ needs.validation.result }}"},
        {"name", "env", "run"},
        exit_code,
    )


def test_required_pytest_contexts_depend_on_whole_three_minor_result():
    # Arrange
    caller = yaml.safe_load(
        (
            ROOT
            / "tests/fixtures"
            / ("hub-proposed-caller-" + ROWS["hub-pytest-matrix.yml"][0])
        ).read_text()
    )
    _original, candidate = source_case("hub-pytest-matrix.yml")
    # Act
    bridge = caller["jobs"]["required-pytest"]
    # Assert
    assert (
        bridge["strategy"],
        candidate["jobs"]["test"]["strategy"],
        bridge["needs"],
    ) == (
        {"fail-fast": False, "matrix": {"python-version": ["3.11", "3.12", "3.13"]}},
        {"fail-fast": False, "matrix": {"python-version": ["3.11", "3.12", "3.13"]}},
        "validation",
    )
