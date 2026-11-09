# Passive CI diagnostics pilot

The first receiver is this repository's original workflow-contract test job.
Its test command, dependency installation and test exit remain the originals.
The observer adds no RAM cap, timeout, runner, dependency or scheduling rule.
Results are attached to the same run as a Job Summary and the
`passive-ci-observation` JSON artifact. Rollout to common leaf jobs follows an
actual useful pilot result and source review.

The artifact records the repository, source SHA, run and attempt, logical job
key, runner, original exit or signal, actual child wait, elapsed time, sampled
descendant RSS, wait4 maximum RSS, and existing cgroup counters before/after.
Each sample also records bounded CPU/I/O pressure reads from `/proc/pressure`,
the sampled descendants' own cumulative CPU ticks, and counts of their kernel
process states. The artifact records the clock tick frequency for those counters.
Command arguments, environment, process command lines and original test output
are excluded. The original stdout/stderr stay in the original job log.

Sampled descendant RSS is a sum of per-process RSS, including resident file and
shared mappings. Shared mappings can be counted more than once; short-lived,
escaped or reparented processes can be missed. It is not distinct or charged
job memory. wait4 maximum RSS is not a sum of
concurrent process usage. Current and peak charged memory are shared runner
cgroup observations, potentially including other work and previous jobs.
OOM event deltas retain that scope: they do not prove that this command was an
OOM victim. SIGKILL alone does not prove OOM. Missing evidence is `unknown`.
Queue duration and a numeric GitHub API job ID are not observed by this wrapper.
An optional `CI_MEMORY_REQUEST_MIB` is a recorded declaration, never enforced.
Host pressure is shared across work on the host; it cannot establish which
command caused a stall or why a particular child timed out. Descendant CPU ticks
are not utilization percentages: membership changes as children exit, and
short-lived processes may be missed. State counts are point-in-time observations,
not a measured duration in that state. Missing, empty or oversized pressure
reads remain `unknown`, rather than zero. These observations add no resource
limits and do not change any command or test deadline.
The metric definitions follow the kernel's [pressure interface](https://docs.kernel.org/accounting/psi.html)
and [process stat fields](https://docs.kernel.org/filesystems/proc.html#process-specific-subdirectories).
An externally requested TERM/INT is forwarded to this command's owned process
group, with a two-second cancellation grace and actual direct-child wait.
External cancellation and its cleanup signal are recorded separately from OOM.
No normal execution timeout is added. Artifact-upload failure warns without
changing the original test verdict.

Agents investigating a failed run should read the job result and summary,
download the JSON artifact, and then read the original failed-step log when
the summary does not establish the cause. For the exact repository/run:

```bash
gh run view RUN_ID --repo OWNER/REPO --json conclusion,jobs,headSha
gh run download RUN_ID --repo OWNER/REPO --name passive-ci-observation --dir OWNED_DIAGNOSTIC_DIR
gh run view RUN_ID --repo OWNER/REPO --log-failed
```

Retain the exact attempt, original error and metric scope in the task evidence.
Do not turn absent observations into zero, infer OOM from an unexplained signal,
or declare a release ready from this pilot. Summary-only consumption by every
fleet agent is not established; adoption requires an actual consumer check.
