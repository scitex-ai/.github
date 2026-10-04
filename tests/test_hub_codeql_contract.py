"""Actual complete CodeQL body and fixed member/outsider routing contract."""

import copy
import hashlib
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / '.github/workflows/hub-codeql-security-analysis.yml'
FIXTURE = ROOT / 'tests/fixtures/hub-original-codeql-analysis.yml'
CALLER = ROOT / 'tests/fixtures/hub-proposed-caller-codeql-analysis.yml'


def sources():
    raw = FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != (
        'e09081aa51ef15a2d9c4127ec784479e44f79512201652897ac3246cd404eb07'
    ):
        raise ValueError('Whole original CodeQL Git body changed')
    return yaml.safe_load(raw), yaml.safe_load(WORKFLOW.read_text())


def test_complete_original_codeql_payload_and_job_fields_are_preserved():
    # Arrange
    original, candidate = sources()
    restored = copy.deepcopy(candidate['jobs']['analyze'])
    # Act
    restored.pop('needs')
    restored['runs-on'] = original['jobs']['analyze']['runs-on']
    restored['steps'] = [original['jobs']['analyze']['steps'][0]] + restored['steps'][3:]
    # Assert
    assert restored == original['jobs']['analyze']


def test_caller_retains_all_original_events_concurrency_and_security_permissions():
    # Arrange
    original, _candidate = sources()
    caller = yaml.safe_load(CALLER.read_text())
    # Act
    observed = (
        caller['name'], caller.get('on', caller.get(True)), caller['concurrency'],
        caller['jobs']['analyze'],
    )
    # Assert
    assert observed == (
        original['name'], original.get('on', original.get(True)), original['concurrency'],
        {
            'name': 'Analyze Code',
            'uses': 'scitex-ai/.github/.github/workflows/hub-codeql-security-analysis.yml@main',
            'permissions': original['jobs']['analyze']['permissions'],
        },
    )


def test_fixed_callee_has_no_input_command_secret_or_oidc_and_exact_gate():
    # Arrange
    original, candidate = sources()
    # Act
    observed = (
        candidate.get('on', candidate.get(True)), candidate['permissions'],
        candidate['jobs']['runner-admission'], set(candidate['jobs']),
    )
    # Assert
    assert observed == (
        {'workflow_call': None}, original['jobs']['analyze']['permissions'],
        {
            'uses': './.github/workflows/runner-admission.yml',
            'with': {'runs_on': '["self-hosted","Linux","X64","scitex-org-cpu"]'},
        },
        {'runner-admission', 'analyze'},
    )


def test_checkout_follows_all_fork_membership_and_fixed_repository_guards():
    # Arrange
    _original, candidate = sources()
    job = candidate['jobs']['analyze']
    # Act
    observed = (
        job['needs'], job['runs-on'],
        [step['name'] for step in job['steps'][:4]],
        job['steps'][0]['if'], job['steps'][1]['if'], job['steps'][2]['env'],
    )
    # Assert
    assert observed == (
        ['runner-admission'],
        (
            "${{ (github.event_name == 'pull_request' && "
            "github.event.pull_request.head.repo.full_name != github.repository) "
            "&& fromJSON('[\"ubuntu-latest\"]') || "
            "fromJSON(needs.runner-admission.outputs.runs_on) }}"
        ),
        [
            'Refuse to run fork-authored code on self-hosted infrastructure',
            'Require confirmed organization membership on native runners',
            'Require the fixed Hub repository before checkout', 'Checkout repository',
        ],
        (
            "github.event_name == 'pull_request' && "
            'github.event.pull_request.head.repo.full_name != github.repository && '
            "runner.environment == 'self-hosted'"
        ),
        (
            "runner.environment == 'self-hosted' && "
            "needs.runner-admission.outputs.native_authorized != 'true'"
        ),
        {'EXPECTED_REPOSITORY': 'scitex-ai/scitex-hub'},
    )


@pytest.mark.parametrize('key', ['permissions', 'strategy', 'name'])
def test_original_both_languages_fail_fast_and_permissions_are_exact(key):
    # Arrange
    original, candidate = sources()
    # Act
    before, after = original['jobs']['analyze'][key], candidate['jobs']['analyze'][key]
    # Assert
    assert after == before


@pytest.mark.parametrize(
    'step_name',
    ['Set up Node.js (JS/TS extractor requires it)', 'Initialize CodeQL',
     'Autobuild', 'Perform CodeQL Analysis'],
)
def test_original_node_security_pack_autobuild_and_analysis_are_whole_equal(step_name):
    # Arrange
    original, candidate = sources()
    # Act
    observed = [next(s for s in body['jobs']['analyze']['steps']
                     if s.get('name') == step_name) for body in (original, candidate)]
    # Assert
    assert observed[0] == observed[1]


@pytest.mark.parametrize(
    'repository,exit_code',
    [('scitex-ai/scitex-hub', 0), ('scitex-ai/other', 1), ('outsider/scitex-hub', 1), ('', 1)],
)
def test_actual_fixed_repo_shell_accepts_only_hub_before_checkout(repository, exit_code):
    # Arrange
    _original, candidate = sources()
    step = candidate['jobs']['analyze']['steps'][2]
    environment = {'PATH': '/usr/bin:/bin', 'GITHUB_REPOSITORY': repository, **step['env']}
    # Act
    result = subprocess.run(['/bin/bash', '-c', step['run']], env=environment,
                            capture_output=True, timeout=2, check=False)
    # Assert
    assert (result.returncode, result.stdout, result.stderr) == (exit_code, b'', b'')


@pytest.mark.parametrize('index', [0, 1])
def test_actual_before_checkout_refusal_shells_fail_loudly(index):
    # Arrange
    _original, candidate = sources()
    step = candidate['jobs']['analyze']['steps'][index]
    # Act
    result = subprocess.run(['/bin/bash', '-c', step['run']],
                            env={'PATH': '/usr/bin:/bin'}, capture_output=True,
                            timeout=2, check=False)
    # Assert
    assert (result.returncode, b'::error::' in result.stdout, result.stderr) == (1, True, b'')
