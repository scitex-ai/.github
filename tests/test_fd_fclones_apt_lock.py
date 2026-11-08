"""Run the actual bootstrap wrapper against APT and owned POSIX locks."""

import fcntl
import os
from pathlib import Path
import pwd
import shlex
import shutil
import signal
import subprocess
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]
NOTICE = "::notice::APT lock busy;"


def _function():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/fd-fclones-integration.yml").read_text()
    )
    step = next(s for s in workflow["jobs"]["native"]["steps"]
                if s.get("name") == "Install fd + fclones")
    script = step["run"]
    return script[script.index("apt_retry_lock() {"):
                  script.index("\napt_retry_lock sudo apt-get update")]


def _fixture(tmp_path):
    # No host sources, hooks, caches, package database, sudo or network access.
    base = tmp_path / "owned apt state"
    for directory in ("etc/parts", "etc/sources", "lists/partial", "cache", "log", "runtime"):
        (base / directory).mkdir(parents=True)
    (base / "etc/sources.list").touch()
    (base / "status").touch()
    user = pwd.getpwuid(os.getuid()).pw_name
    config = base / "apt.conf"
    config.write_text(f'''Dir::Etc "{base}/etc";
Dir::Etc::main "";
Dir::Etc::parts "{base}/etc/parts";
Dir::Etc::sourcelist "{base}/etc/sources.list";
Dir::Etc::sourceparts "{base}/etc/sources";
Dir::State::lists "{base}/lists";
Dir::State::status "{base}/status";
Dir::Cache "{base}/cache";
Dir::Log "{base}/log";
APT::Sandbox::User "{user}";
''')
    executable = shutil.which("apt-get")
    if executable is None:
        raise RuntimeError("Real APT is required on the Ubuntu workflow test runner")
    env = {"PATH": os.environ["PATH"], "LANG": "C", "LC_ALL": "C",
           "RUNNER_TEMP": str(base / "runtime"), "APT_CONFIG": str(config)}
    return base, env, executable


def _script(command):
    return "set -euo pipefail\n" + _function() + "\napt_retry_lock " + shlex.join(command)


def _locked(tmp_path, release):
    base, env, apt = _fixture(tmp_path)
    lock_path = base / "lists/lock"
    output = base / "command.log"
    with lock_path.open("w") as lock, output.open("w") as log:
        fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inode = lock_path.stat().st_ino
        process = subprocess.Popen(
            ["bash", "-c", _script([apt, "update", "-y"])], env=env,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            if release:
                deadline = time.monotonic() + 15
                while NOTICE not in output.read_text():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("No actual APT busy-lock observation: " + output.read_text())
                    time.sleep(0.02)
                fcntl.lockf(lock, fcntl.LOCK_UN)
            code = process.wait(timeout=150)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        same_lock = lock_path.stat().st_ino == inode
    return code, output.read_text(), same_lock, list((base / "runtime").iterdir())


def test_real_apt_lock_release_allows_the_original_command_to_complete(tmp_path):
    code, output, same_lock, leftovers = _locked(tmp_path, release=True)
    assert (code, NOTICE in output, same_lock, leftovers) == (0, True, True, [])


def test_persistent_real_apt_lock_preserves_failure_and_its_owner(tmp_path):
    code, output, same_lock, leftovers = _locked(tmp_path, release=False)
    assert (code, NOTICE in output, same_lock, leftovers) == (100, True, True, [])


def test_other_real_apt_errors_are_not_retried_or_reported_as_success(tmp_path):
    base, env, apt = _fixture(tmp_path)
    result = subprocess.run(
        ["bash", "-c", _script([apt, "--simulate", "install",
                                "scitex-ci-this-package-does-not-exist"])],
        env=env, capture_output=True, text=True, timeout=15,
    )
    output = result.stdout + result.stderr
    assert (result.returncode, output.count("Unable to locate package"),
            NOTICE in output, list((base / "runtime").iterdir())) == (100, 1, False, [])


def test_uncontended_real_apt_command_needs_no_retry(tmp_path):
    base, env, apt = _fixture(tmp_path)
    result = subprocess.run(["bash", "-c", _script([apt, "update", "-y"])],
                            env=env, capture_output=True, text=True, timeout=15)
    assert (result.returncode, NOTICE in result.stdout + result.stderr,
            list((base / "runtime").iterdir())) == (0, False, [])


def test_concurrent_downloads_have_owned_paths_and_cleanup(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/fd-fclones-integration.yml").read_text()
    )
    script = next(s["run"] for s in workflow["jobs"]["native"]["steps"]
                  if s.get("name") == "Install fd + fclones")
    lines = script.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("FCLONES_DEB="))
    fragment = "\n".join(lines[start:start + 2])
    runtime = tmp_path / "owned downloads"
    runtime.mkdir()
    (runtime / "keep").write_text("unrelated owned fixture")
    command = "set -euo pipefail\n" + fragment + '\nprintf "%s\\n" "$FCLONES_DEB"\n'
    command += 'test -f "$FCLONES_DEB"\nsleep 0.1\n'

    def execute(_):
        return subprocess.run(["bash", "-c", command], env={"PATH": os.environ["PATH"],
                              "RUNNER_TEMP": str(runtime)}, capture_output=True,
                              text=True, timeout=5)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, range(2)))
    paths = [Path(r.stdout.strip()) for r in results]
    assert ([r.returncode for r in results], len(set(paths)),
            all(p.parent == runtime for p in paths),
            sorted(p.name for p in runtime.iterdir())) == ([0, 0], 2, True, ["keep"])
