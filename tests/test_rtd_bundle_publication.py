"""Sphinx bundles build centrally and publish only on trusted push events."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_rtd_bundle_publication_is_opt_in_and_push_only():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/rtd-sphinx-build.yml").read_text()
    )
    inputs = workflow.get("on", workflow.get(True))["workflow_call"]["inputs"]
    assert inputs["bundle_dir"]["default"] == ""

    build = workflow["jobs"]["docs-sphinx"]
    upload = next(
        step
        for step in build["steps"]
        if step.get("name") == "Upload built HTML for the caller to publish"
    )
    assert "inputs.bundle_dir != ''" in upload["if"]

    publish = workflow["jobs"]["publish-sphinx-bundle"]
    assert "github.event_name == 'push'" in publish["if"]
    assert publish["needs"] == ["docs-sphinx", "dev-original-sphinx"]
    assert publish["runs-on"] == "ubuntu-latest"
    assert publish["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert any(
        step.get("uses") == "actions/download-artifact@v4"
        for step in publish["steps"]
    )
    assert any("bundle_dir must be a safe" in step.get("run", "") for step in publish["steps"])
    create_pr = next(
        step
        for step in publish["steps"]
        if step.get("uses", "").startswith("peter-evans/create-pull-request@")
    )
    assert create_pr["with"]["base"] == "${{ github.ref_name }}"
    assert create_pr["with"]["branch"] == "ci/sphinx-bundle/${{ github.ref_name }}"
    assert create_pr["with"]["add-paths"] == "${{ inputs.bundle_dir }}"
    assert create_pr["if"] == "${{ !inputs.dev_original_commands }}"
    pushes = [step for step in publish["steps"] if "git push" in step.get("run", "")]
    assert len(pushes) == 1 and pushes[0]["id"] == "dev-docs-commit"
    assert pushes[0]["if"] == "inputs.dev_original_commands"
    assert 'git push origin "HEAD:refs/heads/$PR_BRANCH"' in pushes[0]["run"]
    assert "--force" not in pushes[0]["run"] and "--no-verify" not in pushes[0]["run"]
