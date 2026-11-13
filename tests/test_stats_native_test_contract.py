"""Stats tests use qualified native inputs and cannot transfer release artifacts."""
import hashlib
import json
from pathlib import Path
import urllib.request

import pytest
import yaml
import test_leaf_release_contract as leaf
import test_ci_resource_contract as resource

ROOT = Path(__file__).resolve().parents[1]
FACTS = json.loads((ROOT / 'tests/fixtures/release-core/stats-native.json').read_text())
OWNER = 'scitex-ai/scitex-stats'


def test_stats_plan_selects_complete_matrix_exact_runtime_closure_and_resource():
    plan = leaf.dispatch(repository=OWNER)['plan']
    assert (plan['versions'], plan['timeoutMinutes'], plan['leafSources'],
            plan['sharedResource'], plan['runtime']['qualification_sha256']) == (
        ['3.11', '3.12', '3.13'], 30, FACTS['leaf_sources'],
        FACTS['shared_resource'], FACTS['qualification_sha256'])
    assert plan['runner'] == {'group': 'Organization', 'labels': [
        'self-hosted', 'Linux', 'X64', 'scitex-org-cpu', 'scitex-compute-03']}
    assert plan['image']['sha256'] == 'e8461fc77a2218b5f7e2c475bd601dddaec97c6335bee459a1b0d4e0ca374d83'
    receipt = ROOT / 'tests/fixtures/release-core/stats-native-qualification.json'
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == FACTS['qualification_sha256']


@pytest.mark.parametrize(('changes', 'reason'), [
    ({'operation': 'build'}, 'stats-release-operation-refused'),
    ({'operation': 'publish'}, 'stats-release-operation-refused'),
    ({'native': False}, 'stats-release-membership-required'),
    ({'event': 'pull_request'}, 'stats-release-event-refused'),
    ({'source': 'develop'}, 'stats-source-commit-refused'),
    ({'tag': 'v1.0.0; false'}, 'stats-release-tag-refused'),
    ({'registration': None}, 'stats-runtime-unregistered'),
    ({'registration': {}}, 'stats-runtime-unregistered'),
])
def test_stats_refuses_unqualified_calls_and_every_artifact_operation(changes, reason):
    assert leaf.dispatch(repository=OWNER, **changes) == {'ok': False, 'reason': reason}


def test_stats_registered_resource_runs_real_stager_and_cleanup(tmp_path):
    plan = leaf.dispatch(repository=OWNER)['plan']
    tmp_path.chmod(0o700)
    result = resource.stage(tmp_path, plan['sharedResource'])
    assert result['ok'], result
    path = Path(result['outputs']['context'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == plan['sharedResource']['source_sha256']
    assert resource.cleanup(tmp_path, result)['ok']
    assert list(tmp_path.iterdir()) == []


def test_stats_all_public_immutable_helpers_equal_registered_byte_pins():
    hashes = {}
    for name in FACTS['leaf_sources']:
        url = f"https://raw.githubusercontent.com/{OWNER}/{FACTS['source']}/{name}"
        with urllib.request.urlopen(url, timeout=15) as response:
            assert response.status == 200 and response.url == url
            data = response.read(1024 * 1024 + 1)
        assert len(data) <= 1024 * 1024
        hashes[name] = hashlib.sha256(data).hexdigest()
    assert hashes == FACTS['leaf_sources']


def test_stats_job_retains_thirty_minute_limit_and_build_upload_conditions():
    job = yaml.safe_load((ROOT / '.github/workflows/leaf-release-sif.yml').read_text())['jobs']['native']
    assert job['timeout-minutes'] == "${{ fromJSON(needs.profile.outputs.plan).timeoutMinutes || (inputs.operation == 'build' && 30 || 60) }}"
    steps = job['steps']
    upload = next(s for s in steps if s.get('uses') == 'actions/upload-artifact@v4')
    build = next(s for s in steps if s.get('run', '').endswith('build-in-sif.sh 3.12'))
    assert upload['if'] == build['if'] == "inputs.operation == 'build'"
    gate = next(s for s in steps if s.get('id') == 'inputs')
    assert "profile == 'stats') &&" in gate['env']['NATIVE_CI_SIF']
