"""Execute the real service-DSN handoff for isolated matrix job ports."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _job():
    workflow = Path(__file__).parents[1] / ".github/workflows/pytest-matrix.yml"
    return yaml.safe_load(workflow.read_text())["jobs"]["pytest-matrix"]


def _step():
    return next(
        step
        for step in _job()["steps"]
        if step.get("name") == "Point the store at the service container"
    )


def _handoff(root, port):
    envfile = root / "github-env"
    env = {**os.environ, "GITHUB_ENV": str(envfile)}
    env.pop("POSTGRES_SERVICE_PORT", None)
    if port is not None:
        env["POSTGRES_SERVICE_PORT"] = port
    result = subprocess.run(
        ["bash", "-c", _step()["run"]], env=env, capture_output=True, text=True
    )
    return result, envfile.read_text() if envfile.exists() else ""


def test_service_allocates_a_port_and_handoff_uses_its_context():
    # Arrange / Act
    service = _job()["services"]["postgres"]
    step = _step()
    # Assert
    assert (service["ports"], step["if"], step["env"]["POSTGRES_SERVICE_PORT"]) == (
        [5432],
        "inputs.postgres",
        "${{ job.services.postgres.ports['5432'] }}",
    )


@pytest.mark.parametrize("port", ["32768", "49152"])
def test_actual_shell_exports_the_assigned_port(tmp_path, port):
    # Arrange / Act
    completed, exported = _handoff(tmp_path, port)
    # Assert
    assert (completed.returncode, exported) == (
        0,
        f"SCITEX_STORE_DSN=postgresql://scitex:scitex@127.0.0.1:{port}/scitex\n",
    )


@pytest.mark.parametrize("port", [None, "", "0", "65536", "5432;exit 0", "localhost"])
def test_missing_or_invalid_mapping_cannot_export_a_fallback_dsn(tmp_path, port):
    # Arrange / Act
    completed, exported = _handoff(tmp_path, port)
    # Assert
    assert (completed.returncode, exported) == (1, "")
