"""Build real immutable public leaf sources; no synthetic package payloads."""

import json
from contextlib import contextmanager
import tempfile
import subprocess
import sys
from pathlib import Path

from release_core import PackagePolicy, ReviewedSdistLink

OWNERS = json.loads(
    (Path(__file__).parent / "fixtures/release-core/owners.json").read_text()
)
GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


def git(root, *args):
    return subprocess.run(
        ["/usr/bin/git", "-C", str(root), *args],
        env=GIT_ENV,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def policy(record):
    data = {k: v for k, v in record.items() if k not in {"key", "commit"}}
    data["reviewed_build_json"] = json.dumps(data.pop("reviewed_build"), sort_keys=True)
    data["reviewed_backend_json"] = json.dumps(
        data.pop("reviewed_backend"), sort_keys=True
    )
    for name in (
        "source_mappings",
        "required_members",
        "omitted_paths",
        "omitted_prefixes",
        "forbidden_sdist_paths",
    ):
        data[name] = tuple(tuple(x) if isinstance(x, list) else x for x in data[name])
    data["reviewed_sdist_links"] = tuple(
        ReviewedSdistLink(**x) for x in data.get("reviewed_sdist_links", [])
    )
    data["file_mappings"] = tuple(tuple(pair) for pair in data.get("file_mappings", ()))
    return PackagePolicy(**data)


@contextmanager
def build_workspace(label):
    """Owned normal-build roots outside an ambient ignored cache ancestor.

    Hatch discards VCS exclusion rules when the absolute project root matches
    one of them. A user TMPDIR beneath .cache must not mask missing payloads.
    Public-source fixtures contain no credentials and are removed on teardown.
    """
    with tempfile.TemporaryDirectory(prefix="scitex-release-core-" + label + "-", dir="/tmp") as root:
        yield Path(root)


def build_owner(record, root):
    source = root / "source"
    source.mkdir()
    git(source, "init", "--template=")
    git(
        source,
        "remote",
        "add",
        "origin",
        "https://github.com/" + record["repository"] + ".git",
    )
    git(
        source,
        "-c",
        "protocol.version=2",
        "fetch",
        "--depth=1",
        "origin",
        record["commit"],
    )
    git(source, "checkout", "--detach", record["commit"])
    if git(source, "rev-parse", "HEAD") != record["commit"]:
        raise AssertionError("immutable public source checkout differs")
    output = root / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(output),
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    wheels, sdists = list(output.glob("*.whl")), list(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise AssertionError("normal source build must produce one wheel and one sdist")
    import tomllib

    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    return {
        "policy": policy(record),
        "source": source,
        "commit": record["commit"],
        "version": project["version"],
        "wheel": wheels[0].read_bytes(),
        "sdist": sdists[0].read_bytes(),
        "output": output,
    }
