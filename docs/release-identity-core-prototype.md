# Release identity core and registered owner checks

`release_core` is a stdlib-only archive/source verification port for Python 3.11+.
It does not authorize a release, register an image/profile, resolve an immutable
remote tag, mint credentials, or upload artifacts. Writer and IO retain their existing identity adapters; the explicit Scholar owner
port is prepared for a thin pinned leaf adapter. Its native image/source profile
remains refused until actual full qualification is registered. The leaf-owned publication job must retain its
PyPI Trusted Publisher workflow identity.

The core extracts the qualified Writer/IO wheel, RECORD, sdist and generated
metadata checks behind an explicit owner policy. `PackagePolicy` identifies the
exact repository, distribution, import namespace, source-to-wheel mappings,
required payloads, complete reviewed Hatch backend/build configuration and
omissions. The repository is not inferred from a `scitex-` prefix. A policy
belongs to a pinned reviewed registry; it must never come from request inputs.
The owner records under `tests/fixtures/release-core` are test fixtures, not
production registrations. `DEFAULT_REGISTRY` remains empty and refuses every
owner. The separate `release_core.registered.RELEASE_REGISTRY` contains the
reviewed Scholar package mapping only; this read-only identity policy does not
register its native image, admit a tag or grant publication. `PolicyRegistry` accepts only an explicit immutable tuple of unique owner
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

## Exact source-file mappings

`PackagePolicy.file_mappings` optionally binds individual regular Git files to
exact members inside the registered wheel namespace. This supports a canonical
configuration file packaged under a different name without copying its maintained
source. The mappings are immutable tuples supplied by the reviewed policy, not
inferred from a wheel, build configuration or request.

Mapped sources must exist as regular files in the verified Git commit. Their
wheel bytes and source-archive bytes remain subject to the same complete
membership, RECORD, metadata and Git-object checks. Missing sources, source
symlinks, unsafe paths, duplicate or overlapping mappings, namespace escapes and
rehashed artifact modifications are refused. The complete Hatch/backend policy
still has to match its reviewed configuration.

The Scholar CLI dictionary source case in
`tests/fixtures/release-core/scholar-cli-dictionary.json` exercises the explicit
file mapping. The registered Scholar policy also requires this dictionary and
its exact Hatch wheel/source-archive force-include configuration, retaining the
existing required GUI assets. The registered CLI checks rehashed modifications
to the dictionary against its Git source bytes.

An older immutable consumer pin retains its older registry policy. Registry
registration does not update consumer references or authorize a runtime/image
profile, tag or publisher. Run the real source-build controls with the declared
self-test profile:

```bash
.venv/bin/python -m pytest tests/test_release_core_file_mappings.py -q
```

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


## Pinned Scholar command port

Fetch the reviewed immutable central commit into an owned source directory and
verify the complete `release_core/*.py` source closure before importing it. The
leaf retains its remote tag/main/membership/runtime/OIDC guards and calls:

```bash
PYTHONPATH=/owned/pinned-central python -m release_core verify-files \
  --repository scitex-ai/scitex-scholar --commit <resolved40> \
  --source-root /owned/leaf-source --wheel /owned/dist/package.whl \
  --sdist /owned/dist/package.tar.gz
```

The command resolves an exact central-owned policy, checks actual regular files,
RECORD, source membership/bytes and complete reviewed Hatch configuration, and
prints the source-bound artifact proof. Repeat it immediately before upload and
compare the proof. No policy, import mapping or omission list comes from the
request/leaf artifacts. The positive algorithm fixture uses immutable public Git candidate Scholar1.29.1
(6f8f26cc), not a claimed PyPI publication. The genuine1.29.0 Git/Hatch build
is a required negative control: its ignore rules omit a tracked favicon SVG.
Owned build fixtures use OS /tmp roots so an ambient .cache/TMPDIR ancestor
cannot cause Hatch to silently discard those ignore rules. Native qualification
and publication remain separate mandatory gates.


### Qualified Scholar native profile

The native dispatcher now admits Scholar only on the Organization runner group
with the fixed `scitex-compute-03` host label, retaining Writer and IO selections.
The reviewed E846 image and Apptainer runtime are bound to actual runner 980
context evidence by qualification digest
`3b842983d34ba0b354836048cdf49b899583f871567ad78ebc1968f04ffaf786`.
The eight exact leaf helper hashes were qualified at Scholar source
`49da2f7d2274e60399e178f871ab5298c239d913`: Python 3.11, 3.12 and 3.13 each
passed 1,669 tests with 13 existing skips, owned PostgreSQL, four-worker admission
and cleanup. A separate fresh checkout of the same commit passed the Python 3.12
build, normal wheel all/dev install, pip check and complete artifact identity.

The initial manual build correctly refused a test-generated undeclared runtime
file after a supervisor reused one checkout for tests and build. That refusal
is retained; qualification uses a fresh build checkout as canonical separate
jobs do. No artifact exclusions or validator changes were introduced. The
composed qualification receipt digest is
`f7028e85c9eeb31d02dac4c856a16593894ebfc30c5212b0b719b5211706ab42`.
Registration does not create a tag, publish a package, or authorize another
runner host. Leaf remote identity checks and protected OIDC publishing remain
mandatory.
