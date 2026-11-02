"""The qualified worker-budget change updates exactly one registered source."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci-sif-matrix.yml"
SPEC = importlib.util.spec_from_file_location(
    "sif_worker_budget_contract", ROOT / "tests/test_sif_matrix_contract.py"
)
SIF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SIF)
OLD_DRIVER = "cc690aeca6770e980652f499d50571e0e2fc759abbf2b870c650fcc3dd493786"
NEW_DRIVER = "7efa7c7737bb536f03b822a08186e093030ef8b48e0cc9bce811e11785cfdf01"
BASELINE_WORKFLOW = "1327982f2aa9cd82960d81fc6e0cd1eed2e432834a15aa685a66b1e1a82f5418"


def test_registration_reverses_to_exact_reviewed_whole_workflow():
    # Arrange
    body = WORKFLOW.read_bytes()
    # Act
    original = body.replace(NEW_DRIVER.encode(), OLD_DRIVER.encode())
    # Assert
    assert (body.count(NEW_DRIVER.encode()), hashlib.sha256(original).hexdigest()) == (
        1, BASELINE_WORKFLOW,
    )


@pytest.mark.parametrize("suite", ["matrix", "dev-release"])
def test_actual_native_plan_uses_the_qualified_driver_and_retains_runtime(suite):
    # Arrange
    receipt = json.loads((ROOT / "docs/qualifications/dev-worker-budget-20261102.json").read_text())
    # Act
    result = SIF.contract("plan", suite=suite, event="workflow_dispatch")
    plan = result["value"]
    # Assert
    assert (
        result["ok"], plan["leafSources"][".github/ci/run-in-sif.sh"],
        plan["image"]["sha256"], plan["runtime"]["sha256"],
        plan["pgBin"], plan["pgVersion"],
    ) == (
        True, receipt["critical_driver"]["sha256"], receipt["image"]["sha256"],
        receipt["runtime"]["sha256"], receipt["postgresql"]["bin"],
        receipt["postgresql"]["version"],
    )
