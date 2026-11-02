"""Execute the reusable install/worker policy with disposable command fixtures."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_WORKFLOW = Path(__file__).parents[1] / '.github/workflows/pytest-matrix.yml'


def _workflow():
    return yaml.safe_load(_WORKFLOW.read_text())


def _install_step():
    steps = _workflow()['jobs']['pytest-matrix']['steps']
    return next(step for step in steps if step.get('name') == 'Install (.[all,dev]) + pytest')


def _install_script():
    # Execute the actual workflow through its explicit xdist install, then witness
    # whether execution could reach later preparation/tests after a failed install.
    source = _install_step()['run'].split('# kaleido', 1)[0]
    return source.replace('${{ matrix.python-version }}', '3.12') + '\ntouch reached-tests\n'


def _run_install(tmp_path, group, fail_full):
    binary = tmp_path / 'bin'
    binary.mkdir()
    uv = binary / 'uv'
    uv.write_text(f'#!/usr/bin/env -S {sys.executable} -I -S\n' + '''import json, os, pathlib, sys
args = sys.argv[1:]
with open('uv-argv.jsonl', 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
if args[0] == 'venv':
    pathlib.Path('.venv/bin').mkdir(parents=True)
    sys.exit(0)
full = '.[all,dev]' in args or '.[all]' in args
if full and os.environ['FAIL_FULL'] == '1':
    print('failed to read disposable uv archive fixture', file=sys.stderr)
    sys.exit(37)
path = pathlib.Path('.venv/bin/pytest')
path.write_text('#!/bin/sh\\nexit 0\\n')
path.chmod(0o700)
''')
    uv.chmod(0o700)
    completed = subprocess.run(
        ['/bin/bash', '-c', _install_script()], cwd=tmp_path,
        env={**os.environ, 'PATH': str(binary) + os.pathsep + os.defpath,
             'DEPENDENCY_GROUP': group, 'FAIL_FULL': '1' if fail_full else '0'},
        capture_output=True, text=True, timeout=5,
    )
    calls = [json.loads(line) for line in (tmp_path / 'uv-argv.jsonl').read_text().splitlines()]
    return completed, calls


@pytest.mark.parametrize('group', ['', 'dev'])
def test_failed_declared_install_never_retries_reduced_extras_or_reaches_tests(tmp_path, group):
    # Arrange / Act — real bash set-e and a real failing child process.
    result, calls = _run_install(tmp_path, group, fail_full=True)
    # Assert
    assert (result.returncode, len(calls), (tmp_path / 'reached-tests').exists()) == (37, 2, False)
    assert 'failed to read disposable uv archive fixture' in result.stderr


@pytest.mark.parametrize('group,target,tail', [('', '.[all,dev]', []), ('dev', '.[all]', ['--group', 'dev'])])
def test_successful_install_preserves_runtime_extra_and_toolchain_choice(tmp_path, group, target, tail):
    # Arrange / Act
    result, calls = _run_install(tmp_path, group, fail_full=False)
    # Assert
    assert result.returncode == 0, result.stderr
    assert calls[1] == ['pip', 'install', '--python', '.venv/bin/python', '-e', target, *tail]
    assert calls[2] == ['pip', 'install', '--python', '.venv/bin/python', 'pytest-xdist>=3.0.0']
    assert (tmp_path / 'reached-tests').exists()


def _worker_script():
    run = _install_step()['run']
    return run.split("WORKERS=$(.venv/bin/python - <<'PY'\n", 1)[1].split('\nPY\n)', 1)[0]


def _run_workers(configured, quota='max 100000'):
    source = _worker_script()
    # The policy code itself is unchanged; deterministic kernel allocation inputs.
    prelude = ('import os\nfrom pathlib import Path\n'
               'os.cpu_count = lambda: 32\n'
               'os.sched_getaffinity = lambda pid: set(range(32))\n'
               f'Path.read_text = lambda self: {quota!r}\n')
    return subprocess.run(
        [sys.executable, '-I', '-S', '-c', prelude + source],
        env={**os.environ, 'CI_XDIST_WORKERS': configured},
        capture_output=True, text=True, timeout=5,
    )


@pytest.mark.parametrize('configured,quota,expected', [
    ('', 'max 100000', '32'), ('4', 'max 100000', '4'),
    ('128', 'max 100000', '32'), ('4', '200000 100000', '2'),
])
def test_explicit_worker_cap_respects_actual_allocation(configured, quota, expected):
    # Arrange / Act
    result = _run_workers(configured, quota)
    # Assert
    assert (result.returncode, result.stdout.strip()) == (0, expected)


@pytest.mark.parametrize('configured', ['0', '-1', 'auto', 'NaN', '4;touch injected', '４'])
def test_invalid_worker_cap_fails_instead_of_oversubscribing(configured):
    # Arrange / Act
    result = _run_workers(configured)
    # Assert
    assert result.returncode != 0
    assert 'CI_XDIST_WORKERS must be a positive integer' in result.stderr


def test_worker_input_and_repository_variable_reach_policy_without_shell_interpolation():
    # Arrange
    data = _workflow()
    call = data.get('on', data.get(True))['workflow_call']['inputs']
    # Act / Assert
    assert call['xdist_workers']['default'] == ''
    assert _install_step()['env']['CI_XDIST_WORKERS'] == '${{ inputs.xdist_workers || vars.CI_XDIST_WORKERS }}'
    assert '${{ inputs.xdist_workers' not in _install_step()['run']
