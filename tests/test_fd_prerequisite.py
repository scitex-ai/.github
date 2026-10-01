"""Execute reusable bootstrap integrity and ordering with owned fixtures.

Runtime always uses the pinned official release. Executor fixtures substitute
only an owned file transport and known archive digest; they do not claim fd
functionality or require a host installation/network dependency.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_JOB_IDS = {"pytest-matrix.yml": "pytest-matrix", "quality-audit.yml": "audit"}


def _step(workflow: str) -> tuple[dict, list[dict]]:
    document = yaml.safe_load((_REPO / ".github/workflows" / workflow).read_text())
    steps = document["jobs"][_JOB_IDS[workflow]]["steps"]
    return next(s for s in steps if s.get("name") == "Ensure Rust fd for audit discovery"), steps


def _environment(tmp_path: Path) -> dict[str, str]:
    tools = tmp_path / "path"
    tools.mkdir()
    # Real shell utilities only. Deliberately no fd/fdfind in this PATH.
    for name in ("curl", "sha256sum", "tar", "mktemp", "gzip"):
        origin = shutil.which(name)
        if origin is None:
            raise RuntimeError(f"bootstrap test requires the real {name}")
        (tools / name).symlink_to(origin)
    temp = tmp_path / "runner-temp"
    temp.mkdir()
    github_path = tmp_path / "github-path"
    github_path.touch()
    return {
        **os.environ,
        "PATH": str(tools),
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "RUNNER_TEMP": str(temp),
        "GITHUB_PATH": str(github_path),
    }


def _run(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", script],
        env=env, text=True, capture_output=True, check=False, timeout=60,
    )


def _owned_archive(tmp_path: Path, script: str) -> tuple[str, bytes, str]:
    """Use a real owned tar and executable; no network or host fd prerequisite.

    This tests the host bootstrap's integrity/extraction/registration contract.
    Real upstream fd execution and Dev strict discovery are separate evidence.
    """
    payload = b"#!/bin/sh\nprintf 'owned archive executable\\n'\n"
    assets = tmp_path / "assets"
    assets.mkdir()
    archive = assets / "fd-v10.3.0-x86_64-unknown-linux-musl.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("fd-v10.3.0-x86_64-unknown-linux-musl/fd")
        member.size = len(payload)
        member.mode = 0o755
        stream.addfile(member, io.BytesIO(payload))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    command = script.replace(
        "https://github.com/sharkdp/fd/releases/download/v10.3.0/",
        assets.as_uri() + "/",
    ).replace(
        "digest=2b6bfaae8c48f12050813c2ffe1884c61ea26e750d803df9c9114550a314cd14",
        "digest=" + digest,
    )
    return command, payload, digest


@pytest.mark.parametrize("workflow", _JOB_IDS)
def test_bootstrap_precedes_workspace_code_and_keeps_first_guard(workflow):
    # Arrange
    step, steps = _step(workflow)
    # Act
    ordering = (steps[0]["name"], steps.index(step),
                next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("actions/checkout")),
                next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("astral-sh/setup-uv")))
    # Assert
    assert ordering[0] == "Refuse to run fork-authored code on self-hosted infrastructure" and ordering[2] < ordering[1] < ordering[3]


def test_both_workflows_execute_identical_bootstrap_commands():
    # Arrange
    pytest_step, _ = _step("pytest-matrix.yml")
    quality_step, _ = _step("quality-audit.yml")
    # Act
    commands = (pytest_step["run"], quality_step["run"])
    # Assert
    assert commands[0] == commands[1]


def test_verified_archive_registers_the_exact_owned_executable(tmp_path):
    # Arrange
    step, _ = _step("pytest-matrix.yml")
    env = _environment(tmp_path)
    script, payload, _ = _owned_archive(tmp_path, step["run"])
    # Act
    completed = _run(script, env)
    completed.check_returncode()
    paths = Path(env["GITHUB_PATH"]).read_text().splitlines()
    installed = Path(paths[-1]) / "fd"
    # Assert
    assert (installed.read_bytes(), completed.stdout.strip()) == (payload, "owned archive executable")


@pytest.mark.parametrize("name", ("fd", "fdfind"))
def test_existing_executable_alias_avoids_download_and_path_mutation(tmp_path, name):
    # Arrange
    step, _ = _step("quality-audit.yml")
    env = _environment(tmp_path)
    origin = tmp_path / "owned-existing-tool"
    origin.write_text("#!/bin/sh\nprintf 'owned existing executable\\n'\n")
    origin.chmod(0o755)
    (Path(env["PATH"]) / name).symlink_to(origin)
    # Act
    completed = _run(step["run"], env)
    # Assert
    assert (completed.returncode, Path(env["GITHUB_PATH"]).read_text(), list(Path(env["RUNNER_TEMP"]).iterdir())) == (0, "", [])


def test_wrong_checksum_refuses_extraction_and_path_registration(tmp_path):
    # Arrange
    step, _ = _step("quality-audit.yml")
    env = _environment(tmp_path)
    script, _, digest = _owned_archive(tmp_path, step["run"])
    wrong = ("0" if digest[0] != "0" else "1") + digest[1:]
    script = script.replace("digest=" + digest, "digest=" + wrong)
    # Act
    completed = _run(script, env)
    # Assert
    assert (completed.returncode, Path(env["GITHUB_PATH"]).read_text(), list(Path(env["RUNNER_TEMP"]).rglob("fd"))) == (1, "", [])


def test_unsupported_missing_tool_fails_without_creating_job_artifacts(tmp_path):
    # Arrange
    step, _ = _step("quality-audit.yml")
    env = _environment(tmp_path)
    env["RUNNER_ARCH"] = "RISCV64"
    # Act
    completed = _run(step["run"], env)
    # Assert
    assert (completed.returncode, "no pinned bootstrap" in completed.stdout, list(Path(env["RUNNER_TEMP"]).iterdir())) == (1, True, [])
