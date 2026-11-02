# Release identity core: unregistered prototype

`release_core` is a stdlib-only archive/source verification port for Python 3.11+.
It does not authorize a release, register an image/profile, resolve an immutable
remote tag, mint credentials, or upload artifacts. No existing leaf publisher
or dispatcher consumes it yet. The leaf-owned publication job must retain its
PyPI Trusted Publisher workflow identity.

The core extracts the qualified Writer/IO wheel, RECORD, sdist and generated
metadata checks behind an explicit owner policy. `PackagePolicy` identifies the
exact repository, distribution, import namespace, source-to-wheel mappings,
required payloads, complete reviewed Hatch backend/build configuration and
omissions. The repository is not inferred from a `scitex-` prefix. A policy
belongs to a pinned reviewed registry; it must never come from request inputs.
The owner records under `tests/fixtures/release-core` are test fixtures, not
production registrations. `DEFAULT_REGISTRY` is empty and refuses every
owner. `PolicyRegistry` accepts only an explicit immutable tuple of unique owner
policies and resolves exact repository strings; there is no prefix guess or
implicit FigRecipe mode. Policy mappings/path selections are immutable tuples.

The primary file port is:

```python
from pathlib import Path
from release_core import verify_artifact_files

proof = verify_artifact_files(
    Path(wheel_path), Path(sdist_path), source_commit, registered_policy,
    source_root=Path(source_checkout),
)
```

It reads actual regular files, checks wheel/RECORD/metadata ownership and every
public payload byte against immutable Git objects, and returns their digests
and source membership proof. Repeat the check immediately before uploading and
compare with the earlier proof. Immutable tag/org membership, admitted native
runtime, full leaf tests, complete frontend closure and final remote identity
revalidation remain mandatory caller responsibilities. A successful result from
this library alone does not satisfy those gates.

## Closed source-owned documentation links

The default policy rejects every sdist symlink. Writer and IO retain that empty
policy. The prototype additionally supports an explicit `ReviewedSdistLink`
record: archive path, exact link text, link Git blob, normalized jailed target
path and target Git blob. It validates every archive element before reading a
link target. The target must be a present single-hop regular archive member,
with exact bytes of the registered regular Git object; the source link must
itself be Git mode `120000` with the exact registered blob/text. No host symlink
is followed or archive extracted. Absolute/escaping/changed/unknown links,
chains, duplicates, hardlinks and devices are refused.

This is a reviewed protocol exception, not blanket symlink acceptance. It has
no activated FigRecipe profile. The original FigRecipe source had thirteen
tracked targets and two dangling quickstart targets. The separate source-assets
candidate supplies the two actual generated PNGs with provenance; the fixture
then binds all fifteen links to genuine tracked regular blobs. Producing regular
jailed image bytes in a future leaf sdist remains preferable.

## Reproducible controls

The normal test prerequisites are declared in `self-test.yml`:

```bash
uv venv --seed --python 3.12 .venv
uv pip install --python .venv/bin/python pytest pyyaml build hatchling
.venv/bin/python -m pytest tests/test_release_identity_core.py -q
.venv/bin/python -m pytest tests/ -q
```

The controls fetch exact immutable public Writer, IO and FigRecipe commits into
owned temporary repositories, build genuine Hatch wheel/sdist pairs, and mutate
those artifacts for negative tests. They do not substitute metadata-only positive
payloads. Rehashed foreign bytes/members, invalid RECORD, conflicting owners,
changed metadata, unsupported archive elements and source/policy/link mutations
must still fail at their intended guards. Real qualified Writer/IO verifiers are also called as independent references:
their accepted whole-source digests and rejection of rehashed dependency, Python,
extra, license, dynamic/import and entrypoint metadata must agree with this port.
No production verifier is patched or replaced for that comparison. Public
source fetch/build failures are failures, not skips. These are identity-core controls, not the native full
runtime suites or installed dependency-cohort qualification of the leaves.

Before activation, the owner must review this prototype, qualify the complete
immutable core/policy source closure, preserve the existing tag/admission and
OIDC lifecycle controls, and separately qualify each leaf's actual image,
frontend and runtime. There is no publication shortcut in this change.
