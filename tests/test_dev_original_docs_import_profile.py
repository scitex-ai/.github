"""The Dev-specific reusable profile preserves full original source gates."""

import copy
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures/dev-original-docs-import-source.json"
SPECS = (
    ("rtd-sphinx-build.yml", "docs-sphinx", "sphinx"),
    ("import-smoke.yml", "import-smoke", "install-check"),
)
PINS = {
    "rtd-sphinx-build.yml": (
        "51be02f591beeeb5398b6447a7c26f0959e5487cad5b974bf62d2cf56fd51b5d",
        "36e4dac8cc5954dcd82854b51d3bd8f3f789f726f407088f504677fc0625ba6f",
    ),
    "import-smoke.yml": (
        "6b336bb6cedf7b174106f22a9cf3fd83ad15b6f0ccc08501df1b849420d17626",
        "a5018dd9cb921f2a59cb2fb9a663223c1188d3ee094f9a1e4f897a2934eb56d4",
    ),
}


def sources(name):
    row = json.loads(FIXTURE.read_text())[name]
    return (
        row,
        yaml.safe_load(row["central"]["body"]),
        yaml.safe_load(row["dev"]["body"]),
        yaml.safe_load((ROOT / ".github/workflows" / name).read_text()),
    )


class TestDevOriginalProfile(unittest.TestCase):
    def test_leaf_fixture_contains_the_exact_actual_central_candidate_bodies(self):
        fixture = json.loads(FIXTURE.read_text())
        observed = []
        for name, _, _ in SPECS:
            body = (ROOT / ".github/workflows" / name).read_bytes()
            candidate = fixture[name]["candidate"]
            observed.append(
                (
                    body.decode() == candidate["body"],
                    hashlib.sha256(body).hexdigest() == candidate["sha256"],
                    len(body) == candidate["bytes"],
                )
            )
        admission = (ROOT / ".github/workflows/runner-admission.yml").read_bytes()
        self.assertEqual(observed, [(True, True, True)] * 2)
        self.assertEqual(
            (admission.decode(), hashlib.sha256(admission).hexdigest()),
            (
                fixture["runner_admission"]["body"],
                fixture["runner_admission"]["sha256"],
            ),
        )

    def test_complete_source_fixture_matches_exact_accepted_git_objects(self):
        observed = {}
        for name, _, _ in SPECS:
            row, _, _, _ = sources(name)
            for kind in ("central", "dev"):
                pin = row[kind]
                body = pin["body"].encode()
                observed[(name, kind)] = (
                    hashlib.sha256(body).hexdigest(),
                    len(body) == pin["bytes"],
                    hashlib.sha1(
                        b"blob " + str(len(body)).encode() + b"\0" + body
                    ).hexdigest()
                    == pin["git_blob"],
                )
        self.assertEqual(
            observed,
            {
                (name, kind): (PINS[name][index], True, True)
                for name, _, _ in SPECS
                for index, kind in enumerate(("central", "dev"))
            },
        )

    def test_default_profile_preserves_every_original_shared_job_and_declaration(self):
        restored = []
        for name, standard, leaf in SPECS:
            _, original, _, candidate = sources(name)
            value = copy.deepcopy(candidate)
            events = value.get("on", value.get(True))
            events["workflow_call"]["inputs"].pop("dev_original_commands")
            if name == "rtd-sphinx-build.yml":
                events["workflow_call"]["inputs"].pop("bundle_dir")
                # Bundle publication evolved from a direct protected-branch
                # push to a reviewable PR; compare the unchanged build-only
                # contract and jobs against the captured original source.
                original_events = original.get("on", original.get(True))
                events["workflow_call"]["inputs"]["upload_artifact"]["description"] = (
                    original_events["workflow_call"]["inputs"]["upload_artifact"][
                        "description"
                    ]
                )
                upload = next(
                    step
                    for step in value["jobs"][standard]["steps"]
                    if step.get("name") == "Upload built HTML for the caller to publish"
                )
                upload["if"] = (
                    "${{ inputs.upload_artifact && steps.build.outputs.html_dir != '' }}"
                )
                value["jobs"].pop("publish-sphinx-bundle")
            value["jobs"].pop("dev-original-" + leaf)
            value["jobs"][standard].pop("if")
            restored.append(value == original)
        self.assertEqual(restored, [True, True])

    def test_profile_is_typed_default_off_and_shared_jobs_select_default(self):
        observed = []
        for name, standard, _ in SPECS:
            _, _, _, candidate = sources(name)
            declaration = candidate.get("on", candidate.get(True))["workflow_call"][
                "inputs"
            ]["dev_original_commands"]
            observed.append(
                (
                    declaration["type"],
                    declaration["required"],
                    declaration["default"],
                    candidate["jobs"][standard]["if"],
                )
            )
        self.assertEqual(
            observed,
            [("boolean", False, False, "${{ !inputs.dev_original_commands }}")] * 2,
        )

    def test_whole_original_dev_jobs_and_all_steps_remain_exact(self):
        preserved = []
        for name, standard, leaf in SPECS:
            _, original_shared, baseline, candidate = sources(name)
            original = baseline["jobs"][leaf]
            value = copy.deepcopy(candidate["jobs"]["dev-original-" + leaf])
            owner = value["steps"].pop(3)
            member = value["steps"].pop(2)
            member_ok = member == original_shared["jobs"][standard]["steps"][1]
            fork = value["steps"].pop(1)
            fork_ok = fork == original_shared["jobs"][standard]["steps"][0]
            routed_ok = value["runs-on"] == original_shared["jobs"][standard]["runs-on"]
            value["runs-on"] = original["runs-on"]
            owner_ok = owner == {
                "name": "Require the original Dev caller",
                "env": {"CALLER_REPOSITORY": "${{ github.repository }}"},
                "run": 'test "$CALLER_REPOSITORY" = scitex-ai/scitex-dev',
            }
            expected_if = (
                "inputs.dev_original_commands && (" + original["if"] + ")"
                if "if" in original
                else "inputs.dev_original_commands"
            )
            selected = value.pop("if") == expected_if
            if "if" in original:
                value["if"] = original["if"]
            if "name" not in original:
                value.pop("name")
            preserved.append(
                (owner_ok, member_ok, fork_ok, routed_ok, selected, value == original)
            )
        self.assertEqual(preserved, [(True, True, True, True, True, True)] * 2)

    def test_original_native_first_guard_runs_actual_hosted_and_native_outcomes(self):
        observed = []
        for name, _, leaf in SPECS:
            _, _, _, candidate = sources(name)
            script = candidate["jobs"]["dev-original-" + leaf]["steps"][0]["run"]
            for environment, authorized, destination, expected in (
                (
                    "self-hosted",
                    "true",
                    '{"group":"Organization","labels":["self-hosted","Linux","X64","scitex-org-cpu"]}',
                    0,
                ),
                (
                    "self-hosted",
                    "false",
                    '{"group":"Organization","labels":["self-hosted","Linux","X64","scitex-org-cpu"]}',
                    1,
                ),
                (
                    "self-hosted",
                    "true",
                    '{"group":"Other","labels":["self-hosted","Linux","X64","scitex-org-cpu"]}',
                    1,
                ),
                ("github-hosted", "false", '["ubuntu-latest"]', 0),
                ("unknown", "true", '["ubuntu-latest"]', 1),
            ):
                env = {
                    "PATH": "/usr/bin:/bin",
                    "RUNNER_ENVIRONMENT": environment,
                    "NATIVE_AUTHORIZED": authorized,
                    "ADMISSION_REASON": "confirmed-organization-members",
                    "ADMISSION_RUNS_ON": destination,
                }
                child = subprocess.run(
                    ["/bin/sh", "-c", script],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                observed.append((child.returncode == expected, environment))
        self.assertEqual(
            observed,
            [
                (True, environment)
                for _ in SPECS
                for environment in (
                    "self-hosted",
                    "self-hosted",
                    "self-hosted",
                    "github-hosted",
                    "unknown",
                )
            ],
        )

    def test_source_profile_gate_actually_refuses_foreign_repositories(self):
        observed = []
        for name, _, leaf in SPECS:
            _, _, _, candidate = sources(name)
            script = candidate["jobs"]["dev-original-" + leaf]["steps"][3]["run"]
            for repository in ("scitex-ai/scitex-dev", "scitex-ai/scitex-storage", ""):
                child = subprocess.run(
                    ["/bin/sh", "-c", script],
                    env={"PATH": "/usr/bin:/bin", "CALLER_REPOSITORY": repository},
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
                observed.append(child.returncode)
        self.assertEqual(observed, [0, 1, 1] * 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
