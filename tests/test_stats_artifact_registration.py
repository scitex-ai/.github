"""Stats artifact registration verifies real source bytes without runtime admission."""

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
    (Path(__file__).parent / "fixtures/release-core/stats.json").read_text()
)


@pytest.fixture(scope="module")
def stats():
    with build_workspace("registered-stats") as root:
        yield build_owner(RECORD, root)


def command(owner):
    return [
        sys.executable, "-m", "release_core", "verify-files",
        "--repository", RECORD["repository"], "--commit", owner["commit"],
        "--source-root", str(owner["source"]),
        "--wheel", str(next(owner["output"].glob("*.whl"))),
        "--sdist", str(next(owner["output"].glob("*.tar.gz"))),
    ]


def test_stats_policy_matches_reviewed_actual_hatch_source():
    assert RELEASE_REGISTRY.resolve(RECORD["repository"]) == policy(RECORD)


def test_registered_stats_cli_accepts_all_committed_package_files(stats):
    result = subprocess.run(
        command(stats), cwd=ROOT, check=True, capture_output=True,
        text=True, timeout=30,
    )
    proof = json.loads(result.stdout)
    assert (
        proof["repository"], proof["distribution"], proof["git_commit"],
        proof["wheel_public_members"], proof["sdist_public_members"],
    ) == (
        RECORD["repository"], RECORD["distribution"], RECORD["commit"], 319, 513,
    )


@pytest.mark.parametrize("member", RECORD["required_members"][1:])
@pytest.mark.parametrize("mutation", ["replace", "remove"])
def test_stats_cli_rejects_rehashed_changed_or_missing_resources(
    stats, tmp_path, member, mutation,
):
    # Arrange: change genuine package bytes, including a truthful replacement RECORD.
    files = wheel_files(stats["wheel"])
    if mutation == "replace":
        files[member] += b"\nforeign payload\n"
    else:
        del files[member]
    changed = tmp_path / next(stats["output"].glob("*.whl")).name
    changed.write_bytes(pack_wheel(files, rehash=True))
    args = command(stats)
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
    "other/scitex-stats", "scitex-ai/scitex-stats-extra", "scitex-ai/unknown",
])
def test_stats_registration_is_exact_repository_only(repository):
    with pytest.raises(ValueError, match="not registered"):
        RELEASE_REGISTRY.resolve(repository)


def test_stats_artifact_ownership_cannot_admit_build_or_upload():
    # Arrange: artifact ownership and test-only runtime admission are separate.
    artifact_only = RELEASE_REGISTRY.resolve(RECORD["repository"])
    # Act: exercise the actual workflow router, without a test-helper override.
    result = dispatch(repository=artifact_only.repository, operation="build")
    # Assert
    assert result == {"ok": False, "reason": "stats-release-operation-refused"}
