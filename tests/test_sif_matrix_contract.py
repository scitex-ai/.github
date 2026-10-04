"""Exercise exact inline SIF policy and real owned file boundaries without CI."""

import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci-sif-matrix.yml"
DEV = "scitex-ai/scitex-dev"
SAC = "scitex-ai/scitex-agent-container"


def blocks(marker):
    result = []
    active = None
    for line in WORKFLOW.read_text().splitlines():
        if line.strip() == "// BEGIN " + marker:
            active = []
        elif line.strip() == "// END " + marker:
            result.append("\n".join(active))
            active = None
        elif active is not None:
            if not line.startswith("            "):
                raise ValueError("inline script indentation changed")
            active.append(line[12:])
    return result


def node(program, payload):
    child = subprocess.run(
        ["node", "-e", program, json.dumps(payload)],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
    )
    if child.returncode:
        raise RuntimeError("pure node fixture failed: " + child.stderr)
    return json.loads(child.stdout)


def contract(
    operation,
    repository=DEV,
    event="pull_request",
    native=True,
    registry=None,
    suite="matrix",
):
    program = (
        blocks("SIF_CONTRACT")[0]
        + """
const input = JSON.parse(process.argv[1]);
try {
  const value = input.operation === 'select'
    ? profileSelection(input.repository, input.event, input.suite)
    : planFor(input.repository, input.event, input.native, input.registry || PROFILES, input.suite);
  console.log(JSON.stringify({ok: true, value}));
} catch (error) { console.log(JSON.stringify({ok: false, reason: error.message})); }
"""
    )
    return node(
        program,
        {
            "operation": operation,
            "repository": repository,
            "event": event,
            "native": native,
            "registry": registry,
            "suite": suite,
        },
    )


def image(postgres="16.15", pg=False, delivery=True):
    capabilities = {"postgres": postgres}
    if not pg:
        capabilities.update({"3.11": "3.11.16", "3.12": "3.12.14", "3.13": "3.13.15"})
    return {
        "sha256": "a" * 64,
        "bytes": 16,
        "producer_revision": "b" * 40,
        "source_manifest_sha256": "c" * 64,
        "public_inventory_sha256": "d" * 64,
        "delivery": {
            "url": "https://github.com/scitex-ai/scitex-dev/releases/download/v1/ci.sif",
            "release_id": 1,
            "asset_id": 2,
            "redirect_hosts": ["github.com", "release-assets.githubusercontent.com"],
        }
        if delivery
        else None,
        "capabilities": capabilities,
        "native_paths": ["/public/ci.sif"],
    }


def registry():
    runtime = {
        "path": "/usr/bin/apptainer",
        "sha256": "a" * 64,
        "bytes": 20,
        "qualification_sha256": "b" * 64,
        "user_namespace": True,
        "sif_mount": True,
        "hosted_delivery_sha256": "c" * 64,
    }
    sources = {
        "dev": [
            "exec-in-sif.sh",
            "run-in-sif.sh",
            "release-context.sh",
            "verify-postgres-capability.py",
        ],
        "sac": [
            "exec-in-sif.sh",
            "run-in-sif.sh",
            "tmpdir-lib.sh",
            "clean-tmpdir.sh",
        ],
    }
    result = {}
    for repo, name in [(DEV, "dev"), (SAC, "sac")]:
        result[repo] = {
            "id": name,
            "pgKind": "embedded" if name == "dev" else "separate",
            "pgBin": "/usr/lib/postgresql/16/bin" if name == "dev" else None,
            "pgVersion": "16.15" if name == "dev" else "18",
            "image": image(),
            "pgImage": image("18.4", pg=True) if name == "sac" else None,
            "nativeRuntime": copy.deepcopy(runtime),
            "hostedRuntime": copy.deepcopy(runtime),
            "leafSources": {".github/ci/" + path: "e" * 64 for path in sources[name]},
        }
    return result


class SIFPolicyTests(unittest.TestCase):
    def test_unknown_suite_refuses_before_source_or_image_use(self):
        # Arrange
        # Act
        result = contract("plan", suite="reduced")

        # Assert
        assert result["reason"] == "suite-unsupported"

    def test_nightly_schedule_keeps_only_middle_version(self):
        # Arrange
        # Act
        result = contract("select", repository=SAC, event="schedule", suite="nightly")

        # Assert
        assert result["value"] == {
            "profile": "sac",
            "suite": "nightly",
            "versions": ["3.12"],
        }

    def test_nightly_dispatch_keeps_only_middle_version(self):
        # Arrange
        # Act
        result = contract(
            "select", repository=SAC, event="workflow_dispatch", suite="nightly"
        )

        # Assert
        assert result["value"]["versions"] == ["3.12"]

    def test_path_scoped_nightly_pr_remains_supported(self):
        # Arrange
        # Act
        result = contract("select", repository=SAC, suite="nightly")

        # Assert
        assert result["value"]["versions"] == ["3.12"]

    def test_dev_cannot_request_sac_nightly_contract(self):
        # Arrange
        # Act
        result = contract("select", suite="nightly")

        # Assert
        assert result["reason"] == "nightly-profile-unsupported"

    def test_nightly_push_refuses_unsupported_trigger(self):
        # Arrange
        # Act
        result = contract("select", repository=SAC, event="push", suite="nightly")

        # Assert
        assert result["reason"] == "nightly-event-unsupported"

    def test_native_admission_cannot_move_nightly_to_pool(self):
        # Arrange
        # Act
        result = contract("plan", repository=SAC, registry=registry(), suite="nightly")

        # Assert
        assert result["reason"] == "nightly-native-refused"

    def test_nightly_requires_genuine_hosted_delivery(self):
        # Arrange
        records = registry()
        records[SAC]["image"]["delivery"] = None

        # Act
        result = contract(
            "plan", repository=SAC, native=False, registry=records, suite="nightly"
        )

        # Assert
        assert result["reason"] == "hosted-image-delivery-unqualified"

    def test_registered_nightly_still_uses_same_pg18_full_leaf_plan(self):
        # Arrange
        # Act
        result = contract(
            "plan", repository=SAC, native=False, registry=registry(), suite="nightly"
        )

        # Assert
        assert (
            result["value"]["pgVersion"] == "18.4"
            and result["value"]["native"] is False
        )

    def test_current_unqualified_public_producer_fails_closed(self):
        # Arrange
        # Act
        result = contract("plan", native=False)

        # Assert
        assert result == {"ok": False, "reason": "image-unqualified"}

    def test_unregistered_repository_refuses(self):
        # Arrange
        # Act
        result = contract("select", repository="outside/project")

        # Assert
        assert result["reason"] == "repository-unregistered"

    def test_untrusted_event_refuses(self):
        # Arrange
        # Act
        result = contract("select", event="pull_request_target")

        # Assert
        assert result["reason"] == "event-unsupported"

    def test_dev_pr_retains_all_three_versions(self):
        # Arrange
        # Act
        result = contract("select")

        # Assert
        assert result["value"]["versions"] == ["3.11", "3.12", "3.13"]

    def test_sac_pr_runs_all_supported_python_versions(self):
        # Arrange
        # Act
        result = contract("select", repository=SAC)

        # Assert
        assert result["value"]["versions"] == ["3.11", "3.12", "3.13"]

    def test_runner_pool_is_selected_from_organization_configuration(self):
        # Arrange
        source = WORKFLOW.read_text()

        # Act
        admission = source.split("  runner-admission:\n")[1].split("  profile:\n")[0]

        # Assert
        assert "vars.SCITEX_CI_RUNS_ON || inputs.runs_on" in admission
        assert 'default: \'["ubuntu-latest"]\'' in source

    def test_sac_push_retains_all_versions(self):
        # Arrange
        # Act
        result = contract("select", repository=SAC, event="push")

        # Assert
        assert result["value"]["versions"] == ["3.11", "3.12", "3.13"]

    def test_native_registry_needs_no_hosted_download(self):
        # Arrange
        records = registry()
        records[DEV]["image"]["delivery"] = None

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["ok"]

    def test_hosted_missing_download_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["image"]["delivery"] = None

        # Act
        result = contract("plan", native=False, registry=records)

        # Assert
        assert result["reason"] == "hosted-image-delivery-unqualified"

    def test_hosted_missing_runtime_delivery_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["hostedRuntime"]["hosted_delivery_sha256"] = None

        # Act
        result = contract("plan", native=False, registry=records)

        # Assert
        assert result["reason"] == "hosted-runtime-delivery-unqualified"

    def test_dev_cannot_claim_unmeasured_pg18(self):
        # Arrange
        records = registry()
        records[DEV]["image"]["capabilities"]["postgres"] = "18.4"

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["reason"] == "dev-pg-capability-unqualified"

    def test_sac_cannot_replace_pg18_with_pg16(self):
        # Arrange
        records = registry()
        records[SAC]["pgImage"]["capabilities"]["postgres"] = "16.15"

        # Act
        result = contract("plan", repository=SAC, registry=records)

        # Assert
        assert result["reason"] == "sac-pg18-unqualified"

    def test_sac_exports_qualified_actual_pg_version(self):
        # Arrange
        # Act
        result = contract("plan", repository=SAC, registry=registry())

        # Assert
        assert result["value"]["pgVersion"] == "18.4"

    def test_foreign_download_route_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["image"]["delivery"]["url"] = "https://outside.invalid/ci.sif"

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["reason"] == "image-delivery-invalid"

    def test_foreign_redirect_authority_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["image"]["delivery"]["redirect_hosts"].append("outside.invalid")

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["reason"] == "image-delivery-invalid"

    def test_mutable_producer_revision_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["image"]["producer_revision"] = "main"

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["reason"] == "image-producer-unqualified"

    def test_unknown_private_capability_field_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["image"]["capabilities"]["credential"] = "synthetic-private"

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["reason"] == "image-capabilities-unqualified"

    def test_missing_supported_driver_refuses(self):
        # Arrange
        records = registry()
        del records[SAC]["leafSources"][".github/ci/tmpdir-lib.sh"]

        # Act
        result = contract("plan", repository=SAC, registry=records)

        # Assert
        assert result["reason"] == "leaf-source-closure-unqualified"

    def test_conflicting_repository_profile_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["id"] = "sac"

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["reason"] == "profile-mismatch"

    def test_string_admission_cannot_grant_native(self):
        # Arrange
        # Act
        result = contract("plan", native="true", registry=registry())

        # Assert
        assert result["reason"] == "admission-invalid"

    def test_unqualified_namespace_capability_refuses(self):
        # Arrange
        records = registry()
        records[DEV]["nativeRuntime"]["user_namespace"] = False

        # Act
        result = contract("plan", registry=records)

        # Assert
        assert result["reason"] == "runtime-capability-unqualified"


def gate_case(case):
    with tempfile.TemporaryDirectory(prefix="sif-contract-owned-") as temporary:
        root = Path(temporary)
        workspace = root / "checkout"
        script = workspace / ".github/ci/exec-in-sif.sh"
        script.parent.mkdir(parents=True)
        script.write_bytes(b"synthetic public script\n")
        runtime = root / "apptainer"
        runtime.write_bytes(b"synthetic public runtime")
        sif = root / "ci.sif"
        body = b"synthetic public immutable SIF"
        sif.write_bytes(body)
        scratch = root / "runner-temp"
        scratch.mkdir()

        def digest(data):
            return hashlib.sha256(data).hexdigest()

        plan = {
            "leafSources": {".github/ci/exec-in-sif.sh": digest(script.read_bytes())},
            "runtime": {
                "path": str(runtime),
                "sha256": digest(runtime.read_bytes()),
                "bytes": runtime.stat().st_size,
            },
            "image": {
                "sha256": digest(body),
                "bytes": len(body),
                "native_paths": [str(sif)],
                "delivery": {
                    "url": "https://github.com/scitex-ai/scitex-dev/releases/download/v1/ci.sif",
                    "redirect_hosts": [
                        "github.com",
                        "release-assets.githubusercontent.com",
                    ],
                },
            },
            "pgImage": None,
            "native": not case.startswith("hosted"),
        }
        if case == "source-conflict":
            script.write_bytes(b"changed public script\n")
        elif case == "source-symlink":
            script.unlink()
            script.symlink_to(runtime)
        elif case == "image-conflict":
            sif.write_bytes(b"changed public immutable SIF")
        elif case == "locator-unapproved":
            plan["image"]["native_paths"] = ["/not-approved/ci.sif"]
        program = """
const vm = require('vm');
const input = JSON.parse(process.argv[1]);
const outputs = {};
let fetches = 0;
let writes = 0;
const actualFs = require('fs');
const fileFs = {...actualFs, promises: {...actualFs.promises, open: async (...args) => {
  const handle = await actualFs.promises.open(...args);
  if (args[1] === 'wx' && ['hosted-partial-write', 'hosted-stalled-write'].includes(input.case)) {
    const write = handle.write.bind(handle);
    handle.write = async (buffer, offset, length, position) => {
      writes++;
      if (input.case === 'hosted-stalled-write') return {bytesWritten: 0};
      return write(buffer, offset, Math.min(length, 3), position);
    };
  }
  return handle;
}}};
const writeReceipt = () => input.case.endsWith('-write') ? {writes} : {};
const sandbox = {
  require: name => name === 'fs' ? fileFs : require(name), Buffer, Date, URL, AbortSignal,
  process: {env: input.environment},
  core: {setOutput: (name, value) => { outputs[name] = value; }},
  fetch: async () => {
    fetches++;
    if (input.case === 'hosted-foreign-redirect') return {
      status: 302, ok: false, headers: {get: () => 'https://outside.invalid/private'},
    };
    return {status: 200, ok: true, body: (async function* () {
      yield Buffer.from(input.body, 'base64');
    })()};
  },
};
vm.runInNewContext('(async () => {\\n' + input.source + '\\n})()', sandbox)
  .then(() => console.log(JSON.stringify({
    ok: true, fetches, keys: Object.keys(outputs).sort(), ...writeReceipt(),
  })))
  .catch(error => console.log(JSON.stringify({ok: false, fetches,
    reason: ['ELOOP', 'ENOENT'].includes(error.code) ? error.code : error.message,
    ...writeReceipt()})));
"""
        return node(
            program,
            {
                "source": blocks("SIF_FILE_GATE")[0],
                "case": case,
                "body": base64.b64encode(
                    body if case != "hosted-body-conflict" else b"changed bytes"
                ).decode(),
                "environment": {
                    "PLAN": json.dumps(plan),
                    "GITHUB_WORKSPACE": str(workspace),
                    "RUNNER_TEMP": str(scratch),
                    "NATIVE_CI_SIF": str(sif),
                    "NATIVE_PG_SIF": "",
                },
            },
        )


class SIFFileBoundaryTests(unittest.TestCase):
    def test_real_native_descriptor_byte_receipt(self):
        # Arrange
        # Act
        result = gate_case("native")

        # Assert
        assert result == {
            "ok": True,
            "fetches": 0,
            "keys": ["apptainer", "pg_sif", "sif"],
        }

    def test_real_driver_byte_conflict_refuses_before_network(self):
        # Arrange
        # Act
        result = gate_case("source-conflict")

        # Assert
        assert result == {"ok": False, "fetches": 0, "reason": "file-byte-pin-mismatch"}

    def test_real_leaf_symlink_refuses_without_following(self):
        # Arrange
        # Act
        result = gate_case("source-symlink")

        # Assert
        assert result == {"ok": False, "fetches": 0, "reason": "ELOOP"}

    def test_real_changed_image_refuses(self):
        # Arrange
        # Act
        result = gate_case("image-conflict")

        # Assert
        assert not (result["ok"])

    def test_unapproved_native_locator_refuses(self):
        # Arrange
        # Act
        result = gate_case("locator-unapproved")

        # Assert
        assert result["reason"] == "native-image-locator-unapproved"

    def test_real_owned_streamed_hosted_copy(self):
        # Arrange
        # Act
        result = gate_case("hosted")

        # Assert
        assert result == {
            "ok": True,
            "fetches": 1,
            "keys": ["apptainer", "owned", "pg_sif", "sif"],
        }

    def test_unknown_redirect_refuses_before_second_request(self):
        # Arrange
        # Act
        result = gate_case("hosted-foreign-redirect")

        # Assert
        assert result == {
            "ok": False,
            "fetches": 1,
            "reason": "public-image-redirect-refused",
        }

    def test_replaced_hosted_body_never_becomes_accepted_image(self):
        # Arrange
        # Act
        result = gate_case("hosted-body-conflict")

        # Assert
        assert not (result["ok"])

    def test_real_partial_descriptor_writes_complete_verified_copy(self):
        # Arrange
        # Act
        result = gate_case("hosted-partial-write")

        # Assert
        assert (
            result["ok"]
            and result["writes"] > 1
            and result["keys"] == ["apptainer", "owned", "pg_sif", "sif"]
        )

    def test_zero_descriptor_write_refuses_before_image_acceptance(self):
        # Arrange
        # Act
        result = gate_case("hosted-stalled-write")

        # Assert
        assert result == {
            "ok": False,
            "fetches": 1,
            "writes": 1,
            "reason": "public-image-write-stalled",
        }


class SIFWorkflowSourceTests(unittest.TestCase):
    def test_owned_image_cleanup_cannot_mask_a_failed_leg(self):
        # Arrange
        source = WORKFLOW.read_text()
        # Act
        cleanups = source.split(
            "      - name: Remove this leg's owned hosted image copies\n"
        )[1:]

        # Assert
        assert len(cleanups) == 4 and all(
            "continue-on-error:" not in "\n".join(block.splitlines()[:6])
            for block in cleanups
        )

    def test_existing_sac_coverage_error_policy_remains_explicit(self):
        # Arrange
        # Act
        coverage = (
            WORKFLOW.read_text()
            .split("      - name: SAC coverage\n")[1]
            .split("      - name:", 1)[0]
        )

        # Assert
        assert "continue-on-error: true" in coverage

    def test_both_profile_source_gates_are_identical(self):
        # Arrange
        # Act
        scripts = blocks("SIF_FILE_GATE")

        # Assert
        assert scripts == [scripts[0]] * 4

    def test_native_refusals_are_before_each_checkout(self):
        # Arrange
        source = WORKFLOW.read_text()
        # Act
        jobs = [
            source.split("  test-dev:\n")[1].split("  test-sac:\n")[0],
            source.split("  test-sac:\n")[1].split("  nightly-sac:\n")[0],
            source.split("  nightly-sac:\n")[1],
        ]

        # Assert
        assert all(
            job.index("Require confirmed organization membership")
            < job.index("actions/checkout")
            and job.index("Refuse to run fork-authored") < job.index("actions/checkout")
            for job in jobs
        )

    def test_dev_has_no_oidc_permission(self):
        # Arrange
        # Act
        dev = WORKFLOW.read_text().split("  test-dev:\n")[1].split("  test-sac:\n")[0]

        # Assert
        assert "id-token: write" not in dev

    def test_sac_coverage_stays_in_genuine_test_leg(self):
        # Arrange
        # Act
        sac = (
            WORKFLOW.read_text().split("  test-sac:\n")[1].split("  nightly-sac:\n")[0]
        )

        # Assert
        assert (
            "id-token: write" in sac
            and "use_oidc: true" in sac
            and "Preserve SAC per-leg always cleanup" in sac
            and "Dev coverage" not in sac
            and "name: pytest-matrix-on-ubuntu-py${{ matrix.python-version }}" in sac
        )

    def test_sac_verdict_is_retained_in_the_central_workflow(self):
        # Arrange
        source = WORKFLOW.read_text()

        # Act
        verdict = source.split("  sac-verdict:\n")[1].split("  nightly-sac:\n")[0]

        # Assert
        assert "needs: [runner-admission, profile, test-sac]" in verdict
        assert "continue-on-error: true" in verdict
        assert "ci_card_rail.py verdict" in verdict
        assert "sac-control-plane" in verdict
        assert "name: Summarize auxiliary Cards delivery" in verdict
        assert "${{ steps.verdict.outcome }}" in verdict
        assert "does not change the test verdict" in verdict

    def test_nightly_has_no_coverage_or_oidc_and_keeps_hosted_budget(self):
        # Arrange
        # Act
        nightly = WORKFLOW.read_text().split("  nightly-sac:\n")[1]

        # Assert
        assert (
            "runs-on: ubuntu-latest" in nightly
            and "timeout-minutes: 90" in nightly
            and "id-token:" not in nightly
            and "codecov/" not in nightly
            and "run: bash .github/ci/exec-in-sif.sh run-in-sif.sh ${{ matrix.python-version }} nightly"
            in nightly
            and "Preserve SAC per-leg always cleanup" in nightly
            and "issues:" not in nightly
        )

    def test_nightly_forces_hosted_admission_before_profile_gate(self):
        # Arrange
        # Act
        admission = (
            WORKFLOW.read_text()
            .split("  runner-admission:\n")[1]
            .split("  profile:\n")[0]
        )

        # Assert
        assert "inputs.suite == 'nightly' && '[\"ubuntu-latest\"]'" in admission

    def test_existing_protected_workflow_bodies_unchanged(self):
        # Arrange: retained pins, reviewed import and restricted-group successors.
        expected = {
            "auto-merge-to-develop.yml": "a28d9b92576590903290809643f21c93f680a6b2a1a8913d6c6e2fed89993de0",
            "cla.yml": "d39672edd41d5689c4d3f203bd94b7fb7ecfd1dce589e07f40ccff8b494d1732",
            "import-smoke.yml": "3df1f4d4abd9da553b36484e37b8c5588e5684f6618d1b102c698893595fe8d6",
            "promote-develop-to-main-on-tag.yml": "1e3cec556f96612ff987f1bc2969dd145f85ebfff48297a3bf3adccd0b8c0c69",
            "pytest-matrix.yml": "4c6663947b4c3727954953226e6110a703ab4fb09180d64b2f15164e2310dfcf",
            "quality-audit.yml": "f44a2e6b5c479c2975d1cedf66738fdbf402a74cf1d8e26340bb9895524e7b4a",
            "rtd-sphinx-build.yml": "cc680b6ceecac73566b212a0db96ba016b3aa28766700e95b04691981ededaad",
            "runner-admission.yml": "406b82aae0183da8bf35b3fcfa424f22231e3b132ba3e002f72e09c713828205",
        }
        # Act
        actual = {
            name: hashlib.sha256(
                (ROOT / ".github/workflows" / name).read_bytes()
            ).hexdigest()
            for name in expected
        }

        # Assert
        assert actual == expected


if __name__ == "__main__":
    unittest.main()
