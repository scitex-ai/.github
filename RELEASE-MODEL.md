# SciTeX release model

**A release workflow must not merge to `main` unless CI passes.**

> 「リリースのワークフローということですけれど、CI が通らないとマージしちゃ
> だめですよね。明らかに」
> — operator, 2026-08-11

This document and `promote-develop-to-main-on-tag.yml` implement that ruling.

## What this consolidates — measured, and then corrected

Surveyed across all 73 active `scitex-ai` repos on 2026-08-12:

| measurement | count |
|---|---|
| repos with a tag-triggered release/publish workflow | **68** |
| …that run `gh pr merge --admin` on a `develop -> main` sync at tag push | **45** |
| …of those 45, where the merge job is reachable only **after** a job that runs the tests | **45 of 45** |
| …that gate the PyPI publish on a test job in the same workflow | 65 of 68 |
| …that publish with **no** test job upstream | **3** |
| …publishing via OIDC trusted publishing | **69 of 69 files** |
| …publishing via an API-token secret | **0** |
| of the 45, repos whose `main` has no branch protection at all | **1** (`scitex-python`) |

> ### Correction — this document first shipped the opposite claim
>
> The first version of this file, and the PR that landed it, asserted that all
> 68 read **zero** check state and that the 45 admin-merges ran with "no
> greenness test whatsoever". **That was wrong.** It came from grepping for
> `needs: ci` and finding none, when the repos actually spell it `needs: test`
> or `needs: build`. Resolving the `needs:` graph instead of matching a keyword
> shows the merge gated in **45 of 45**.
>
> A keyword search is not a reachability check — the exact text-vs-behaviour
> error `tests/test_release_gate.py` was written to prevent, committed in the
> same change that introduced the test. The numbers above are the corrected
> ones, produced by walking each workflow's dependency closure.

**So this reusable is a consolidation, not an urgent fix.** Its value is one
audited implementation instead of 45 drifting copies, running the org
`pytest-matrix` rather than each repo's bespoke inline matrix. A repo adopting
it is trading a working local gate for a shared one — a real benefit, but not
a hole being closed. Weigh it on that basis.

The findings that remain genuinely open, and are **not** fixed by this file:

- **3 repos publish to PyPI with no test job upstream of the publish job** —
  `claude-code-telegrammer`, `scitex-orochi`, `scitex-pd`. This is the actual
  instance of the hazard originally claimed for 45.
- **`scitex-python` has no branch protection on `main`.**
- For the other 44, the required contexts that `--admin` bypasses are the same
  `pytest-matrix` checks the release workflow already ran, so the bypass
  changes little in practice — but it does mean the merge commit itself is
  never independently verified.

## The flow

A release is cut by pushing a version tag on `develop`:

```
git tag vX.Y.Z && git push origin vX.Y.Z
```

```
 tag v* on develop
        │
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ promote-develop-to-main-on-tag.yml   (ORG REUSABLE)          │
 │   ci      : pytest-matrix on the TAGGED commit               │
 │   promote : needs: ci  ← THE GATE. Only if green: open a     │
 │             develop→main PR at that same commit and merge it │
 │             with a MERGE commit (never squash)               │
 └──────────────────────────────────────────────────────────────┘
        │  (caller: build `needs: promote`)
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ the leaf repo's OWN top-level workflow  (NOT centralised)    │
 │   build   : wheel + sdist from the tag                       │
 │   publish : CONTAINMENT GUARD, then PyPI via OIDC            │
 │   release : GitHub Release from the tag                      │
 │   report  : consolidated verdict → github.actor              │
 └──────────────────────────────────────────────────────────────┘
```

`gh pr merge --admin` inside `promote` bypasses required **review** — nobody
reviews an automated same-commit promotion — **not** required checks. The
checks already ran, in this DAG, ahead of the merge. That distinction is the
entire reason this design satisfies the ruling, and it is pinned by
`tests/test_release_gate.py`.

## Why the publish half is NOT centralised

It looks like duplication left on the table. It is the only shape that works.

PyPI Trusted Publishing validates the OIDC **`job_workflow_ref`** claim and
ignores `workflow_ref`. For a job inside a reusable workflow,
`job_workflow_ref` names the **reusable's** repo and path
(`scitex-ai/.github/...@main`), while PyPI's expectation is built from the
**caller's** repo plus the registered filename
(`scitex-ai/<leaf>/.github/workflows/<name>@refs/tags/vX.Y.Z`). The repo
component alone can never match, so a publish delegated to a cross-repo
reusable fails `invalid-publisher` — every release, every repo, with **no
configuration that can fix it**. `pypi/warehouse#11096` has tracked this since
2022 and is still open with no timeline.

`pypa/gh-action-pypi-publish` states the remedy directly: *"keep the job
calling `pypi-publish` in a top-level one."*

Since all 69 of this org's publish workflows use OIDC and none uses a token,
this applies universally here. The full working, sources and measurement are
in [`.old/2026-08-12/WHY-THIS-IS-HERE.md`](.old/2026-08-12/WHY-THIS-IS-HERE.md),
alongside the drafted reusable that had to be withdrawn because of it.

**The consolation is large:** the publish job never moves and the workflow
filename never changes, so adopting the gate needs **zero trusted-publisher
changes on pypi.org** — for any of the 68 repos. The half that carries the
operator's ruling (`promote`) is exactly the half that centralises cleanly.

## The containment guard

A squash merge does not fail. It silently mints a *new* SHA, so the tag's
commit leaves `main`'s history and `setuptools-scm` miscomputes the version.
Repo settings can be changed and fail silently, so the guard is an assertion at
publish time instead:

```bash
TAG_SHA="$(git rev-list -n1 "refs/tags/${TAG}")"
git fetch --no-tags --prune origin main
git merge-base --is-ancestor "${TAG_SHA}" origin/main \
  || { echo "::error::CONTAINMENT GUARD FAILED — tag not in main"; exit 1; }
```

Not contained → **abort the publish, fail red.** Works under squash *or*
fast-forward. `promote` also merges with `--merge` and re-checks containment
straight after merging, so the guard is the backstop, not the only defence.

## Adopting it — the minimal diff for an existing repo

**Do not replace a working release workflow.** 51 of the 68 have a green latest
release run; rewriting them risks a publish regression to fix a merge problem.
Adoption is two edits to the file the repo already has:

1. Add the `promote` job that calls the org reusable.
2. Add `needs: promote` to the workflow's first job (usually `build`), and
   delete whatever `gh pr create` / `gh pr merge --admin` block the repo
   currently runs inline.

```yaml
jobs:
  promote:
    uses: scitex-ai/.github/.github/workflows/promote-develop-to-main-on-tag.yml@main
    with:
      runs-on-json: '["self-hosted","Linux","X64","scitex-ci"]'
      ci-runs-on-json: '["self-hosted","Linux","X64","spartan-cpu"]'
    secrets:
      CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}

  build:
    needs: promote          # <-- the gate reaches this repo through this line
    ...                     # everything below is UNCHANGED
```

Keep the filename. Keep the publish job. Both are load-bearing for OIDC.

`workflow-templates/release.yml` is the full canonical shape for a **new**
repo, and shows where each piece goes.

### Runners

`runs-on-json` selects the promote job's runner; `ci-runs-on-json` is forwarded
to `pytest-matrix`'s own `runs_on`. A hosted-only repo passes
`'"ubuntu-latest"'` and `'["ubuntu-latest"]'` respectively. An earlier draft
listed hosted-only CI as an unresolved blocker because `uses:` cannot be an
expression — but `pytest-matrix.yml` has since gained a `runs_on` input, so
only the *runner* ever needed to be caller-selectable. That caveat is retired.

### Order of adoption — the whole risk

**Never delete a repo's release workflow before its replacement has cut a real
release for that repo.** Deleting first stops every release in the fleet. The
minimal-diff recipe above avoids this by construction: nothing is deleted, one
edge is added.

Convert in tranches with a check between them. Do not pick a repo whose latest
release run is already failing (17 of the 68 on 2026-08-12) — you would be
debugging its fault, not the gate's. Do not pick one whose `main` still
hardcodes `/data/gpfs` (7 repos on 2026-08-12).

## Ownership

`scitex-ai/.github` has **no owning agent**, which is why this sat as a draft
from 2026-07-23 to 2026-08-12. This change makes `.github` the most
load-bearing repo in the org: a defect in `promote-develop-to-main-on-tag.yml`
is a defect in every release in the fleet. **It needs a named owner.**
