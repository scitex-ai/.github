"""Run the reusable import body against real synthetic source packages."""

import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/import-smoke.yml"
SAC = "scitex-ai/scitex-agent-container"
DEV = "scitex-ai/scitex-dev"
SAC_GATE = (
    "github.repository == 'scitex-ai/scitex-agent-container' "
    "&& inputs.console_script != 'sac'"
)


def steps():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["import-smoke"]["steps"]


def run_import(repository, packages):
    """Adapt only the installed interpreter locator; never create a venv."""
    with tempfile.TemporaryDirectory(prefix="central-import-fixture-") as directory:
        root = Path(directory)
        binaries = root / "commands"
        binaries.mkdir()
        uv = binaries / "uv"
        uv.write_text("#!/bin/sh\nexit 0\n")
        uv.chmod(0o700)
        for name, body in packages.items():
            package = root / "src" / name
            package.mkdir(parents=True)
            (package / "__init__.py").write_text(body)
        body = next(
            step["run"]
            for step in steps()
            if step.get("name") == "Install (no extras) + import"
        )
        body = body.replace(".venv/bin/python", shlex.quote(sys.executable) + " -S")
        return subprocess.run(
            ["bash", "-c", body],
            cwd=root,
            env={
                "PATH": str(binaries) + ":/usr/bin:/bin",
                "HOME": str(root),
                "GITHUB_REPOSITORY": repository,
                "PYTHONPATH": str(root / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )


def run_sac_console(body):
    """Execute the literal command against a real synthetic console program."""
    with tempfile.TemporaryDirectory(prefix="central-console-fixture-") as directory:
        root = Path(directory)
        script = root / "sac"
        script.write_text("#!" + sys.executable + "\n" + body)
        script.chmod(0o700)
        command = next(step["run"] for step in steps() if step.get("if") == SAC_GATE)
        command = command.replace(".venv/bin/sac", shlex.quote(str(script)))
        return subprocess.run(
            ["bash", "-c", command],
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(root),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )


def test_sac_imports_main_package_instead_of_bootstrap():
    # Arrange
    packages = {
        "_scitex_agent_container_bootstrap": "__version__ = 'bootstrap-only'\n",
        "scitex_agent_container": "__version__ = '0.29.4'\n",
    }
    # Act
    result = run_import(SAC, packages)
    # Assert
    assert (result.returncode, result.stdout.strip()) == (0, "0.29.4")


def test_bootstrap_success_does_not_hide_broken_sac_import():
    # Arrange
    packages = {
        "_scitex_agent_container_bootstrap": "__version__ = 'bootstrap-only'\n",
        "scitex_agent_container": "raise RuntimeError('main-package-import-failed')\n",
    }
    # Act
    result = run_import(SAC, packages)
    # Assert
    assert result.returncode != 0 and "main-package-import-failed" in result.stderr


def test_dev_prints_actual_module_version_with_an_earlier_package_present():
    # Arrange
    packages = {"_bootstrap": "", "scitex_dev": "__version__ = '0.61.4'\n"}
    # Act
    result = run_import(DEV, packages)
    # Assert
    assert (result.returncode, result.stdout.strip()) == (0, "0.61.4")


@pytest.mark.parametrize(
    "repository,module", [(DEV, "scitex_dev"), (SAC, "scitex_agent_container")]
)
def test_selected_module_missing_version_refuses(repository, module):
    # Arrange
    packages = {module: ""}
    # Act
    result = run_import(repository, packages)
    # Assert
    assert result.returncode != 0 and "__version__" in result.stderr


def test_sac_main_package_absence_refuses_despite_bootstrap():
    # Arrange
    packages = {"_scitex_agent_container_bootstrap": ""}
    # Act
    result = run_import(SAC, packages)
    # Assert
    assert result.returncode != 0 and "scitex_agent_container" in result.stderr


def test_generic_repository_keeps_alphabetical_discovery_without_version():
    # Arrange
    packages = {
        "z_package": "raise RuntimeError('wrong generic package')\n",
        "a_package": "",
    }
    # Act
    result = run_import("outside/generic", packages)
    # Assert
    assert (result.returncode, result.stdout.strip()) == (0, "import OK: a_package")


def test_repository_suffix_does_not_acquire_sac_profile():
    # Arrange
    packages = {
        "a_package": "",
        "scitex_agent_container": "raise RuntimeError('wrong profile')\n",
    }
    # Act
    result = run_import("outside/scitex-agent-container", packages)
    # Assert
    assert (result.returncode, result.stdout.strip()) == (0, "import OK: a_package")


def test_sac_default_console_executes_real_version_argument():
    # Arrange
    body = "import sys\nassert sys.argv[1:] == ['--version']\nprint('sac 0.29.4')\n"
    # Act
    result = run_sac_console(body)
    # Assert
    assert (result.returncode, result.stdout.strip()) == (0, "sac 0.29.4")


def test_broken_sac_console_fails_even_after_main_import_success():
    # Arrange
    body = "raise RuntimeError('entry-point-broken')\n"
    # Act
    result = run_sac_console(body)
    # Assert
    assert result.returncode != 0 and "entry-point-broken" in result.stderr


def test_sac_console_gate_does_not_duplicate_explicit_sac_input():
    # Arrange
    gated = [step for step in steps() if step.get("if") == SAC_GATE]
    # Act
    commands = [step["run"] for step in gated]
    # Assert
    assert len(commands) == 1 and commands[0].strip().endswith(
        ".venv/bin/sac --version"
    )


@pytest.mark.parametrize(
    "repository,console,expected",
    [
        (SAC, "", True),
        (SAC, "sac", False),
        (SAC, "other", True),
        (DEV, "", False),
        ("outside/generic", "tool", False),
    ],
)
def test_actual_sac_gate_is_finite_and_preserves_optional_callers(
    repository, console, expected
):
    # Arrange
    gate = next(step["if"] for step in steps() if step.get("if") == SAC_GATE)
    source = (
        "const github = {repository: " + json.dumps(repository) + "};\n"
        "const inputs = {console_script: " + json.dumps(console) + "};\n"
        "console.log(JSON.stringify(Boolean(" + gate + ")));\n"
    )
    # Act
    result = subprocess.run(
        ["node", "-e", source],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    # Assert
    assert json.loads(result.stdout) is expected
