"""Reviewed production owner policies; these grant no runtime or publish admission."""

import json

from .policy import PackagePolicy
from .registry import PolicyRegistry

SCHOLAR_POLICY = PackagePolicy(
    repository="scitex-ai/scitex-scholar",
    distribution="scitex-scholar",
    package="scitex_scholar",
    source_mappings=(("src/scitex_scholar/", "scitex_scholar/"),),
    reviewed_build_json=json.dumps(
        {"targets": {"wheel": {"packages": ["src/scitex_scholar"]}}},
        sort_keys=True,
    ),
    reviewed_backend_json=json.dumps(
        {"build-backend": "hatchling.build", "requires": ["hatchling"]},
        sort_keys=True,
    ),
    required_members=(
        "scitex_scholar/__init__.py",
        "scitex_scholar/_django/manifest.json",
        "scitex_scholar/_django/urls.py",
        "scitex_scholar/_django/templates/scholar/scholar.html",
    ),
)

# This exact owner table is separate from the empty algorithm-default registry.
# A package policy alone cannot select an image, authorize a tag or mint OIDC.
RELEASE_REGISTRY = PolicyRegistry((SCHOLAR_POLICY,))
