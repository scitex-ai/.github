"""Full SDK validation bodies and actual original-event admission controls."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILES = (
    ("sdk-python-package.yml", "sdk-original-python-package.yml"),
    ("sdk-frontend.yml", "sdk-original-frontend.yml"),
)
FORK = (
    "github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name != github.repository"
)
NATIVE_GUARD = "Require confirmed organization membership on native runners"
SOURCE_GUARD = "Require the declared SDK source repository"


def load(path):
    return yaml.safe_load(path.read_text())


def sources(profile):
    filename, fixture = profile
    return (
        load(ROOT / ".github/workflows" / filename),
        load(ROOT / "tests/fixtures" / fixture),
    )


def admission_errors(workflow):
    errors = []
    jobs = workflow["jobs"]
    admission = jobs.get("runner-admission", {})
    if admission.get("uses") != "./.github/workflows/runner-admission.yml":
        errors.append("same-revision-admission")
    for name, job in jobs.items():
        if "steps" not in job:
            continue
        if job.get("needs") != "runner-admission":
            errors.append(name + ":missing-needs")
        routing = str(job.get("runs-on", ""))
        if FORK not in routing or "ubuntu-latest" not in routing:
            errors.append(name + ":fork-routing")
        if "needs.runner-admission.outputs.runs_on" not in routing:
            errors.append(name + ":unadmitted-destination")
        steps = job["steps"]
        checkouts = [
            index
            for index, step in enumerate(steps)
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        guards = [
            index
            for index, step in enumerate(steps)
            if step.get("name") == NATIVE_GUARD
            and "native_authorized != 'true'" in step.get("if", "")
            and "exit 1" in step.get("run", "")
        ]
        if not checkouts or len(guards) != 1 or guards[0] >= min(checkouts):
            errors.append(name + ":native-before-checkout")
    return errors


@pytest.mark.parametrize("profile", PROFILES)
def test_original_sdk_source_demonstrates_actual_missing_admission(profile):
    # Arrange
    _, original = sources(profile)
    # Act
    actual = admission_errors(original)
    # Assert
    assert "same-revision-admission" in actual and any(
        value.endswith(":native-before-checkout") for value in actual
    )


@pytest.mark.parametrize("profile", PROFILES)
def test_successor_admits_before_every_original_checkout(profile):
    # Arrange
    current, _ = sources(profile)
    # Act
    actual = admission_errors(current)
    # Assert
    assert actual == []


@pytest.mark.parametrize("profile", PROFILES)
def test_complete_original_jobs_matrix_timeout_and_validation_tail_survive(profile):
    # Arrange
    current, original = sources(profile)
    # Act
    observed = {
        name: {
            key: value
            for key, value in job.items()
            if key not in ("needs", "runs-on", "steps")
        }
        | {"steps": job["steps"][3:]}
        for name, job in current["jobs"].items()
        if name != "runner-admission"
    }
    expected = {
        name: {
            key: value for key, value in job.items() if key not in ("runs-on", "steps")
        }
        | {"steps": job["steps"][1:]}
        for name, job in original["jobs"].items()
    }
    # Assert
    assert observed == expected


@pytest.mark.parametrize("profile", PROFILES)
def test_fixed_no_command_or_secret_oidc_interface(profile):
    # Arrange
    current, _ = sources(profile)
    # Act
    interface = current.get(True, current.get("on"))["workflow_call"]
    inputs = interface.get("inputs", {}) if interface else {}
    observed = (
        current["permissions"],
        set(inputs),
        any(
            "secrets" in job or "permissions" in job for job in current["jobs"].values()
        ),
    )
    # Assert
    assert observed == (
        {"contents": "read"},
        {"ref"} if profile[0] == "sdk-frontend.yml" else set(),
        False,
    )


@pytest.mark.parametrize("profile", PROFILES)
def test_declared_sdk_repository_guard_before_any_source_execution(profile):
    # Arrange
    current, _ = sources(profile)
    # Act
    observed = [
        (
            job["steps"][2]["name"],
            job["steps"][2]["run"],
            job["steps"][3]["uses"],
        )
        for job in current["jobs"].values()
        if "steps" in job
    ]
    # Assert
    assert (
        observed
        == [
            (
                SOURCE_GUARD,
                'test "$GITHUB_REPOSITORY" = "scitex-ai/scitex-sdk"\n',
                "actions/checkout@v4",
            )
        ]
        * len(observed)
        and observed
    )


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("mutation", ("admission", "route", "guard", "order"))
def test_concrete_authority_mutations_are_refused(profile, mutation):
    # Arrange
    source, _ = sources(profile)
    changed = copy.deepcopy(source)
    job = next(job for job in changed["jobs"].values() if "steps" in job)
    # Act
    if mutation == "admission":
        changed["jobs"]["runner-admission"]["uses"] = "./foreign.yml"
    elif mutation == "route":
        job["runs-on"] = ["self-hosted", "scitex-ci"]
    elif mutation == "guard":
        job["steps"][1]["if"] = "false"
    else:
        job["steps"][1], job["steps"][3] = job["steps"][3], job["steps"][1]
    actual = admission_errors(changed)
    # Assert
    assert actual


def execute_admission(tmp_path, **changes):
    """Reuse the real admitted Node script and its existing no-network harness."""
    path = ROOT / "tests/test_member_admission.py"
    spec = importlib.util.spec_from_file_location("sdk_actual_member_admission", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.execute(tmp_path, REPOSITORY="scitex-ai/scitex-sdk", **changes)


@pytest.mark.parametrize("actor", ("ORIGINAL_ACTOR", "TRIGGERING_ACTOR", "PR_AUTHOR"))
def test_sdk_native_requires_each_trusted_event_identity(tmp_path, actor):
    # Arrange
    changes = {
        "EVENT_NAME": "pull_request",
        "PR_AUTHOR": "ywatanabe1989",
        "PR_AUTHOR_ID": "42527473",
        "HEAD_REPOSITORY": "scitex-ai/scitex-sdk",
        actor: "external",
    }
    if actor == "ORIGINAL_ACTOR":
        changes["ORIGINAL_ACTOR_ID"] = "100"
    elif actor == "TRIGGERING_ACTOR":
        changes["TRIGGERING_ACTOR"] = "external"
    else:
        changes["PR_AUTHOR_ID"] = "100"
    # Act
    observed = execute_admission(tmp_path, **changes)
    # Assert
    assert (observed["native_authorized"], observed["runs_on"]) == (
        "false",
        ["ubuntu-latest"],
    )


@pytest.mark.parametrize("origin", ("", "contributor/sdk"))
def test_sdk_member_fork_or_missing_origin_stays_hosted(tmp_path, origin):
    # Arrange
    changes = {
        "EVENT_NAME": "pull_request",
        "PR_AUTHOR": "ywatanabe1989",
        "PR_AUTHOR_ID": "42527473",
        "HEAD_REPOSITORY": origin,
    }
    # Act
    observed = execute_admission(tmp_path, **changes)
    # Assert
    assert (observed["native_authorized"], observed["runs_on"]) == (
        "false",
        ["ubuntu-latest"],
    )


def test_sdk_confirmed_members_select_exact_company_group(tmp_path):
    # Arrange
    changes = {
        "EVENT_NAME": "pull_request",
        "PR_AUTHOR": "ywatanabe1989",
        "PR_AUTHOR_ID": "42527473",
        "HEAD_REPOSITORY": "scitex-ai/scitex-sdk",
    }
    # Act
    observed = execute_admission(tmp_path, **changes)
    # Assert
    assert (observed["native_authorized"], observed["runs_on"]) == (
        "true",
        {
            "group": "Organization",
            "labels": ["self-hosted", "Linux", "X64", "scitex-org-cpu"],
        },
    )
