"""Execute actual expressions and source guards; fixture only platform context."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/rtd-sphinx-build.yml'
NODE = shutil.which('node')
SOURCE = 'a' * 40


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def node(code, value):
    result = subprocess.run([NODE, '-e', code, json.dumps(value)],
                            env={'PATH': os.defpath}, capture_output=True,
                            text=True, check=True, timeout=5)
    return json.loads(result.stdout)


def evaluate(expression, **changes):
    context = {'inputs': {'bundle_dir': 'src/scitex_dev/_sphinx_html',
                          'dev_original_commands': True},
               'github': {'event_name': 'push', 'ref_name': 'develop',
                          'ref': 'refs/heads/develop', 'sha': SOURCE, 'run_id': '12345'},
               'needs': {'docs-sphinx': {'result': 'skipped'},
                         'dev-original-sphinx': {'result': 'success'}},
               'cancelled': False}
    context.update(changes)
    context['expression'] = expression.strip().removeprefix('${{').removesuffix('}}').strip()
    return node(r"""
const x=JSON.parse(process.argv[1]);
const format=(s,...v)=>s.replace(/\{(\d+)\}/g,(_,i)=>String(v[Number(i)]));
const run=new Function('inputs','github','needs','always','cancelled','format',
 'return ('+x.expression+')');
process.stdout.write(JSON.stringify(run(x.inputs,x.github,x.needs,()=>true,()=>x.cancelled,format)));
""", context)


def marker(name):
    for step in workflow()['jobs']['publish-sphinx-bundle']['steps']:
        script = step.get('with', {}).get('script', '')
        if '// BEGIN ' + name in script:
            return script.split('// BEGIN ' + name, 1)[1].split('// END ' + name, 1)[0]
    raise AssertionError(name)


@pytest.mark.parametrize('dev', [False, True])
@pytest.mark.parametrize('state', ['success', 'failure', 'cancelled', 'skipped'])
def test_only_selected_successful_producer_can_publish(dev, state):
    inputs = {'bundle_dir': 'src/scitex_dev/_sphinx_html', 'dev_original_commands': dev}
    selected = 'dev-original-sphinx' if dev else 'docs-sphinx'
    other = 'docs-sphinx' if dev else 'dev-original-sphinx'
    needs = {selected: {'result': state}, other: {'result': 'skipped'}}
    assert evaluate(workflow()['jobs']['publish-sphinx-bundle']['if'], inputs=inputs,
                    needs=needs) == (state == 'success')


@pytest.mark.parametrize('event', ['push', 'pull_request', 'workflow_dispatch'])
@pytest.mark.parametrize('cancelled', [False, True])
def test_publication_refuses_nonpush_and_cancellation(event, cancelled):
    github = {'event_name': event, 'ref': 'refs/heads/develop'}
    assert evaluate(workflow()['jobs']['publish-sphinx-bundle']['if'], github=github,
                    cancelled=cancelled) == (event == 'push' and not cancelled)


@pytest.mark.parametrize('dev', [False, True])
@pytest.mark.parametrize('ref', [
    'refs/heads/develop', 'refs/heads/main', 'refs/heads/feature',
    'refs/tags/v0.62.30',
])
def test_dev_staging_selects_only_develop_and_preserves_generic_pushes(dev, ref):
    # Exercise the actual job expression, including the main-push context
    # that previously selected a job its own source guard must refuse.
    inputs = {'bundle_dir': 'src/scitex_dev/_sphinx_html',
              'dev_original_commands': dev}
    selected = 'dev-original-sphinx' if dev else 'docs-sphinx'
    other = 'docs-sphinx' if dev else 'dev-original-sphinx'
    needs = {selected: {'result': 'success'}, other: {'result': 'skipped'}}
    github = {'event_name': 'push', 'ref': ref}
    assert evaluate(workflow()['jobs']['publish-sphinx-bundle']['if'],
                    inputs=inputs, github=github, needs=needs) == (
                        not dev or ref == 'refs/heads/develop')


@pytest.mark.parametrize('dev', [False, True])
def test_empty_destination_never_publishes(dev):
    assert evaluate(workflow()['jobs']['publish-sphinx-bundle']['if'],
                    inputs={'bundle_dir': '', 'dev_original_commands': dev}) is False


@pytest.mark.parametrize('dev', [False, True])
def test_branch_draft_title_and_budget_preserve_generic_or_bind_dev_source(dev):
    job = workflow()['jobs']['publish-sphinx-bundle']
    action = next(s for s in job['steps'] if s.get('uses', '').startswith('peter-evans/'))
    inputs = {'bundle_dir': 'src/scitex_dev/_sphinx_html', 'dev_original_commands': dev}
    assert evaluate(action['if'], inputs=inputs) == (not dev)
    if dev:
        prepare = next(s for s in job['steps'] if s.get('id') == 'dev-docs-commit')
        assert evaluate(prepare['env']['PR_BRANCH'], inputs=inputs) == f'ci/dev-sphinx-{SOURCE}-12345'
        assert prepare['timeout-minutes'] == 1
    else:
        actual = (action['with']['branch'].replace('${{ github.ref_name }}',
                  evaluate('${{ github.ref_name }}', inputs=inputs)),
                  action['with'].get('draft', False), action['with']['title'])
        assert actual == ('ci/sphinx-bundle/develop', False, 'docs: refresh generated Sphinx bundle')
    assert evaluate(job['timeout-minutes'], inputs=inputs) == (5 if dev else 360)
    assert action['with']['base'] == '${{ github.ref_name }}'
    assert action['with']['add-paths'] == '${{ inputs.bundle_dir }}'


@pytest.mark.parametrize('changes,reason', [
    ({}, None),
    ({'repository': 'scitex-ai/other'}, 'dev-docs-source-contract-refused'),
    ({'event': 'pull_request'}, 'dev-docs-source-contract-refused'),
    ({'ref': 'refs/heads/main'}, 'dev-docs-source-contract-refused'),
    ({'source': SOURCE + '\n'}, 'dev-docs-source-contract-refused'),
    ({'destination': '../foreign'}, 'dev-docs-source-contract-refused'),
    ({'branch': {'name': 'develop', 'commit': {'sha': 'b' * 40}}}, 'dev-docs-source-advanced'),
    ({'branch': {'name': 'main', 'commit': {'sha': SOURCE}}}, 'dev-docs-source-advanced'),
])
def test_actual_source_guard_refuses_foreign_or_advanced_context(changes, reason):
    value = {'repository': 'scitex-ai/scitex-dev', 'event': 'push',
             'ref': 'refs/heads/develop', 'source': SOURCE,
             'destination': 'src/scitex_dev/_sphinx_html',
             'branch': {'name': 'develop', 'commit': {'sha': SOURCE}}}
    value.update(changes)
    code = marker('DEV_DOCS_SOURCE') + """
const x=JSON.parse(process.argv[1]);let result;
try {result={source:qualifyDevDocsSource(x.repository,x.event,x.ref,x.source,x.destination,x.branch)}}
catch(e){result={reason:e.message}}
process.stdout.write(JSON.stringify(result));
"""
    assert node(code, value) == ({'source': SOURCE} if reason is None else {'reason': reason})


@pytest.mark.parametrize('expected,sha,accepted', [
    (SOURCE, SOURCE, True), (SOURCE, 'b' * 40, False), ('', '', False),
    (SOURCE + '\n', SOURCE, False),
])
def test_after_guard_reads_actual_transport_result_and_refuses_source_advance(expected, sha, accepted):
    # Adapt the external GitHub REST transport; execute the unchanged after script.
    code = """
const x=JSON.parse(process.argv[1]);
process.env.EXPECTED_SOURCE=x.expected;
const context={repo:{owner:'scitex-ai',repo:'scitex-dev'}};
const github={rest:{repos:{getBranch:async options=>{
 if(options.owner!=='scitex-ai'||options.repo!=='scitex-dev'||options.branch!=='develop'
    ||options.request.timeout!==10000)throw new Error('transport-contract-wrong');
 return {data:x.branch};
}}}};
(async()=>{let out;try{SCRIPT;out={ok:true}}catch(e){out={ok:false,reason:e.message}}
process.stdout.write(JSON.stringify(out))})().catch(e=>{throw e});
""".replace('SCRIPT', marker('DEV_DOCS_AFTER'))
    value = {'expected': expected, 'branch': {'name': 'develop', 'commit': {'sha': sha}}}
    assert node(code, value) == ({'ok': True} if accepted else {'ok': False, 'reason': 'dev-docs-source-advanced'})


def test_only_publication_adapter_changes_the_captured_rtd_contract():
    fixture = json.loads((ROOT / 'tests/fixtures/dev-original-docs-import-source.json').read_text())
    original = yaml.safe_load(fixture['rtd-sphinx-build.yml']['candidate']['body'])
    current = workflow()
    assert {k: v for k, v in current.items() if k != 'jobs'} == {
        k: v for k, v in original.items() if k != 'jobs'}
    assert set(current['jobs']) == set(original['jobs'])
    generic = next(copy.deepcopy(x) for x in current['jobs']['publish-sphinx-bundle']['steps']
                   if x.get('uses', '').startswith('peter-evans/'))
    assert generic.pop('if') == '${{ !inputs.dev_original_commands }}'
    assert generic == next(x for x in original['jobs']['publish-sphinx-bundle']['steps']
                           if x.get('uses', '').startswith('peter-evans/'))
    changed = {k for k in current['jobs'] if current['jobs'][k] != original['jobs'][k]}
    assert changed == {'publish-sphinx-bundle', 'dev-original-sphinx'}
    old = original['jobs']['dev-original-sphinx']
    new = current['jobs']['dev-original-sphinx']
    assert {k: v for k, v in new.items() if k != 'steps'} == {
        k: v for k, v in old.items() if k != 'steps'}
    assert new['permissions'] == {'contents': 'write'}
    assert new['steps'][:-2] == old['steps'][:-1]
    legacy = copy.deepcopy(new['steps'][-2])
    assert legacy.pop('if') == old['steps'][-1]['if'] + " && inputs.bundle_dir == ''"
    assert legacy == {k: v for k, v in old['steps'][-1].items() if k != 'if'}
    upload = new['steps'][-1]
    assert upload['with'] == {'name': '${{ inputs.artifact_name }}',
                             'path': 'src/scitex_dev/_sphinx_html', 'if-no-files-found': 'error'}
    assert evaluate(upload['if']) is True
    assert evaluate(upload['if'], inputs={'bundle_dir': '', 'dev_original_commands': True}) is False


@pytest.mark.parametrize('actual,accepted', [(SOURCE, True), ('b' * 40, False)])
def test_before_step_exports_only_the_source_confirmed_by_the_transport(actual, accepted):
    step = next(s for s in workflow()['jobs']['publish-sphinx-bundle']['steps']
                if s.get('id') == 'dev-docs-source')
    code = """
const x=JSON.parse(process.argv[1]);
process.env.BUNDLE_DIR='src/scitex_dev/_sphinx_html';
const outputs={};const core={setOutput:(k,v)=>{outputs[k]=v}};
const context={repo:{owner:'scitex-ai',repo:'scitex-dev'},
 payload:{repository:{full_name:'scitex-ai/scitex-dev'}},
 eventName:'push',ref:'refs/heads/develop',sha:x.expected};
const github={rest:{repos:{getBranch:async options=>{
 if(options.owner!=='scitex-ai'||options.repo!=='scitex-dev'||options.branch!=='develop'
    ||options.request.timeout!==10000)throw new Error('transport-contract-wrong');
 return {data:{name:'develop',commit:{sha:x.actual}}};
}}}};
(async()=>{let out;try{SCRIPT;out={ok:true,outputs}}catch(e){out={ok:false,outputs,reason:e.message}}
process.stdout.write(JSON.stringify(out))})().catch(e=>{throw e});
""".replace('SCRIPT', step['with']['script'])
    assert node(code, {'actual': actual, 'expected': SOURCE}) == (
        {'ok': True, 'outputs': {'source': SOURCE}} if accepted else
        {'ok': False, 'outputs': {}, 'reason': 'dev-docs-source-advanced'})
