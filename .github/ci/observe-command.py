#!/usr/bin/env python3
"""Observe one CI command without imposing resource limits or changing its exit.

Pilot: the org's own workflow contract tests. No command arguments, environment,
process command lines, or test output are copied into the diagnostic artifact.
The original stdout/stderr remain in the original GitHub job log.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path


def unavailable(reason: str) -> dict:
    return {"state": "unknown", "reason": reason}


def cgroup_snapshot(
    proc_root: Path = Path("/proc"), root: Path = Path("/sys/fs/cgroup")
) -> dict:
    """The existing runner cgroup is shared; none of its counters are job RSS."""
    try:
        entries = (proc_root / "self/cgroup").read_text().splitlines()
        relative = next(row[3:] for row in entries if row.startswith("0::"))
        parts = Path(relative).parts
        if ".." in parts:
            return unavailable("invalid-cgroup-path")
        base = root.resolve()
        directory = (base / relative.lstrip("/")).resolve()
        if not directory.is_relative_to(base):
            return unavailable("cgroup-outside-mount")
        values = {}
        for name in (
            "memory.current",
            "memory.peak",
            "memory.events",
            "memory.pressure",
        ):
            try:
                body = (directory / name).read_text()
                if name in ("memory.current", "memory.peak"):
                    values[name] = {"state": "observed", "bytes": int(body.strip())}
                elif name == "memory.events":
                    values[name] = {
                        "state": "observed",
                        "counters": {
                            key: int(value)
                            for key, value in (row.split() for row in body.splitlines())
                        },
                    }
                else:
                    values[name] = {"state": "observed", "raw": body[:4096]}
            except (OSError, ValueError):
                values[name] = unavailable("counter-unavailable")
        directory_stat = directory.stat()
        return {
            "state": "observed",
            "scope": "existing-runner-cgroup-shared-not-job-isolated",
            "identity": [directory_stat.st_dev, directory_stat.st_ino],
            "counters": values,
        }
    except (OSError, StopIteration, ValueError):
        return unavailable("unified-cgroup-unavailable")


def process_tree_sample(pid: int, birth: int, proc_root: Path = Path("/proc")) -> dict:
    """Sample the sum of RSS; shared mappings may be counted more than once."""
    rows = {}
    unreadable = 0
    try:
        directories = list(proc_root.iterdir())
    except OSError:
        return unavailable("process-table-unavailable")
    for entry in directories:
        if not entry.name.isdecimal():
            continue
        try:
            body = (entry / "stat").read_text()
            # comm can contain spaces and ')'; its last ')' ends field2.
            fields = body[body.rindex(")") + 2 :].split()
            rows[int(entry.name)] = (int(fields[1]), int(fields[19]), int(fields[21]))
        except (OSError, ValueError, IndexError):
            unreadable += 1
    if pid not in rows or rows[pid][1] != birth:
        return unavailable("command-birth-not-current")
    members = {pid}
    changed = True
    while changed:
        additions = {
            child
            for child, (parent, _, _) in rows.items()
            if parent in members and child not in members
        }
        changed = bool(additions)
        members.update(additions)
    return {
        "state": "observed",
        "bytes": sum(max(0, rows[member][2]) for member in members)
        * os.sysconf("SC_PAGE_SIZE"),
        "processes": len(members),
        "unreadable_proc_entries": unreadable,
        "scope": "sampled-sum-process-rss-not-distinct-or-charged-memory",
    }


def oom_evidence(before: dict, after: dict) -> dict:
    try:
        if before["identity"] != after["identity"]:
            return unavailable("cgroup-scope-changed")
        start = before["counters"]["memory.events"]["counters"]
        end = after["counters"]["memory.events"]["counters"]
        deltas = {key: end[key] - start[key] for key in ("oom", "oom_kill")}
        if any(value < 0 for value in deltas.values()):
            return unavailable("counter-reset-or-scope-changed")
        return {
            "state": "observed",
            "deltas": deltas,
            "attribution": "unknown-shared-cgroup",
            "meaning": "shared-cgroup-event-counter-delta-only",
        }
    except (KeyError, TypeError):
        return unavailable("oom-event-counters-unavailable")


def write_json_exclusive(path: Path, payload: dict) -> None:
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode):
        raise OSError("artifact-parent-not-directory")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def identity() -> dict:
    names = (
        "GITHUB_REPOSITORY",
        "GITHUB_SHA",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_JOB",
        "RUNNER_NAME",
        "RUNNER_OS",
        "RUNNER_ARCH",
        "RUNNER_ENVIRONMENT",
    )
    values = {name.lower(): os.environ.get(name, "")[:256] for name in names}
    values["job_id_kind"] = "logical-GITHUB_JOB-numeric-API-job-id-unobserved"
    request = os.environ.get("CI_MEMORY_REQUEST_MIB", "")
    values["declared_memory_request_mib"] = (
        int(request)
        if len(request) < 11 and request.isdecimal() and 0 < int(request) < 2**31
        else None
    )
    values["declared_request_enforced"] = False
    return values


def summary(payload: dict) -> str:
    peak = payload["sampled_process_tree_rss_peak_bytes"]
    signal_number = payload["command"]["signal"]
    original = (
        f"signal {signal_number}"
        if signal_number
        else f"exit {payload['command']['exit_code']}"
    )
    return (
        "\n### Passive CI command observation\n\n"
        f"Original command result: **{original}**. "
        "Original failure details remain in this job's log.\n\n"
        "Sampled descendant RSS peak: "
        f"**{peak if peak is not None else 'UNKNOWN'} bytes** "
        "(a sampled sum; shared mappings may be counted more than once, "
        "and short-lived or reparented processes may be missed).\n\n"
        f"wait4 maximum RSS: **{payload['wait4_maxrss_kib']} KiB** "
        "(largest reported process usage; not summed concurrent memory).\n\n"
        "Cgroup memory current/peak are shared runner counters, "
        "not this job's exclusive usage. OOM attribution is UNKNOWN "
        "even when a shared counter rises; SIGKILL alone does not prove OOM.\n\n"
        f"External cancellation: **{payload['cancellation']['signal'] or 'none'}**. "
        "Cancellation is kept separate from OOM evidence.\n\n"
        "No resource limits, scheduling, registrations or command dependencies "
        "were changed. Download `passive-ci-observation` for exact run/attempt, "
        "samples and event counters.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required")
    before = cgroup_snapshot()
    started = time.monotonic()
    process = None
    birth = None
    cancellation_signal = None
    cancellation_at = None
    cancellation_forwarded = False
    cancellation_kill_requested = False
    cancellation_grace_seconds = 2.0
    previous_handlers = {}

    def signal_owned_group(signum):
        if process is None or birth is None:
            return
        try:
            body = Path(f"/proc/{process.pid}/stat").read_text()
            current = int(body[body.rindex(")") + 2 :].split()[19])
            if current != birth:
                return
            os.killpg(process.pid, signum)
        except (OSError, ValueError, IndexError):
            pass

    def forward(signum, _frame):
        nonlocal cancellation_signal, cancellation_at, cancellation_forwarded
        if cancellation_signal is None:
            cancellation_signal = signum
            cancellation_at = time.monotonic()
        if process is not None and birth is not None:
            signal_owned_group(signum)
            cancellation_forwarded = True

    # Install before Popen: a signal during process publication stays pending.
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.signal(signum, forward)
    samples = []
    try:
        try:
            process = subprocess.Popen(command, start_new_session=True)
        except OSError:
            print(
                "::error title=CI command launch failed::Original command could "
                "not start; no resource diagnosis is available.",
                file=sys.stderr,
            )
            return 128 + cancellation_signal if cancellation_signal else 127
        try:
            body = Path(f"/proc/{process.pid}/stat").read_text()
            birth = int(body[body.rindex(")") + 2 :].split()[19])
        except (OSError, ValueError, IndexError):
            pass
        while True:
            if cancellation_signal is not None:
                if not cancellation_forwarded:
                    signal_owned_group(cancellation_signal)
                    cancellation_forwarded = True
                # Keep the unreaped leader as the incarnation anchor while its
                # group gets a bounded grace after an EXTERNAL cancellation.
                # This is never an execution timeout or resource allocation.
                if time.monotonic() - cancellation_at < cancellation_grace_seconds:
                    time.sleep(0.05)
                    continue
                if not cancellation_kill_requested:
                    signal_owned_group(signal.SIGKILL)
                    cancellation_kill_requested = True
            waited, status, usage = os.wait4(process.pid, os.WNOHANG)
            if waited:
                code = os.waitstatus_to_exitcode(status)
                process.returncode = code
                break
            sample = (
                process_tree_sample(process.pid, birth)
                if birth is not None
                else unavailable("command-birth-unobserved")
            )
            sample["elapsed_seconds"] = round(time.monotonic() - started, 3)
            samples.append(sample)
            time.sleep(0.25)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    after = cgroup_snapshot()
    observed = [row["bytes"] for row in samples if row["state"] == "observed"]
    payload = {
        "schema_version": 1,
        "phase": "passive-pilot",
        "identity": identity(),
        "command": {
            "exit_code": code if code >= 0 else None,
            "signal": -code if code < 0 else None,
            "pid": process.pid,
            "birth_ticks": birth,
            "actual_wait_reaped": True,
        },
        "duration_seconds": round(time.monotonic() - started, 3),
        "sample_interval_seconds": 0.25,
        "samples": samples,
        "sampled_process_tree_rss_peak_bytes": max(observed) if observed else None,
        "wait4_maxrss_kib": usage.ru_maxrss,
        "existing_cgroup_before": before,
        "existing_cgroup_after": after,
        "oom_evidence": oom_evidence(before, after),
        "queue_duration": unavailable("queue-not-observed-by-command-wrapper"),
        "resource_limits_changed": False,
        "cancellation": {
            "signal": cancellation_signal,
            "grace_seconds": cancellation_grace_seconds,
            "owned_group_kill_requested": cancellation_kill_requested,
        },
    }
    try:
        write_json_exclusive(args.artifact, payload)
        if args.summary:
            with args.summary.open("a") as stream:
                stream.write(summary(payload))
    except OSError:
        print(
            "::warning title=CI observation unavailable::Diagnostic output "
            "could not be recorded; original command result is retained.",
            file=sys.stderr,
        )
    if cancellation_signal is not None:
        return 128 + cancellation_signal
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main())
