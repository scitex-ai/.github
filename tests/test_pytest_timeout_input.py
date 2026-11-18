"""Contract for the per-leg timeout_minutes input of pytest-matrix.yml.

That reverting this input (pop it, restore the literal 30) yields the prior
body is pinned by the legacy digest in test_pytest_job_environment.py.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pytest-matrix.yml"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def test_timeout_input_is_optional_number_defaulting_to_prior_thirty():
    # Arrange
    workflow = _workflow()
    # Act
    declared = workflow.get("on", workflow.get(True))["workflow_call"]["inputs"][
        "timeout_minutes"
    ]
    # Assert
    assert (declared["type"], declared["required"], declared["default"]) == (
        "number",
        False,
        30,
    )


def test_only_the_pytest_matrix_legs_read_the_timeout_input():
    # Arrange
    jobs = _workflow()["jobs"]
    # Act
    readers = {
        name: job.get("timeout-minutes")
        for name, job in jobs.items()
        if "inputs.timeout_minutes" in str(job.get("timeout-minutes", ""))
    }
    # Assert
    assert readers == {"pytest-matrix": "${{ inputs.timeout_minutes }}"}
