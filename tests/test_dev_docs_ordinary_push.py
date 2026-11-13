"""Execute the production Dev push script against real owned Git repositories."""
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEST = 'src/scitex_dev/_sphinx_html'


def git(cwd, env, *args):
    return subprocess.run(['git', *args], cwd=cwd, env=env, check=True,
                          text=True, capture_output=True, timeout=5).stdout.strip()


@pytest.mark.parametrize('case', ['fresh', 'unchanged', 'existing', 'foreign-index',
                                  'advanced', 'missing-remote', 'commit-refused', 'push-refused'])
def test_actual_normal_push_preserves_foreign_state_and_refusals(tmp_path, case):
    repo = tmp_path / 'repo'; remote = tmp_path / 'remote.git'; home = tmp_path / 'home'
    repo.mkdir(); home.mkdir()
    env = {'PATH': os.defpath, 'HOME': str(home), 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_ALLOW_PROTOCOL': 'file'}
    git(repo, env, 'init', '--initial-branch=develop')
    git(repo, env, 'init', '--bare', str(remote))
    git(repo, env, 'config', 'user.name', 'Fixture')
    git(repo, env, 'config', 'user.email', 'fixture@example.invalid')
    page = repo / DEST / 'guide.html'; page.parent.mkdir(parents=True); page.write_text('old')
    git(repo, env, 'add', '.')
    git(repo, env, 'commit', '-m', 'base')
    source = git(repo, env, 'rev-parse', 'HEAD')
    git(repo, env, 'remote', 'add', 'origin', str(remote))
    git(repo, env, 'push', 'origin', 'HEAD:refs/heads/develop')
    branch = f'ci/dev-sphinx-{source}-12345'
    if case != 'unchanged': page.write_text('rendered')
    if case == 'existing': git(repo, env, 'push', 'origin', f'HEAD:refs/heads/{branch}')
    if case == 'foreign-index':
        (repo / 'foreign.txt').write_text('preserve')
        git(repo, env, 'add', 'foreign.txt')
    if case == 'advanced':
        (repo / 'foreign.txt').write_text('preserve')
        git(repo, env, 'add', 'foreign.txt')
        git(repo, env, 'commit', '-m', 'advanced source')
    before = git(repo, env, 'rev-parse', 'HEAD')
    if case == 'missing-remote': git(repo, env, 'remote', 'set-url', 'origin', str(tmp_path/'absent'))
    if case in {'commit-refused', 'push-refused'}:
        hook = repo/'.git/hooks/pre-commit' if case == 'commit-refused' else remote/'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o700)
    output = tmp_path / 'outputs'; output.touch()
    env.update(BUNDLE_DIR=DEST, EXPECTED_SOURCE=source, WORKFLOW_RUN_ID='12345',
               PR_BRANCH=branch, GITHUB_OUTPUT=str(output))
    steps = yaml.safe_load((ROOT/'.github/workflows/rtd-sphinx-build.yml').read_text())['jobs']['publish-sphinx-bundle']['steps']
    script = next(s['run'] for s in steps if s.get('id') == 'dev-docs-commit')
    assert '--force' not in script and '--no-verify' not in script
    result = subprocess.run(['/bin/bash', '-c', script], cwd=repo, env=env,
                            text=True, capture_output=True, timeout=10)
    accepted = case in {'fresh', 'unchanged'}
    assert (result.returncode == 0) == accepted, result.stderr
    refs = git(repo, env, '--git-dir='+str(remote), 'show-ref', '--heads')
    assert next(line.split()[0] for line in refs.splitlines() if line.endswith('refs/heads/develop')) == source
    remote_head = next((line.split()[0] for line in refs.splitlines()
                        if line.endswith('refs/heads/'+branch)), None)
    fields = dict(line.split('=', 1) for line in output.read_text().splitlines())
    if case == 'fresh':
        assert fields == {'changed': 'true', 'branch': branch,
                          'head': git(repo, env, 'rev-parse', 'HEAD')}
        assert remote_head == fields['head']
        assert git(repo, env, 'rev-parse', 'HEAD^') == source
        assert git(repo, env, 'diff', '--name-only', source, 'HEAD') == DEST+'/guide.html'
        assert git(repo, env, 'show', 'HEAD:'+DEST+'/guide.html') == 'rendered'
    elif case == 'unchanged':
        assert fields == {'changed': 'false'} and remote_head is None
    else:
        assert fields == {} and remote_head == (source if case == 'existing' else None)
        assert git(repo, env, 'rev-parse', 'HEAD') == before or case == 'push-refused'
        if case == 'foreign-index':
            assert git(repo, env, 'diff', '--cached', '--name-only') == 'foreign.txt'
