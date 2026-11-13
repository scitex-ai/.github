# Optional shared CI resources

The leaf release caller supports a `sharedResource` descriptor for the
`owned-context-v1` role. A registered profile supplies an immutable Dev Git
revision and SHA-256 values for the stager and lifecycle source. The transport
accepts no arbitrary host, repository, file path or environment-variable name.

The caller downloads through HTTPS, refuses redirects and unexpected bytes,
limits each input to 1 MiB, and verifies the stager before executing it. The Dev
helper creates the resource mode 0600 in an exclusive mode 0700 directory.
The path is exported only after success. Python receives a minimal environment.

Metadata requires exact-length lowercase digests/revisions and exactly
representable integer file identifiers. Unsupported identifiers fail closed.
Cleanup checks root and claimed file identities. Entry operations use the held
Linux directory descriptor; only recorded bootstrap files and an empty bootstrap
directory are removed. Unknown entries or replacements cause refusal. Cleanup
never recursively removes RUNNER_TEMP or a leaf application root. Cleanup runs
before artifact upload, so a cleanup failure also blocks that transfer. Each
optional step has a one-minute cap within the existing job budget.

Stats supplies the pinned descriptor for its test-only native profile. Writer,
IO, Scholar and Browser omit it, retain their existing plans and skip both
optional steps. Resource transport grants no release tag or publisher.

Tests execute actual script blocks with Node, immutable public HTTPS inputs,
the real Dev Python helper and filesystem objects. The Actions-core adapter
captures outputs and environment exports. Controls cover incorrect digests,
invalid metadata, unknown entries and replacements. Existing plans are compared
against actual outputs frozen from shared main
ab781bd43d0cb2090d4d567daccc984abdf93ba2.
