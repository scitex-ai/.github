# SciTeX release model (DRAFT proposal — for operator review, not adopted)

This document + the two reusable workflows it describes are a **draft
proposal**. Nothing here is wired into any leaf repo yet. The goal is to
replace the 68 inlined, drifting copies of
`pypi-publish-and-github-release-on-tag.yml` with **one** org reusable, and to
implement the operator-confirmed release model (TG 2026-07-23) exactly.

## The flow

A release is cut by **pushing a version tag on `develop`**:

```
git tag vX.Y.Z && git push origin vX.Y.Z
```

Everything else is automatic. The leaf repo's thin `release.yml` (see
`workflow-templates/release.yml`) composes two org reusables:

```
 tag v* on develop
        │
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Reusable A — promote-develop-to-main-on-tag.yml             │
 │   ci      : run full CI on the TAGGED commit (pytest-matrix)│
 │   promote : if green, open develop→main PR at the same      │
 │             commit and auto-merge it with a MERGE commit    │
 │             (never squash) → main now contains the tag sha  │
 └─────────────────────────────────────────────────────────────┘
        │  (caller: publish `needs: promote`)
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Reusable B — pypi-publish-and-github-release-on-tag.yml     │
 │   build   : wheel + sdist from the tag                      │
 │   publish : CONTAINMENT GUARD, then PyPI (hosted | sif)     │
 │   release : GitHub Release from the tag                     │
 │   report  : consolidated verdict → github.actor             │
 └─────────────────────────────────────────────────────────────┘
```

Because the caller wires `publish: {needs: promote}`, **B never runs until A
has landed the tag's commit on `main`**. Both are reusables (not a single
mega-workflow) so the caller can express that one `needs:` edge — that is the
reason A is a reusable and not just documented triggers.

## The containment guard (the load-bearing part)

A **squash merge does not fail** — it silently creates a *new* SHA, so the
tag's commit leaves `main`'s history and `setuptools-scm` miscomputes the
version. We do **not** fight this with repo settings (they can be changed, and
a wrong setting fails silently). Instead, at publish time in B we assert the
tag's commit is contained in `main`:

```bash
TAG_SHA="$(git rev-list -n1 "refs/tags/${TAG}")"
git fetch --no-tags --prune origin main
git merge-base --is-ancestor "${TAG_SHA}" origin/main \
  || { echo "::error::CONTAINMENT GUARD FAILED — tag not in main"; exit 1; }
```

Not contained → **ABORT publish, fail RED.** This turns the silent squash
failure into a loud one and works under squash **or** fast-forward. Reusable A
also merges with `--merge` (never `--squash`) and re-checks containment right
after merging, so the guard in B is the backstop, not the only line of
defence.

## The feedback loop (A→B ⇒ B→A)

Each stage reports its result back to `github.actor` (the tag pusher):

- Every job appends a `repo + stage + tag + verdict` line to
  `$GITHUB_STEP_SUMMARY`.
- B's final `report` job emits a **consolidated verdict** and **fails red** if
  any stage failed, so the actor's GitHub run-failure notification carries the
  whole-pipeline outcome (which repo, which stage).
- Every failure path is marked `# FLEET-HOOK:` in the YAML — that is exactly
  where an out-of-band **scitex-todo card / DM to `github.actor`** plugs in
  once the fleet channel is chosen. The draft deliberately uses only
  GitHub-native surfaces (job summary + a failing status) so it is adoptable
  today without the fleet dependency.

## The two publish backends

The single reusable B parametrizes **both** real variants behind
`publish-backend`:

| backend  | runner (`runs-on-json`)                        | build                         | publish                                                        |
|----------|------------------------------------------------|-------------------------------|----------------------------------------------------------------|
| `hosted` | `'"ubuntu-latest"'`                            | `setup-python` + `python -m build` | `pypa/gh-action-pypi-publish` (Docker action, OIDC trusted publisher) |
| `sif`    | `'["self-hosted","Linux","X64","scitex-ci"]'` | `.github/ci/exec-in-sif.sh build-in-sif.sh` | `.github/ci/exec-in-sif.sh publish-in-sif.sh` (manual OIDC: GitHub JWT → PyPI mint-token → twine, inside the SIF) |

The caller selects the backend **and** the matching runner. A `sif` repo must
never be given a hosted `runs-on-json` — that is the `no-hosted-runners-guard`
posture (the Spartan nodes have no Docker and no bare-node Python; the SIF path
is self-hosted by construction). `runs-on-json` is consumed via `fromJSON`, so
a bare quoted string (`'"ubuntu-latest"'`) and a label array both work in the
same field.

**Secrets (decision-for-review):** both backends publish via **OIDC Trusted
Publishing**, so **no API-token secret is required** by default. B declares one
*optional* `PYPI_API_TOKEN` secret as the documented fallback for any repo that
still publishes with a classic token instead of a trusted publisher. The
caller passes `secrets: inherit`.

## How a leaf repo adopts it (the thin caller)

Copy `workflow-templates/release.yml` to `.github/workflows/release.yml`, delete
the repo's old inlined `pypi-publish-and-github-release-on-tag.yml`, and set the
three marked values (`publish-backend`, `runs-on-json` on both jobs,
`pypi-project`). A `sif` repo also keeps its `.github/ci/*.sh` scripts (the
reusable calls them in the caller's checkout).

### Worked example — scitex-dev (the SIF case)

`scitex-dev/.github/workflows/release.yml`:

```yaml
name: release
on:
  push:
    tags: ['v*']
jobs:
  promote:
    uses: scitex-ai/.github/.github/workflows/promote-develop-to-main-on-tag.yml@main
    with:
      runs-on-json: '["self-hosted","Linux","X64","scitex-ci"]'
    secrets: inherit
  publish:
    needs: promote
    uses: scitex-ai/.github/.github/workflows/pypi-publish-and-github-release-on-tag.yml@main
    with:
      publish-backend: sif
      runs-on-json: '["self-hosted","Linux","X64","scitex-ci"]'
      pypi-project: scitex-dev
    secrets: inherit
```

scitex-dev already ships `.github/ci/build-in-sif.sh`, `exec-in-sif.sh`,
`run-in-sif.sh`, and `publish-in-sif.sh`, so no other change is needed. The
PyPI Trusted Publisher on `pypi.org/p/scitex-dev` must list the **new**
workflow filename — see the human-decision list.

A hosted repo's caller is identical except `publish-backend: hosted` and
`runs-on-json: '"ubuntu-latest"'` on both jobs.

## What still needs a human decision

- **PyPI Trusted Publisher filename.** Trusted publishing is keyed on the
  *workflow filename*. Moving publish into a reusable means the actual runner
  filename the caller invokes is still the leaf repo's `release.yml`, but the
  OIDC subject differs when a reusable does the upload — each package's PyPI
  trusted-publisher config must be re-checked / updated before first real
  release (per-package, ~68 entries). This is the single biggest gate.
- **Hosted-only CI runner.** Reusable A runs CI via the org `pytest-matrix.yml`
  reusable, which is self-hosted by construction (`uses:` can't be an
  expression, so the CI ref is fixed). Repos that must run CI on hosted runners
  need either a hosted `pytest-matrix` variant or a `runs-on` input added to
  the shared `pytest-matrix.yml`. Decide before onboarding any hosted-only repo.
- **`--admin` auto-merge.** A promotes with `gh pr merge --merge --admin` to
  bypass required-review on the automated same-commit promotion. Confirm every
  target repo's branch protection permits admin merge with a merge commit (not
  squash-only), or the guard will (correctly) abort the release.
- **The 5 CALLER+extra repos.** A handful of repos append extra steps to their
  current inlined release (e.g. docs/artifact uploads, Zenodo DOI, extra smoke
  gates). Those extras must become either **inputs** on B or **companion jobs**
  in the leaf caller — enumerate them and decide input-vs-companion per repo
  before migrating them off their inlined copies.
- **Rollout order.** Pilot on one SIF repo (scitex-dev) and one hosted repo
  before the org-wide sweep; keep each leaf repo's old inlined workflow until
  its first reusable-driven release is verified green.
