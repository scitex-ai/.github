"""Execute the actual review controller; fixtures adapt only GitHub transport."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'a'*40
HEAD = 'b'*40
BRANCH = f'ci/dev-sphinx-{SOURCE}-12345'


@pytest.mark.parametrize('changes,accepted', [({}, True), ({'head': HEAD+'\n'}, False),
    ({'repository': 'scitex-ai/other'}, False), ({'source': SOURCE+'\n'}, False),
    ({'run': 0}, False), ({'branch': 'ci/foreign'}, False),
    ({'remote_sha': 'c'*40}, False), ({'remote_type': 'tag'}, False),
    ({'remote_ref': 'refs/heads/other'}, False)])
def test_review_report_is_bound_to_the_actual_pushed_ref(changes, accepted):
    value = dict(repository='scitex-ai/scitex-dev', source=SOURCE, run=12345,
                 head=HEAD, branch=BRANCH, remote_sha=HEAD, remote_type='commit',
                 remote_ref='refs/heads/'+BRANCH)
    value.update(changes)
    steps = yaml.safe_load((ROOT/'.github/workflows/rtd-sphinx-build.yml').read_text())['jobs']['publish-sphinx-bundle']['steps']
    step = next(s for s in steps if s.get('id') == 'dev-docs-review')
    assert step['if'] == "inputs.dev_original_commands && steps.dev-docs-commit.outputs.changed == 'true'"
    assert step['timeout-minutes'] == 1
    script = step['with']['script']
    code = r"""
const x=JSON.parse(process.argv[1]);const outputs={};let creates=0,writes=0;const summary={text:'',links:[]};
process.env.PR_BRANCH=x.branch;process.env.EXPECTED_HEAD=x.head;
const context={repo:{owner:'scitex-ai',repo:'scitex-dev'},sha:x.source,runId:x.run,
 payload:{repository:{full_name:x.repository}}};
const report={addHeading:v=>{summary.text+=v;return report},
 addRaw:v=>{summary.text+=v;return report},addLink:(v,u)=>{summary.links.push(u);return report},
 write:async()=>{writes++}};
const core={setOutput:(k,v)=>{outputs[k]=v},notice:()=>{},summary:report};
const github={rest:{git:{getRef:async options=>{
 if(options.owner!=='scitex-ai'||options.repo!=='scitex-dev'
   ||options.ref!=='heads/'+x.branch||options.request.timeout!==10000)
   throw new Error('transport-contract-wrong');
 return {data:{ref:x.remote_ref,object:{type:x.remote_type,sha:x.remote_sha}}};
}},pulls:{create:async()=>{creates++;throw new Error('unexpected-pr-write')}}}};
(async()=>{let result;try{SCRIPT;result={ok:true,creates,writes,outputs,summary}}
catch(e){result={ok:false,creates,writes,outputs,reason:e.message}}
process.stdout.write(JSON.stringify(result))})().catch(e=>{throw e});
""".replace('SCRIPT', script)
    result = subprocess.run([shutil.which('node'), '-e', code, json.dumps(value)],
                            env={'PATH': os.defpath}, capture_output=True, text=True,
                            check=True, timeout=5)
    observed = json.loads(result.stdout)
    if accepted:
        compare = 'https://github.com/scitex-ai/scitex-dev/compare/develop...'+BRANCH+'?quick_pull=1'
        assert observed['ok'] and observed['creates'] == 0 and observed['writes'] == 1
        assert observed['outputs'] == {'branch': BRANCH, 'head': HEAD, 'compare-url': compare}
        assert observed['summary']['links'] == [compare]
        assert SOURCE in observed['summary']['text'] and HEAD in observed['summary']['text']
        assert 'maintainer accepted by runner admission' in observed['summary']['text']
    else:
        assert observed == {'ok': False, 'creates': 0, 'writes': 0, 'outputs': {},
                            'reason': 'dev-docs-review-contract-refused'}
