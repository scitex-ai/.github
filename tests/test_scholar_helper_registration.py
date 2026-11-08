"""Bind the complete Scholar helper table to real immutable public Git bytes."""

import hashlib
import subprocess

import pytest
from _release_core_fixtures import GIT_ENV, build_workspace, git
from test_leaf_release_contract import dispatch

SOURCE_COMMIT = "d303ae9a6e1a007d2f67350f83ded4268b5587ba"


@pytest.fixture(scope="module")
def source():
    with build_workspace("registered-scholar-helpers") as root:
        git(root, "init", "--template=")
        git(
            root,
            "remote",
            "add",
            "origin",
            "https://github.com/scitex-ai/scitex-scholar.git",
        )
        git(root, "fetch", "--depth=1", "origin", SOURCE_COMMIT)
        git(root, "checkout", "--detach", SOURCE_COMMIT)
        yield root


def test_scholar_helper_registration_matches_every_actual_public_source_file(source):
    # Arrange
    plan = dispatch(repository="scitex-ai/scitex-scholar", tag="v1.29.2")["plan"]
    # Act
    actual = {
        name: hashlib.sha256(
            subprocess.check_output(
                ["git", "-C", str(source), "show", SOURCE_COMMIT + ":" + name],
                env=GIT_ENV,
            )
        ).hexdigest()
        for name in plan["leafSources"]
    }
    # Assert
    assert actual == plan["leafSources"]
