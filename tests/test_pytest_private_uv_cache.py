"""Real shell controls for private CI uv-cache allocation and environment handoff."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import os
import stat
import subprocess
from pathlib import Path


from test_pytest_declared_install import _install_script, _workflow


def _steps():
    return _workflow()['jobs']['pytest-matrix']['steps']


def _cache_step():
    return next(step for step in _steps() if step.get('name') == 'Create a private uv cache for this job')


def _prepare(root, inherited, envfile=None):
    envfile = envfile or root / 'job-env'
    result = subprocess.run(
        ['/bin/bash', '-c', _cache_step()['run']],
        env={**os.environ, 'RUNNER_TEMP': str(root), 'GITHUB_ENV': str(envfile),
             'UV_CACHE_DIR': str(inherited)},
        capture_output=True, text=True, timeout=5,
    )
    values = dict(line.split('=', 1) for line in envfile.read_text().splitlines()) if envfile.exists() else {}
    return result, values


def test_concurrent_job_caches_are_fresh_private_and_preserve_inherited_state(tmp_path):
    # Arrange — a disposable representation of the runner's inherited cache.
    shared = tmp_path / 'shared'
    shared.mkdir()
    marker = shared / 'archive-marker'
    marker.write_bytes(b'existing shared archive remains unchanged\x00')
    baseline = marker.read_bytes()
    # Act — two independent jobs share the runner temp and inherited environment.
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(_prepare, tmp_path, shared, tmp_path / name) for name in ('first.env', 'second.env')]
        (first_result, first_env), (second_result, second_env) = [job.result() for job in jobs]
    caches = [Path(row['UV_CACHE_DIR']) for row in (first_env, second_env)]
    # Assert
    assert (first_result.returncode, second_result.returncode) == (0, 0)
    assert caches[0] != caches[1]
    assert all(path.parent == tmp_path and path.name.startswith('scitex-pytest-uv.') for path in caches)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 and list(path.iterdir()) == [] for path in caches)
    assert marker.read_bytes() == baseline
    assert sorted(path.name for path in shared.iterdir()) == ['archive-marker']


def test_actual_install_inherits_prepared_cache_not_runner_shared_cache(tmp_path):
    # Arrange
    import sys

    inherited = tmp_path / 'shared'
    inherited.mkdir()
    result, exported = _prepare(tmp_path, inherited)
    assert result.returncode == 0, result.stderr
    binary = tmp_path / 'bin'
    binary.mkdir()
    uv = binary / 'uv'
    uv.write_text(f'#!/usr/bin/env -S {sys.executable} -I -S\n' + '''import json, os, pathlib, sys
with open('installer-caches.jsonl', 'a') as stream:
    stream.write(json.dumps(os.environ['UV_CACHE_DIR']) + '\\n')
if sys.argv[1] == 'venv':
    pathlib.Path('.venv/bin').mkdir(parents=True)
else:
    path = pathlib.Path('.venv/bin/pytest')
    path.write_text('#!/bin/sh\\nexit 0\\n')
    path.chmod(0o700)
''')
    uv.chmod(0o700)
    # Act — apply the actual GITHUB_ENV export to the later actual install shell.
    installed = subprocess.run(
        ['/bin/bash', '-c', _install_script()], cwd=tmp_path,
        env={**os.environ, 'UV_CACHE_DIR': str(inherited), **exported,
             'DEPENDENCY_GROUP': '', 'PATH': str(binary) + os.pathsep + os.defpath},
        capture_output=True, text=True, timeout=5,
    )
    observed = [json.loads(line) for line in (tmp_path / 'installer-caches.jsonl').read_text().splitlines()]
    # Assert
    assert installed.returncode == 0, installed.stderr
    assert observed == [exported['UV_CACHE_DIR']] * 3
    assert list(inherited.iterdir()) == []


def test_failed_cache_allocation_stops_before_setup_or_install(tmp_path):
    # Arrange — RUNNER_TEMP must exist; failing allocation cannot reuse shared state.
    missing = tmp_path / 'missing'
    # Act
    result, exported = _prepare(missing, tmp_path / 'inherited')
    # Assert
    assert result.returncode != 0
    assert exported == {}


def test_setup_uv_runs_after_private_cache_and_disables_archive_restore():
    # Arrange
    steps = _steps()
    preparation = steps.index(_cache_step())
    setup = next(index for index, step in enumerate(steps) if step.get('uses') == 'astral-sh/setup-uv@v7')
    # Act / Assert
    callback = next(index for index, step in enumerate(steps) if step.get('name') == 'Repository-specific test preparation')
    assert preparation < callback < setup
    assert steps[setup]['with']['enable-cache'] is False
    assert 'UV_CACHE_DIR' not in steps[setup].get('env', {})
    assert not any('uv cache clean' in step.get('run', '') or 'uv cache prune' in step.get('run', '') for step in steps)


def test_empty_runner_temp_cannot_fall_back_to_inherited_cache(tmp_path):
    # Arrange
    envfile = tmp_path / 'job-env'
    # Act
    result = subprocess.run(
        ['/bin/bash', '-c', _cache_step()['run']],
        env={**os.environ, 'RUNNER_TEMP': '', 'GITHUB_ENV': str(envfile),
             'UV_CACHE_DIR': str(tmp_path / 'inherited')},
        capture_output=True, text=True, timeout=5,
    )
    # Assert
    assert result.returncode != 0
    assert not envfile.exists()
