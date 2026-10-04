"""Run the production Dev release policy against finite source metadata."""
import copy
import hashlib
import unittest
from pathlib import Path

import yaml
from test_sif_matrix_contract import DEV, SAC, WORKFLOW, blocks, contract, node


def source_case(changes=None):
    commit = "a" * 40
    main = {"name": "main", "protected": True, "commit": {"sha": "b" * 40}}
    data = {
        "repository": DEV, "event": "workflow_dispatch", "ref": "refs/heads/main",
        "requested": "v0.62.3",
        "workflow": DEV + "/.github/workflows/pypi-publish-and-github-release-on-tag.yml@refs/heads/main",
        "commit": commit, "eventSha": "b" * 40, "before": main,
        "after": copy.deepcopy(main),
        "comparison": {"status": "ahead", "base_commit": {"sha": commit},
                       "merge_base_commit": {"sha": commit}},
    }
    data.update(changes or {})
    program = blocks("SIF_CONTRACT")[0] + "\n" + blocks("DEV_RELEASE_SOURCE")[0] + """
const input = JSON.parse(process.argv[1]);
try {
  const request = releaseRequest(input.repository, input.event, input.ref, input.requested, input.workflow);
  const identity = qualifyReleaseSource(request, input.commit, input.eventSha, input.before, input.comparison, input.after);
  console.log(JSON.stringify({ok: true, identity}));
} catch (error) { console.log(JSON.stringify({ok: false, reason: error.message})); }
"""
    return node(program, data)


class ReleaseSourceTests(unittest.TestCase):
    def test_actual_registered_release_plan_retains_three_minors_and_exact_drivers(self):
        # Arrange
        workflow = yaml.safe_load(WORKFLOW.read_text())
        # Act
        result = contract("plan", event="workflow_dispatch", suite="dev-release")
        # Assert
        self.assertTrue(result["ok"])
        self.assertEqual(result["value"]["versions"], ["3.11", "3.12", "3.13"])
        self.assertEqual(len(result["value"]["leafSources"]), 7)
        self.assertEqual(workflow["jobs"]["build-dev-release"]["needs"],
                         ["runner-admission", "profile", "test-dev"])

    def test_sac_cannot_borrow_dev_release_registration(self):
        # Arrange
        # Act
        result = contract("select", repository=SAC, event="push", suite="dev-release")
        # Assert
        self.assertEqual(result["reason"], "release-profile-unsupported")

    def test_pr_cannot_trigger_release_operations(self):
        # Arrange
        # Act
        result = contract("select", event="pull_request", suite="dev-release")
        # Assert
        self.assertEqual(result["reason"], "release-event-unsupported")

    def test_missing_membership_retains_private_image_refusal(self):
        # Arrange
        # Act
        result = contract("plan", native=False, event="push", suite="dev-release")
        # Assert
        self.assertEqual(result["reason"], "image-unqualified")

    def test_protected_main_dispatch_accepts_one_promoted_commit(self):
        # Arrange
        # Act
        result = source_case()
        # Assert
        self.assertEqual(result, {"ok": True, "identity": {"tag": "v0.62.3", "commit": "a" * 40}})

    def test_tag_event_requires_exact_pushed_commit(self):
        # Arrange
        fields = {"event": "push", "ref": "refs/tags/v0.62.3",
                  "workflow": DEV + "/.github/workflows/pypi-publish-and-github-release-on-tag.yml@refs/tags/v0.62.3"}
        # Act
        result = source_case(fields)
        # Assert
        self.assertEqual(result["reason"], "release-tag-event-mismatch")

    def test_unknown_caller_cannot_claim_publisher_identity(self):
        # Arrange
        # Act
        result = source_case({"workflow": DEV + "/.github/workflows/other.yml@refs/heads/main"})
        # Assert
        self.assertEqual(result["reason"], "release-caller-refused")

    def test_manual_nonmain_ref_refuses(self):
        # Arrange
        # Act
        result = source_case({"ref": "refs/heads/develop"})
        # Assert
        self.assertEqual(result["reason"], "release-ref-refused")

    def test_malformed_tag_refuses_before_lookup(self):
        # Arrange
        # Act
        result = source_case({"requested": "v0.62.3;echo unexpected"})
        # Assert
        self.assertEqual(result["reason"], "release-tag-refused")

    def test_unprotected_main_cannot_publish(self):
        # Arrange
        before = {"name": "main", "protected": False, "commit": {"sha": "b" * 40}}
        # Act
        result = source_case({"before": before})
        # Assert
        self.assertEqual(result["reason"], "release-main-unprotected")

    def test_main_change_during_lookup_refuses(self):
        # Arrange
        after = {"name": "main", "protected": True, "commit": {"sha": "c" * 40}}
        # Act
        result = source_case({"after": after})
        # Assert
        self.assertEqual(result["reason"], "release-main-changed")

    def test_dispatch_definition_must_match_current_protected_main(self):
        # Arrange
        # Act
        result = source_case({"eventSha": "c" * 40})
        # Assert
        self.assertEqual(result["reason"], "release-dispatch-source-changed")

    def test_unpromoted_tag_cannot_publish(self):
        # Arrange
        comparison = {"status": "diverged", "base_commit": {"sha": "a" * 40},
                      "merge_base_commit": {"sha": "d" * 40}}
        # Act
        result = source_case({"comparison": comparison})
        # Assert
        self.assertEqual(result["reason"], "release-not-promoted-to-main")

    def test_all_shared_file_gates_keep_same_descriptor_code(self):
        # Arrange
        scripts = blocks("SIF_FILE_GATE")
        # Act
        digests = {hashlib.sha256(body.encode()).hexdigest() for body in scripts}
        # Assert
        self.assertEqual((len(scripts), len(digests)), (4, 1))

    def test_existing_sac_and_nightly_job_bodies_are_unchanged_except_check_name(self):
        # Arrange
        baseline = Path(__file__).parent / "fixtures/dev-release-central-original.yml"
        old = yaml.safe_load(baseline.read_text())
        new = yaml.safe_load(WORKFLOW.read_text())
        # Act
        old_sac = dict(old["jobs"]["test-sac"])
        new_sac = dict(new["jobs"]["test-sac"])
        old_sac.pop("name", None)
        new_sac.pop("name", None)
        changed = [name for name in ("nightly-sac", "runner-admission")
                   if old["jobs"][name] != new["jobs"][name]]
        if old_sac != new_sac:
            changed.append("test-sac")
        # Assert
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
