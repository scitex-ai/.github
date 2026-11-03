"""Compare real qualified leaf verifiers and the central port, without mocks."""

import importlib.util
import sys

import pytest
from _release_core_archives import pack_wheel, wheel_files
from _release_core_fixtures import OWNERS, build_owner, build_workspace

from release_core import source_payload_identity


@pytest.fixture(
    scope="module",
    params=[row for row in OWNERS if row["key"] in {"writer", "io"}],
    ids=lambda row: row["key"],
)
def reference_owner(request):
    with build_workspace("reference-" + request.param["key"]) as root:
        owner = build_owner(request.param, root)
        path = owner["source"] / ".github/ci/release-identity.py"
        spec = importlib.util.spec_from_file_location(
            "qualified_reference_" + request.param["key"], path
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        owner["reference"] = module
        yield owner

def test_actual_legacy_verifier_and_shared_port_accept_the_same_whole_source(
    reference_owner,
):
    # Arrange
    owner = reference_owner
    # Act
    old = owner["reference"].source_payload_identity(
        owner["wheel"], owner["sdist"], owner["commit"], source_root=owner["source"]
    )
    new = source_payload_identity(
        owner["wheel"],
        owner["sdist"],
        owner["commit"],
        owner["policy"],
        source_root=owner["source"],
    )
    # Assert
    assert (
        new["git_commit"],
        new["wheel_public_members"],
        new["source_membership_sha256"],
    ) == (
        old["git_commit"],
        old["wheel_public_members"],
        old["source_membership_sha256"],
    )


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("Requires-Python", ">=0", "source Requires-Python differs"),
        ("Provides-Extra", "unqualified", "source extras differ"),
        (
            "Requires-Dist",
            "unqualified-dependency>=99",
            "source runtime requirements differ",
        ),
        ("License-File", "NOT-LICENSE", "source license payload differs"),
        ("Dynamic", "requires-dist", "dynamic artifact metadata is not qualified"),
        (
            "Import-Name",
            "unqualified",
            "generated import declarations are not qualified",
        ),
    ],
)
def test_rehashed_metadata_guard_matches_the_real_qualified_leaf(
    reference_owner, field, value, reason
):
    # Arrange: modify a genuine normal-built wheel and retain a correct RECORD.
    owner = reference_owner
    files = wheel_files(owner["wheel"])
    metadata = next(name for name in files if name.endswith(".dist-info/METADATA"))
    headers, body = files[metadata].split(b"\n\n", 1)
    prefix = field.encode() + b":"
    new_headers = b"\n".join(
        line for line in headers.splitlines() if not line.startswith(prefix)
    )
    new_headers += b"\n" + prefix + b" " + value.encode()
    files[metadata] = new_headers + b"\n\n" + body
    raw = pack_wheel(files)
    # Act / Assert: both actual algorithms reach the same substantive guard.
    with pytest.raises(ValueError, match=reason):
        owner["reference"].source_payload_identity(
            raw, owner["sdist"], owner["commit"], source_root=owner["source"]
        )
    with pytest.raises(ValueError, match=reason):
        source_payload_identity(
            raw,
            owner["sdist"],
            owner["commit"],
            owner["policy"],
            source_root=owner["source"],
        )


def test_qualified_entrypoint_metadata_survives_extraction(reference_owner):
    # Arrange
    owner = reference_owner
    files = wheel_files(owner["wheel"])
    metadata = next(name for name in files if name.endswith(".dist-info/METADATA"))
    entry = metadata.rsplit("/", 1)[0] + "/entry_points.txt"
    files[entry] += b"\n[unqualified]\ncommand = unknown:main\n"
    raw = pack_wheel(files)
    # Act / Assert: the shared and existing qualified verifier enforce the same port.
    with pytest.raises(ValueError, match="source entry points differ"):
        owner["reference"].source_payload_identity(
            raw, owner["sdist"], owner["commit"], source_root=owner["source"]
        )
    with pytest.raises(ValueError, match="source entry points differ"):
        source_payload_identity(
            raw,
            owner["sdist"],
            owner["commit"],
            owner["policy"],
            source_root=owner["source"],
        )
