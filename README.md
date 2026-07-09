# scitex-ai/.github

Org-wide defaults for the SciTeX ecosystem: reusable CI workflows (called via
`workflow_call`) and community-health files.

## Reusable workflows

Under `.github/workflows/`, called from a leaf repo like:

```yaml
jobs:
  call:
    uses: scitex-ai/.github/.github/workflows/<name>.yml@main
    secrets: inherit
```

- `pytest-matrix.yml` — pytest across the supported Python versions.
- `import-smoke.yml` — bare-install import smoke test.
- `quality-audit.yml` — `scitex-dev ecosystem audit-all` quality gate.
- `rtd-sphinx-build.yml` — local `sphinx-build` smoke check.
- `cla.yml` — CLA Assistant + owner direct-push bypass.
- `auto-merge-to-develop.yml` — auto-merge green PRs targeting `develop`.

PyPI publish/release workflows stay local to each leaf repo — PyPI trusted
publishing (OIDC) does not support `workflow_call` reusable workflows
(`invalid-publisher` error), so that job must run in a workflow file that
lives directly in the publishing repo.

## Branches

- `main` — stable, what callers reference (`@main`).
- `develop` — working branch for changes to these workflows, promoted to
  `main` the same way as the rest of the ecosystem.
