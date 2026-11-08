"""Explicit policy supplied by a pinned, reviewed release registry, never user input."""

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from ._metadata import normalized_name


def _path(value, *, directory=False):
    raw = value.rstrip("/") if directory else value
    parts = raw.split("/")
    if (
        not raw
        or "\\" in raw
        or PurePosixPath(raw).is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("unsafe registered package path")
    if directory and not value.endswith("/"):
        raise ValueError("registered directory needs trailing slash")


@dataclass(frozen=True)
class ReviewedSdistLink:
    """One reviewed Git symlink and its single-hop, regular Git target."""

    path: str
    text: str
    target_path: str
    link_blob: str
    target_blob: str

    def __post_init__(self):
        if not all(
            isinstance(value, str)
            for value in (
                self.path,
                self.text,
                self.target_path,
                self.link_blob,
                self.target_blob,
            )
        ):
            raise TypeError("registered link fields must be immutable strings")
        _path(self.path)
        _path(self.target_path)
        if (
            not self.text
            or "\\" in self.text
            or "\x00" in self.text
            or PurePosixPath(self.text).is_absolute()
        ):
            raise ValueError("unsafe registered sdist link")
        joined = posixpath.normpath(str(PurePosixPath(self.path).parent / self.text))
        if joined != self.target_path or joined.startswith("../"):
            raise ValueError("registered sdist link escapes its source root")
        if not all(
            re.fullmatch(r"[a-f0-9]{40}", x) for x in (self.link_blob, self.target_blob)
        ):
            raise ValueError("unqualified registered link object identity")
        if git_blob_identity(self.text.encode()) != self.link_blob:
            raise ValueError("registered link text differs from its Git blob")


def git_blob_identity(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


@dataclass(frozen=True)
class PackagePolicy:
    """Registry-owned exact identity, source mapping and reviewed Hatch selection.

    No policy is inferred from a repository prefix, package name or artifact.
    `reviewed_build_json` is the complete reviewed tool.hatch.build object.
    Explicit omitted files/directories must correspond to that reviewed mapping;
    this core deliberately does not guess Hatch/gitignore pattern semantics.
    """

    repository: str
    distribution: str
    package: str
    source_mappings: tuple[tuple[str, str], ...]
    reviewed_build_json: str
    required_members: tuple[str, ...]
    reviewed_backend_json: str
    omitted_paths: tuple[str, ...] = ()
    omitted_prefixes: tuple[str, ...] = ()
    forbidden_sdist_paths: tuple[str, ...] = ()
    reviewed_sdist_links: tuple[ReviewedSdistLink, ...] = ()
    file_mappings: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if not all(
            isinstance(value, str)
            for value in (
                self.repository,
                self.distribution,
                self.package,
                self.reviewed_build_json,
                self.reviewed_backend_json,
            )
        ):
            raise TypeError(
                "registered identity and configuration must be immutable strings"
            )
        if not isinstance(self.source_mappings, tuple) or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(isinstance(value, str) for value in pair)
            for pair in self.source_mappings
        ):
            raise TypeError("registered source mappings must be immutable tuples")
        for values in (
            self.required_members,
            self.omitted_paths,
            self.omitted_prefixes,
            self.forbidden_sdist_paths,
        ):
            if not isinstance(values, tuple) or not all(
                isinstance(value, str) for value in values
            ):
                raise TypeError("registered path selections must be immutable tuples")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository) or any(
            part in {".", ".."} for part in self.repository.split("/")
        ):
            raise ValueError("invalid registered repository identity")
        if normalized_name(self.distribution) != self.distribution:
            raise ValueError("distribution must be canonical")
        if not re.fullmatch(r"[A-Za-z_]\w*", self.package):
            raise ValueError("invalid registered import package")
        if not self.source_mappings or not self.required_members:
            raise ValueError("empty registered public package selection")
        for source, target in self.source_mappings:
            _path(source, directory=True)
            _path(target, directory=True)
            if not target.startswith(self.package + "/"):
                raise ValueError("mapping escapes registered import package")
        if not isinstance(self.file_mappings, tuple) or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(isinstance(value, str) for value in pair)
            for pair in self.file_mappings
        ):
            raise TypeError("registered file mappings must be immutable tuples")
        for source, target in self.file_mappings:
            _path(source)
            _path(target)
            if not target.startswith(self.package + "/"):
                raise ValueError("file mapping escapes registered import package")
            if any(source.startswith(prefix) for prefix, _ in self.source_mappings):
                raise ValueError("file mapping overlaps registered directory source")
        if len({source for source, _ in self.file_mappings}) != len(self.file_mappings):
            raise ValueError("duplicate registered file source")
        if len({target for _, target in self.file_mappings}) != len(self.file_mappings):
            raise ValueError("duplicate registered file destination")
        targets = [target for _, target in self.file_mappings]
        if any(a != b and a.startswith(b + "/") for a in targets for b in targets):
            raise ValueError("overlapping registered file destinations")
        sources = [source for source, _ in self.source_mappings]
        if any(a != b and a.startswith(b) for a in sources for b in sources) or len(
            set(sources)
        ) != len(sources):
            raise ValueError("ambiguous registered source mapping")
        for path in self.required_members:
            _path(path)
            if not path.startswith(self.package + "/"):
                raise ValueError("required member has another owner")
        for path in (*self.omitted_paths, *self.forbidden_sdist_paths):
            _path(path)
        for path in self.omitted_prefixes:
            _path(path, directory=True)
        if any(
            not any(path.startswith(source) for source in sources)
            for path in (
                *self.omitted_paths,
                *self.omitted_prefixes,
                *self.forbidden_sdist_paths,
            )
        ):
            raise ValueError("omission is outside the reviewed package sources")
        if (
            json.loads(self.reviewed_backend_json).get("build-backend")
            != "hatchling.build"
        ):
            raise ValueError("unqualified build backend")
        if not isinstance(json.loads(self.reviewed_build_json), dict):
            raise TypeError("reviewed Hatch policy must be an object")
        if not isinstance(self.reviewed_sdist_links, tuple) or any(
            not isinstance(link, ReviewedSdistLink)
            for link in self.reviewed_sdist_links
        ):
            raise ValueError("reviewed links must be immutable explicit link policies")
        links = [link.path for link in self.reviewed_sdist_links]
        if len(links) != len(set(links)):
            raise ValueError("duplicate registered sdist link")
        if any(link.target_path in links for link in self.reviewed_sdist_links):
            raise ValueError("registered sdist link chain is forbidden")

    def link_for(self, path):
        return next(
            (link for link in self.reviewed_sdist_links if link.path == path), None
        )

    def owner(self, version):
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise ValueError("unsupported release version")
        return self.distribution.replace("-", "_") + "-" + version + ".dist-info"

    def omitted(self, path):
        return path in self.omitted_paths or any(
            path.startswith(prefix) for prefix in self.omitted_prefixes
        )

    def destination(self, path):
        for source, target in self.file_mappings:
            if path == source:
                return target
        for source, target in self.source_mappings:
            if path.startswith(source):
                return target + path.removeprefix(source)
        return None

    def source_for(self, member):
        for source, target in self.file_mappings:
            if member == target:
                return source
        candidates = [
            (len(target), source + member.removeprefix(target))
            for source, target in self.source_mappings
            if member.startswith(target)
        ]
        if not candidates:
            raise ValueError("required member lacks registered source mapping")
        return max(candidates)[1]

    def verify_build(self, project):
        if project["build-system"] != json.loads(self.reviewed_backend_json):
            raise ValueError("reviewed build backend changed")
        if project["tool"]["hatch"]["build"] != json.loads(self.reviewed_build_json):
            raise ValueError("reviewed package mapping changed")
