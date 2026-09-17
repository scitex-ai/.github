#!/usr/bin/env python3
"""Safely prepare a shared self-hosted runner's npm cache directory."""

from __future__ import annotations

import contextlib
import ctypes
import datetime as dt
import errno
import fcntl
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

_CACHE_NAME = ".npm"
_LOCK_ENV = "SCITEX_NPM_CACHE_LOCK_PATH"
_RENAME_NOREPLACE = 1
_MAX_RACE_RETRIES = 128
_MAX_QUARANTINE_COLLISIONS = 10_000


class PreflightError(RuntimeError):
    """A condition that cannot be repaired without risking runner state."""


def _identity(st: os.stat_result) -> tuple[int, int]:
    return st.st_uid, st.st_gid


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _require_owner(st: os.stat_result, uid: int, gid: int, label: str) -> None:
    if _identity(st) != (uid, gid):
        raise PreflightError(
            f"{label} ownership is {_identity(st)[0]}:{_identity(st)[1]}; "
            f"expected {uid}:{gid}; refusing to mutate it"
        )


@contextlib.contextmanager
def _locked(lock_path: Path, uid: int, gid: int) -> Iterator[None]:
    """Open a regular owned lock without following links or truncating data."""
    common_flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    created = False
    try:
        try:
            fd = os.open(lock_path, common_flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            fd = os.open(lock_path, common_flags)
    except OSError as exc:
        raise PreflightError(f"cannot safely open lock {lock_path}: {exc}") from exc

    try:
        lock_stat = os.fstat(fd)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise PreflightError(f"lock {lock_path} is not a regular file")
        _require_owner(lock_stat, uid, gid, "lock")
        if lock_stat.st_nlink != 1:
            raise PreflightError(
                f"lock {lock_path} has {lock_stat.st_nlink} links; expected exactly one"
            )
        if created and stat.S_IMODE(lock_stat.st_mode) != 0o600:
            raise PreflightError(f"new lock {lock_path} was not created with mode 0600")

        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            path_stat = os.stat(lock_path, follow_symlinks=False)
        except OSError as exc:
            raise PreflightError(f"lock {lock_path} disappeared while acquiring it") from exc
        if not _same_object(lock_stat, path_stat):
            raise PreflightError(f"lock {lock_path} was replaced while acquiring it")
        yield
    finally:
        os.close(fd)


def _timestamp() -> str:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    try:
        epoch = int(raw_epoch) if raw_epoch is not None else None
    except ValueError as exc:
        raise PreflightError("SOURCE_DATE_EPOCH must be an integer") from exc
    moment = dt.datetime.fromtimestamp(epoch, dt.UTC) if epoch is not None else dt.datetime.now(dt.UTC)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _rename_noreplace(directory_fd: int, source: str, destination: str) -> None:
    """Atomically rename *source* while refusing to replace *destination*."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise PreflightError("renameat2 is unavailable; cannot quarantine without clobbering") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        directory_fd,
        os.fsencode(source),
        directory_fd,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), destination)


def _quarantine(
    home_fd: int,
    source_stat: os.stat_result,
    uid: int,
    gid: int,
) -> str:
    """Move the inspected cache artifact aside without clobbering evidence."""
    base = f"{_CACHE_NAME}.quarantine-{_timestamp()}"
    for collision in range(_MAX_QUARANTINE_COLLISIONS):
        destination = base if collision == 0 else f"{base}.{collision}"
        try:
            current = os.stat(_CACHE_NAME, dir_fd=home_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise PreflightError("cache artifact disappeared before quarantine") from exc
        if not _same_object(source_stat, current):
            raise PreflightError("cache artifact was replaced before quarantine")
        _require_owner(current, uid, gid, "cache artifact")
        try:
            _rename_noreplace(home_fd, _CACHE_NAME, destination)
        except FileExistsError:
            continue
        except OSError as exc:
            raise PreflightError(f"cannot quarantine cache artifact: {exc}") from exc

        moved = os.stat(destination, dir_fd=home_fd, follow_symlinks=False)
        if not _same_object(source_stat, moved):
            raise PreflightError("quarantined object does not match the inspected cache artifact")
        return destination
    raise PreflightError("too many quarantine name collisions; refusing to discard evidence")


def _open_cache_directory(home_fd: int) -> int:
    flags = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    return os.open(_CACHE_NAME, flags, dir_fd=home_fd)


def _make_directory_usable(cache_fd: int) -> None:
    """Repair permissions through an already-open descriptor, then probe writes."""
    descriptor_path = f"/proc/self/fd/{cache_fd}"
    try:
        os.chmod(descriptor_path, 0o755)
    except OSError as exc:
        raise PreflightError(f"cannot set cache directory mode 0755: {exc}") from exc

    probe = f".scitex-npm-cache-preflight-{os.getpid()}"
    probe_fd: int | None = None
    try:
        probe_fd = os.open(
            probe,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=cache_fd,
        )
    except OSError as exc:
        raise PreflightError(f"cache directory is not writable after mode repair: {exc}") from exc
    finally:
        if probe_fd is not None:
            os.close(probe_fd)
    try:
        os.unlink(probe, dir_fd=cache_fd)
    except OSError as exc:
        raise PreflightError(f"cannot remove cache usability probe: {exc}") from exc


def _repair_cache(home_fd: int, uid: int, gid: int) -> str | None:
    """Return a quarantine name when repair moved an artifact, otherwise None."""
    quarantine: str | None = None
    for _ in range(_MAX_RACE_RETRIES):
        try:
            inspected = os.stat(_CACHE_NAME, dir_fd=home_fd, follow_symlinks=False)
        except FileNotFoundError:
            try:
                os.mkdir(_CACHE_NAME, 0o755, dir_fd=home_fd)
            except FileExistsError:
                continue
            except OSError as exc:
                raise PreflightError(f"cannot create cache directory: {exc}") from exc
            continue

        if not stat.S_ISDIR(inspected.st_mode):
            _require_owner(inspected, uid, gid, "cache artifact")
            quarantine = _quarantine(home_fd, inspected, uid, gid)
            continue

        try:
            cache_fd = _open_cache_directory(home_fd)
        except FileNotFoundError:
            continue
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                continue
            raise PreflightError(f"cannot safely open cache directory: {exc}") from exc
        try:
            opened = os.fstat(cache_fd)
            if not _same_object(inspected, opened):
                continue
            _require_owner(opened, uid, gid, "cache directory")
            _make_directory_usable(cache_fd)
            repaired = os.fstat(cache_fd)
            if stat.S_IMODE(repaired.st_mode) != 0o755:
                raise PreflightError("cache directory mode is not 0755 after repair")
            try:
                current = os.stat(_CACHE_NAME, dir_fd=home_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not _same_object(repaired, current):
                continue
            return quarantine
        finally:
            os.close(cache_fd)
    raise PreflightError("cache path kept changing; refusing to continue")


def preflight(home: Path, lock_path: Path) -> str | None:
    """Serialize and safely prepare ``home/.npm``."""
    uid = os.geteuid()
    gid = os.getegid()
    with _locked(lock_path, uid, gid):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            home_fd = os.open(home, flags)
        except OSError as exc:
            raise PreflightError(f"HOME is not an accessible real directory: {exc}") from exc
        try:
            home_stat = os.fstat(home_fd)
            _require_owner(home_stat, uid, gid, "HOME")
            return _repair_cache(home_fd, uid, gid)
        finally:
            os.close(home_fd)


def main() -> int:
    raw_home = os.environ.get("HOME")
    if not raw_home:
        print("::error title=npm cache preflight::HOME must be set", file=sys.stderr)
        return 1
    home = Path(raw_home)
    lock_path = Path(
        os.environ.get(_LOCK_ENV, f"/tmp/scitex-runner-npm-cache-{os.geteuid()}.lock")
    )
    try:
        quarantine = preflight(home, lock_path)
    except (OSError, PreflightError) as exc:
        print(f"::error title=npm cache preflight::{exc}", file=sys.stderr)
        return 1
    if quarantine is not None:
        print(
            "::warning title=npm cache repaired::"
            f"quarantined non-directory cache artifact at {home / quarantine}"
        )
    print(f"npm cache preflight: ready: {home / _CACHE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
