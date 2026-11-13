# Browser artifact identity

The shared artifact registry recognizes the exact repository
scitex-ai/scitex-browser. Its reviewed Hatch mapping includes the entire
src/scitex_browser package without omissions or additional mappings.
The package initializer, main skill and Sphinx index are required resources;
the verifier also compares every committed package file with both archives.

The real-source fixture is commit
486e229d58c3b17abc23c9519818fdbffac6821c, from the draft Browser repair.
Tests fetch that exact public Git object and build a normal wheel and sdist.
They check all 190 committed package files and 268 selected sdist source files,
and reject changed or removed skill
and documentation resources even when an altered wheel has a truthful RECORD.

Independent private qualification on compute-03 used the existing image with
SHA256 aa5836a6c317640d7e20f01eb79aa7385b3dca2f369b595065c50ba3dd34a7d5.
The unchanged retained release script passed all three Python versions
(3.11, 3.12 and 3.13): 240 tests and two optional-peer skips per version,
with all 32 workers retained. The private build, fresh noneditable base install,
198 installed RECORD hashes, all 190 package payloads, five real feedback-stream
controls and both archive metadata checks passed. Test coverage was 26%;
this does not establish live-site or real-browser behavior.

Initial qualification setup failures remain recorded: an isolated configuration
directory outside the writable binds prevented plugin startup, and a reused
checkout carried the preceding run's coverage.xml into the next audit.
The accepted runs used the supported SCITEX_DIR under owned writable scratch
and clean per-version snapshots. No audit waiver, whitelist, test reduction or
worker/deadline relaxation was used.

This registration provides artifact identity only. It does not register Browser
in the native release dispatcher, admit an image or runner, configure PyPI trust,
authorize a version tag, or publish a package. A regression test verifies that
the native dispatcher still refuses Browser. The same-version 0.1.15 artifacts
used for private qualification must never be uploaded. Protected-main source,
runtime admission, final release artifacts and actual publisher registration
remain separate release requirements.
