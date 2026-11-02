"""Mutate genuine built artifacts; optionally rebuild a truthful RECORD."""

import base64
import copy
import csv
import hashlib
import io
import tarfile
import zipfile


def wheel_files(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def pack_wheel(files, *, rehash=True, mode_changes=None):
    files = dict(files)
    if rehash:
        record = next(name for name in files if name.endswith(".dist-info/RECORD"))
        text = io.StringIO()
        rows = csv.writer(text)
        for name, body in files.items():
            if name != record:
                digest = (
                    base64.urlsafe_b64encode(hashlib.sha256(body).digest())
                    .decode()
                    .rstrip("=")
                )
                rows.writerow([name, "sha256=" + digest, str(len(body))])
        rows.writerow([record, "", ""])
        files[record] = text.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            item = zipfile.ZipInfo(name)
            if mode_changes and name in mode_changes:
                item.external_attr = mode_changes[name] << 16
            archive.writestr(item, body)
    return output.getvalue()


def tar_entries(raw):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        return [
            (
                copy.copy(item),
                archive.extractfile(item).read() if item.isfile() else None,
            )
            for item in archive.getmembers()
        ]


def pack_tar(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for item, body in entries:
            item = copy.copy(item)
            if body is not None:
                item.size = len(body)
            archive.addfile(item, io.BytesIO(body) if body is not None else None)
    return output.getvalue()
