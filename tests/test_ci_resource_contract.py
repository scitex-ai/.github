"""Real Node/HTTPS/Python/filesystem controls; only Actions outputs are adapted."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
import yaml
import test_writer_release_contract as writer
import test_leaf_release_contract as leaf

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
RESOURCE = {
 "kind":"owned-context-v1",
 "revision":"4e14fe28571617ccf7b6fffd9cff0e15a7bfc38c",
 "stager_sha256":"554ee91a86a0fc36da302dc0e97cf7324df940f122ff68856ca0190aa80fea04",
 "source_sha256":"a795678455d409e076a1c93a4a810b50c89499fcb83ae4c90a8d31a19e90e5d1",
}

def execute(marker, parent, **values):
    code = writer.blocks(marker)[0]
    wrapper = """
(async()=>{
 const outputs={}, environment={};
 const core={setOutput:(k,v)=>{outputs[k]=v},
             exportVariable:(k,v)=>{environment[k]=v}};
 try {
 SCRIPT
 process.stdout.write(JSON.stringify({ok:true,outputs,environment}));
 } catch(e) {
 process.stdout.write(JSON.stringify({ok:false,reason:e.message,outputs,environment}));
 }
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
""".replace("SCRIPT", code)
    result = subprocess.run([NODE,"-e",wrapper],
        env={"PATH":os.defpath,"RUNNER_TEMP":str(parent),**values},
        capture_output=True,text=True,timeout=60)
    result.check_returncode()
    return json.loads(result.stdout)

def stage(parent, descriptor=None):
    return execute("CI_RESOURCE_STAGE",parent,
        PLAN=json.dumps({"sharedResource":RESOURCE if descriptor is None else descriptor}))

def cleanup(parent, receipt):
    return execute("CI_RESOURCE_CLEANUP",parent,OWNED=receipt["outputs"]["owned"])

def prepared(tmp_path):
    parent=tmp_path/"parent"
    parent.mkdir(mode=0o700)
    result=stage(parent)
    if not result["ok"]:
        raise RuntimeError(result["reason"])
    return parent,result,Path(result["outputs"]["context"])

def test_real_download_staging_export_and_owned_cleanup(tmp_path):
    parent,result,context=prepared(tmp_path)
    facts=(hashlib.sha256(context.read_bytes()).hexdigest(),
           context.stat().st_mode&0o777,result["environment"])
    removed=cleanup(parent,result)
    assert (facts,removed["ok"],context.parent.exists()) == (
      (RESOURCE["source_sha256"],0o600,{"SCITEX_CI_OWNED_CONTEXT":str(context)}),True,False)

@pytest.mark.parametrize("field",["stager_sha256","source_sha256"])
def test_real_download_wrong_digest_refuses_execution_and_cleans_owned_files(tmp_path,field):
    parent=tmp_path/"parent"
    parent.mkdir(mode=0o700)
    result=stage(parent,{**RESOURCE,field:"0"*64})
    removed=cleanup(parent,result)
    assert (result["ok"],result["reason"],result["environment"],
            removed["ok"],list(parent.iterdir())) == (
        False,"resource-digest-refused",{},True,[])

@pytest.mark.parametrize("changes",[{"kind":"unknown"},{"revision":"main"},
                                   {"stager_sha256":"no"},{"extra":True},
                                   {"revision":[RESOURCE["revision"]]},
                                   {"source_sha256":[RESOURCE["source_sha256"]]},
                                   {"revision":RESOURCE["revision"]+"\n"},
                                   {"source_sha256":RESOURCE["source_sha256"]+"\n"}])
def test_invalid_descriptor_refused_before_allocating_or_exporting(tmp_path,changes):
    parent=tmp_path/"parent"
    parent.mkdir(mode=0o700)
    result=stage(parent,{**RESOURCE,**changes})
    assert (result["ok"],result["reason"],result["outputs"],
            result["environment"],list(parent.iterdir())) == (
        False,"resource-contract-invalid",{},{},[])

def test_cleanup_preserves_unknown_entries_and_known_resources(tmp_path):
    parent,result,context=prepared(tmp_path)
    foreign=context.parent/"foreign"
    foreign.write_bytes(b"preserve")
    removed=cleanup(parent,result)
    assert (removed["ok"],removed["reason"],foreign.read_bytes(),
            hashlib.sha256(context.read_bytes()).hexdigest()) == (
        False,"resource-cleanup-unknown-entry",b"preserve",RESOURCE["source_sha256"])

def test_cleanup_preserves_replacement_file(tmp_path):
    parent,result,context=prepared(tmp_path)
    original=tmp_path/"original-resource"
    context.rename(original)
    context.write_bytes(b"foreign replacement")
    context.chmod(0o600)
    removed=cleanup(parent,result)
    assert (removed["ok"],removed["reason"],context.read_bytes(),
            hashlib.sha256(original.read_bytes()).hexdigest()) == (
        False,"resource-cleanup-file-changed",b"foreign replacement",RESOURCE["source_sha256"])

def test_cleanup_preserves_replaced_root_and_moved_original(tmp_path):
    parent,result,context=prepared(tmp_path)
    moved=tmp_path/"moved-original"
    context.parent.rename(moved)
    context.parent.mkdir(mode=0o700)
    sentinel=context.parent/"foreign"
    sentinel.write_bytes(b"preserve")
    removed=cleanup(parent,result)
    assert (removed["ok"],removed["reason"],sentinel.read_bytes(),
            hashlib.sha256((moved/"context.sh").read_bytes()).hexdigest()) == (
        False,"resource-cleanup-root-changed",b"preserve",RESOURCE["source_sha256"])

def test_existing_plans_match_actual_frozen_pre_staging_outputs():
    baseline=json.loads((ROOT/"tests/fixtures/ci-resource-original-plans.json").read_text())
    assert [leaf.dispatch(**c["inputs"]) for c in baseline["cases"]] == [
        c["result"] for c in baseline["cases"]]

def test_resource_hooks_are_conditional_and_leave_operations_unchanged():
    workflow=yaml.safe_load(writer.WORKFLOW.read_text())
    job=next(j for j in workflow["jobs"].values()
             if any(s.get("id")=="inputs" for s in j.get("steps",[])))
    steps=job["steps"]
    resource=next(s for s in steps if s.get("id")=="resources")
    removal=next(s for s in steps if "CI_RESOURCE_CLEANUP" in s.get("with",{}).get("script",""))
    consumer=next(s for s in steps if s.get("name")=="Run the registered complete leaf suite")
    upload=next(s for s in steps if s.get("uses","").startswith("actions/upload-artifact@"))
    assert (resource["if"],removal["if"],steps.index(resource)<steps.index(consumer),
            resource["timeout-minutes"],removal["timeout-minutes"],
            steps.index(removal)<steps.index(upload),consumer["run"]) == (
      "fromJSON(needs.profile.outputs.plan).sharedResource != null",
      "always() && steps.resources.outputs.owned != ''",True,1,1,True,
      "bash .github/ci/exec-in-sif.sh run-in-sif.sh "+chr(36)+"{{ matrix.python-version }}")


def test_stats_resource_admission_cannot_enable_build_or_upload():
    assert leaf.dispatch(repository="scitex-ai/scitex-stats", operation="build")["reason"] == "stats-release-operation-refused"


def test_cleanup_refuses_symlink_without_touching_target(tmp_path):
    parent,result,context=prepared(tmp_path)
    original=tmp_path/"original-resource"
    context.rename(original)
    foreign=tmp_path/"foreign-target"
    foreign.write_bytes(b"preserve")
    context.symlink_to(foreign)
    removed=cleanup(parent,result)
    assert (removed["ok"],removed["reason"],context.is_symlink(),foreign.read_bytes(),
            hashlib.sha256(original.read_bytes()).hexdigest()) == (
        False,"resource-cleanup-file-changed",True,b"preserve",RESOURCE["source_sha256"])


def test_cleanup_refuses_inexact_identifiers_without_deleting(tmp_path):
    parent,result,context=prepared(tmp_path)
    record=json.loads(result["outputs"]["owned"])
    record["ino"]=2**53
    result["outputs"]["owned"]=json.dumps(record)
    removed=cleanup(parent,result)
    assert (removed["ok"],removed["reason"],
            hashlib.sha256(context.read_bytes()).hexdigest()) == (
        False,"resource-cleanup-contract-invalid",RESOURCE["source_sha256"])
