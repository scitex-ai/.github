# Documentation publishing

The package repository owns its Sphinx sources. The organization owns the
build and publication workflows. Read the Docs and the SciTeX Docs app are
two views of those sources; neither is a second authoring location.

| Destination | Published artifact | Update path |
| --- | --- | --- |
| Read the Docs | Sphinx built from the requested branch | `rtd-publish.yml` triggers a build, checks its exact commit and success, then checks public HTML contents. |
| `scitex.ai/docs/` | Installed packages' `_sphinx_html` bundles | `rtd-sphinx-build.yml` builds once and opens a bundle PR. The reviewed package release reaches production through the normal deployment profile. |
| `compute-03-net.scitex.ai/docs/` | Development profile's package bundles | The same bundle and resolver, using sources admitted by the development deployment gate. |

The `/docs/` alias opens `/apps/docs/`. Package pages appear in the Docs app's
package navigation. Raw pages and assets are served under
`/apps/docs/sphinx/<package>/<page>`. A Read the Docs update alone does not
update an installed production package.

## Repository caller

Keep the existing required build job ID. Pin both reusable workflows to a
reviewed immutable organization commit. The build job uses
`rtd-sphinx-build.yml` with `required: true`, `fail_on_warning: true`, the same
Python version as `.readthedocs.yaml`, and `bundle_dir: src/<module>/_sphinx_html`.
Give this job `contents: write` and `pull-requests: write` for its existing
push-only bundle PR publisher. Pull requests only build.

Add a publication job that depends on that build, calls `rtd-publish.yml`, and
runs only on pushes or manual dispatches to the project's documentation branch.
Pass `project`, `version` (usually `latest`), a representative `page`, and
`expected_text`. Pass only the explicitly named `RTD_TOKEN` secret. Publication
does not check out repository code or execute Sphinx configuration with that
token. Its receipt records the build ID, exact source commit, and checked URL.

Configure the existing RTD project's repository and default branch before
adoption. `latest` must track the caller branch; a completed build of another
commit fails, even if it succeeded. A newer branch push can legitimately race
the RTD checkout: rerun from the current head rather than accepting mismatched
source. Stable documentation follows normal release tags; do not move a
published tag to update documentation.

Store the RTD token as a selected-repository organization secret. Do not copy
tokens into workflow files, forward all secrets, or send publication credentials
to pull-request jobs. Existing GitHub/RTD webhooks may coexist, but are not
required by this explicit publication path.

## Hosting checks

After the normal package/profile update, check the actual Docs app page and
its raw HTML and assets. Confirm meaningful content, diagrams, page navigation,
and mobile layout. HTTP 200 with a fallback page is insufficient. An older
production package may correctly lack a page present in development; report
that difference until its deployment completes.
