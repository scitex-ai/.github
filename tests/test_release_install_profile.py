"""Release tests must never proceed after a required-profile install fails.

Inert executable protocol fixtures record the actual workflow's shell control
flow. They do not install dependencies or qualify a package's scientific tests.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _workflow():
    path = Path(__file__).parents[1] / ".github/workflows/release-publish.yml"
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def _default_profile():
    return _workflow()["on"]["workflow_call"]["inputs"]["test_extras"]["default"]


def _execute(root, profile, fail_install=False):
    step = next(
        s
        for s in _workflow()["jobs"]["test"]["steps"]
        if s.get("name") == "Run tests in a uv venv"
    )
    python_driver = (
        f"#!{sys.executable}\n"
        "import os,sys\nfrom pathlib import Path\n"
        "if sys.argv[1:3]==['-m','pytest']:\n"
        " Path('pytest-started').touch()\n raise SystemExit(0)\n"
        "os.execv(sys.executable,[sys.executable,*sys.argv[1:]])\n"
    )
    tools = root / "bin"
    tools.mkdir()
    uv = tools / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import os,sys\nfrom pathlib import Path\n"
        "args=sys.argv[1:]\n"
        "with Path('uv-calls').open('a') as stream: stream.write(repr(args)+'\\n')\n"
        "if args[0]=='venv':\n"
        " Path('.venv/bin').mkdir(parents=True)\n"
        f" Path('.venv/bin/python').write_text({python_driver!r})\n"
        " Path('.venv/bin/python').chmod(0o755)\n"
        "if '-e' in args and os.environ.get('FAIL_REQUIRED')=='1' and args[-1]=='.[all,dev]':\n"
        " raise SystemExit(71)\n"
    )
    uv.chmod(0o755)
    (root / "pyproject.toml").write_text(
        '[project]\nname="release-profile-fixture"\nversion="0.0.0"\n'
        "[project.optional-dependencies]\nall=[]\ndev=[]\n"
    )
    substitutions = {
        "${{ inputs.test_extras }}": profile,
        "${{ inputs.extra_test_deps }}": "pytest-xdist>=3.0.0",
        "${{ matrix.python-version }}": "3.12",
        "${{ inputs.package_name }}": "fixture",
    }
    script = step["run"]
    for pattern, value in substitutions.items():
        script = script.replace(pattern, value)
    environment = dict(
        os.environ,
        PATH=str(tools) + os.pathsep + os.environ["PATH"],
        FAIL_REQUIRED="1" if fail_install else "0",
    )
    for name, value in step.get("env", {}).items():
        environment[name] = substitutions.get(value, value)
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
    )
    calls = root / "uv-calls"
    installs = (
        [ast.literal_eval(row) for row in calls.read_text().splitlines()]
        if calls.exists()
        else []
    )
    editable = [args[-1] for args in installs if "-e" in args]
    return completed.returncode, editable, (root / "pytest-started").exists()


def test_release_default_is_one_required_profile():
    # Arrange
    expected = ".[all,dev]"
    # Act
    profile = _default_profile()
    # Assert
    assert profile == expected


def test_required_profile_failure_halts_before_pytest_without_fallback(tmp_path):
    # Arrange
    profile = _default_profile()
    # Act
    observed = _execute(tmp_path, profile, fail_install=True)
    # Assert
    assert observed == (71, [".[all,dev]"], False)


@pytest.mark.parametrize("profile", [".[all,dev]", ".[dev]", "."])
def test_explicit_declared_profile_can_reach_the_test_command(tmp_path, profile):
    # Arrange
    workspace = tmp_path
    # Act
    observed = _execute(workspace, profile)
    # Assert
    assert observed == (0, [profile], True)


@pytest.mark.parametrize("profile", [".[all,dev] .[dev] .", ".[missing]", ""])
def test_ambiguous_or_undeclared_profiles_cannot_reach_project_install(
    tmp_path, profile
):
    # Arrange
    workspace = tmp_path
    # Act
    code, installs, started = _execute(workspace, profile)
    # Assert
    assert (code != 0, installs, started) == (True, [], False)


def test_extra_test_requirement_keeps_its_version_constraint_as_a_literal(tmp_path):
    # Arrange
    profile = ".[dev]"
    # Act
    _execute(tmp_path, profile)
    calls = [
        ast.literal_eval(row)
        for row in (tmp_path / "uv-calls").read_text().splitlines()
    ]
    # Assert
    assert any("pytest-xdist>=3.0.0" in args for args in calls)
