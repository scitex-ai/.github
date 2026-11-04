"""Execute the production shell with real local Git and an owned GH boundary."""

import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / '.github/workflows/promote-develop-to-main-on-tag.yml'


def git(root, *args):
    return subprocess.check_output(
        ['/usr/bin/git', '-C', str(root), *args], text=True,
        stderr=subprocess.PIPE, timeout=20,
    ).strip()


@pytest.fixture
def promotion(tmp_path, monkeypatch):
    """All refs, Git configuration, GH argv and resulting merges are owned."""
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', '/dev/null')
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    origin = tmp_path / 'origin.git'
    seed = tmp_path / 'seed'
    seed.mkdir()
    git(tmp_path, 'init', '--bare', str(origin))
    git(seed, 'init', '-b', 'main')
    git(seed, 'config', 'user.name', 'Owned Fixture')
    git(seed, 'config', 'user.email', 'fixture@example.invalid')
    (seed / 'base.txt').write_text('base\n')
    git(seed, 'add', '.')
    git(seed, 'commit', '-m', 'Base')
    base = git(seed, 'rev-parse', 'HEAD')
    git(seed, 'checkout', '-b', 'develop')
    (seed / 'release.txt').write_text('qualified release\n')
    git(seed, 'add', '.')
    git(seed, 'commit', '-m', 'Qualified tag')
    tag = git(seed, 'rev-parse', 'HEAD')
    git(seed, 'tag', 'v1.2.3')
    (seed / 'future.txt').write_text('unqualified future\n')
    git(seed, 'add', '.')
    git(seed, 'commit', '-m', 'Future develop')
    future = git(seed, 'rev-parse', 'HEAD')
    git(seed, 'remote', 'add', 'origin', str(origin))
    git(seed, 'push', 'origin', 'main', 'develop', '--tags')
    git(origin, 'update-ref', 'refs/heads/develop', tag)
    checkout = tmp_path / 'checkout'
    git(tmp_path, 'clone', str(origin), str(checkout))
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    driver = (REPO / 'tests/_promotion_gh_boundary.py').read_text()
    boundary = bindir / 'gh'
    boundary.write_text(f'#!{sys.executable}\n' + driver)
    boundary.chmod(0o700)
    shell = next(
        step['run'] for step in yaml.safe_load(WORKFLOW.read_text())['jobs']['promote']['steps']
        if step.get('name') == 'Open + auto-merge develop -> main (MERGE commit, never squash)'
    ).replace('${{ github.actor }}', 'owned-fixture')
    env = {
        'PATH': f'{bindir}:/usr/bin:/bin', 'HOME': str(tmp_path),
        'LANG': 'C.UTF-8', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_CONFIG_NOSYSTEM': '1', 'GITHUB_STEP_SUMMARY': str(tmp_path / 'summary'),
        'REPO': 'owned/fixture', 'DEV': 'develop', 'MAIN': 'main', 'TAG': 'v1.2.3',
        'PROMOTION_FIXTURE': str(tmp_path), 'TAG_SHA': tag, 'FUTURE_SHA': future,
    }

    def run(mode='safe'):
        return subprocess.run(
            ['/bin/bash', '-c', shell], cwd=checkout,
            env={**env, 'PROMOTION_MODE': mode}, capture_output=True,
            text=True, timeout=30,
        )

    return tmp_path, origin, base, tag, future, run


def calls(root):
    path = root / 'calls.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_contained_tag_skips_advanced_develop_without_gh(promotion):
    # Arrange: tag is already in main, but newer develop must not be promoted.
    root, origin, _, tag, future, run = promotion
    git(origin, 'update-ref', 'refs/heads/main', tag)
    git(origin, 'update-ref', 'refs/heads/develop', future)
    # Act
    result = run()
    # Assert
    assert (result.returncode, calls(root), git(origin, 'rev-parse', 'main')) == (0, [], tag)


def test_unqualified_advanced_develop_refuses_before_gh(promotion):
    # Arrange
    root, origin, base, _, future, run = promotion
    git(origin, 'update-ref', 'refs/heads/develop', future)
    # Act
    result = run()
    # Assert
    assert (result.returncode != 0, calls(root), git(origin, 'rev-parse', 'main')) == (True, [], base)


def test_racing_head_is_refused_by_normal_expected_head_boundary(promotion):
    # Arrange
    root, origin, base, tag, _, run = promotion
    # Act: owned GH boundary advances develop after preflight.
    result = run('race')
    merge = calls(root)[-1]
    # Assert
    assert (
        result.returncode != 0, git(origin, 'rev-parse', 'main'),
        '--admin' not in merge, merge[merge.index('--match-head-commit') + 1],
        'Head changed' in result.stderr,
    ) == (True, base, True, tag, True)


def test_normal_merge_preserves_qualified_tag_ancestor(promotion):
    # Arrange
    root, origin, base, tag, _, run = promotion
    # Act
    result = run()
    parents = git(origin, 'show', '-s', '--format=%P', 'main').split()
    # Assert: a real local merge, not a synthetic success response.
    assert (result.returncode, parents, calls(root)[-1][-3:]) == (
        0, [base, tag], ['--merge', '--match-head-commit', tag],
    )


def test_unresolvable_tag_refuses_before_gh(promotion):
    # Arrange
    root, origin, base, _, _, run = promotion
    git(root / 'checkout', 'tag', '-d', 'v1.2.3')
    # Act
    result = run()
    # Assert
    assert (result.returncode != 0, calls(root), git(origin, 'rev-parse', 'main')) == (True, [], base)
