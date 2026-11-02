"""Strict public wheel/RECORD/sdist ownership checks; no network or publishing."""

import base64
import csv
import hashlib
import io
import os
import stat
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import PurePosixPath

from .policy import git_blob_identity


def regular_bytes(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("artifact must be a regular file")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 268435456:
            raise ValueError("artifact type or size is invalid")
        raw = stream.read()
        after = os.fstat(stream.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or path.lstat().st_ino != before.st_ino:
        raise ValueError("artifact changed while reading")
    return raw


def safe_member(name):
    path = PurePosixPath(name)
    if (
        "\\" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
    ):
        raise ValueError("unsafe archive member")


def metadata_identity(raw, version, policy):
    message = BytesParser().parsebytes(raw)
    names = message.get_all("Name")
    if names not in ([policy.distribution], [policy.distribution.replace("-", "_")]):
        raise ValueError("artifact distribution differs")
    if message.get_all("Version") != [version]:
        raise ValueError("artifact version differs")


def wheel_identity(raw, version, policy):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 20000:
            raise ValueError("duplicate or excessive wheel members")
        for item in archive.infolist():
            safe_member(item.filename)
            mode = stat.S_IFMT(item.external_attr >> 16)
            if mode not in {0, stat.S_IFREG, stat.S_IFDIR} or item.file_size > 67108864:
                raise ValueError("unsupported wheel member")
        if sum(item.file_size for item in archive.infolist()) > 1073741824:
            raise ValueError("wheel expanded size exceeded")
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        records = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(metadata) != 1 or len(records) != 1:
            raise ValueError("wheel metadata identity is ambiguous")
        metadata_identity(archive.read(metadata[0]), version, policy)
        record = records[0]
        owner = policy.owner(version)
        if metadata[0] != owner + "/METADATA" or record != owner + "/RECORD":
            raise ValueError("wheel metadata and RECORD owners differ")
        seen = set()
        for name, digest, size in csv.reader(
            io.StringIO(archive.read(record).decode())
        ):
            if name in seen or name not in names:
                raise ValueError("wheel RECORD membership differs")
            seen.add(name)
            if name == record:
                if digest or size:
                    raise ValueError("wheel RECORD self entry differs")
                continue
            body = archive.read(name)
            expected = "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(body).digest()
            ).decode().rstrip("=")
            if digest != expected or size != str(len(body)):
                raise ValueError("wheel RECORD hash or size differs")
        if seen != set(names):
            raise ValueError("wheel has unrecorded members")
        if not set(policy.required_members).issubset(names):
            raise ValueError("wheel lost required public payload")
        return {"members": len(names), "record_members": len(seen)}


def _reviewed_link(archive, item, root, policy):
    if not item.name.startswith(root + "/"):
        raise ValueError("sdist link cannot replace archive root")
    relative = item.name.removeprefix(root + "/")
    link = policy.link_for(relative)
    if link is None or item.linkname != link.text or item.size != 0:
        raise ValueError("unreviewed or changed sdist link")
    if git_blob_identity(item.linkname.encode()) != link.link_blob:
        raise ValueError("sdist link Git identity differs")
    target_name = root + "/" + link.target_path
    try:
        target = archive.getmember(target_name)
    except KeyError:
        raise ValueError("sdist link target is missing") from None
    if not target.isfile():
        raise ValueError("sdist link target is not a single-hop regular member")
    if git_blob_identity(archive.extractfile(target).read()) != link.target_blob:
        raise ValueError("sdist link target Git bytes differ")


def sdist_identity(raw, version, policy):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        entries = archive.getmembers()
        names = [item.name for item in entries]
        if len(names) != len(set(names)) or len(names) > 20000:
            raise ValueError("duplicate or excessive sdist members")
        for item in entries:
            safe_member(item.name)
        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise ValueError("sdist has multiple roots")
        root = next(iter(roots))
        if root != policy.owner(version).removesuffix(".dist-info"):
            raise ValueError("sdist root identity differs")
        for item in entries:
            if not (item.isfile() or item.isdir() or item.issym()):
                raise ValueError("unsupported sdist member")
            if item.size > 67108864:
                raise ValueError("unsupported sdist member")
        if sum(item.size for item in entries) > 1073741824:
            raise ValueError("sdist expanded size exceeded")
        for item in entries:
            if item.issym():
                _reviewed_link(archive, item, root, policy)
        required = {
            root + "/" + policy.source_for(path) for path in policy.required_members
        }
        required.update({root + "/PKG-INFO", root + "/pyproject.toml"})
        if not required.issubset(names) or any(
            not archive.getmember(name).isfile() for name in required
        ):
            raise ValueError("sdist lost required public payload")
        metadata_identity(
            archive.extractfile(root + "/PKG-INFO").read(), version, policy
        )
        project = tomllib.loads(
            archive.extractfile(root + "/pyproject.toml").read().decode()
        )["project"]
        if (
            project["version"] != version
            or project["name"].replace("_", "-").lower() != policy.distribution
        ):
            raise ValueError("sdist project identity differs")
        return {"members": len(entries)}
