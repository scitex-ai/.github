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
RUNTIME_RECEIPT = ROOT / "docs/qualifications/dev-apptainer-1.5.5-20261126.json"
# The later, separately qualified Apptainer re-pin (test_dev_runtime_qualification.py)
# is the only other registered change; undo it to recover the reviewed bytes.
OLD_RUNTIME = """                nativePgImage: null,
                nativeRuntime: {
                  path: '/usr/bin/apptainer',
                  sha256: '7bdb501fdddbb7264b4e4d6038e0ec27201f63e217519e5f7f0db950c9285ddd',
                  bytes: 48096048,
                  qualification_sha256: '22362dd8da22aa93653613d899e9ab6232d3a099576d7da646ea617a35f2e036',
"""


def new_runtime():
    digest = hashlib.sha256(RUNTIME_RECEIPT.read_bytes()).hexdigest()
    return f"""                nativePgImage: null,
                // Apptainer 1.5.5 on scitex-compute-02: all three full suites and
                // the 3.12 release build measured there (docs/qualifications/
                // dev-apptainer-1.5.5-20261126.json; qualification_sha256 is its
                // sha256). The caller scopes runners to compute-02.
                nativeRuntime: {{
                  path: '/usr/bin/apptainer',
                  sha256: '5dc04ef6490f8349a3b5db2a07a3447ac492320078e14b11eace14caa3230aba',
                  bytes: 47822320,
                  qualification_sha256: '{digest}',
"""


def test_registration_reverses_to_exact_reviewed_whole_workflow():
    # Arrange
    body = WORKFLOW.read_bytes()
    # Act
    runtime = new_runtime().encode()
    original = body.replace(NEW_DRIVER.encode(), OLD_DRIVER.encode()).replace(
        runtime, OLD_RUNTIME.encode())
    # Assert
    assert (body.count(NEW_DRIVER.encode()), body.count(runtime),
            hashlib.sha256(original).hexdigest()) == (1, 1, BASELINE_WORKFLOW)


@pytest.mark.parametrize("suite", ["matrix", "dev-release"])
def test_actual_native_plan_uses_the_qualified_driver_and_qualified_runtime(suite):
    # Arrange
    receipt = json.loads((ROOT / "docs/qualifications/dev-worker-budget-20261102.json").read_text())
    runtime = json.loads(RUNTIME_RECEIPT.read_text())["runtime"]
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
        runtime["sha256"], receipt["postgresql"]["bin"],
        receipt["postgresql"]["version"],
    )
