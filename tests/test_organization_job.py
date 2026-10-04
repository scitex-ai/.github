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
    assert "native_authorized != 'true'" in run["steps"][0]["if"]
    assert run["steps"][1]["uses"].startswith("actions/checkout@")
    assert run["steps"][2]["env"] == {"CALLER_COMMAND": "${{ inputs.command }}"}
    assert "secrets" not in workflow
