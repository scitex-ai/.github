"""Browser artifact registration verifies real source bytes without runtime admission."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from _release_core_archives import pack_wheel, wheel_files
from _release_core_fixtures import build_owner, build_workspace, policy
from release_core.registered import RELEASE_REGISTRY
from test_leaf_release_contract import dispatch

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads(
    (Path(__file__).parent / "fixtures/release-core/browser.json").read_text()
)


@pytest.fixture(scope="module")
def browser():
    with build_workspace("registered-browser") as root:
        yield build_owner(RECORD, root)


def command(owner):
    return [
        sys.executable, "-m", "release_core", "verify-files",
        "--repository", RECORD["repository"], "--commit", owner["commit"],
        "--source-root", str(owner["source"]),
        "--wheel", str(next(owner["output"].glob("*.whl"))),
        "--sdist", str(next(owner["output"].glob("*.tar.gz"))),
    ]


def test_browser_policy_matches_reviewed_actual_hatch_source():
    assert RELEASE_REGISTRY.resolve(RECORD["repository"]) == policy(RECORD)


def test_registered_browser_cli_accepts_all_committed_package_files(browser):
    result = subprocess.run(
        command(browser), cwd=ROOT, check=True, capture_output=True,
        text=True, timeout=30,
    )
    proof = json.loads(result.stdout)
    assert (
        proof["repository"], proof["distribution"], proof["git_commit"],
        proof["wheel_public_members"], proof["sdist_public_members"],
    ) == (
        RECORD["repository"], RECORD["distribution"], RECORD["commit"], 190, 268,
    )


@pytest.mark.parametrize("member", RECORD["required_members"][1:])
@pytest.mark.parametrize("mutation", ["replace", "remove"])
def test_browser_cli_rejects_rehashed_changed_or_missing_resources(
    browser, tmp_path, member, mutation,
):
    # Arrange: change genuine package bytes, including a truthful replacement RECORD.
    files = wheel_files(browser["wheel"])
    if mutation == "replace":
        files[member] += b"\nforeign payload\n"
    else:
        del files[member]
    changed = tmp_path / next(browser["output"].glob("*.whl")).name
    changed.write_bytes(pack_wheel(files, rehash=True))
    args = command(browser)
    args[args.index("--wheel") + 1] = str(changed)

    # Act
    result = subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True, timeout=30,
    )

    # Assert
    message = (
        "wheel public source bytes differ" if mutation == "replace"
        else "wheel lost required public payload"
    )
    assert (result.returncode != 0, message in result.stderr) == (True, True)


@pytest.mark.parametrize("repository", [
    "other/scitex-browser", "scitex-ai/scitex-browser-extra", "scitex-ai/unknown",
])
def test_browser_registration_is_exact_repository_only(repository):
    with pytest.raises(ValueError, match="not registered"):
        RELEASE_REGISTRY.resolve(repository)


def test_browser_artifact_registration_does_not_admit_runtime():
    # Arrange: the genuine artifact policy is not a native image/runtime record.
    artifact_only = RECORD
    # Act
    result = dispatch(repository=RECORD["repository"], registration=artifact_only)
    # Assert
    assert result == {"ok": False, "reason": "browser-runtime-unregistered"}
