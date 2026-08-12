# `pypi-publish-and-github-release-on-tag.yml` — displaced 2026-08-12

This file was drafted as **reusable workflow B**: a cross-repo
`on: workflow_call` reusable in `scitex-ai/.github` that 68 leaf repos would
delegate their build + publish + GitHub-Release pipeline to.

**It cannot work, and it is displaced here rather than deleted so the
containment guard and the two publish-backend bodies stay available to the
follow-up that reworks them into a supported shape.**

## Why it cannot work

Every one of the 68 tag-triggered publish workflows in this org publishes to
PyPI with **OIDC Trusted Publishing** — measured 2026-08-12 across all of
them: 69 workflow files, 69 using `id-token: write`, **zero** using a
`PYPI_API_TOKEN` or any other token secret. So the publish step's auth is
entirely a function of the OIDC claims GitHub mints for the job.

PyPI validates the **`job_workflow_ref`** claim, and explicitly ignores
`workflow_ref`. In `warehouse/oidc/models/github.py`, `workflow_ref` sits in
`__unchecked_claims__` while `job_workflow_ref` is in
`__required_verifiable_claims__`, and the publisher lookup keys on the
filename extracted from `job_workflow_ref`.

GitHub sets those two claims differently for a reusable call
([OIDC with reusable workflows][gh-oidc]): the token carries "the standard
claims that contain information about the **calling** workflow, and will also
include a custom claim called `job_workflow_ref` that contains information
about the **called** workflow."

So for leaf repo `scitex-ai/scitex-foo` calling this file:

| claim | value |
|---|---|
| `repository` | `scitex-ai/scitex-foo` |
| `workflow_ref` | `scitex-ai/scitex-foo/.github/workflows/<caller>.yml@refs/tags/v1.2.3` — **ignored** |
| `job_workflow_ref` | `scitex-ai/.github/.github/workflows/pypi-publish-and-github-release-on-tag.yml@main` — **checked** |

PyPI builds its expectation as
`<caller repo>/.github/workflows/<configured filename>@<caller ref>`. The
actual claim names a **different repository** (`scitex-ai/.github`) and a
**different ref** (`main`, not the tag). No value of the configured filename
can ever match — the repo component alone makes it unsatisfiable. Every
release through this reusable would fail `invalid-publisher`.

This is not a policy that could be waived per-repo. It is structural.

## Upstream says the same thing, and says what to do instead

[`pypa/gh-action-pypi-publish`][action] README, verbatim:

> Trusted publishing cannot be used from within a reusable workflow at this
> time. It is recommended to instead create a non-reusable workflow that
> contains a job calling your reusable workflow, and then do the trusted
> publishing step from a separate job within that non-reusable workflow.
>
> […] The current recommendation is to put everything else you want into a
> reusable workflow but **keep the job calling `pypi-publish` in a top-level
> one**.

[docs.pypi.org troubleshooting][docs]: "Reusable workflows cannot currently be
used as the workflow in a Trusted Publisher. This is a practical limitation,
and is being tracked in warehouse#11096."

**warehouse#11096 is still OPEN** — filed 2022-04-01, last active 2026-05-02,
no timeline. Do not plan around it landing.

## What replaced it

`promote-develop-to-main-on-tag.yml` (**reusable A**) — which is unaffected,
because it performs no OIDC publish at all. It runs CI and merges with
`github.token`, so it centralises fine.

That split is fortunate rather than lucky: **A is the half that carries the
operator's ruling**, and A is exactly the half that is centralisable.

(Correction, PR #31: this paragraph first cited "45 repos running
`gh pr merge --admin` on tag push with no greenness test" as the measured
hazard. All 45 are in fact already gated on a test job via `needs:`; the
number came from a keyword grep rather than a reachability check. A is a
consolidation of those 45 gates, not a repair of them.)

The publish half stays in each leaf repo's top-level workflow — which is both
what upstream recommends and, conveniently, a **zero-diff** outcome for the
publish path: adopting the gate does not touch the publish job, does not
change the workflow filename, and therefore does not require re-registering a
single trusted publisher on pypi.org.

[gh-oidc]: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows
[action]: https://github.com/pypa/gh-action-pypi-publish
[docs]: https://docs.pypi.org/trusted-publishers/troubleshooting/
