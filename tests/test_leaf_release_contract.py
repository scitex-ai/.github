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
try { console.log(JSON.stringify({ok:true,plan:leafReleasePlan(x.repository,
 x.event,x.native,x.operation,x.source,x.tag)})); }
catch (e) {console.log(JSON.stringify({ok:false,reason:e.message}));}
'''
    result = subprocess.run(['node','-e',code,json.dumps(value)],capture_output=True,
                            text=True,check=True,timeout=5)
    return json.loads(result.stdout)

def test_io_remains_failed_closed_until_actual_qualification():
    assert dispatch()['reason'] == 'io-runtime-unregistered'

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
