"""Execute the actual hosted admission script with synthetic HTTP responses."""
import json
import os
from pathlib import Path
import subprocess
import shutil

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NATIVE = '["self-hosted","Linux","X64","scitex-org-cpu"]'
NODE_BIN = shutil.which("node")
FILES = ["pytest-matrix.yml", "import-smoke.yml", "quality-audit.yml", "rtd-sphinx-build.yml",
         "cla.yml", "auto-merge-to-develop.yml", "promote-develop-to-main-on-tag.yml", "runner-health.yml"]


def execute(tmp_path, **changes):
    wf = yaml.safe_load((ROOT / ".github/workflows/runner-admission.yml").read_text())
    script = wf["jobs"]["admission"]["steps"][0]["run"]
    body = script.split("node <<'NODE'\n", 1)[1].rsplit("\nNODE", 1)[0]
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "REPOSITORY": "scitex-ai/package",
           "ORIGINAL_ACTOR": "internal", "TRIGGERING_ACTOR": "internal", "EVENT_NAME": "push",
           "PR_AUTHOR": "", "HEAD_REPOSITORY": "", "REQUESTED_RUNS_ON": NATIVE}
    statuses = changes.pop("statuses", {})
    env.update(changes)
    out = tmp_path / "outputs"
    env["GITHUB_OUTPUT"] = str(out)
    harness = ("global.fetch=async(url,options)=>{let who=url.split('/').pop();"
               "if(options.redirect!=='error'||options.headers.Authorization)throw Error('unsafe request');"
               "let statuses=" + json.dumps(statuses) + ";let status=statuses[who]??204;"
               "if(status==='error')throw Error('PRIVATE_ERROR_BODY');"
               "return {status};};\n")
    if NODE_BIN is None:
        raise RuntimeError("Existing Node interpreter is required for workflow tests")
    p = subprocess.run([NODE_BIN, "-"], input=harness + body, capture_output=True,
                       text=True, env=env, timeout=5)
    assert p.returncode == 0, p.stderr
    assert "PRIVATE_ERROR_BODY" not in p.stdout + p.stderr
    output = dict(line.split("=", 1) for line in out.read_text().splitlines())
    output["runs_on"] = json.loads(output["runs_on"])
    return output


def test_confirmed_internal_event_selects_restricted_company_group(tmp_path):
    r = execute(tmp_path)
    assert r["native_authorized"] == "true"
    assert r["runs_on"] == {"group": "Organization", "labels": json.loads(NATIVE)}


@pytest.mark.parametrize("status", [404, 403, 429, 500, 200, "error"])
def test_unconfirmed_membership_defaults_hosted_without_failing_ci(tmp_path, status):
    r = execute(tmp_path, statuses={"internal": status})
    assert r["native_authorized"] == "false"
    assert r["runs_on"] == ["ubuntu-latest"]


def test_member_rerun_cannot_authorize_original_external_actor(tmp_path):
    r = execute(tmp_path, ORIGINAL_ACTOR="external", statuses={"external": 404})
    assert r["native_authorized"] == "false"


def test_external_rerun_cannot_use_original_member_privilege(tmp_path):
    r = execute(tmp_path, TRIGGERING_ACTOR="external", statuses={"external": 404})
    assert r["native_authorized"] == "false"


def test_same_repo_pr_author_is_checked_independently(tmp_path):
    r = execute(tmp_path, EVENT_NAME="pull_request", PR_AUTHOR="external",
                HEAD_REPOSITORY="scitex-ai/package", statuses={"external": 404})
    assert r["native_authorized"] == "false"


def test_member_fork_and_missing_pr_origin_both_stay_hosted(tmp_path):
    for head in ("internal/fork", ""):
        r = execute(tmp_path, EVENT_NAME="pull_request", PR_AUTHOR="internal", HEAD_REPOSITORY=head)
        assert r["native_authorized"] == "false"
        assert r["runs_on"] == ["ubuntu-latest"]


@pytest.mark.parametrize("changes", [{"REPOSITORY": "ywatanabe1989/.dotfiles"},
                                     {"EVENT_NAME": "pull_request_target"},
                                     {"EVENT_NAME": "workflow_run"},
                                     {"PR_AUTHOR": "", "EVENT_NAME": "pull_request", "HEAD_REPOSITORY": "scitex-ai/package"},
                                     {"ORIGINAL_ACTOR": "bad/user"},
                                     {"ORIGINAL_ACTOR": ""},
                                     {"TRIGGERING_ACTOR": ""},
                                     {"REQUESTED_RUNS_ON": '["self-hosted","unknown-pool"]'}])
def test_incomplete_unsupported_or_foreign_context_cannot_authorize_native(tmp_path, changes):
    assert execute(tmp_path, **changes)["native_authorized"] == "false"


def test_existing_hosted_request_is_preserved_for_confirmed_member(tmp_path):
    r = execute(tmp_path, REQUESTED_RUNS_ON='["ubuntu-22.04"]')
    assert r["runs_on"] == ["ubuntu-22.04"]
    assert r["native_authorized"] == "false"


def test_existing_scalar_hosted_promotion_input_keeps_its_destination(tmp_path):
    r = execute(tmp_path, REQUESTED_RUNS_ON='"windows-latest"')
    assert r["runs_on"] == ["windows-latest"]
    assert r["native_authorized"] == "false"


@pytest.mark.parametrize("filename", FILES)
def test_every_native_capable_body_depends_on_same_revision_hosted_admission(filename):
    d = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
    admission = d["jobs"]["runner-admission"]
    assert admission["uses"] == "./.github/workflows/runner-admission.yml"
    for name, job in d["jobs"].items():
        if "runs-on" not in job or "${{" not in str(job["runs-on"]):
            continue
        needs = job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "runner-admission" in needs, name
        assert "needs.runner-admission.outputs.runs_on" in str(job["runs-on"]), name
        steps = job["steps"]
        backstop = next(i for i, s in enumerate(steps) if s.get("name") == "Require confirmed organization membership on native runners")
        checkouts = [i for i, s in enumerate(steps) if "actions/checkout" in s.get("uses", "")]
        assert all(backstop < i for i in checkouts)


def test_admission_has_no_checkout_credential_or_self_hosted_authority():
    d = yaml.safe_load((ROOT / ".github/workflows/runner-admission.yml").read_text())
    job = d["jobs"]["admission"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["permissions"] == {}
    assert not any("uses" in s for s in job["steps"])
    assert "github.token" not in str(job)
    assert "toJSON(github)" not in str(job)
    assert job["steps"][0]["env"] == {
        "REPOSITORY": "${{ github.repository }}",
        "ORIGINAL_ACTOR": "${{ github.actor }}",
        "TRIGGERING_ACTOR": "${{ github.triggering_actor }}",
        "EVENT_NAME": "${{ github.event_name }}",
        "PR_AUTHOR": "${{ github.event.pull_request.user.login }}",
        "HEAD_REPOSITORY": "${{ github.event.pull_request.head.repo.full_name }}",
        "REQUESTED_RUNS_ON": "${{ inputs.runs_on }}",
    }


def test_native_definitions_keep_all_nested_workflows_at_the_selected_revision():
    workflows = [yaml.safe_load((ROOT / ".github/workflows" / name).read_text()) for name in FILES]
    mutable = [job["uses"] for workflow in workflows for job in workflow["jobs"].values()
               if "uses" in job and not job["uses"].startswith("./.github/workflows/")]
    assert mutable == []
