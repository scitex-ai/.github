"""The aggregate verdict needs no native runner and remains fail-closed."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/pytest-matrix.yml"


def test_aggregate_uses_hosted_metadata_execution_without_token_permissions():
    # Arrange
    data = yaml.safe_load(WORKFLOW.read_text())
    # Act
    gate = data["jobs"]["pytest-aggregate"]
    # Assert
    assert (
        gate["name"], gate["runs-on"], gate["permissions"],
        gate["needs"], gate["if"], any("uses" in step for step in gate["steps"]),
    ) == (
        "pytest aggregate gate", "ubuntu-latest", {},
        ["pytest-matrix", "runner-admission"], "always()", False,
    )


@pytest.mark.parametrize(
    "result,exit_code",
    [
        ("success", 0), ("failure", 1), ("cancelled", 1),
        ("skipped", 1), ("", 1), ("timed_out", 1),
        ("$(touch SENTINEL)", 1), ("success; touch SENTINEL", 1),
    ],
)
def test_actual_aggregate_script_accepts_only_success(tmp_path, result, exit_code):
    # Arrange
    gate = yaml.safe_load(WORKFLOW.read_text())["jobs"]["pytest-aggregate"]
    step = next(s for s in gate["steps"] if s["name"] == "Require every selected compatibility leg")
    # Act
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        env={"PATH": os.defpath, "RESULT": result}, cwd=tmp_path,
        capture_output=True, text=True, check=False, timeout=5,
    )
    # Assert
    assert (completed.returncode, (tmp_path / "SENTINEL").exists()) == (exit_code, False)
