"""Run the new fixed release policy with genuine Node; no native dispatch."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

import test_sif_matrix_contract as fixtures

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/writer-release-sif.yml"


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
            assert line.startswith("            ")
            active.append(line[12:])
    return result


def run_policy(**changes):
    payload = {
        "repository": "scitex-ai/scitex-writer",
        "event": "workflow_dispatch",
        "native": True,
        "operation": "test",
        "source": "a" * 40,
        "tag": "v2.43.9",
        "registration": {
            "image": fixtures.image(),
            "runtime": fixtures.registry()[fixtures.DEV]["nativeRuntime"],
        },
    }
    payload.update(changes)
    program = (
        blocks("WRITER_RELEASE_CONTRACT")[0]
        + """
const x = JSON.parse(process.argv[1]);
try {
  const p = writerPlan(x.repository, x.event, x.native, x.operation, x.source,
    x.tag, x.registration === 'production' ? REGISTRATION : x.registration);
  console.log(JSON.stringify({ok: true, plan: p}));
} catch (e) { console.log(JSON.stringify({ok: false, reason: e.message})); }
"""
    )
    executable = shutil.which("node")
    assert executable is not None
    child = subprocess.run(
        [executable, "-e", program, json.dumps(payload)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


class WriterReleaseContract(unittest.TestCase):
    def test_actual_production_registration_accepts_genuine_record(self):
        # Arrange — REGISTRATION is genuinely populated (2.43.10 runtime), so
        # the production path yields a full plan instead of refusing.
        # Act
        result = run_policy(registration="production")
        # Assert
        assert result["ok"] is True
        assert result["plan"]["versions"] == ["3.11", "3.12", "3.13"]

    def test_all_three_original_test_versions_remain(self):
        # Arrange
        # Act
        result = run_policy()
        # Assert
        assert result["plan"]["versions"] == ["3.11", "3.12", "3.13"]

    def test_build_keeps_only_original_middle_version(self):
        # Arrange
        # Act
        result = run_policy(operation="build")
        # Assert
        assert result["plan"]["versions"] == ["3.12"]

    def test_preflight_resolved_commit_is_retained(self):
        # Arrange
        resolved = "f" * 40
        # Act
        result = run_policy(source=resolved)
        # Assert
        assert result["plan"]["sourceCommit"] == resolved
        assert "ref: ${{ inputs.source_commit }}" in WORKFLOW.read_text()
        assert "ref: ${{ github.sha }}" not in WORKFLOW.read_text()

    def test_arbitrary_repository_is_refused(self):
        # Arrange
        # Act
        result = run_policy(repository="scitex-ai/scitex-dev")
        # Assert
        assert result["reason"] == "writer-repository-refused"

    def test_nonmember_release_is_refused(self):
        # Arrange
        # Act
        result = run_policy(native=False)
        # Assert
        assert result["reason"] == "writer-release-membership-required"

    def test_fork_event_cannot_select_native_release(self):
        # Arrange
        # Act
        result = run_policy(event="pull_request")
        # Assert
        assert result["reason"] == "writer-release-event-refused"

    def test_arbitrary_command_cannot_select_a_driver(self):
        # Arrange
        # Act
        result = run_policy(operation="bash owned-by-caller.sh")
        # Assert
        assert result["reason"] == "writer-release-operation-refused"

    def test_floating_commit_is_refused(self):
        # Arrange
        # Act
        result = run_policy(source="main")
        # Assert
        assert result["reason"] == "writer-source-commit-refused"

    def test_trailing_newline_commit_is_refused(self):
        # Arrange
        # Act
        result = run_policy(source="a" * 40 + "\n")
        # Assert
        assert result["reason"] == "writer-source-commit-refused"

    def test_tag_shell_syntax_is_refused(self):
        # Arrange
        # Act
        result = run_policy(tag="v2.43.9;echo extra")
        # Assert
        assert result["reason"] == "writer-release-tag-refused"

    def test_tag_trailing_newline_is_refused(self):
        # Arrange
        # Act
        result = run_policy(tag="v2.43.9\n")
        # Assert
        assert result["reason"] == "writer-release-tag-refused"

    def test_missing_whole_image_still_refuses(self):
        # Arrange
        registration = {
            "image": None,
            "runtime": fixtures.registry()[fixtures.DEV]["nativeRuntime"],
        }
        # Act
        result = run_policy(registration=registration)
        # Assert
        assert result["reason"] == "image-unqualified"

    def test_existing_file_boundary_is_retained_verbatim(self):
        # Arrange
        original = fixtures.blocks("SIF_FILE_GATE")[0]
        # Act
        current = blocks("SIF_FILE_GATE")[0]
        # Assert
        assert current == original

    def test_build_artifact_identity_uses_resolved_commit(self):
        # Arrange
        source = WORKFLOW.read_text()
        # Act
        name = "name: writer-dist-${{ inputs.source_commit }}"
        # Assert
        assert name in source
        assert "if-no-files-found: error" in source
        assert "inputs.operation == 'build' && 30 || 60" in source


if __name__ == "__main__":
    unittest.main()
