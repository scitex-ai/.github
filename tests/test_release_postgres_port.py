"""Execute the generic release workflow's real service-DSN handoff."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _job():
    path = Path(__file__).parents[1] / ".github/workflows/release-publish.yml"
    return yaml.safe_load(path.read_text())["jobs"]["test"]


def _step():
    return next(
        s
        for s in _job()["steps"]
        if s.get("name") == "Point the store at the service container"
    )


def _handoff(root, port, variable="SCITEX_STORE_DSN"):
    envfile = root / "github-env"
    environment = dict(os.environ, GITHUB_ENV=str(envfile))
    environment.pop("POSTGRES_SERVICE_PORT", None)
    if port is not None:
        environment["POSTGRES_SERVICE_PORT"] = port
    script = _step()["run"].replace("${{ inputs.store_dsn_var }}", variable)
    result = subprocess.run(
        ["bash", "-c", script], env=environment, capture_output=True, text=True
    )
    return result.returncode, envfile.read_text() if envfile.exists() else ""


def test_release_service_allocates_an_independent_host_port():
    # Arrange / Act
    job, step = _job(), _step()
    # Assert
    assert (
        job["services"]["postgres"]["ports"],
        step["if"],
        step.get("env", {}).get("POSTGRES_SERVICE_PORT"),
    ) == (
        [5432],
        "inputs.postgres",
        "${{ job.services.postgres.ports['5432'] }}",
    )


@pytest.mark.parametrize(
    "port,variable", [("32768", "SCITEX_STORE_DSN"), ("49152", "SCITEX_LIBRARY_DSN")]
)
def test_release_handoff_uses_the_allocated_port_and_service_credentials(
    tmp_path, port, variable
):
    # Arrange
    credentials = _job()["services"]["postgres"]["env"]
    expected = (
        f"{variable}=postgresql://{credentials['POSTGRES_USER']}:"
        f"{credentials['POSTGRES_PASSWORD']}@127.0.0.1:{port}/{credentials['POSTGRES_DB']}\n"
    )
    # Act
    observed = _handoff(tmp_path, port, variable)
    # Assert
    assert observed == (0, expected)


@pytest.mark.parametrize("port", [None, "", "0", "65536", "5432;exit 0", "localhost"])
def test_release_handoff_rejects_an_absent_or_invalid_port_without_exporting(
    tmp_path, port
):
    # Arrange / Act
    observed = _handoff(tmp_path, port)
    # Assert
    assert observed == (1, "")
