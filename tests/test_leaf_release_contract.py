"""Exercise the registered dispatcher with real Node and its Writer adapter."""
import json
import subprocess
from pathlib import Path
import yaml
import test_writer_release_contract as writer

ROOT = Path(__file__).resolve().parents[1]

def dispatch(**changes):
    value = dict(repository='scitex-ai/scitex-io', event='workflow_dispatch',
                 native=True, operation='test', source='a'*40, tag='v0.4.2')
    value.update(changes)
    code = writer.blocks('WRITER_RELEASE_CONTRACT')[0] + '''
const x = JSON.parse(process.argv[1]);
try { const plan = Object.hasOwn(x, 'registration')
 ? ioPlan(x.repository,x.event,x.native,x.operation,x.source,x.tag,x.registration)
 : leafReleasePlan(x.repository,x.event,x.native,x.operation,x.source,x.tag);
 console.log(JSON.stringify({ok:true,plan})); }
catch (e) {console.log(JSON.stringify({ok:false,reason:e.message}));}
'''
    result = subprocess.run(['node','-e',code,json.dumps(value)],capture_output=True,
                            text=True,check=True,timeout=5)
    return json.loads(result.stdout)

def test_io_qualified_profile_uses_actual_image_complete_closure_and_worker_budget():
    plan = dispatch()['plan']
    assert (plan['image']['sha256'], plan['versions'], plan['pytestWorkers'],
            set(plan['leafSources'])) == (
        'e8461fc77a2218b5f7e2c475bd601dddaec97c6335bee459a1b0d4e0ca374d83',
        ['3.11', '3.12', '3.13'], 4, {
            '.github/ci/exec-in-sif.sh', '.github/ci/release-context.sh',
            '.github/ci/run-in-sif.sh', '.github/ci/build-in-sif.sh',
            '.github/ci/publish-in-sif.sh', '.github/ci/release-identity.py',
            '.github/ci/_release_artifacts.py', '.github/ci/_release_source.py',
            '.github/ci/probe-first-observer.py', '.github/ci/io_test_store.py'})


def test_io_build_profile_keeps_only_qualified_build_interpreter():
    assert dispatch(operation='build')['plan']['versions'] == ['3.12']


def test_io_missing_registration_remains_failed_closed():
    assert dispatch(registration=None)['reason'] == 'io-runtime-unregistered'


def test_io_partial_registration_remains_failed_closed():
    assert dispatch(registration={})['reason'] == 'io-runtime-unregistered'

def test_unknown_repository_cannot_select_any_profile():
    assert dispatch(repository='scitex-ai/unknown')['reason'] == 'release-repository-refused'

def test_nonmember_cannot_reach_io_registration():
    assert dispatch(native=False)['reason'] == 'io-release-membership-required'

def test_fork_event_cannot_reach_io_registration():
    assert dispatch(event='pull_request')['reason'] == 'io-release-event-refused'

def test_arbitrary_operation_cannot_reach_io_registration():
    assert dispatch(operation='publish')['reason'] == 'io-release-operation-refused'

def test_floating_source_cannot_reach_io_registration():
    assert dispatch(source='develop')['reason'] == 'io-source-commit-refused'

def test_tag_injection_cannot_reach_io_registration():
    assert dispatch(tag='v0.4.2; false')['reason'] == 'io-release-tag-refused'

def test_writer_compatibility_caller_forwards_exact_original_inputs():
    source=yaml.safe_load((ROOT/'.github/workflows/writer-release-sif.yml').read_text())
    job=source['jobs']['release-driver']
    assert job == {'uses':'./.github/workflows/leaf-release-sif.yml', 'with':{
      'operation':'${{ inputs.operation }}', 'source_commit':'${{ inputs.source_commit }}',
      'release_tag':'${{ inputs.release_tag }}'}}

def test_writer_dispatch_retains_qualified_original_profile():
    result=dispatch(repository='scitex-ai/scitex-writer',tag='v2.43.17')
    assert result['plan'] == writer.run_policy(tag='v2.43.17',registration='production')['plan']


def test_scholar_source_protocol_refuses_unqualified_native_registration():
    assert dispatch(repository='scitex-ai/scitex-scholar', tag='v1.29.1')['reason'] == 'scholar-runtime-unregistered'


def test_scholar_nonmember_remains_refused_before_registration():
    assert dispatch(repository='scitex-ai/scitex-scholar', native=False)['reason'] == 'scholar-release-membership-required'


def test_scholar_fork_cannot_reach_registration():
    assert dispatch(repository='scitex-ai/scitex-scholar', event='pull_request')['reason'] == 'scholar-release-event-refused'


def test_scholar_unsupported_operation_is_refused():
    assert dispatch(repository='scitex-ai/scitex-scholar', operation='publish')['reason'] == 'scholar-release-operation-refused'


def test_scholar_floating_source_is_refused():
    assert dispatch(repository='scitex-ai/scitex-scholar', source='develop')['reason'] == 'scholar-source-commit-refused'


def test_scholar_tag_injection_is_refused():
    assert dispatch(repository='scitex-ai/scitex-scholar', tag='v1.29.1; false')['reason'] == 'scholar-release-tag-refused'
