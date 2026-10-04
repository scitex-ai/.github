"""Execute the hosted admission script with representative GitHub events."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NATIVE = '["self-hosted","Linux","X64","scitex-org-cpu"]'
TRUSTED_ID = "42527473"
NODE_BIN = shutil.which("node")
FILES = ["pytest-matrix.yml", "import-smoke.yml", "quality-audit.yml", "rtd-sphinx-build.yml",
         "cla.yml", "auto-merge-to-develop.yml", "promote-develop-to-main-on-tag.yml", "runner-health.yml",
         "fd-fclones-integration.yml"]


def execute(tmp_path, **changes):
    wf = yaml.safe_load((ROOT / ".github/workflows/runner-admission.yml").read_text())
    script = wf["jobs"]["admission"]["steps"][0]["run"]
    body = script.split("node <<'NODE'\n", 1)[1].rsplit("\nNODE", 1)[0]
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "REPOSITORY": "scitex-ai/package",
           "ORIGINAL_ACTOR": "ywatanabe1989", "ORIGINAL_ACTOR_ID": TRUSTED_ID,
           "TRIGGERING_ACTOR": "ywatanabe1989", "EVENT_NAME": "push",
           "PR_AUTHOR": "", "PR_AUTHOR_ID": "", "HEAD_REPOSITORY": "",
           "REQUESTED_RUNS_ON": NATIVE}
    env.update(changes)
    out = tmp_path / "outputs"
    env["GITHUB_OUTPUT"] = str(out)
    harness = "global.fetch=()=>{throw Error('admission must not call an external API')};\n"
    if NODE_BIN is None:
        raise RuntimeError("Existing Node interpreter is required for workflow tests")
    p = subprocess.run([NODE_BIN, "-"], input=harness + body, capture_output=True,
                       text=True, env=env, timeout=5)
    assert p.returncode == 0, p.stderr
    output = dict(line.split("=", 1) for line in out.read_text().splitlines())
    output["runs_on"] = json.loads(output["runs_on"])
    return output


def test_trusted_push_selects_restricted_company_group(tmp_path):
    r = execute(tmp_path)
    assert r["native_authorized"] == "true"
    assert r["reason"] == "trusted-actor"
    assert r["runs_on"] == {"group": "Organization", "labels": json.loads(NATIVE)}


@pytest.mark.parametrize("node", ["02", "03", "04"])
def test_trusted_actor_can_select_each_company_compute_node(tmp_path, node):
    requested = json.loads(NATIVE) + ["scitex-compute-" + node]
    result = execute(tmp_path, REQUESTED_RUNS_ON=json.dumps(requested))
    assert result["runs_on"] == {"group": "Organization", "labels": requested}
    assert result["native_authorized"] == "true"


@pytest.mark.parametrize("changes", [
    {"ORIGINAL_ACTOR": "trusted-name-but-wrong-id", "ORIGINAL_ACTOR_ID": "100"},
    {"ORIGINAL_ACTOR_ID": ""},
    {"ORIGINAL_ACTOR_ID": "42527474"},
    {"TRIGGERING_ACTOR": "other-user"},
])
def test_unlisted_actor_or_rerunner_stays_hosted(tmp_path, changes):
    r = execute(tmp_path, **changes)
    assert r["native_authorized"] == "false"
    assert r["runs_on"] == ["ubuntu-latest"]


def test_unowned_compute_node_remains_an_undeclared_destination(tmp_path):
    requested = json.loads(NATIVE) + ["scitex-compute-05"]
    result = execute(tmp_path, REQUESTED_RUNS_ON=json.dumps(requested))
    assert result["runs_on"] == ["ubuntu-latest"]
    assert result["reason"] == "undeclared-native-destination"


def test_trusted_same_repo_pr_selects_company_group(tmp_path):
    r = execute(tmp_path, EVENT_NAME="pull_request", PR_AUTHOR="ywatanabe1989",
                PR_AUTHOR_ID=TRUSTED_ID, HEAD_REPOSITORY="scitex-ai/package")
    assert r["native_authorized"] == "true"
    assert r["runs_on"] == {"group": "Organization", "labels": json.loads(NATIVE)}


@pytest.mark.parametrize("changes", [
    {"HEAD_REPOSITORY": "external/fork"},
    {"HEAD_REPOSITORY": ""},
    {"PR_AUTHOR": "external", "PR_AUTHOR_ID": "100"},
    {"PR_AUTHOR": "ywatanabe1989", "PR_AUTHOR_ID": "100"},
    {"ORIGINAL_ACTOR_ID": "100"},
])
def test_forks_and_untrusted_pr_authors_stay_hosted(tmp_path, changes):
    base = {"EVENT_NAME": "pull_request", "PR_AUTHOR": "ywatanabe1989",
            "PR_AUTHOR_ID": TRUSTED_ID, "HEAD_REPOSITORY": "scitex-ai/package"}
    base.update(changes)
    r = execute(tmp_path, **base)
    assert r["native_authorized"] == "false"
    assert r["runs_on"] == ["ubuntu-latest"]


@pytest.mark.parametrize("changes", [
    {"REPOSITORY": "ywatanabe1989/.dotfiles"},
    {"EVENT_NAME": "pull_request_target"},
    {"EVENT_NAME": "workflow_run"},
    {"ORIGINAL_ACTOR": "bad/user"},
    {"TRIGGERING_ACTOR": ""},
    {"ORIGINAL_ACTOR_ID": "not-numeric"},
    {"REQUESTED_RUNS_ON": '["self-hosted","unknown-pool"]'},
])
def test_incomplete_unsupported_or_foreign_context_cannot_authorize_native(tmp_path, changes):
    assert execute(tmp_path, **changes)["native_authorized"] == "false"


def test_existing_hosted_request_is_preserved_for_trusted_actor(tmp_path):
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
        backstop = next(i for i, s in enumerate(steps) if s.get("name") in {
            "Require confirmed organization membership on native runners",
            "Require allowlisted actor on native runners",
        })
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
        "ORIGINAL_ACTOR_ID": "${{ github.actor_id }}",
        "TRIGGERING_ACTOR": "${{ github.triggering_actor }}",
        "EVENT_NAME": "${{ github.event_name }}",
        "PR_AUTHOR": "${{ github.event.pull_request.user.login }}",
        "PR_AUTHOR_ID": "${{ github.event.pull_request.user.id }}",
        "HEAD_REPOSITORY": "${{ github.event.pull_request.head.repo.full_name }}",
        "REQUESTED_RUNS_ON": "${{ inputs.runs_on }}",
    }


def test_native_definitions_keep_all_nested_workflows_at_the_selected_revision():
    workflows = [yaml.safe_load((ROOT / ".github/workflows" / name).read_text()) for name in FILES]
    mutable = [job["uses"] for workflow in workflows for job in workflow["jobs"].values()
               if "uses" in job and not job["uses"].startswith("./.github/workflows/")]
    assert mutable == []
