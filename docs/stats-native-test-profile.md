# Stats native test profile

Stats admits only the complete test matrix on compute-03 with the qualified
E846 image and Apptainer bytes. The three Python versions each passed 3,217
tests with 19 skips using all/dev, 32 workers and coverage inside the original
1,800-second, 64-GiB qualification scopes. The workflow keeps a 30-minute job
limit. The owning leaf driver chooses its original host CPU worker count;
the shared transport does not replace its dependency or test policies.

The ten pinned leaf helpers match immutable public source at
9eb22bd3a7a785bf561ab0b6add148d613415d29. The profile stages the qualified Dev
owned-context resource at 4e14fe28571617ccf7b6fffd9cff0e15a7bfc38c. The resource
stager is verified before execution. Leaf cleanup owns its application root;
the shared caller removes only its separately recorded bootstrap files.

The qualification receipt records aggregate native results. Individual audit
controls were checked in original source and post-merge CI separately. Selected
early installer and later MCP cancellation timings passed; this does not cover
every possible interruption point.

Build and publish operations are refused before native scheduling. This prevents
upload of the existing private 1.0.0 artifacts. An unused successor version,
archive and installed-wheel qualification, main promotion, tag binding and
publisher trust remain separate requirements. Test-profile registration alone
establishes no successful shared Actions invocation or release readiness.

Writer, IO, Scholar and Browser retain their prior plans, operations, workers
and limits. Existing fixed-path Browser selection is extended to Stats without
changing other profiles' repository-variable locators.
