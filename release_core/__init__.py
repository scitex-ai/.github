"""Central stdlib release identity ports, with explicit reviewed owner policy.

Neither the library nor its registered-owner CLI authorizes a publisher/image profile. The source/file ports perform
archive checks before source comparison. Callers retain immutable tag/member admission around
these pure operations; this package cannot mint credentials or upload files.
"""

from .artifacts import regular_bytes, sdist_identity, wheel_identity
from .files import verify_artifact_files
from .policy import PackagePolicy, ReviewedSdistLink
from .registry import DEFAULT_REGISTRY, PolicyRegistry
from .source import source_payload_identity

__all__ = [
    "DEFAULT_REGISTRY",
    "PackagePolicy",
    "PolicyRegistry",
    "ReviewedSdistLink",
    "regular_bytes",
    "sdist_identity",
    "source_payload_identity",
    "verify_artifact_files",
    "wheel_identity",
]
