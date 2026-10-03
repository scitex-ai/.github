"""Run the finite health observation and retain its admission boundary."""
import os
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/runner-health.yml").read_text())


def test_runtime_observation_executes_real_cpu_memory_and_filesystem_reads(tmp_path):
    # Arrange
    step = workflow()["jobs"]["health"]["steps"][1]
    env = dict(os.environ, RUNNER_TEMP=str(tmp_path), OBSERVED_RUNNER_NAME="owned-fixture",
               OBSERVED_RUNNER_ENVIRONMENT="source-test")
    # Act
    result = subprocess.run(["bash", "-c", step["run"]], env=env, capture_output=True,
                            text=True, timeout=10)
    # Assert
    assert result.returncode == 0, result.stderr
    assert "runner=owned-fixture\nenvironment=source-test\n" in result.stdout
    rows = result.stdout.splitlines()
    assert int(next(row.split("=", 1)[1] for row in rows if row.startswith("available_cpus="))) > 0
    assert int(next(row.split("=", 1)[1] for row in rows if row.startswith("online_cpus="))) > 0
    assert "MemTotal:" in result.stdout and "MemAvailable:" in result.stdout
    assert "scope=one-admitted-runner-sample;not-whole-pool-or-package-CI" in rows


def test_missing_runtime_directory_fails_instead_of_reporting_healthy(tmp_path):
    # Arrange
    script = workflow()["jobs"]["health"]["steps"][1]["run"]
    env = dict(os.environ, RUNNER_TEMP=str(tmp_path / "absent"), OBSERVED_RUNNER_NAME="owned-fixture",
               OBSERVED_RUNNER_ENVIRONMENT="source-test")
    # Act
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                            text=True, timeout=10)
    # Assert
    assert result.returncode != 0
    assert "scope=one-admitted-runner-sample;not-whole-pool-or-package-CI" not in result.stdout


def test_health_is_bounded_without_checkout_credentials_or_package_installation():
    # Arrange
    definition = workflow()
    job = definition["jobs"]["health"]
    # Act
    steps = job["steps"]
    # Assert
    assert definition["permissions"] == job["permissions"] == {}
    assert job["timeout-minutes"] == 3
    assert not any("uses" in step for step in steps)
    assert not any(word in str(steps) for word in ("github.token", "secrets.", "pip install", "uv pip"))


def test_periodic_caller_uses_same_revision_shared_admission_without_secrets():
    # Arrange
    caller = yaml.safe_load((ROOT / ".github/workflows/company-ci-pool-health.yml").read_text())
    # Act
    events = caller.get("on", caller.get(True))
    # Assert
    assert events == {"workflow_dispatch": None, "schedule": [{"cron": "*/15 * * * *"}]}
    assert caller["jobs"]["sample"]["uses"] == "./.github/workflows/runner-health.yml"
    assert caller["permissions"] == {}
    assert "secrets" not in caller["jobs"]["sample"]
    assert caller["jobs"]["sample"]["strategy"] == {
        "fail-fast": False, "matrix": {"node": ["02", "03", "04"]}
    }
    assert caller["jobs"]["sample"]["with"]["verify_docker"] is True
