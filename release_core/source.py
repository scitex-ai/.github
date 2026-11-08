"""Bind every public payload byte to the actual immutable Git source objects."""

import hashlib
import io
import json
import os
import re
import signal
import subprocess
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from ._metadata import metadata_source_identity
from .artifacts import safe_member, sdist_identity, wheel_identity

SHA = re.compile(r"[0-9a-f]{40}")


def git_read(argv, source_root, stdin=None):
    process = subprocess.Popen(
        ["/usr/bin/git", "-C", str(source_root), *argv],
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, _ = process.communicate(stdin, timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise ValueError("public source read timed out") from None
    if process.returncode:
        raise ValueError("public source Git read failed")
    return stdout


def source_payload_identity(
    wheel_raw, sdist_raw, commit, policy, source_root=Path(".")
):
    """Compare public payload membership and bytes with this exact Git commit."""
    if not SHA.fullmatch(commit):
        raise ValueError("public source commit is malformed")
    if git_read(["cat-file", "-t", commit], source_root) != b"commit\n":
        raise ValueError("public source identity is not a commit")
    rows = git_read(["ls-tree", "-r", "-z", "--full-tree", commit], source_root).split(
        b"\0"
    )
    entries = {}
    for row in filter(None, rows):
        metadata, path_raw = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = path_raw.decode()
        safe_member(path)
        if path in entries or kind != "blob" or not SHA.fullmatch(oid):
            raise ValueError("public source tree is ambiguous")
        entries[path] = (mode, oid)
    if len(entries) > 20000:
        raise ValueError("public source tree exceeds bounds")
    ids = sorted({oid for _, oid in entries.values()})
    frames = (
        git_read(
            ["cat-file", "--batch-check"], source_root, ("\n".join(ids) + "\n").encode()
        )
        .decode()
        .splitlines()
    )
    if len(frames) != len(ids):
        raise ValueError("public source size inventory differs")
    sizes = []
    for oid, frame in zip(ids, frames, strict=True):
        values = frame.split()
        if (
            len(values) != 3
            or values[:2] != [oid, "blob"]
            or not values[2].isdigit()
            or int(values[2]) > 67108864
        ):
            raise ValueError("public source object size differs")
        sizes.append(int(values[2]))
    if sum(sizes) > 268435456:
        raise ValueError("public source byte inventory exceeds bounds")
    stream = io.BytesIO(
        git_read(["cat-file", "--batch"], source_root, ("\n".join(ids) + "\n").encode())
    )
    bodies = {}
    for expected in ids:
        header = stream.readline().decode().strip().split()
        if (
            len(header) != 3
            or header[:2] != [expected, "blob"]
            or not header[2].isdigit()
            or int(header[2]) > 67108864
        ):
            raise ValueError("public source object frame differs")
        body = stream.read(int(header[2]))
        if (
            stream.read(1) != b"\n"
            or hashlib.sha1(b"blob " + header[2].encode() + b"\0" + body).hexdigest()
            != expected
        ):
            raise ValueError("public source object bytes differ")
        bodies[expected] = body
    if stream.read(1):
        raise ValueError("public source object stream has extra data")
    if entries.get("pyproject.toml", ("", ""))[0] not in {"100644", "100755"}:
        raise ValueError("public source metadata is missing")
    project = tomllib.loads(bodies[entries["pyproject.toml"][1]].decode())
    policy.verify_build(project)
    version = project["project"]["version"]
    wheel_identity(wheel_raw, version, policy)
    sdist_identity(sdist_raw, version, policy)
    link_proofs = {}
    for link in policy.reviewed_sdist_links:
        if entries.get(link.path) != ("120000", link.link_blob):
            raise ValueError("reviewed source link Git mode or object differs")
        if bodies[link.link_blob] != link.text.encode():
            raise ValueError("reviewed source link text differs")
        target = entries.get(link.target_path)
        if (
            not target
            or target[0] not in {"100644", "100755"}
            or target[1] != link.target_blob
        ):
            raise ValueError(
                "reviewed source link target is not its registered regular Git blob"
            )
        link_proofs[link.path] = {
            "link_blob": link.link_blob,
            "target_path": link.target_path,
            "target_blob": link.target_blob,
        }
    expected = {}
    source_paths = set()
    for source, _ in policy.file_mappings:
        if entries.get(source, ("", ""))[0] not in {"100644", "100755"}:
            raise ValueError(
                "registered file source is missing or not a regular Git blob"
            )
    for path, (mode, oid) in entries.items():
        if policy.omitted(path):
            continue
        destination = policy.destination(path)
        if destination is None:
            continue
        if mode not in {"100644", "100755"} or destination in expected:
            raise ValueError("unsupported or colliding public package member")
        expected[destination] = bodies[oid]
        source_paths.add(path)
    if not expected:
        raise ValueError("public source package membership is empty")
    for _, target in policy.file_mappings:
        if any(member.startswith(target + "/") for member in expected):
            raise ValueError("registered file destination overlaps a package directory")
    with zipfile.ZipFile(io.BytesIO(wheel_raw)) as wheel:
        actual = {
            name
            for name in wheel.namelist()
            if name.startswith(policy.package + "/") and not name.endswith("/")
        }
        if actual != set(expected):
            raise ValueError("whole wheel public source membership differs")
        for name, body in expected.items():
            if wheel.read(name) != body:
                raise ValueError("wheel public source bytes differ")
        owners = {
            name.split("/", 1)[0] for name in wheel.namelist() if ".dist-info/" in name
        }
        if len(owners) != 1 or any(
            not name.startswith(policy.package + "/")
            and name.split("/", 1)[0] not in owners
            for name in wheel.namelist()
        ):
            raise ValueError("wheel contains undeclared payload")
        owner = policy.owner(project["project"]["version"])
        if owners != {owner}:
            raise ValueError("wheel generated metadata owner differs")
        allowed = {
            owner + "/" + name
            for name in (
                "METADATA",
                "WHEEL",
                "RECORD",
                "entry_points.txt",
                "licenses/LICENSE",
            )
        }
        if any(
            name.startswith(owner + "/") and name not in allowed
            for name in wheel.namelist()
        ):
            raise ValueError("wheel contains unqualified generated metadata")
        wheel_metadata = wheel.read(owner + "/METADATA")
        wheel_headers = BytesParser().parsebytes(wheel.read(owner + "/WHEEL"))
        if (
            wheel_headers.get_all("Wheel-Version") != ["1.0"]
            or wheel_headers.get_all("Root-Is-Purelib") != ["true"]
            or wheel_headers.get_all("Tag") != ["py3-none-any"]
        ):
            raise ValueError("wheel format differs from reviewed pure package")
        wheel_entry_points = (
            wheel.read(owner + "/entry_points.txt")
            if owner + "/entry_points.txt" in wheel.namelist()
            else None
        )
        license_headers = (
            BytesParser().parsebytes(wheel_metadata).get_all("License-File", [])
        )
        if (
            license_headers != ["LICENSE"]
            or owner + "/licenses/LICENSE" not in wheel.namelist()
        ):
            raise ValueError("source license payload differs")
        if wheel.read(owner + "/licenses/LICENSE") != bodies[entries["LICENSE"][1]]:
            raise ValueError("wheel license source bytes differ")
    with tarfile.open(fileobj=io.BytesIO(sdist_raw), mode="r:gz") as sdist:
        members = sdist.getmembers()
        root = PurePosixPath(members[0].name).parts[0]
        actual = set()
        sdist_metadata = sdist.extractfile(root + "/PKG-INFO").read()
        generated_metadata_identity = metadata_source_identity(
            wheel_metadata, sdist_metadata, wheel_entry_points, project["project"]
        )
        for item in members:
            if item.isdir():
                continue
            relative = item.name.removeprefix(root + "/")
            if relative == "PKG-INFO":
                continue
            if item.issym():
                if relative not in link_proofs:
                    raise ValueError("unreviewed source symlink")
                actual.add(relative)
                continue
            if relative in policy.forbidden_sdist_paths:
                raise ValueError("sdist contains declared excluded public path")
            if (
                relative not in entries
                or entries[relative][0] not in {"100644", "100755"}
                or not item.isfile()
            ):
                raise ValueError("sdist contains undeclared public payload")
            if sdist.extractfile(item).read() != bodies[entries[relative][1]]:
                raise ValueError("sdist public source bytes differ")
            actual.add(relative)
        if not (
            source_paths
            | set(link_proofs)
            | {"README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml"}
        ).issubset(actual):
            raise ValueError("sdist public source membership is incomplete")
    manifest = [
        {"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        for name, body in sorted(expected.items())
    ]
    return {
        "git_commit": commit,
        "reviewed_sdist_links": link_proofs,
        "generated_metadata": generated_metadata_identity,
        "wheel_public_members": len(manifest),
        "source_membership_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "sdist_public_members": len(actual),
    }
