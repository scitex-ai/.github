"""Adversarial tests for the self-hosted runner npm-cache preflight."""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "runner-npm-cache-preflight.sh"
_HELPER = _REPO / "scripts" / "runner_npm_cache_preflight.py"
_ACTION = _REPO / ".github" / "actions" / "runner-npm-cache-preflight" / "action.yml"
_LOCK_ENV = "SCITEX_NPM_CACHE_LOCK_PATH"


def _environment(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env[_LOCK_ENV] = str(home.parent / "npm-cache-preflight.lock")
    if extra:
        env.update(extra)
    return env


def _run(
    home: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        env=_environment(home, extra_env),
        check=False,
        text=True,
        capture_output=True,
    )


def _run_action(home: Path) -> subprocess.CompletedProcess[str]:
    """Execute the command declared by the real composite action metadata."""
    action = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    steps = action["runs"]["steps"]
    assert len(steps) == 1
    step = steps[0]
    command = step["run"].replace("${{ github.action_path }}", str(_ACTION.parent))
    return subprocess.run(
        [step["shell"], "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", command],
        cwd=_REPO,
        env=_environment(home),
        check=False,
        text=True,
        capture_output=True,
    )


def _quarantines(home: Path) -> list[Path]:
    return sorted(home.glob(".npm.quarantine-*"))


def _load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("runner_npm_cache_preflight", _HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {_HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _with_gid(st: os.stat_result, gid: int) -> os.stat_result:
    values = list(st)
    values[5] = gid
    return os.stat_result(values)


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


def test_mode_zero_owned_directory_is_repaired_in_place(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cache = home / ".npm"
    cache.mkdir(parents=True)
    marker = cache / "marker"
    marker.write_text("keep\n", encoding="utf-8")
    before_inode = cache.stat().st_ino
    cache.chmod(0)

    try:
        result = _run(home)
        assert result.returncode == 0, result.stderr
        assert cache.stat().st_ino == before_inode
        assert stat.S_IMODE(cache.stat().st_mode) == 0o755
        assert marker.read_text(encoding="utf-8") == "keep\n"
    finally:
        cache.chmod(0o755)


def test_cache_ownership_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_helper()
    home = tmp_path / "home"
    cache = home / ".npm"
    cache.mkdir(parents=True)
    marker = cache / "marker"
    marker.write_text("keep\n", encoding="utf-8")
    cache_inode = cache.stat().st_ino
    real_fstat = module.os.fstat

    def mismatched_cache_owner(fd: int) -> os.stat_result:
        current = real_fstat(fd)
        if current.st_ino == cache_inode:
            return _with_gid(current, os.getgid() + 1)
        return current

    monkeypatch.setattr(module.os, "fstat", mismatched_cache_owner)
    home_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(module.PreflightError, match="cache directory ownership"):
            module._repair_cache(home_fd, os.getuid(), os.getgid())
    finally:
        os.close(home_fd)
    assert cache.is_dir() and not cache.is_symlink()
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert _quarantines(home) == []


def test_lock_symlink_is_rejected_without_truncating_target(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    victim = tmp_path / "victim"
    victim.write_text("runner-owned evidence\n", encoding="utf-8")
    lock = tmp_path / "npm-cache-preflight.lock"
    lock.symlink_to(victim)

    result = _run(home)

    assert result.returncode != 0
    assert "lock" in result.stderr
    assert victim.read_text(encoding="utf-8") == "runner-owned evidence\n"
    assert not (home / ".npm").exists()


def test_lock_ownership_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_helper()
    lock = tmp_path / "npm-cache-preflight.lock"
    lock.touch(mode=0o600)
    lock_inode = lock.stat().st_ino
    real_fstat = module.os.fstat

    def mismatched_lock_owner(fd: int) -> os.stat_result:
        current = real_fstat(fd)
        if current.st_ino == lock_inode:
            return _with_gid(current, os.getgid() + 1)
        return current

    monkeypatch.setattr(module.os, "fstat", mismatched_lock_owner)
    with pytest.raises(module.PreflightError, match="lock ownership"):
        with module._locked(lock, os.getuid(), os.getgid()):
            raise AssertionError("ownership mismatch must not acquire the lock")


def test_create_race_never_follows_replacement_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_helper()
    home = tmp_path / "home"
    home.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o700)
    real_mkdir = module.os.mkdir
    raced = False

    def racing_mkdir(
        path: Any, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> None:
        nonlocal raced
        if path == ".npm" and dir_fd is not None and not raced:
            raced = True
            (home / ".npm").symlink_to(victim, target_is_directory=True)
        real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(module.os, "mkdir", racing_mkdir)

    module.preflight(home, tmp_path / "lock")

    assert raced
    assert stat.S_IMODE(victim.stat().st_mode) == 0o700
    assert (home / ".npm").is_dir()
    assert not (home / ".npm").is_symlink()
    quarantines = _quarantines(home)
    assert len(quarantines) == 1
    assert quarantines[0].is_symlink()
    assert os.readlink(quarantines[0]) == str(victim)


def test_quarantine_collision_never_clobbers_existing_evidence(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cache = home / ".npm"
    cache.write_text("new artifact\n", encoding="utf-8")
    first = home / ".npm.quarantine-20000101T000000Z"
    first.write_text("prior evidence\n", encoding="utf-8")

    result = _run(home, {"SOURCE_DATE_EPOCH": "946684800"})

    second = home / ".npm.quarantine-20000101T000000Z.1"
    assert result.returncode == 0, result.stderr
    assert first.read_text(encoding="utf-8") == "prior evidence\n"
    assert second.read_text(encoding="utf-8") == "new artifact\n"
    assert cache.is_dir() and not cache.is_symlink()


def test_concurrent_preflights_quarantine_once(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".npm").symlink_to(tmp_path / "missing")
    env = _environment(home)

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


def test_real_composite_action_executes_the_preflight(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = _run_action(home)

    assert result.returncode == 0, result.stderr
    cache = home / ".npm"
    assert cache.is_dir() and not cache.is_symlink()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o755
