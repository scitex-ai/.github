# scitex-ai/.github

Org-wide defaults for the SciTeX ecosystem: reusable CI workflows (called via
`workflow_call`) and community-health files.

## Reusable workflows

Under `.github/workflows/`, called from a leaf repo like:

```yaml
jobs:
  pytest-matrix:   # <-- the job id is load-bearing. See "Caller job ids" below.
    uses: scitex-ai/.github/.github/workflows/pytest-matrix.yml@main
    secrets: inherit
```

Copy the stub from [`workflow-templates/`](workflow-templates/) rather than
writing one — it also shows up under *Actions → New workflow* in every repo.

- `pytest-matrix.yml` — pytest across the supported Python versions.
- `import-smoke.yml` — bare-install import smoke test.
- `quality-audit.yml` — `scitex-dev ecosystem audit-all` quality gate.
- `rtd-sphinx-build.yml` — local `sphinx-build` smoke check.
- `cla.yml` — CLA Assistant + owner direct-push bypass.
- `auto-merge-to-develop.yml` — auto-merge green PRs targeting `develop`.

## Caller job ids — DO NOT INVENT THEM

**The caller's job id is the branch-protection context prefix.** GitHub names the
status check of a reusable-workflow call:

```
"<caller job id> / <job name inside the reusable workflow>"
```

So a repo that calls `pytest-matrix.yml` from a job it named `test` emits
`test / pytest-matrix-on-ubuntu-py3.11`, while one that named it `pytest-matrix`
emits `pytest-matrix / pytest-matrix-on-ubuntu-py3.11`. Different repos, different
required-check names, and **one protection list can no longer serve the ecosystem** —
every repo needs a bespoke list, hand-read off a real PR, forever.

Use exactly these job ids. They are what the already-migrated repos emit today
(`scitex-dict`, `scitex-ui`, `scitex-todo`, `scitex-scholar`), so adopting them
is a no-op for those repos rather than fresh churn:

| reusable workflow | caller job id | resulting status check |
|---|---|---|
| `pytest-matrix.yml` | `pytest-matrix` | `pytest-matrix / pytest-matrix-on-ubuntu-py3.{11,12,13}` |
| `import-smoke.yml` | `import-smoke` | `import-smoke / import-smoke-on-ubuntu-py3-12` |
| `quality-audit.yml` | `quality-audit` | `quality-audit / audit` |
| `rtd-sphinx-build.yml` | `docs-sphinx` | `docs-sphinx / docs-sphinx` |

`cla.yml` and `auto-merge-to-develop.yml` are exempt: neither emits a prefixed
required check (the CLA status is posted by the action as a plain `CLAssistant`
commit status, and auto-merge gates nothing), so their caller job id is not
load-bearing.

### Migrating a repo onto these workflows

Adopting a reusable workflow **renames that repo's status checks** (the prefix is
added). Branch protection must be reconciled in the same change, or the repo goes
green-but-unmergeable — every check passing, `mergeStateStatus: BLOCKED`, no error
anywhere.

1. Open the migration PR and let CI run.
2. **Read the emitted check names off that real PR.** Never guess them.
3. Compare with `required_status_checks.contexts` on **each** protected branch
   (`main` *and* `develop` — they drift apart).
4. Reconcile — *reconcile*, not blanket-flip. Some repos already had protection
   set to the post-migration names in anticipation, and need no change at all;
   others still carry the pre-migration names and do.

Note `scitex-dev`: its protection was deliberately set back to the **bare**
(pre-migration) names as an interim to unblock merges. When it migrates, its
protection must be flipped **to the prefixed names in the same change**.

PyPI publish/release workflows stay local to each leaf repo — PyPI trusted
publishing (OIDC) does not support `workflow_call` reusable workflows
(`invalid-publisher` error), so that job must run in a workflow file that
lives directly in the publishing repo.

## Branches

- `main` — stable, what callers reference (`@main`).
- `develop` — working branch for changes to these workflows, promoted to
  `main` the same way as the rest of the ecosystem.
