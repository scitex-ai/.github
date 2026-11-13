"""Exercise Browser admission and the mandatory installed-wheel build step."""

import copy
import json
from pathlib import Path

import pytest
import yaml

import test_leaf_release_contract as leaf

ROOT = Path(__file__).resolve().parents[1]
FACTS = json.loads((ROOT / "tests/fixtures/release-core/browser-native.json").read_text())
OWNER = "scitex-ai/scitex-browser"


def browser(**changes):
    return leaf.dispatch(repository=OWNER, **changes)


def test_browser_uses_measured_image_runtime_and_complete_owning_closure():
    # Arrange
    expected = FACTS
    # Act
    plan = browser()["plan"]
    # Assert
    assert (plan["image"], plan["runtime"], plan["leafSources"]) == (
        expected["registration"]["image"], expected["registration"]["runtime"],
        expected["leaf_sources"],
    )
    assert plan["versions"] == ["3.11", "3.12", "3.13"]
    assert "pytestWorkers" not in plan
    assert plan["runner"] == {
        "group": "Organization",
        "labels": ["self-hosted", "Linux", "X64", "scitex-org-cpu", "scitex-compute-03"],
    }


def test_browser_build_uses_only_the_qualified_build_interpreter():
    # Arrange
    operation = "build"
    # Act
    plan = browser(operation=operation)["plan"]
    # Assert
    assert plan["versions"] == ["3.12"]


@pytest.mark.parametrize(("changes", "reason"), [
    ({"native": False}, "browser-release-membership-required"),
    ({"event": "pull_request"}, "browser-release-event-refused"),
    ({"operation": "publish"}, "browser-release-operation-refused"),
    ({"source": "develop"}, "browser-source-commit-refused"),
    ({"tag": "v0.1.16; false"}, "browser-release-tag-refused"),
    ({"registration": None}, "browser-runtime-unregistered"),
    ({"registration": {}}, "browser-runtime-unregistered"),
])
def test_browser_refuses_unadmitted_calls(changes, reason):
    # Arrange
    request = changes
    # Act
    result = browser(**request)
    # Assert
    assert result == {"ok": False, "reason": reason}


@pytest.mark.parametrize(("section", "field", "value", "reason"), [
    ("image", "sha256", "wrong", "image-byte-pin-invalid"),
    ("image", "bytes", 0, "image-byte-pin-invalid"),
    ("image", "native_paths", ["../unqualified.sif"], "native-image-authority-unqualified"),
    ("runtime", "user_namespace", False, "runtime-capability-unqualified"),
    ("runtime", "sif_mount", False, "runtime-capability-unqualified"),
    ("runtime", "qualification_sha256", "wrong", "runtime-capability-unqualified"),
])
def test_browser_refuses_incomplete_or_unqualified_runtime_facts(section, field, value, reason):
    # Arrange
    registration = copy.deepcopy(FACTS["registration"])
    registration[section][field] = value
    # Act
    result = browser(registration=registration)
    # Assert
    assert result == {"ok": False, "reason": reason}


@pytest.mark.parametrize("capability", ["chromium", "playwright"])
def test_browser_cannot_use_the_generic_image_capability_shape(capability):
    # Arrange
    registration = copy.deepcopy(FACTS["registration"])
    del registration["image"]["capabilities"][capability]
    # Act
    result = browser(registration=registration)
    # Assert
    assert result == {"ok": False, "reason": "image-capabilities-unqualified"}


def test_browser_build_requires_real_installed_wheel_probe_before_artifact_upload():
    # Arrange
    workflow = yaml.safe_load((ROOT / ".github/workflows/leaf-release-sif.yml").read_text())
    steps = workflow["jobs"]["native"]["steps"]
    # Act
    probe = next(row for row in steps if row.get("run", "").endswith("probe-wheel-in-sif.sh 3.12"))
    build = next(i for i, row in enumerate(steps) if row.get("run", "").endswith("build-in-sif.sh 3.12"))
    upload = next(i for i, row in enumerate(steps) if row.get("uses") == "actions/upload-artifact@v4")
    # Assert
    assert build < steps.index(probe) < upload
    assert probe["if"] == "inputs.operation == 'build' && fromJSON(needs.profile.outputs.plan).profile == 'browser'"
    assert probe["env"] == {
        "SCITEX_CI_SIF": "${{ steps.inputs.outputs.sif }}",
        "SCITEX_CI_SIF_SHA256": "${{ fromJSON(needs.profile.outputs.plan).image.sha256 }}",
        "SCITEX_CI_APPTAINER": "${{ steps.inputs.outputs.apptainer }}",
        "SCITEX_BROWSER_RELEASE_SOURCE_SHA": "${{ inputs.source_commit }}",
        "SCITEX_BROWSER_RELEASE_VERSION": "${{ inputs.release_tag }}",
    }
    assert workflow["permissions"] == {"contents": "read"}


def test_browser_uses_approved_content_path_without_changing_other_profile_locators():
    # Arrange
    workflow = yaml.safe_load((ROOT / ".github/workflows/leaf-release-sif.yml").read_text())
    # Act
    gate = next(s for s in workflow["jobs"]["native"]["steps"] if s.get("id") == "inputs")
    locator = gate["env"]["NATIVE_CI_SIF"]
    # Assert
    assert locator == "${{ (fromJSON(needs.profile.outputs.plan).profile == 'browser' || fromJSON(needs.profile.outputs.plan).profile == 'stats') && fromJSON(needs.profile.outputs.plan).image.native_paths[0] || vars.SCITEX_CI_SIF }}"
