"""Regression tests for the self-hosted runner npm-cache preflight.

The incident this pins was a broken ``$HOME/.npm`` symlink.  npm then failed
before dependency installation, so every JavaScript check scheduled on the
host failed for runner state rather than for the checked-out revision.

These tests execute the real hook against isolated HOME directories.  They do
not need npm or network access.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "runner-npm-cache-preflight.sh"
_ACTION = _REPO / ".github" / "actions" / "runner-npm-cache-preflight" / "action.yml"


def _run(home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def _quarantines(home: Path) -> list[Path]:
    return sorted(home.glob(".npm.quarantine-*"))


def test_missing_cache_becomes_owned_real_directory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = _run(home)

    cache = home / ".npm"
    assert result.returncode == 0, result.stderr
    assert cache.is_dir()
    assert not cache.is_symlink()
    assert cache.stat().st_uid == os.getuid()
    assert cache.stat().st_gid == os.getgid()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o755
    assert _quarantines(home) == []


def test_broken_symlink_is_quarantined_without_dereferencing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cache = home / ".npm"
    missing_target = tmp_path / "missing" / "npm"
    cache.symlink_to(missing_target)

    result = _run(home)

    quarantines = _quarantines(home)
    assert result.returncode == 0, result.stderr
    assert cache.is_dir() and not cache.is_symlink()
    assert len(quarantines) == 1
    assert quarantines[0].is_symlink()
    assert os.readlink(quarantines[0]) == str(missing_target)


def test_regular_file_is_preserved_in_quarantine(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cache = home / ".npm"
    cache.write_text("corrupt-cache-artifact\n", encoding="utf-8")

    result = _run(home)

    quarantines = _quarantines(home)
    assert result.returncode == 0, result.stderr
    assert cache.is_dir()
    assert len(quarantines) == 1
    assert quarantines[0].read_text(encoding="utf-8") == "corrupt-cache-artifact\n"


def test_existing_owned_directory_is_left_intact(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cache = home / ".npm"
    cache.mkdir(parents=True)
    marker = cache / "marker"
    marker.write_text("keep\n", encoding="utf-8")
    before_inode = cache.stat().st_ino

    result = _run(home)

    assert result.returncode == 0, result.stderr
    assert cache.stat().st_ino == before_inode
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert _quarantines(home) == []


def test_concurrent_preflights_quarantine_once(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".npm").symlink_to(tmp_path / "missing")
    env = os.environ.copy()
    env["HOME"] = str(home)

    processes = [
        subprocess.Popen(
            ["bash", str(_SCRIPT)],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=10) + (process.returncode,) for process in processes]

    assert [result[2] for result in results] == [0, 0], results
    assert (home / ".npm").is_dir()
    assert len(_quarantines(home)) == 1


def test_composite_action_executes_the_preflight() -> None:
    action = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))

    assert action["runs"]["using"] == "composite"
    steps = action["runs"]["steps"]
    assert len(steps) == 1
    assert steps[0]["shell"] == "bash"
    assert "runner-npm-cache-preflight.sh" in steps[0]["run"]
