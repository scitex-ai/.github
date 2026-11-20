"""Exercise the actual shared publisher without credentials or network access."""
import io
import json
from pathlib import Path

import pytest
import yaml

WORKFLOW = yaml.safe_load((Path(__file__).resolve().parents[1] /
                          '.github/workflows/rtd-publish.yml').read_text())
STEP = WORKFLOW['jobs']['publish']['steps'][0]
NAMESPACE = {'__name__': 'publisher_contract'}
exec(compile(STEP['run'], '<rtd-publish>', 'exec'), NAMESPACE)
PUBLISH = NAMESPACE['publish']
SHA = 'a' * 40
ENV = {'RTD_PROJECT': 'scitex-live-paper', 'RTD_VERSION': 'latest',
       'RTD_PAGE': 'architecture.html', 'RTD_EXPECTED_TEXT': 'Scientific Paper Architecture',
       'SOURCE_REPOSITORY': 'scitex-ai/scitex-live-paper', 'SOURCE_BRANCH': 'develop',
       'SOURCE_COMMIT': SHA, 'RTD_TOKEN': 'synthetic-test-token'}


class Response(io.BytesIO):
    status = 200


class Server:
    def __init__(self, *, commit=SHA, success=True, repository=None, running=False, html=None):
        self.requests = []
        self.commit, self.success, self.running = commit, success, running
        self.repository = repository or 'https://github.com/scitex-ai/scitex-live-paper.git'
        self.html = html or '<html><h1>Scientific Paper Architecture</h1></html>'

    def open(self, request, timeout):
        self.requests.append(request)
        if '.readthedocs.io/' in request.full_url:
            assert request.get_header('Authorization') is None
            # RTD's public Cloudflare endpoint rejects Python-urllib's default
            # agent with 1010; identify our client explicitly instead.
            assert request.get_header('User-agent').startswith('SciTeX-Documentation-Publisher/')
            return Response(self.html.encode())
        assert request.get_header('Authorization') == 'Token synthetic-test-token'
        if request.get_method() == 'POST':
            value = {'build': {'id': 42}}
        elif request.full_url.endswith('/builds/42/'):
            value = {'state': {'code': 'building' if self.running else 'finished'},
                     'success': self.success, 'commit': self.commit}
        elif '/versions/latest/' in request.full_url:
            value = {'type': 'branch', 'identifier': 'develop'}
        else:
            value = {'repository': {'url': self.repository}, 'default_branch': 'develop'}
        return Response(json.dumps(value).encode())


def test_success_checks_exact_commit_and_public_contents():
    server = Server()
    receipt = PUBLISH(ENV, opener=server)
    assert receipt['source_commit'] == SHA and receipt['build_id'] == 42
    assert receipt['verified_url'].endswith('/en/latest/architecture.html')
    assert len([r for r in server.requests if r.get_method() == 'POST']) == 1


@pytest.mark.parametrize('options,match', [
    ({'commit': 'b' * 40}, 'different commit'),
    ({'success': False}, 'failed'),
    ({'repository': 'https://github.com/another/repo.git'}, 'caller repository'),
])
def test_build_or_repository_mismatch_is_never_success(options, match):
    with pytest.raises((ValueError, RuntimeError), match=match):
        PUBLISH(ENV, opener=Server(**options))


@pytest.mark.parametrize('page', ['../secrets.html', '/index.html', 'x//a.html',
                                 'a.html?x=1', 'a\\b.html', 'https://host/x.html'])
def test_invalid_page_is_rejected_before_network(page):
    server = Server()
    with pytest.raises(ValueError):
        PUBLISH(dict(ENV, RTD_PAGE=page), opener=server)
    assert not server.requests


@pytest.mark.parametrize('options', [{'running': True}, {'html': '<html>Wrong contents</html>'}])
def test_waits_are_bounded_and_http_200_alone_is_insufficient(options):
    elapsed = [0]
    def sleep(seconds):
        elapsed[0] += seconds
    with pytest.raises(TimeoutError):
        PUBLISH(ENV, opener=Server(**options), now=lambda: elapsed[0], sleep=sleep)
    assert elapsed[0] == 600


def test_job_does_not_check_out_source_or_receive_implicit_secrets():
    job = WORKFLOW['jobs']['publish']
    assert job['runs-on'] == 'ubuntu-latest'
    assert 'pull_request' not in job['if']
    assert "refs/heads/main" in job['if'] and "refs/heads/develop" in job['if']
    assert not any('checkout' in step.get('uses', '') for step in job['steps'])
    assert STEP['env']['RTD_TOKEN'] == '${{ secrets.RTD_TOKEN }}'
    assert WORKFLOW['permissions'] == {'contents': 'read'}
