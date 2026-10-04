"""The selected reusable workflow is the only caller-controlled compute entry."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_organization_job_routes_through_membership_admission():
    workflow = yaml.safe_load((ROOT / ".github/workflows/organization-job.yml").read_text())
    jobs = workflow["jobs"]
    admission = jobs["runner-admission"]
    run = jobs["run"]

    events = workflow.get("on", workflow.get(True))
    assert events["workflow_call"]["inputs"]["command"]["required"] is True
    assert admission["uses"] == "./.github/workflows/runner-admission.yml"
    assert run["needs"] == "runner-admission"
    assert "needs.runner-admission.outputs.runs_on" in run["runs-on"]
    assert run["steps"][0]["name"] == "Refuse to run fork-authored code on self-hosted infrastructure"
    assert run["steps"][1]["name"] == "Require allowlisted actor on native runners"
    assert run["steps"][2]["uses"].startswith("actions/checkout@")
    assert run["steps"][3]["env"] == {
        "CALLER_COMMAND": "${{ inputs.command }}",
        "RUNNER_ENVIRONMENT": "${{ runner.environment }}",
    }
    assert yaml.safe_load(workflow["on" if "on" in workflow else True]["workflow_call"]["inputs"]["runs_on"]["default"]) == [
        "self-hosted", "Linux", "X64", "scitex-org-cpu"
    ]
    assert "secrets" not in workflow
