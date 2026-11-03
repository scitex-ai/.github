"""Real public Scholar builds exercise the pinned registered command port."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from _release_core_fixtures import OWNERS, build_owner, build_workspace, policy
from release_core.registered import RELEASE_REGISTRY, SCHOLAR_POLICY

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def scholar():
    record = next(row for row in OWNERS if row["key"] == "scholar")
    with build_workspace("registered-scholar") as root:
        yield build_owner(record, root)


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


def test_legacy_1290_normal_build_is_rejected_for_missing_tracked_svg():
    import zipfile
    from release_core import source_payload_identity
    from _release_core_fixtures import git

    record = dict(next(row for row in OWNERS if row["key"] == "scholar"))
    record["commit"] = "d6d5f8ecb9ce4a57000013a8c5943bf7e2b4018e"
    with build_workspace("legacy-scholar-1290") as root:
        owner = build_owner(record, root)
        expected = {row.removeprefix("src/") for row in git(owner["source"], "ls-tree", "-r", "--name-only", "HEAD", "--", "src/scitex_scholar").splitlines()}
        with zipfile.ZipFile(next(owner["output"].glob("*.whl"))) as wheel:
            actual = {name for name in wheel.namelist() if name.startswith("scitex_scholar/") and not name.endswith("/")}
        assert expected - actual == {"scitex_scholar/_django/static/scholar/img/scitex-favicon-official.svg"} and not actual - expected
        with pytest.raises(ValueError, match="whole wheel public source membership differs"):
            source_payload_identity(owner["wheel"], owner["sdist"], owner["commit"], owner["policy"], source_root=owner["source"])


def test_build_workspace_does_not_inherit_ignored_cache_ancestor(monkeypatch, tmp_path):
    cache = tmp_path / ".cache"
    cache.mkdir()
    monkeypatch.setenv("TMPDIR", str(cache))
    with build_workspace("cache-independent") as root:
        assert root.parent == Path("/tmp") and ".cache" not in root.parts
