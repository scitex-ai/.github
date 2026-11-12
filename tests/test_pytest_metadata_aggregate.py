"""The aggregate verdict needs no native runner and remains fail-closed."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/pytest-matrix.yml"


def test_only_reviewed_aggregate_fields_differ_from_native_baseline():
    # Arrange: restore only the two reviewed metadata fields before hashing.
    data = yaml.safe_load(WORKFLOW.read_text())
    gate = data["jobs"]["pytest-aggregate"]
    gate["runs-on"] = (
        "${{ (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name != github.repository)"
        "\n    && fromJSON('[\"ubuntu-latest\"]')"
        "\n    || fromJSON(needs.runner-admission.outputs.runs_on) }}"
    )
    gate.pop("permissions")
    data["on"] = data.pop(True)
    # Act
    digest = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # Assert: every other field equals the complete pre-change source.
    assert digest == "a5aa4a300456107819994b81cbb71579df823f5690a92a8628af4330825b1a73"


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
