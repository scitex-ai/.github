"""Execute the actual reusable fd bootstrap in temporary runner directories."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_JOB_IDS = {"pytest-matrix.yml": "pytest-matrix", "quality-audit.yml": "audit"}
_PYTHON = Path(os.environ.get("SCITEX_TEST_PYTHON", os.sys.executable))


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


def test_missing_fd_downloads_verified_tool_for_real_strict_discovery(tmp_path):
    # Arrange
    step, _ = _step("pytest-matrix.yml")
    env = _environment(tmp_path)
    project = tmp_path / "synthetic"
    project.mkdir()
    (project / "visible.py").write_text("value = 1\n")
    (project / ".hidden.py").write_text("hidden = 1\n")
    # Act
    completed = _run(step["run"], env)
    paths = Path(env["GITHUB_PATH"]).read_text().splitlines()
    completed.check_returncode()
    env["PATH"] = paths[-1] + os.pathsep + env["PATH"]
    probe = subprocess.run(
        [str(_PYTHON), "-c", "from pathlib import Path; import json; from scitex_dev._cli.audit._fd import fd_find_files; print(json.dumps([p.name for p in fd_find_files(Path(__import__('sys').argv[1]), glob='*.py', require_fd=True)]))", str(project)],
        env=env, text=True, capture_output=True, check=False, timeout=30,
    )
    # Assert
    assert (probe.returncode, json.loads(probe.stdout)) == (0, ["visible.py"])


@pytest.mark.parametrize("name", ("fd", "fdfind"))
def test_existing_real_fd_alias_avoids_download_and_path_mutation(tmp_path, name):
    # Arrange
    step, _ = _step("quality-audit.yml")
    env = _environment(tmp_path)
    origin = shutil.which("fdfind") or shutil.which("fd")
    if origin is None:
        raise RuntimeError("existing-tool control requires real fd/fdfind")
    (Path(env["PATH"]) / name).symlink_to(origin)
    # Act
    completed = _run(step["run"], env)
    # Assert
    assert (completed.returncode, Path(env["GITHUB_PATH"]).read_text(), list(Path(env["RUNNER_TEMP"]).iterdir())) == (0, "", [])


def test_wrong_checksum_refuses_extraction_and_path_registration(tmp_path):
    # Arrange
    step, _ = _step("quality-audit.yml")
    env = _environment(tmp_path)
    script = step["run"].replace("digest=2b6bf", "digest=0b6bf")
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
