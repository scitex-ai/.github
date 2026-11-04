"""Actual owned Git history survives the PR GraphQL 250-object transport cap."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / '.github/cla/baseline-transports.js'
SCRIPT = r'''
const m=require(process.argv[1]);
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
const rows=input.rows.slice(0,input.count).map(commit=>({commit}));
const before={state:'open',base:{sha:input.base,ref:'main',repo:{full_name:'owned/repo'}},
 head:{sha:rows.at(-1)?.commit.oid||input.base},commits:input.count};
const mutation=input.mutation;
if(mutation==='cycle')rows[0].commit.parents={totalCount:1,nodes:[
 {oid:before.head.sha,tree:rows.at(-1).commit.tree}]};
if(mutation==='disconnected')rows.at(-1).commit.parents={totalCount:0,nodes:[]};
if(mutation==='late-unknown'){
 rows.at(-1).commit.author={name:'Unknown'};rows.at(-1).commit.committer={name:'Unknown'};
}
if(['late-actor','rest-frontloads-late-actor'].includes(mutation))rows.at(-1).commit.author.user={login:'late-user',databaseId:2};
if(['covered-late-actor','rest-hides-covered-actor'].includes(mutation)){
 rows[99].commit.author.user={login:'late-user',databaseId:2};
 rows.at(-1).commit.author.user={login:'late-user',databaseId:2};
}
const inventory=rows.map(row=>({sha:row.commit.oid,node_id:'fixture:'+row.commit.oid,
 author:{login:'REST-MUST-NOT-REPLACE-ATTESTED-IDENTITY',id:999}}));
if(mutation==='rest-frontloads-late-actor')[inventory[0],inventory[inventory.length-1]]=[inventory.at(-1),inventory[0]];
if(mutation==='rest-hides-covered-actor')[inventory[99],inventory[250]]=[inventory[250],inventory[99]];
const byId=new Map(rows.map(row=>['fixture:'+row.commit.oid,row.commit]));
let pullCalls=0,compareCalls=0,objectCalls=0;
const page=async cursor=>{
 pullCalls++;
 const start=cursor===null?0:Number(cursor);
 const end=Math.min(start+100,rows.length,250);
 const pull={baseRefOid:before.base.sha,headRefOid:before.head.sha,
 commits:{totalCount:input.count,nodes:structuredClone(rows.slice(start,end)),
 pageInfo:{hasNextPage:end<Math.min(rows.length,250),endCursor:String(end)}}};
 if(mutation==='changed-head'&&start>0)pull.headRefOid='e'.repeat(40);
 return pull;
};
const compare=async number=>{
 compareCalls++;
 const start=(number-1)*100;
 const result={total_commits:input.count,base_commit:{sha:before.base.sha},
 commits:structuredClone(inventory.slice(start,start+100))};
 if(mutation==='rest-order'&&number===1)[result.commits[0],result.commits[1]]=[result.commits[1],result.commits[0]];
 if(mutation==='rest-short')result.commits.pop();
 if(mutation==='rest-duplicate'&&number===2)result.commits[0]=inventory[0];
 if(mutation==='rest-duplicate-node'&&number===2)result.commits[0].node_id=inventory[0].node_id;
 if(mutation==='rest-total')result.total_commits++;
 if(mutation==='rest-base')result.base_commit.sha='e'.repeat(40);
 return result;
};
const objects=async ids=>{
 objectCalls++;
 const nodes=ids.map(id=>structuredClone(byId.get(id)));
 if(mutation==='objects-short')nodes.pop();
 if(mutation==='objects-null')nodes[0]=null;
 if(mutation==='objects-wrong-oid')nodes[0].oid='e'.repeat(40);
 if(mutation==='overlap-author')nodes[0].author.user.databaseId=999;
 if(mutation==='missing-parent')nodes[0].parents.nodes=[];
 if(mutation==='wrong-parent-tree'&&nodes.at(-1)?.oid===rows.at(-1).commit.oid)nodes.at(-1).parents.nodes[0].tree.oid='e'.repeat(40);
 if(mutation==='late-missing-parent'&&nodes.at(-1)?.oid===rows.at(-1).commit.oid)nodes.at(-1).parents.nodes=[];
 return {nodes};
};
(async()=>{try{
 if(input.runtime){
  const output={}; let calls=0; let final=false;
  const github={rest:{pulls:{get:async()=>({data:structuredClone(before)})},
   repos:{getBranch:async()=>({data:{protected:true,commit:{sha:before.base.sha}}}),
          compareCommitsWithBasehead:async args=>({data:await compare(args.page)})}},
   graphql:async(document,args)=>{
    calls++;
    if(document.includes('nodes(ids:')){
     const response=await objects(args.ids);
     if(final&&mutation==='final-author-change')response.nodes.at(-1).author.user.databaseId=99;
     return response;
    }
    return {repository:{pullRequest:await page(args.cursor)}};
   }};
  await m.qualify({github,context:{repo:{owner:'owned',repo:'repo'},issue:{number:1}},
   core:{setOutput:(name,value)=>output[name]=value,info:()=>{},warning:()=>{}},
   ownerAllowlist:'original-owner'});
  final=true;
  await m.verifyFinalBinding({github,context:{repo:{owner:'owned',repo:'repo'},issue:{number:1}},
   snapshot:JSON.parse(output.proof)});
  process.stdout.write(JSON.stringify({accepted:true,allowlist:output.allowlist,calls}));return;
 }
 const recovered=await m.completeCommits(before,{owner:'owned',repo:'repo'},page,
  prefix=>m.comparisonCommits(before,prefix,compare,objects));
 process.stdout.write(JSON.stringify({accepted:true,count:recovered.length,
  pullCalls,compareCalls,objectCalls}));
}catch(error){process.stdout.write(JSON.stringify({accepted:false,error:error.message,
 pullCalls,compareCalls,objectCalls}));}})();
'''


class ComparisonTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='cla-actual-history-')
        root = Path(cls.tmp.name)
        repo = root / 'repo.git'
        template = root / 'empty-template'
        template.mkdir()
        env = os.environ.copy()
        for name in subprocess.check_output(
            ['git', 'rev-parse', '--local-env-vars'], text=True
        ).splitlines():
            env.pop(name, None)
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        subprocess.run(['git', 'init', '--bare', f'--template={template}', str(repo)],
                       env=env, capture_output=True, check=True, timeout=5)
        commands = []
        for index in range(2001):
            body = f'owned fixture {index}\n'
            commands.append(f'blob\nmark :{index + 1}\ndata {len(body)}\n{body}')
            commands.append(
                f'commit refs/heads/owned\nmark :{10001 + index}\n'
                f'committer Owned <fixture@example.invalid> {1700000000 + index} +0000\n'
                f'data 5\nowned\n' +
                (f'from :{10000 + index}\n' if index else '') +
                f'M 100644 :{index + 1} fixture.txt\n\n'
            )
        subprocess.run(['git', '-C', str(repo), 'fast-import', '--quiet'],
                       input=''.join(commands), text=True, capture_output=True,
                       env=env, check=True, timeout=20)
        history = subprocess.check_output(
            ['git', '-C', str(repo), 'log', '--reverse', '--format=%H%x09%T%x09%P',
             'refs/heads/owned'], env=env, text=True, timeout=5,
        ).splitlines()
        parsed = [line.split('\t') for line in history]
        trees = {oid: tree for oid, tree, _ in parsed}
        cls.base = parsed[0][0]
        cls.rows = []
        for oid, tree, parents in parsed[1:]:
            actor = {'name': 'Owned fixture',
                     'user': {'login': 'fixture-user', 'databaseId': 1}}
            parent_rows = [{'oid': parent, 'tree': {'oid': trees[parent]}}
                           for parent in parents.split()]
            cls.rows.append({'oid': oid, 'tree': {'oid': tree},
                             'author': actor, 'committer': actor,
                             'parents': {'totalCount': len(parent_rows),
                                         'nodes': parent_rows}})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def collect(self, count=656, mutation=None, runtime=False):
        result = subprocess.run(
            ['node', '-e', SCRIPT, str(HELPER)],
            input=json.dumps({'base': self.base, 'rows': self.rows,
                              'count': count, 'mutation': mutation, 'runtime': runtime}),
            capture_output=True, text=True, check=True, timeout=10,
        )
        return json.loads(result.stdout)

    def test_complete_owned_history_beyond_the_connection_cap(self):
        for count in [251, 656, 2000]:
            with self.subTest(count=count):
                result = self.collect(count)
                self.assertEqual((result['accepted'], result.get('count'),
                                  result['pullCalls'], result['compareCalls'],
                                  result['objectCalls']),
                                 (True, count, 3, (count + 99) // 100,
                                  (count + 99) // 100))

    def test_normal_short_connections_do_not_use_recovery(self):
        for count in [1, 100, 250]:
            with self.subTest(count=count):
                result = self.collect(count)
                self.assertEqual((result['accepted'], result['compareCalls'],
                                  result['objectCalls']), (True, 0, 0))

    def test_incomplete_or_changed_attestation_fails_closed(self):
        for mutation in ['rest-short', 'rest-duplicate', 'rest-duplicate-node',
                         'rest-total', 'rest-base', 'objects-short', 'objects-null',
                         'objects-wrong-oid', 'overlap-author', 'changed-head',
                         'missing-parent', 'late-missing-parent', 'wrong-parent-tree', 'cycle', 'disconnected']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.collect(mutation=mutation)['accepted'])

    def test_unknown_or_uncovered_late_person_still_refuses(self):
        for mutation in ['late-unknown', 'late-actor']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.collect(mutation=mutation)['accepted'])

    def test_covered_person_remains_covered_without_rest_author_substitution(self):
        self.assertTrue(self.collect(mutation='covered-late-actor')['accepted'])

    def test_rest_order_does_not_replace_the_original_action_prefix(self):
        self.assertTrue(self.collect(mutation='rest-order')['accepted'])

    def test_comparison_order_cannot_launder_an_uncovered_person_into_first100(self):
        self.assertFalse(self.collect(mutation='rest-frontloads-late-actor')['accepted'])

    def test_comparison_order_cannot_hide_a_person_the_action_already_covers(self):
        self.assertTrue(self.collect(mutation='rest-hides-covered-actor')['accepted'])

    def test_runtime_qualification_and_final_binding_recover_the_same_full_inventory(self):
        result = self.collect(runtime=True)
        self.assertEqual((result['accepted'], result.get('allowlist')),
                         (True, 'original-owner'))

    def test_runtime_final_identity_change_still_refuses(self):
        self.assertFalse(self.collect(mutation='final-author-change', runtime=True)['accepted'])

    def test_limit_is_not_raised(self):
        result = self.collect(2001)
        self.assertEqual((result['accepted'], result['pullCalls'],
                          result['compareCalls'], result['objectCalls']), (False, 0, 0, 0))


if __name__ == '__main__':
    unittest.main()
