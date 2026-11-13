# Dev original docs through a reviewable PR

The Dev-specific original Sphinx profile supports the existing `bundle_dir`
option. A caller selects `dev_original_commands: true`, sets `bundle_dir` to
`src/scitex_dev/_sphinx_html` and can select an `artifact_name`. The builder
retains its original installation, Sphinx, runner, loop and contents-only write
contracts. On a successful develop push it stages the complete HTML for the
separate publisher job. No new secret is inherited.

The publisher selects the successful producer and refuses non-push events,
cancellation and failed or skipped selected builds. Dev's new PR phase has an
initial five-minute budget; the builder's existing budget is unchanged. The
publisher checks that the original source still heads develop before and after
preparation. It opens a draft on a source/run-specific branch, with the original
refresh commit/title marker so normal merging retains the loop convention.
It never merges the draft. A changed base makes the phase fail; review any
created draft as incomplete rather than adopting stale output.

Non-Dev callers retain their generic branch, title, permissions and job budget.
An unconfigured Dev caller retains the legacy direct-push path until explicit
adoption; the new controller alone does not close its known GH006 delivery
failure. Source qualification, consumer adoption and actual draft-PR creation
are separate checks. Inspect actual downstream CI, source binding, generated
content/version and branch protection before merging. Creating a PR alone does
not establish that those checks ran or that a package/host serves the result.

Controls execute the actual selection expressions and source guards with
platform-context/REST transport fixtures. Historical snapshots stay frozen;
all original builder commands and its contents-only permission are compared
against the captured producer. Original hosted CI and actual consumer delivery
remain required beyond these scoped controls.
