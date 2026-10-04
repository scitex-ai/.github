"""The generic organization job keeps admission and tool setup centralized."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_organization_job_admits_before_checkout_and_sets_up_uv():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/organization-job.yml").read_text()
    )
    jobs = workflow["jobs"]
    assert jobs["runner-admission"]["uses"] == (
        "./.github/workflows/runner-admission.yml"
    )
    job = jobs["run"]
    assert job["needs"] == "runner-admission"
    assert "needs.runner-admission.outputs.runs_on" in job["runs-on"]
    steps = job["steps"]
    checkout_index = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert steps[checkout_index + 1]["uses"] == "astral-sh/setup-uv@v7"
    assert steps[checkout_index + 2]["name"] == "Run caller job"
    assert steps[checkout_index + 2]["env"]["CALLER_COMMAND"] == "${{ inputs.command }}"
