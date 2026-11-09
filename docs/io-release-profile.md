# IO native release profile

`leaf-release-sif.yml` dispatches fixed registered leaf repository profiles. The
Writer compatibility workflow forwards its original operation, commit, and tag
inputs; its qualified image, runtime, source closure and complete suite remain
unchanged. The shared byte gate checks the complete image and native runtime,
not merely their presence or mutable filenames.

IO is registered against the whole E846 image and verified Apptainer runtime.
Qualification used source `618e79b88615002cf3264435cf349911be34bb7c`: actual
Python 3.11.17, 3.12.15 and 3.13.16 each passed the complete all/dev suite
(2,680 passed, seven existing skips), mandatory first-citation persistence in a
new private Unix-socket PG cluster, and guarded teardown. The Python 3.12
wheel/sdist build also passed normal dependency resolution, isolated whole-wheel
imports, RECORD/metadata and Git-source verification on admitted compute-03.
The ten helper hashes cover the native drivers, owned-context cleanup, artifact
identity verification, real citation probe and test-store guard. A valid-looking
image record or successful generic PR tests alone do not qualify a profile. Unknown repositories, fork events, nonmembers,
arbitrary operations, floating source commits and malformed tags refuse.

The intended IO leaf caller resolves an existing tag against protected main
before native test/build execution. Publication retains a separate hosted OIDC
boundary after complete wheel/sdist source and metadata verification. No IO tag
or publication is authorized by adding this source-only dispatcher.


The IO workload budget is at most four pytest workers per runner,
clamped further by affinity/visible cgroup quota. This is bounded admission,
not exclusive ownership of a node. The fixed descriptor supplies the validated
budget through the clean native environment; no fleet runner setting changes.
The IO source closure also includes the mandatory first-citation consumer probe
and the shared stdlib-only test-store ownership/routing guard:
it uses the public Dev ephemeral-cluster SPI and a newly owned Unix-socket PG
cluster, with an offline child and no ambient host-store fallback. The private cluster wraps the entire suite and installed-wheel smoke; ordinary
local tests instead force an owned unavailable Unix socket and make no SQL
persistence claim. The earlier compute-04 initdb timeout remains a failed build
attempt; qualification did not raise its 120-second deadline or substitute RAM
for the normal scratch filesystem. This registration does not authorize a tag
or publication; the existing protected-main and OIDC boundaries still apply.


## Version-job admission

The native matrix admits **one version job at a time per workflow invocation**.
Each registered test version still runs, and `fail-fast: false` keeps a failed
version from cancelling the remaining versions. The complete dependency profile,
pytest worker budget, image/runtime verification, private PostgreSQL checks,
operation deadlines and guarded cleanup remain unchanged. This reduces overlap
between the large fresh environments created by the matrix.

This is a workflow scheduling budget, not an exclusive host reservation. Other
workflow invocations and user jobs can still compete for the same disk. A leaf
must adopt an accepted immutable workflow revision containing this policy before
it applies; changing this producer does not change an existing tag's pinned
executor. Native qualification is required before claiming a recovered release.


## Qualified host scope

The registered company IO executor currently admits **compute-03 only** for
native tests and builds. Its complete source qualification used
`618e79b88615002cf3264435cf349911be34bb7c` on that host, with all three full
Python suites, private first-citation persistence, verified teardown and the
separate same-source build. The image, runtime, ten helper hashes and operation
deadlines remain the existing qualified values.

A generic organization CPU label alone does not qualify another host for this
workload. Compute-04's initializer and first-save timeouts remain failed evidence;
this routing correction does not repair that host or establish fleet-wide
readiness. Another host needs complete qualification before admission is widened.
The public IO library's platform support is separate from this company release
configuration. Writer and Scholar retain their independent existing selections.
