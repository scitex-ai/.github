"""Read and verify the actual files before a leaf-owned publication stage."""

import hashlib

from .artifacts import regular_bytes
from .source import source_payload_identity


def verify_artifact_files(wheel, sdist, commit, policy, *, source_root):
    """Return source-bound digests; no token minting or uploads occur here.

    Repeat immediately before any upload and compare with the earlier proof.
    Immutable tag/org membership and admitted runtime remain caller obligations.
    """
    wheel_raw, sdist_raw = regular_bytes(wheel), regular_bytes(sdist)
    report = source_payload_identity(
        wheel_raw, sdist_raw, commit, policy, source_root=source_root
    )
    return {
        **report,
        "repository": policy.repository,
        "distribution": policy.distribution,
        "wheel_sha256": hashlib.sha256(wheel_raw).hexdigest(),
        "sdist_sha256": hashlib.sha256(sdist_raw).hexdigest(),
    }
