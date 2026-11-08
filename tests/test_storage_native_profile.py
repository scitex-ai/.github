"""Real failed installs must stay job-local and preserve their failure."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _install(tmp_path, runtime, name):
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/fd-fclones-integration.yml").read_text()
    )
    script = next(s["run"] for s in workflow["jobs"]["native"]["steps"]
                  if s.get("name") == "Install scitex-storage[dev]")
    project = tmp_path / name
    project.mkdir()
    github_path = project / "github-path"
    github_path.touch()
    # The empty owned project is invalid. Real pip must fail without consulting
    # an index, and the actual shell script must not publish its failed profile.
    env = dict(os.environ, RUNNER_TEMP=str(runtime), GITHUB_PATH=str(github_path),
               PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    result = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-c", script],
                            cwd=project, env=env, capture_output=True, text=True,
                            timeout=60)
    return result, github_path.read_text()


def _inspect(profile):
    result = subprocess.run(
        [str(profile / "bin/python"), "-c",
         "import json,sys; print(json.dumps([sys.prefix,sys.base_prefix]))"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    return json.loads(result.stdout)


def test_failed_real_install_does_not_publish_or_mutate_shared_python(tmp_path):
    runtime = tmp_path / "owned runner temp"
    runtime.mkdir()
    keep = runtime / "keep"
    keep.write_text("unrelated owned fixture")
    result, published = _install(tmp_path, runtime, "empty project")
    profiles = list(runtime.glob("storage-python.*"))
    assert (result.returncode != 0, published, len(profiles), keep.read_text()) == (
        True, "", 1, "unrelated owned fixture"
    )
    prefix, base = _inspect(profiles[0])
    assert Path(prefix) == profiles[0] and prefix != base
    assert "include-system-site-packages = false" in (profiles[0] / "pyvenv.cfg").read_text()


def test_concurrent_failed_installs_use_separate_real_virtual_environments(tmp_path):
    runtime = tmp_path / "shared owned runner temp"
    runtime.mkdir()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_install, tmp_path, runtime, str(i)) for i in range(2)]
        results = [future.result() for future in futures]
    profiles = list(runtime.glob("storage-python.*"))
    assert len(profiles) == 2
    assert all(result.returncode != 0 and published == "" for result, published in results)
    assert {Path(_inspect(profile)[0]) for profile in profiles} == set(profiles)
