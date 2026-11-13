# Dev original docs through a reviewed branch

The Dev-specific original Sphinx profile supports the existing `bundle_dir`
option. A caller selects `dev_original_commands: true`, sets `bundle_dir` to
`src/scitex_dev/_sphinx_html` and can select an `artifact_name`. The builder
retains its original installation, Sphinx, runner, loop and contents-only write
contracts. On a successful develop push it stages the HTML for the separate
publisher job. No new secret is inherited.

The publisher selects the successful producer and refuses cancellation and
failed or skipped selected builds. Dev's publication phase has an initial
five-minute budget; the original builder budget is unchanged. It checks the
develop source before and after preparation, refuses an existing remote branch
or foreign staged index, and pushes a fresh source/run-specific branch with an
ordinary Git push. Commit and push failures emit no success outputs. The generic
PR action, whose update implementation uses force-with-lease, is not selected
for Dev. Generic callers retain that existing action and their behavior.

A read-only API step checks the actual pushed ref and reports its source, head
and compare link in the job summary. It does not create a bot-authored PR.
The current Dev native CI admission refuses the Actions bot identity; approving
that bot's workflow does not turn it into an admitted original actor. A
maintainer accepted by the existing admission policy reviews the artifact and
opens the PR under their authorized identity. An agent in that maintainer's
session can perform this handoff. Keep the original refresh commit/title marker
`docs(sphinx_html): refresh from CI build` so a normal merge retains the loop
convention. The controller never merges the branch or changes runner admission.

Before opening or merging, check that develop still matches the recorded source,
verify the actual artifact digest, rendered content and generated tree, and
inspect the real downstream checks. A changed base refuses the publication
phase; any staged branch remains incomplete until reviewed. Source qualification,
consumer adoption, branch staging and installed/public delivery are separate
facts. The opt-in controller alone does not close an unconfigured caller's legacy
GH006 failure. Actual Git controls cover fresh/no-change output, existing refs,
foreign index/source state, missing remotes and rejected commit/push hooks.
GitHub transport fixtures execute the actual review/source guards. Full original
CI and actual consumer qualification remain required beyond scoped controls.
