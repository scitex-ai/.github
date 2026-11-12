"""Actual Git/uv/Python controls for an opt-in job-owned environment."""

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pytest-matrix.yml"
STEP = "Stage job-owned virtual environment"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def _stage_script():
    return next(
        s["run"]
        for s in _workflow()["jobs"]["pytest-matrix"]["steps"]
        if s.get("name") == STEP
    )


def _checkout(tmp_path, ignored=".venv\n"):
    checkout = tmp_path / "caller checkout"
    parent = tmp_path / "job scratch"
    checkout.mkdir()
    parent.mkdir()
    env = dict(
        os.environ,
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        UV_CACHE_DIR=str(parent / "uv-cache"),
        UV_NO_CONFIG="1",
        RUNNER_TEMP=str(parent),
    )
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "VIRTUAL_ENV"):
        env.pop(key, None)
    subprocess.run(["git", "init", "-q", str(checkout)], env=env, check=True)
    (checkout / ".gitignore").write_text(ignored)
    (checkout / "kept-source.txt").write_text("unrelated source stays visible\n")
    return checkout, parent, env


def _stage(checkout, env, *, check=False):
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _stage_script()],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=check,
    )


def _status(checkout, env):
    return subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=checkout, env=env, text=True
    )


def test_opt_in_preserves_every_legacy_workflow_field():
    # Arrange
    workflow = _workflow()
    events = workflow.get("on", workflow.get(True))
    declared = events["workflow_call"]["inputs"].pop("job_owned_environment")
    steps = workflow["jobs"]["pytest-matrix"]["steps"]
    stage = next(s for s in steps if s.get("name") == STEP)
    # Act
    steps.remove(stage)
    workflow["on"] = workflow.pop(True)
    digest = hashlib.sha256(
        json.dumps(workflow, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # Assert
    assert (
        declared["type"],
        declared["required"],
        declared["default"],
        stage["if"],
        digest,
    ) == (
        "boolean",
        False,
        False,
        "inputs.job_owned_environment",
        # Reviewed metadata-only aggregate route; native baseline is also
        # protected independently by test_pytest_metadata_aggregate.py.
        "391dd6376841acca4850992c5480546763ae52cc93527757ba2412b4695b2daf",
    )


def test_real_seeded_environment_is_removed_with_job_scratch(tmp_path):
    # Arrange
    checkout, parent, env = _checkout(tmp_path)
    before = _status(checkout, env)
    exclude = (checkout / ".git/info/exclude").read_bytes()
    # Act
    staged = _stage(checkout, env, check=True)
    install = next(
        s["run"]
        for s in _workflow()["jobs"]["pytest-matrix"]["steps"]
        if s.get("name") == "Install (.[all,dev]) + pytest"
    )
    seed = install.split('if [ -n "${DEPENDENCY_GROUP}" ]; then', 1)[0]
    seed = seed.replace("${{ matrix.python-version }}", shlex.quote(sys.executable))
    seeded = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", seed],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    target = (checkout / ".venv").resolve()
    probe = subprocess.run(
        [
            str(checkout / ".venv/bin/python"),
            "-I",
            "-c",
            (
                "import sys,json,importlib.metadata as m;from pathlib import Path;"
                'print(json.dumps({"prefix":str(Path(sys.prefix).resolve()),'
                '"pip":m.version("pip")}))'
            ),
        ],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    observed = (
        staged.returncode,
        seeded.returncode,
        probe.returncode,
        (checkout / ".venv").is_symlink(),
        target.is_relative_to(parent),
        json.loads(probe.stdout)["prefix"] == str(target),
        bool(json.loads(probe.stdout)["pip"]),
    )
    shutil.rmtree(parent)
    # Assert
    assert (
        observed,
        (checkout / ".venv").is_symlink(),
        (checkout / ".venv").exists(),
        _status(checkout, env) == before,
        (checkout / ".git/info/exclude").read_bytes() == exclude,
        (checkout / "kept-source.txt").read_text(),
    ) == (
        (0, 0, 0, True, True, True, True),
        True,
        False,
        True,
        True,
        "unrelated source stays visible\n",
    )


@pytest.mark.parametrize("ignored", [".venv/\n", "!.venv\n", ""])
def test_ineligible_ignore_rules_refuse_without_metadata_edits(tmp_path, ignored):
    # Arrange
    checkout, parent, env = _checkout(tmp_path, ignored)
    before = _status(checkout, env)
    exclude = (checkout / ".git/info/exclude").read_bytes()
    # Act
    result = _stage(checkout, env)
    # Assert
    assert (
        result.returncode,
        (checkout / ".venv").is_symlink(),
        list(parent.iterdir()),
        (checkout / ".gitignore").read_text(),
        (checkout / ".git/info/exclude").read_bytes(),
        _status(checkout, env),
    ) == (1, False, [], ignored, exclude, before)


def _existing_directory(link, target):
    link.mkdir()
    (link / "kept.txt").write_text("keep existing environment")


def _existing_symlink(link, target):
    target.mkdir()
    (target / "kept.txt").write_text("keep existing environment")
    link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("prepare", [_existing_directory, _existing_symlink])
def test_existing_environment_is_never_overwritten(tmp_path, prepare):
    # Arrange
    checkout, parent, env = _checkout(tmp_path)
    link = checkout / ".venv"
    prepare(link, tmp_path / "existing target")
    before = link.lstat()
    # Act
    result = _stage(checkout, env)
    # Assert
    assert (
        result.returncode,
        link.lstat().st_ino == before.st_ino,
        (link / "kept.txt").read_text(),
        list(parent.iterdir()),
    ) == (1, True, "keep existing environment", [])


@pytest.mark.parametrize("location", ["", "relative/path"])
def test_missing_or_relative_job_parent_refuses(tmp_path, location):
    # Arrange
    checkout, parent, env = _checkout(tmp_path)
    env["RUNNER_TEMP"] = location
    # Act
    result = _stage(checkout, env)
    # Assert
    assert (
        result.returncode != 0,
        (checkout / ".venv").is_symlink(),
        list(parent.iterdir()),
    ) == (True, False, [])


def test_git_environment_cannot_redirect_checkout_authority(tmp_path):
    # Arrange
    checkout, parent, env = _checkout(tmp_path)
    foreign = tmp_path / "foreign"
    subprocess.run(["git", "init", "-q", str(foreign)], env=env, check=True)
    env["GIT_DIR"] = str(foreign / ".git")
    # Act
    result = _stage(checkout, env)
    # Assert
    assert (
        result.returncode,
        (checkout / ".venv").is_symlink(),
        list(parent.iterdir()),
    ) == (1, False, [])


def test_symlinked_job_parent_inside_checkout_refuses(tmp_path):
    # Arrange
    checkout, parent, env = _checkout(tmp_path)
    alias = tmp_path / "scratch alias"
    alias.symlink_to(checkout, target_is_directory=True)
    env["RUNNER_TEMP"] = str(alias)
    # Act
    result = _stage(checkout, env)
    # Assert
    assert (
        result.returncode,
        (checkout / ".venv").is_symlink(),
        list(parent.iterdir()),
        list(checkout.glob("scitex-pytest-venv.*")),
    ) == (1, False, [], [])
