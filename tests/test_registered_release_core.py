"""Real public Scholar builds exercise the pinned registered command port."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from _release_core_fixtures import OWNERS, build_owner, policy
from release_core.registered import RELEASE_REGISTRY, SCHOLAR_POLICY

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def scholar(tmp_path_factory):
    record = next(row for row in OWNERS if row["key"] == "scholar")
    return build_owner(record, tmp_path_factory.mktemp("registered-scholar"))


def test_registered_policy_matches_reviewed_actual_hatch_source():
    record = next(row for row in OWNERS if row["key"] == "scholar")
    assert SCHOLAR_POLICY == policy(record)


@pytest.mark.parametrize("repository", ["scitex-ai/figrecipe", "other/scitex-scholar", "scitex-ai/scitex-scholar-extra"])
def test_unregistered_repository_cannot_select_scholar_policy(repository):
    with pytest.raises(ValueError, match="not registered"):
        RELEASE_REGISTRY.resolve(repository)


def command(owner):
    return [sys.executable, "-m", "release_core", "verify-files", "--repository", "scitex-ai/scitex-scholar", "--commit", owner["commit"], "--source-root", str(owner["source"]), "--wheel", str(next(owner["output"].glob("*.whl"))), "--sdist", str(next(owner["output"].glob("*.tar.gz")))]


def test_registered_cli_accepts_real_source_bound_wheel_and_sdist(scholar):
    actual = subprocess.run(command(scholar), cwd=ROOT, check=True, capture_output=True, text=True, timeout=30)
    proof = json.loads(actual.stdout)
    assert (proof["repository"], proof["distribution"], proof["git_commit"], proof["wheel_public_members"] > 0) == ("scitex-ai/scitex-scholar", "scitex-scholar", scholar["commit"], True)


def test_registered_cli_rejects_artifact_byte_tampering(scholar, tmp_path):
    from _release_core_archives import pack_wheel, wheel_files

    files = wheel_files(scholar["wheel"])
    files["scitex_scholar/__init__.py"] += b"\n# foreign rehashed source\n"
    changed = tmp_path / next(scholar["output"].glob("*.whl")).name
    changed.write_bytes(pack_wheel(files, rehash=True))
    args = command(scholar)
    args[args.index("--wheel") + 1] = str(changed)
    actual = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert actual.returncode != 0 and "wheel public source bytes differ" in actual.stderr
