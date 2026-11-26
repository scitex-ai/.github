"""The dev profile's Apptainer pin is the binary its committed receipt measured."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "docs/qualifications/dev-apptainer-1.5.5-20261126.json"
SPEC = importlib.util.spec_from_file_location(
    "sif_dev_runtime_contract", ROOT / "tests/test_sif_matrix_contract.py"
)
SIF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SIF)


@pytest.mark.parametrize("suite", ["matrix", "dev-release"])
def test_dev_runtime_pin_is_the_qualified_apptainer_binary(suite):
    # Arrange
    receipt = json.loads(RECEIPT.read_text())["runtime"]
    # Act
    result = SIF.contract("plan", suite=suite, event="workflow_dispatch")
    runtime = result["value"]["runtime"]
    # Assert
    assert (result["ok"], runtime["path"], runtime["sha256"], runtime["bytes"]) == (
        True,
        receipt["path"],
        receipt["sha256"],
        receipt["bytes"],
    )


def test_dev_qualification_digest_is_the_committed_receipt():
    # Arrange
    digest = hashlib.sha256(RECEIPT.read_bytes()).hexdigest()
    # Act
    runtime = SIF.contract("plan", suite="dev-release", event="workflow_dispatch")[
        "value"
    ]["runtime"]
    # Assert
    assert runtime["qualification_sha256"] == digest


def test_dev_receipt_measured_the_registered_image_and_sources():
    # Arrange
    receipt = json.loads(RECEIPT.read_text())
    # Act
    plan = SIF.contract("plan", suite="dev-release", event="workflow_dispatch")["value"]
    # Assert
    assert (
        receipt["image"]["sha256"],
        receipt["image"]["bytes"],
        receipt["leaf_sources"],
        receipt["postgresql"]["bin"],
        receipt["postgresql"]["version"],
    ) == (
        plan["image"]["sha256"],
        plan["image"]["bytes"],
        plan["leafSources"],
        plan["pgBin"],
        plan["pgVersion"],
    )


def test_dev_receipt_records_passing_suites_and_build():
    # Arrange
    receipt = json.loads(RECEIPT.read_text())
    # Act
    outcomes = [
        (row["python"], row["returncode"], row["postgres_readiness"])
        for row in receipt["test"]["versions"]
    ]
    # Assert
    assert (
        outcomes,
        receipt["build"]["returncode"],
        receipt["build"]["wheel_import_check_passed"],
        receipt["host"],
    ) == (
        [("3.11", 0, True), ("3.12", 0, True), ("3.13", 0, True)],
        0,
        True,
        "scitex-compute-02",
    )


def test_sac_keeps_its_own_unchanged_runtime_qualification():
    # Arrange
    receipt = json.loads(RECEIPT.read_text())["runtime"]
    # Act
    runtime = SIF.contract("plan", repository=SIF.SAC, event="push")["value"]["runtime"]
    # Assert
    assert (runtime["sha256"], runtime["qualification_sha256"]) == (
        "7bdb501fdddbb7264b4e4d6038e0ec27201f63e217519e5f7f0db950c9285ddd",
        "75e24f6fa3a80369b45e8c3d1029d940076109c92404d0d82a168be74859771b",
    ) and runtime["sha256"] != receipt["sha256"]
