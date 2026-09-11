"""The reusable CLA workflow keeps one organization-wide signature ledger."""

from pathlib import Path

import yaml


_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "cla.yml"


def _workflow() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _cla_step() -> dict:
    steps = _workflow()["jobs"]["CLAssistant"]["steps"]
    return next(step for step in steps if step.get("name") == "CLA Assistant")


def test_cla_signatures_are_stored_in_the_org_repository() -> None:
    inputs = _cla_step()["with"]

    assert inputs["remote-organization-name"] == "scitex-ai"
    assert inputs["remote-repository-name"] == ".github"
    assert inputs["branch"] == "cla"
    assert inputs["path-to-signatures"] == "signatures/cla.json"


def test_cla_document_stays_in_the_calling_repository() -> None:
    document = _cla_step()["with"]["path-to-document"]

    assert "${{ github.repository }}" in document
    assert "${{ inputs.default_branch }}" in document


def test_outsider_triggerable_cla_jobs_keep_hosted_default_and_no_checkout() -> None:
    workflow = _workflow()
    assert workflow[True]["workflow_call"]["inputs"]["runs_on"]["default"] == (
        '["ubuntu-latest"]'
    )

    for job in workflow["jobs"].values():
        assert job["runs-on"] == "${{ fromJSON(inputs.runs_on) }}"
        assert all("actions/checkout" not in str(step.get("uses", "")) for step in job["steps"])
