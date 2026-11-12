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

### Pytest aggregate result

The `pytest aggregate gate` runs on `ubuntu-latest` with no token permissions.
It waits for runner admission and the selected test matrix, then accepts only
a successful matrix result. This metadata-only step does not check out the
caller or consume a native test runner. Test execution retains its existing
runner admission, compatibility matrix, verified-image and resource controls.

### Organization job uv cache

`organization-job.yml` gives setup-uv an explicit cache directory under
`runner.temp`. Restore, caller tools and post-job pruning use that directory
rather than an inherited operator cache. Cache restore/save and pruning stay
enabled. This cache policy applies to the organization-job reusable workflow.

The self-test workflow calls the reusable job and checks the exported cache
path, uv's resolved path and a real Ruff invocation. Its final job result also
covers setup-uv's post-job cleanup.

### Job-owned pytest environments (opt-in)

`pytest-matrix.yml` accepts `job_owned_environment: true`. It creates the
environment under `RUNNER_TEMP` and leaves a `.venv` symlink in the caller
checkout, preserving the existing install, test and wheel commands. The runner's
temporary-directory lifecycle removes that environment after the job. The
default remains `false`, retaining the existing checkout environment behavior.

```yaml
jobs:
  pytest-matrix:
    uses: scitex-ai/.github/.github/workflows/pytest-matrix.yml@main
    with:
      job_owned_environment: true
```

An opting-in leaf must ignore the `.venv` path, which covers its symlink;
a directory-only `.venv/` rule does not. Setup refuses existing `.venv` entries,
redirected or linked Git checkouts, and scratch inside the checkout. It leaves
source ignore rules and Git metadata unchanged. Existing runner workspaces,
caches and environments are not cleaned by this option.

The new controls execute the source staging step and original seeded-venv
command with real Git, uv and Python, including job-end removal and refusal
cases. Self-tests run them on hosted CI and through the admitted organization
job. This qualifies the mechanism; each leaf still needs its own required CI
before adopting the option. Preserve needed diagnostics through that job's
artifact policy because the environment itself is temporary.

### Storage native integration dependencies

`fd-fclones-integration.yml` installs fd and fclones before running Storage's
full test suite. On shared hosts, APT setup retries only exit status 100 with
the explicit `E: Could not get lock` diagnostic, waiting up to 120 seconds for
the owner to release its lock. Other errors and an exhausted lock-wait budget
retain their original failure status. The workflow does not remove locks or
terminate their owners; an installation that acquires its lock runs normally.
The fclones download uses a unique file under `RUNNER_TEMP`, removed on exit.
Admission, the declared package profile and the full pytest command are unchanged.

### PostgreSQL for tests

Callers that need a disposable PostgreSQL 16 database pass `postgres: true` to
`pytest-matrix.yml`. Each matrix job publishes container port 5432 on a free host
port and exports `SCITEX_STORE_DSN` using its assigned mapping. Missing or invalid
port mappings fail before installation or tests. Callers that leave the input
false start no database and receive no DSN export from this workflow.

`release-publish.yml` uses the same per-job port allocation for its disposable
database. It exports the DSN to `store_dsn_var` (`SCITEX_STORE_DSN` by default)
with the service's declared fixture credentials. Setting `postgres: false`
skips that service and handoff.

The jobs run directly on their runner, so the DSN uses `127.0.0.1`, not the
container service name. Free-port allocation allows concurrent jobs on a shared
runner host without reserving its PostgreSQL port. See
[GitHub's service-container networking documentation](https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers).

### Release test profiles

`release-publish.yml` installs one local `test_extras` profile, defaulting to
`.[all,dev]`. Callers may explicitly select another profile, such as `.[dev]`
or `.`, rather than supplying a fallback list. Requested extras must be
declared in `project.optional-dependencies`; an invalid profile or failed
install stops the job before pytest. The TOML parser uses the standard library
on Python 3.11+ and an explicit `tomli` compatibility dependency on older Python.

`extra_test_deps` remains a whitespace-separated list of additional requirements.
The job passes each requirement as a literal argument, preserving constraints
such as `pytest-xdist>=3.0.0`.

## CLA attribution completeness

The trusted helper binds attribution to immutable PR base/head SHAs. If the
GraphQL commit connection ends before its declared total, it can collect the
complete set through explicitly paginated REST comparison and canonical GraphQL
commit objects. The original GraphQL first 100 retain their exact order and
metadata; REST ordering cannot replace the pinned action’s coverage set.

Fetching every commit does not establish CLA admission. The unchanged pinned
action must cover every contributor identity; late, unlinked, conflicting or
otherwise unproven identities still refuse. No signature or exemption is created
by the fallback. Both attribution phases retain the 2,000-commit, 48-request,
30-second budget and four-second request bounds, with final PR and protected-base
binding checks. Consumers execute only the length/hash-verified organization
helper at its immutable commit, never a PR source checkout.

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

## Fork guard

Every job here that is self-hosted **and** runs `actions/checkout` carries
two layers that keep fork-authored code off self-hosted infrastructure:

1. **Routing.** The job's `runs-on` is a conditional expression: a
   fork-authored PR resolves to `ubuntu-latest`, unconditionally, regardless
   of what the caller passed for `inputs.runs_on` / `inputs.runs-on-json`.
   Every other run — including self-hosted ones — is unaffected.
2. **A backstop guard step**, first, ahead of `actions/checkout`, that fires
   only if a fork PR somehow still lands on a self-hosted runner anyway:

```yaml
- name: Refuse to run fork-authored code on self-hosted infrastructure
  if: >-
    github.event_name == 'pull_request' &&
    github.event.pull_request.head.repo.full_name != github.repository &&
    runner.environment == 'self-hosted'
```

Which jobs need this is **derived, not listed** — `tests/test_fork_guard.py`
parses every workflow, selects the jobs matching the routable/self-hosted
predicate, and requires both the routing expression and the guard step on
exactly them. Add a self-hosted workflow that checks out a PR and those tests
go red on your change. `cla.yml` is excluded because its jobs check out
nothing, not by an exemption.

### Why route rather than only refuse

Two operator mandates originally constrained this, and pointed in opposite
directions:

| date | mandate |
|---|---|
| 2026-07-14 | 「PR用のテストとgithub側のランナーというのは本当にもう一切使わないでください…強制です、例外なしです」 — never use GitHub-hosted runners, no exceptions. Enforced as PS-169. |
| 2026-07-30 | 「大学の資源を外部の人にも使わせる形になったら一発でアウト」 — external people using university resources is unacceptable. |

The first was **repealed twice** since (2026-07-31: "hosted is the DEFAULT
CHOICE for new work... not a blanket policy"; 2026-08-05, constitution:
hosted is "a reasonable fallback") — see `pytest-matrix.yml`'s own `runs_on`
input description and the runner-default tests in `tests/test_fork_guard.py`
for the same correction applied there. The second mandate never moved and
still holds in full: nothing fork-authored may execute on university /
self-hosted hardware.

With only the second mandate standing, unconditionally REFUSING every fork
PR was no longer necessary. It also stopped being harmless: measured
2026-08-31 on scitex-ai/scitex-io, two CLA-signed, waiting external
contributions (#166, #164) died in 3-8 seconds on this exact guard, on every
job, having never run a single test — even though `ubuntu-latest` (which
satisfies the surviving mandate on its own) was sitting right there, unused.

So a fork-authored PR is now **routed** to `ubuntu-latest` instead of
refused. These jobs run **bare** on shared University of Melbourne HPC nodes
when self-hosted: no container, no overlay, two concurrent jobs sharing one
`$HOME` (measured by scitex-hpc on the CI supervisor allocation, job
28161762, spartan-bm062). So `uv pip install -e .` would execute a pull
request's own build-backend hooks on university hardware, and
`rtd-sphinx-build` would execute the fork's `conf.py` as plain Python — which
is exactly what the routing above now prevents by construction, and what the
backstop guard step still refuses, loudly, if it is ever wrong. The guard
**fails** rather than skipping: a skipped job's check can be reported as
successful to branch protection, which is a red that looks green.

### Organization membership and workflow access

The 2026-10-03 operator mandate limits the compute02/03/04 company runner
pool to organization members. Each of the seven reusable workflows first
calls `runner-admission.yml` at the same source revision on a GitHub-hosted
runner. It checks the original actor and the triggering actor separately;
same-repository pull requests also require the PR author to qualify. Only
an anonymous public-membership response of HTTP 204 confirms membership.
Forks, private or unavailable membership, unsupported events, and failed
checks receive hosted CI. A member's rerun cannot authorize an external
original actor. This adds no membership token or secret authority.

Workflow source alone cannot prevent a caller from declaring its own
native job. The organization runner group must also restrict workflow
access to the seven reviewed reusable workflows at their full commit SHA.
GitHub applies that restriction to jobs directly defined in each selected
workflow: the pytest workflow called by promotion needs its own entry.
The hosted admission workflow needs no company runner access. Common
labels and a fork-run approval do not grant membership authorization.

Source publication and the group API readback are separate checks. Do not
claim enforcement until the group reports the exact seven selected
revisions and `restricted_to_workflows: true`. Keep public contributions
on hosted runners when membership or source qualification is unknown.
See [GitHub runner-group access](https://docs.github.com/en/enterprise-cloud@latest/actions/how-tos/manage-runners/self-hosted-runners/manage-access)
and [public membership responses](https://docs.github.com/en/rest/orgs/members#check-public-organization-membership-for-a-user).

## Self-hosted runner npm-cache preflight

Jobs that use npm on a self-hosted org runner should run the central preflight
before `setup-node`, `npm`, or checkout of same-repo code. On self-hosted
pull-request jobs it belongs immediately after the existing fork-guard step,
which must remain first:

```yaml
- name: Validate the runner npm cache
  uses: scitex-ai/.github/.github/actions/runner-npm-cache-preflight@93e7732c73b76b2ca81e8200f521fd88d00df6cb
```

The full 40-character commit is intentional: this action runs before checkout
on a privileged self-hosted runner, so callers must review and pin an immutable
commit rather than trust an unprotected mutable branch such as `main`.

The action runs `scripts/runner-npm-cache-preflight.sh`. Multiple runner
services share `$HOME`, so the script serializes inspection and repair with a
per-user host lock that is opened without following links or truncating an
existing file. An existing owned real directory is normalized in place to mode
0755 and checked for write access. A symlink or non-directory artifact owned by
the runner user is moved, without dereferencing it or replacing prior evidence,
to `$HOME/.npm.quarantine-<UTC>[.<collision>]`; then an owned real directory is
created atomically. Unexpected ownership is a hard failure, not an attempted
`sudo` or recursive `chown`.

For runners configured with GitHub's job-started hook, the same script may be
used directly as `ACTIONS_RUNNER_HOOK_JOB_STARTED` from a trusted, pinned local
checkout. Do not point a runner hook at a script from the repository under
test. The composite action remains necessary until that host-level hook is
explicitly deployed to every runner service.

## Branches

- `main` — stable, what callers reference (`@main`).
- `develop` — working branch for changes to these workflows, promoted to
  `main` the same way as the rest of the ecosystem.


## Required Storage browser regressions

The native fd/fclones workflow installs the same `.[dev]` dependencies into a
fresh virtual environment under `RUNNER_TEMP`. Its Playwright installs the
matching Chromium headless shell into a separate job-owned directory. A launch
preflight sets `SCITEX_STORAGE_TEST_CHROMIUM` explicitly, so a missing executable
fails the browser regressions instead of skipping them. The runner cleans its
temporary directory after the job.

Admission rules, the native dependency installer, the full pytest command and
test deadlines are unchanged. Matching prerequisites do not establish the cause
of every intermittent screenshot protocol failure.
