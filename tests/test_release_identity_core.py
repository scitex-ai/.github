"""Real public Writer/IO/Fig build and archive identity contracts."""

import copy
import hashlib
import posixpath
import tarfile
from pathlib import Path

import pytest
from _release_core_fixtures import OWNERS, build_owner, git

from release_core import (
    sdist_identity,
    source_payload_identity,
    wheel_identity,
)


@pytest.fixture(scope="module")
def built_owners(tmp_path_factory):
    built = {}

    def get(record):
        if record["key"] not in built:
            built[record["key"]] = build_owner(
                record, tmp_path_factory.mktemp("release-core-" + record["key"])
            )
        return built[record["key"]]

    return get


@pytest.fixture(scope="module", params=OWNERS, ids=[row["key"] for row in OWNERS])
def owner(request, built_owners):
    return built_owners(request.param)


@pytest.fixture(scope="module")
def linked_owner(built_owners):
    return built_owners(next(row for row in OWNERS if row.get("reviewed_sdist_links")))


def test_actual_public_source_build_is_accepted(owner):
    # Arrange
    policy = owner["policy"]
    # Act
    result = source_payload_identity(
        owner["wheel"],
        owner["sdist"],
        owner["commit"],
        policy,
        source_root=owner["source"],
    )
    # Assert
    assert (
        result["git_commit"],
        result["wheel_public_members"] > 0,
        result["sdist_public_members"] > 0,
    ) == (owner["commit"], True, True)


import stat
from dataclasses import replace

from _release_core_archives import pack_tar, pack_wheel, tar_entries, wheel_files

from release_core import regular_bytes, verify_artifact_files


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("body", "RECORD hash or size"),
        ("metadata-owner", "metadata and RECORD owners"),
        ("duplicate-name", "artifact distribution"),
        ("duplicate-version", "artifact version"),
        ("missing-payload", "lost required public payload"),
        ("record-duplicate", "RECORD membership"),
        ("record-self", "RECORD self"),
        ("symlink", "unsupported wheel member"),
    ],
)
def test_wheel_rejects_changed_RECORD_payload_and_identity(owner, mutation, reason):
    # Arrange
    files = wheel_files(owner["wheel"])
    metadata = next(name for name in files if name.endswith(".dist-info/METADATA"))
    record = next(name for name in files if name.endswith(".dist-info/RECORD"))
    public = owner["policy"].required_members[0]
    edits = {
        "body": lambda: files.__setitem__(public, files[public] + b"\n# changed\n"),
        "metadata-owner": lambda: files.__setitem__(
            "foreign-1.dist-info/METADATA", files.pop(metadata)
        ),
        "duplicate-name": lambda: files.__setitem__(
            metadata, b"Name: foreign\n" + files[metadata]
        ),
        "duplicate-version": lambda: files.__setitem__(
            metadata, b"Version: 99.0.0\n" + files[metadata]
        ),
        "missing-payload": lambda: files.pop(public),
        "record-duplicate": lambda: files.__setitem__(
            record, files[record] + files[record].splitlines(keepends=True)[0]
        ),
        "record-self": lambda: files.__setitem__(
            record,
            files[record].replace(
                (record + ",,").encode(), (record + ",sha256=bad,1").encode()
            ),
        ),
        "symlink": lambda: None,
    }
    edits[mutation]()
    modes = {public: stat.S_IFLNK | 0o777} if mutation == "symlink" else None
    raw = pack_wheel(
        files,
        rehash=mutation not in {"body", "record-duplicate", "record-self"},
        mode_changes=modes,
    )
    # Act / Assert: the specific guard must fire, not an unrelated rejection.
    with pytest.raises(ValueError, match=reason):
        wheel_identity(raw, owner["version"], owner["policy"])


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("body", "wheel public source bytes differ"),
        ("extra", "whole wheel public source membership differs"),
        ("foreign", "wheel contains undeclared payload"),
        ("generated", "wheel contains unqualified generated metadata"),
        ("requirement", "source runtime requirements differ"),
    ],
)
def test_whole_source_refuses_coordinated_rehashing(owner, mutation, reason):
    # Arrange
    files = wheel_files(owner["wheel"])
    public = owner["policy"].required_members[0]
    metadata = next(name for name in files if name.endswith(".dist-info/METADATA"))
    owner_prefix = metadata.rsplit("/", 1)[0]
    edits = {
        "body": lambda: files.__setitem__(public, files[public] + b"\n# changed\n"),
        "extra": lambda: files.__setitem__(
            owner["policy"].package + "/foreign_payload.py", b"UNDECLARED = True\n"
        ),
        "foreign": lambda: files.__setitem__(
            "another_owner/payload.py", b"UNDECLARED = True\n"
        ),
        "generated": lambda: files.__setitem__(
            owner_prefix + "/foreign.txt", b"UNDECLARED"
        ),
        "requirement": lambda: files.__setitem__(
            metadata,
            files[metadata].replace(
                b"\n\n", b"\nRequires-Dist: foreign-dependency>=99\n\n", 1
            ),
        ),
    }
    edits[mutation]()
    raw = pack_wheel(files)
    # Act / Assert
    with pytest.raises(ValueError, match=reason):
        source_payload_identity(
            raw,
            owner["sdist"],
            owner["commit"],
            owner["policy"],
            source_root=owner["source"],
        )


@pytest.mark.parametrize(
    "kind", [tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE]
)
def test_special_sdist_members_are_always_refused(owner, kind):
    # Arrange
    entries = tar_entries(owner["sdist"])
    root = entries[0][0].name.split("/")[0]
    item = tarfile.TarInfo(root + "/unqualified-special")
    item.type = kind
    item.linkname = root + "/LICENSE"
    entries.append((item, None))
    raw = pack_tar(entries)
    # Act / Assert
    with pytest.raises(ValueError, match="unsupported sdist member"):
        sdist_identity(raw, owner["version"], owner["policy"])


def test_default_policy_rejects_unreviewed_sdist_symlinks(owner):
    # Arrange
    policy = replace(owner["policy"], reviewed_sdist_links=())
    entries = tar_entries(owner["sdist"])
    root = entries[0][0].name.split("/")[0]
    item = tarfile.TarInfo(root + "/unreviewed-link")
    item.type = tarfile.SYMTYPE
    item.linkname = "LICENSE"
    entries.append((item, None))
    # Act / Assert
    with pytest.raises(ValueError, match="unreviewed or changed sdist link"):
        sdist_identity(pack_tar(entries), owner["version"], policy)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("bytes", "sdist public source bytes differ"),
        ("extra", "sdist contains undeclared public payload"),
        ("duplicate", "duplicate or excessive sdist members"),
        ("absolute", "unsafe archive member"),
        ("escape", "unsafe archive member"),
    ],
)
def test_sdist_membership_and_namespace_are_not_waived(owner, mutation, reason):
    # Arrange
    entries = tar_entries(owner["sdist"])
    root = entries[0][0].name.split("/")[0]
    public = (
        root + "/" + owner["policy"].source_for(owner["policy"].required_members[0])
    )
    matching = next(i for i, (item, _) in enumerate(entries) if item.name == public)
    item, body = entries[matching]
    replacements = {
        "bytes": (copy.copy(item), body + b"\n# changed\n"),
        "extra": (
            tarfile.TarInfo(root + "/untracked-foreign.py"),
            b"UNDECLARED = True\n",
        ),
        "duplicate": (copy.copy(item), body),
        "absolute": (tarfile.TarInfo("/absolute"), b"bad"),
        "escape": (tarfile.TarInfo(root + "/../escape"), b"bad"),
    }
    replacement = replacements[mutation]
    # Act
    changed = (
        entries[:matching] + [replacement] + entries[matching + 1 :]
        if mutation == "bytes"
        else entries + [replacement]
    )
    # Assert
    with pytest.raises(ValueError, match=reason):
        source_payload_identity(
            owner["wheel"],
            pack_tar(changed),
            owner["commit"],
            owner["policy"],
            source_root=owner["source"],
        )


def test_file_facade_reads_actual_regular_files_and_owns_the_report(owner):
    # Arrange
    wheel = next(owner["output"].glob("*.whl"))
    sdist = next(owner["output"].glob("*.tar.gz"))
    # Act
    report = verify_artifact_files(
        wheel, sdist, owner["commit"], owner["policy"], source_root=owner["source"]
    )
    # Assert
    assert (
        report["repository"],
        report["distribution"],
        report["wheel_sha256"],
        report["sdist_sha256"],
    ) == (
        owner["policy"].repository,
        owner["policy"].distribution,
        hashlib.sha256(owner["wheel"]).hexdigest(),
        hashlib.sha256(owner["sdist"]).hexdigest(),
    )


def test_artifact_file_symlink_is_not_accepted(owner, tmp_path):
    # Arrange
    link = tmp_path / "alias.whl"
    link.symlink_to(next(owner["output"].glob("*.whl")))
    # Act / Assert
    with pytest.raises(ValueError, match="regular file"):
        regular_bytes(link)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("changed", "unreviewed or changed sdist link"),
        ("absolute", "unreviewed or changed sdist link"),
        ("escape", "unreviewed or changed sdist link"),
        ("missing-target", "sdist link target is missing"),
        ("target-bytes", "sdist link target Git bytes differ"),
        ("target-symlink", "not a single-hop regular member"),
        ("hardlink", "unsupported sdist member"),
        ("unknown", "unreviewed or changed sdist link"),
        ("duplicate", "duplicate or excessive sdist members"),
    ],
)
def test_reviewed_link_port_refuses_every_unqualified_variant(
    linked_owner, mutation, reason
):
    # Arrange: mutate actual source-owned documentation links in a real sdist.
    owner = linked_owner
    entries = tar_entries(owner["sdist"])
    root = entries[0][0].name.split("/")[0]
    link = owner["policy"].reviewed_sdist_links[0]
    link_index = next(
        i for i, (item, _) in enumerate(entries) if item.name == root + "/" + link.path
    )
    target_index = next(
        i
        for i, (item, _) in enumerate(entries)
        if item.name == root + "/" + link.target_path
    )
    item, body = entries[link_index]
    edits = {
        "changed": lambda: setattr(item, "linkname", link.text + "-changed"),
        "absolute": lambda: setattr(item, "linkname", "/outside"),
        "escape": lambda: setattr(item, "linkname", "../../../../outside"),
        "missing-target": lambda: entries.pop(target_index),
        "target-bytes": lambda: entries.__setitem__(
            target_index,
            (entries[target_index][0], entries[target_index][1] + b"\nchanged"),
        ),
        "target-symlink": lambda: setattr(
            entries[target_index][0], "type", tarfile.SYMTYPE
        ),
        "hardlink": lambda: setattr(item, "type", tarfile.LNKTYPE),
        "unknown": lambda: setattr(item, "name", root + "/unreviewed-link"),
        "duplicate": lambda: entries.append((copy.copy(item), body)),
    }
    edits[mutation]()
    # Act / Assert
    with pytest.raises(ValueError, match=reason):
        sdist_identity(pack_tar(entries), owner["version"], owner["policy"])


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("duplicate", "duplicate registered sdist link"),
        ("absolute", "unsafe registered sdist link"),
        ("escape", "escapes its source root"),
        ("text-blob", "text differs from its Git blob"),
        ("chain", "link chain is forbidden"),
    ],
)
def test_link_registry_policy_itself_is_closed(linked_owner, mutation, reason):
    # Arrange
    from release_core.policy import git_blob_identity

    owner = linked_owner
    first, second = owner["policy"].reviewed_sdist_links[:2]
    replacements = {
        "duplicate": lambda: replace(
            owner["policy"], reviewed_sdist_links=(first, first)
        ),
        "absolute": lambda: replace(first, text="/outside"),
        "escape": lambda: replace(first, text="../../../../outside"),
        "text-blob": lambda: replace(
            first,
            text=first.text + "-changed",
            target_path=first.target_path + "-changed",
        ),
        "chain": lambda: replace(
            owner["policy"],
            reviewed_sdist_links=(
                replace(
                    first,
                    text=posixpath.relpath(second.path, str(Path(first.path).parent)),
                    target_path=second.path,
                    target_blob=second.link_blob,
                    link_blob=git_blob_identity(
                        posixpath.relpath(
                            second.path, str(Path(first.path).parent)
                        ).encode()
                    ),
                ),
                second,
            ),
        ),
    }
    # Act / Assert
    with pytest.raises(ValueError, match=reason):
        replacements[mutation]()


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("link-mode", "source link Git mode or object differs"),
        ("target-bytes", "not its registered regular Git blob"),
        ("target-link", "not its registered regular Git blob"),
        ("build-policy", "reviewed package mapping changed"),
        ("backend-policy", "reviewed build backend changed"),
    ],
)
def test_actual_new_git_source_cannot_reuse_an_old_reviewed_policy(
    linked_owner, tmp_path, mutation, reason
):
    # Arrange: this is an independent owned Git worktree, never the author's checkout.
    owner = linked_owner
    source = tmp_path / "candidate"
    git(owner["source"], "worktree", "add", "--detach", str(source), owner["commit"])
    link = owner["policy"].reviewed_sdist_links[0]

    def change_link_mode():
        (source / link.path).unlink()
        (source / link.path).write_text(link.text)

    def change_target_bytes():
        target = source / link.target_path
        target.write_bytes(target.read_bytes() + b"\nchanged")

    def change_target_kind():
        (source / link.target_path).unlink()
        (source / link.target_path).symlink_to("unqualified")

    def change_build():
        project = source / "pyproject.toml"
        project.write_text(
            project.read_text() + "\n[tool.hatch.build.unqualified]\nclaim = true\n"
        )

    def change_backend():
        project = source / "pyproject.toml"
        text = project.read_text()
        assert text.count('build-backend = "hatchling.build"') == 1
        project.write_text(
            text.replace(
                'build-backend = "hatchling.build"',
                'build-backend = "unqualified.backend"',
            )
        )

    edits = {
        "link-mode": change_link_mode,
        "target-bytes": change_target_bytes,
        "target-link": change_target_kind,
        "build-policy": change_build,
        "backend-policy": change_backend,
    }
    edits[mutation]()
    git(source, "add", "-A")
    git(
        source,
        "-c",
        "user.name=Release fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Owned negative source fixture",
    )
    commit = git(source, "rev-parse", "HEAD")
    # Act / Assert: the intended source/policy guard fires before generic byte mismatch.
    with pytest.raises(ValueError, match=reason):
        source_payload_identity(
            owner["wheel"], owner["sdist"], commit, owner["policy"], source_root=source
        )


def test_sdist_root_namespace_belongs_to_the_release(owner):
    # Arrange
    entries = tar_entries(owner["sdist"])
    root = entries[0][0].name.split("/")[0]
    for item, _ in entries:
        item.name = "another-owner/" + item.name.removeprefix(root + "/")
        item.pax_headers = {
            key: value for key, value in item.pax_headers.items() if key != "path"
        }
    raw = pack_tar(entries)
    # Act / Assert
    with pytest.raises(ValueError, match="sdist root identity differs"):
        sdist_identity(raw, owner["version"], owner["policy"])


def test_tree_object_cannot_impersonate_the_source_commit(owner):
    # Arrange: the tree has exactly the same public bytes but is not a commit.
    tree = git(owner["source"], "rev-parse", owner["commit"] + "^{tree}")
    # Act / Assert
    with pytest.raises(ValueError, match="public source identity is not a commit"):
        source_payload_identity(
            owner["wheel"],
            owner["sdist"],
            tree,
            owner["policy"],
            source_root=owner["source"],
        )
