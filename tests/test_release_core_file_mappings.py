"""Verify explicitly mapped files against real immutable Scholar artifacts."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from _release_core_archives import pack_tar, pack_wheel, tar_entries, wheel_files
from _release_core_fixtures import build_owner, build_workspace, git, policy

from release_core import source_payload_identity

RECORD = json.loads(
    (
        Path(__file__).parent / "fixtures/release-core/scholar-cli-dictionary.json"
    ).read_text()
)
SOURCE = ".scitex/dev/cli-audit-dict.yaml"
TARGET = "scitex_scholar/_cli_audit_dict.yaml"


@pytest.fixture(scope="module")
def owner():
    with build_workspace("scholar-cli-dictionary") as root:
        yield build_owner(RECORD, root)


def test_real_source_file_mapping_passes_whole_artifact_identity(owner):
    # Arrange / Act
    result = source_payload_identity(
        owner["wheel"],
        owner["sdist"],
        owner["commit"],
        owner["policy"],
        owner["source"],
    )
    # Assert
    assert (result["git_commit"], result["wheel_public_members"] > 1000) == (
        RECORD["commit"],
        True,
    )


def test_rehashed_mapped_file_cannot_replace_git_source_bytes(owner):
    # Arrange
    files = wheel_files(owner["wheel"])
    files[TARGET] += b"\n# coordinated artifact modification\n"
    wheel = pack_wheel(files)
    # Act / Assert
    with pytest.raises(ValueError, match="wheel public source bytes differ"):
        source_payload_identity(
            wheel, owner["sdist"], owner["commit"], owner["policy"], owner["source"]
        )


def test_mapped_source_cannot_be_a_symlink_in_a_new_git_commit(owner, tmp_path):
    # Arrange
    source = tmp_path / "source"
    git(tmp_path, "clone", "--no-hardlinks", str(owner["source"]), str(source))
    dictionary = source / SOURCE
    dictionary.unlink()
    dictionary.symlink_to("../../LICENSE")
    git(source, "add", SOURCE)
    git(
        source,
        "-c",
        "user.name=Owned refusal fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "Replace mapped source with an owned symlink",
    )
    commit = git(source, "rev-parse", "HEAD")
    # Act / Assert
    with pytest.raises(
        ValueError, match="file source is missing or not a regular Git blob"
    ):
        source_payload_identity(
            owner["wheel"], owner["sdist"], commit, owner["policy"], source
        )


def test_mapped_source_must_survive_in_source_archive(owner):
    # Arrange
    entries = [
        (member, body)
        for member, body in tar_entries(owner["sdist"])
        if not member.name.endswith("/" + SOURCE)
    ]
    sdist = pack_tar(entries)
    # Act / Assert
    with pytest.raises(ValueError, match="sdist lost required public payload"):
        source_payload_identity(
            owner["wheel"], sdist, owner["commit"], owner["policy"], owner["source"]
        )


def test_new_artifact_cannot_use_a_policy_without_the_exact_file_mapping(owner):
    # Arrange
    unqualified = replace(owner["policy"], file_mappings=())
    # Act / Assert
    with pytest.raises(ValueError, match="sdist lost required public payload"):
        source_payload_identity(
            owner["wheel"],
            owner["sdist"],
            owner["commit"],
            unqualified,
            owner["source"],
        )


@pytest.mark.parametrize(
    "mappings,reason",
    [
        (
            ((SOURCE + ".missing", TARGET),),
            "file source is missing or not a regular Git blob",
        ),
        (
            ((SOURCE, "scitex_scholar/_cli"),),
            "file destination overlaps a package directory",
        ),
    ],
)
def test_mapping_must_match_real_regular_sources_and_noncolliding_targets(
    owner, mappings, reason
):
    # Arrange
    changed = replace(
        owner["policy"],
        file_mappings=mappings,
        required_members=("scitex_scholar/__init__.py",),
    )
    # Act / Assert
    with pytest.raises(ValueError, match=reason):
        source_payload_identity(
            owner["wheel"], owner["sdist"], owner["commit"], changed, owner["source"]
        )


@pytest.mark.parametrize(
    "mappings,reason",
    [
        ([(SOURCE, TARGET)], "immutable tuples"),
        (([SOURCE, TARGET],), "immutable tuples"),
        ((("../escape", TARGET),), "unsafe registered package path"),
        (
            ((SOURCE, "another_owner/dictionary.yaml"),),
            "escapes registered import package",
        ),
        (
            (("src/scitex_scholar/existing", TARGET),),
            "overlaps registered directory source",
        ),
        (
            ((SOURCE, TARGET), (SOURCE, TARGET + "2")),
            "duplicate registered file source",
        ),
        (
            ((SOURCE, TARGET), (SOURCE + "2", TARGET)),
            "duplicate registered file destination",
        ),
    ],
)
def test_unqualified_file_mapping_policy_is_refused(mappings, reason):
    # Arrange
    original = policy(RECORD)
    # Act / Assert
    with pytest.raises((ValueError, TypeError), match=reason):
        replace(original, file_mappings=mappings)
