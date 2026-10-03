"""Real child exits, untouched artifacts, Linux sampling and honest OOM scope."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/ci/observe-command.py"
spec = importlib.util.spec_from_file_location("ci_observer", SCRIPT)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


@pytest.mark.parametrize("exit_code", [0, 7])
def test_actual_child_result_and_original_logs_are_preserved(tmp_path, exit_code):
    artifact = tmp_path / "observation.json"
    summary = tmp_path / "summary.md"
    marker = "private-argument-must-not-enter-artifact"
    env = dict(
        os.environ,
        CCT_BOT_TOKEN="never-record-this-token",
        GITHUB_RUN_ID="123",
        GITHUB_RUN_ATTEMPT="2",
    )
    code = (
        "import sys,time;print('original stdout');"
        "print('original stderr',file=sys.stderr);"
        f"time.sleep(.4);sys.exit({exit_code})"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--artifact",
            str(artifact),
            "--summary",
            str(summary),
            "--",
            sys.executable,
            "-c",
            code,
            marker,
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    assert result.returncode == exit_code
    assert "original stdout" in result.stdout
    assert "original stderr" in result.stderr
    body = artifact.read_text()
    receipt = json.loads(body)
    assert receipt["command"]["exit_code"] == exit_code
    assert receipt["command"]["actual_wait_reaped"] is True
    assert receipt["identity"]["github_run_id"] == "123"
    assert receipt["identity"]["github_run_attempt"] == "2"
    assert receipt["resource_limits_changed"] is False
    assert receipt["sampled_process_tree_rss_peak_bytes"] > 0
    assert receipt["queue_duration"]["state"] == "unknown"
    assert not Path(f"/proc/{receipt['command']['pid']}").exists()
    assert marker not in body and "never-record-this-token" not in body
    assert "original stdout" not in body and "original stderr" not in body
    assert "OOM attribution is UNKNOWN" in summary.read_text()


def test_signal_death_retains_signal_without_inventing_oom(tmp_path):
    artifact = tmp_path / "signal.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--artifact",
            str(artifact),
            "--",
            sys.executable,
            "-c",
            "import os,signal;os.kill(os.getpid(),signal.SIGKILL)",
        ],
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 137
    receipt = json.loads(artifact.read_text())
    assert receipt["command"]["signal"] == 9
    assert receipt["command"]["exit_code"] is None
    if receipt["oom_evidence"]["state"] == "observed":
        assert receipt["oom_evidence"]["attribution"] == "unknown-shared-cgroup"


@pytest.mark.parametrize("during_publication", [True, False])
def test_external_cancel_during_publication_or_running_command_is_reaped(
    tmp_path, during_publication
):
    artifact = tmp_path / "cancel.json"
    ready = tmp_path / "ready"
    child = (
        "import os,signal,time,pathlib;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid()));"
        "time.sleep(30)"
    )
    program = (
        "import importlib.util,os,pathlib,signal,sys,time\n"
        f"spec=importlib.util.spec_from_file_location('observer',{str(SCRIPT)!r})\n"
        "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
        "original=module.subprocess.Popen\n"
        "def publish(*args,**kwargs):\n"
        "    process=original(*args,**kwargs)\n"
        "    deadline=time.monotonic()+2\n"
        f"    while not pathlib.Path({str(ready)!r}).exists():\n"
        "        if time.monotonic()>deadline: raise RuntimeError('child not ready')\n"
        "        time.sleep(.01)\n"
        "    os.kill(os.getpid(),signal.SIGTERM)\n"
        "    return process\n"
        + ("module.subprocess.Popen=publish\n" if during_publication else "")
        + f"sys.argv=['observe','--artifact',{str(artifact)!r},'--',"
        f"{sys.executable!r},'-c',{child!r}]\n"
        "raise SystemExit(module.main())\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", program],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 3
        while not ready.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.01)
        if not during_publication:
            os.kill(process.pid, signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 143, (stdout, stderr)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        if not artifact.exists() and ready.exists():
            # Failure cleanup only for this fixture's owned child.
            try:
                os.kill(int(ready.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
    receipt = json.loads(artifact.read_text())
    assert receipt["cancellation"]["signal"] == 15
    assert receipt["cancellation"]["owned_group_kill_requested"] is True
    assert receipt["command"]["signal"] == 9
    assert receipt["command"]["actual_wait_reaped"] is True
    assert not Path(f"/proc/{receipt['command']['pid']}").exists()


def test_existing_artifact_is_never_overwritten_or_original_failure_masked(tmp_path):
    artifact = tmp_path / "existing.json"
    artifact.write_text("existing evidence\n")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--artifact",
            str(artifact),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(19)",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 19
    assert artifact.read_text() == "existing evidence\n"
    assert "CI observation unavailable" in result.stderr


def test_unreadable_cgroup_is_unknown_and_shared_events_never_prove_job_oom(tmp_path):
    assert observer.cgroup_snapshot(tmp_path, tmp_path)["state"] == "unknown"

    def snapshot(oom, killed, identity=(1, 2)):
        return {
            "identity": list(identity),
            "counters": {
                "memory.events": {"counters": {"oom": oom, "oom_kill": killed}}
            },
        }

    event = observer.oom_evidence(snapshot(0, 0), snapshot(2, 1))
    assert event["deltas"] == {"oom": 2, "oom_kill": 1}
    assert event["attribution"] == "unknown-shared-cgroup"
    assert observer.oom_evidence(snapshot(3, 1), snapshot(0, 0))["state"] == "unknown"
    assert (
        observer.oom_evidence(snapshot(0, 0), snapshot(2, 1, (1, 3)))["reason"]
        == "cgroup-scope-changed"
    )


def test_descendant_sampling_excludes_unrelated_process_and_fences_pid_reuse(tmp_path):
    def proc(pid, parent, birth, rss):
        directory = tmp_path / str(pid)
        directory.mkdir()
        fields = ["0"] * 22
        fields[0], fields[1], fields[19], fields[21] = (
            "S",
            str(parent),
            str(birth),
            str(rss),
        )
        (directory / "stat").write_text(
            f"{pid} (command ) with spaces) " + " ".join(fields)
        )

    proc(42, 1, 100, 2)
    proc(43, 42, 101, 3)
    proc(44, 1, 102, 999999)
    sample = observer.process_tree_sample(42, 100, tmp_path)
    assert sample["bytes"] == 5 * os.sysconf("SC_PAGE_SIZE")
    assert sample["processes"] == 2
    assert observer.process_tree_sample(42, 99, tmp_path)["state"] == "unknown"


def test_pilot_retains_original_contract_test_command_and_always_reports_missing_data():
    workflow = yaml.safe_load((ROOT / ".github/workflows/self-test.yml").read_text())
    steps = workflow["jobs"]["pytest"]["steps"]
    command = next(
        step for step in steps if step.get("name") == "run workflow contract tests"
    )
    assert command["run"].endswith("-- .venv/bin/python -m pytest tests/ -v\n")
    assert "continue-on-error" not in command
    complete = next(
        step
        for step in steps
        if step.get("name") == "Report missing passive observation"
    )
    assert complete["if"] == "always()"
    assert "UNKNOWN" in complete["run"]
    upload = next(
        step for step in steps if step.get("name") == "Upload passive CI observation"
    )
    assert upload["if"] == "always()"
    assert upload["continue-on-error"] is True
    assert upload["with"]["if-no-files-found"] == "warn"
    warning = next(
        step
        for step in steps
        if step.get("name") == "Report unavailable diagnostic upload"
    )
    assert warning["if"] == "always() && steps.observation-upload.outcome == 'failure'"
