# IO native release profile

`leaf-release-sif.yml` dispatches fixed Writer and IO repository profiles. The
Writer compatibility workflow forwards its original operation, commit, and tag
inputs; its qualified image, runtime, source closure and complete suite remain
unchanged. The shared byte gate checks the complete image and native runtime,
not merely their presence or mutable filenames.

IO is currently unregistered. Its dispatcher refuses release execution until
its actual leaf drivers and native image execution have been qualified. A
valid-looking image record or successful generic PR tests do not qualify that
profile. Registration requires the immutable image/runtime identities, the
complete leaf helper closure, and real full all/dev-suite execution using owned
state and temporary contexts. Unknown repositories, fork events, nonmembers,
arbitrary operations, floating source commits and malformed tags refuse.

The intended IO leaf caller resolves an existing tag against protected main
before native test/build execution. Publication retains a separate hosted OIDC
boundary after complete wheel/sdist source and metadata verification. No IO tag
or publication is authorized by adding this source-only dispatcher.
