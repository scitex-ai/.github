"""Complete capped GraphQL attribution without widening the action's coverage."""
import json
import subprocess
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / '.github/cla/baseline-transports.js'
SCRIPT = r'''
const m=require(process.argv[1]), input=JSON.parse(require('fs').readFileSync(0,'utf8'));
const oid=n=>n.toString(16).padStart(40,'0'), count=input.count??665;
const before={state:'open',base:{sha:oid(10001),ref:'main',repo:{full_name:'owned/repo'}},
 head:{sha:oid(count)},commits:count};
const user={login:'fixture-user',databaseId:1};
const rows=Array.from({length:count},(_,i)=>({oid:oid(i+1),tree:{oid:oid(10002)},
 author:{name:'Owned fixture',user:{...user}},committer:{name:'Owned fixture',user:{...user}},
 parents:{totalCount:0,nodes:[]}}));
const ordered=()=>[...rows.slice(0,100).reverse(),...rows.slice(100)];
const expected=ordered();
const snapshot=m.snapshotFor(before,expected,true);
if(input.mutation==='late-actor') rows.at(-1).author.user={login:'late-user',databaseId:2};
if(input.mutation==='late-reused-login') rows.at(-1).author.user.databaseId=2;
if(input.mutation==='late-unknown') rows.at(-1).author.user=rows.at(-1).committer.user=null;
if(input.mutation==='covered-late-actor'){
 rows[99].author.user={login:'late-user',databaseId:2};
 rows.at(-1).author.user={login:'late-user',databaseId:2};
}
if(input.mutation==='snapshot-attribution') rows.forEach(c=>{c.author.name='Changed name';});
if(input.mutation==='all-author-user-missing')rows.forEach(c=>{delete c.author.user;});
if(input.mutation==='all-author-user-null')rows.forEach(c=>{c.author.user=null;});
const calls={graph:0,compare:0,objects:0,pull:0,branch:0};
let clock=0;
if(input.mutation==='deadline')Date.now=()=>clock;
function tick(kind){calls[kind]++;if(input.mutation==='deadline')clock+=5000;}
async function page(cursor){
 tick('graph');
 if(input.mutation==='graph-api')throw Error('Owned GraphQL API refusal');
 if(input.mutation==='graph-null')return null;
 const cap=Math.min(count,input.cap??250),start=cursor===null?0:Number(cursor.slice(1));
 const end=Math.min(start+100,cap),nodes=structuredClone(ordered().slice(start,end)).map(commit=>({commit}));
 if(input.mutation==='graph-duplicate'&&start>0)nodes[0]={commit:structuredClone(rows[0])};
 const pull={baseRefOid:before.base.sha,headRefOid:before.head.sha,commits:{totalCount:count,nodes,
  pageInfo:{hasNextPage:end<cap,endCursor:end?'p'+end:null}}};
 if(start>0&&input.mutation==='graph-head')pull.headRefOid=oid(20001);
 if(start>0&&input.mutation==='graph-base')pull.baseRefOid=oid(20002);
 return pull;
}
async function comparison(page){
 tick('compare');
 if(input.mutation==='compare-api')throw Error('Owned compare API refusal');
 if(input.mutation==='compare-null')return null;
 const commits=rows.slice((page-1)*100,page*100).map(c=>({sha:c.oid}));
 if(input.mutation==='compare-cap250'&&page===3)commits.splice(50);
 if(input.mutation==='compare-duplicate'&&page>1)commits[0].sha=rows[0].oid;
 if(input.mutation==='compare-short')commits.pop();
 if(input.mutation==='compare-invalid')commits[0].sha='invalid';
 if(input.mutation==='compare-no-head'&&page===Math.ceil(count/100))commits.at(-1).sha=oid(50001);
 return {base_commit:{sha:input.mutation==='compare-base'?oid(20001):before.base.sha},
  total_commits:input.mutation==='compare-total'?count+1:count,commits};
}
async function objects(ids){
 tick('objects');
 if(input.mutation==='objects-api')throw Error('Owned canonical object API refusal');
 if(input.mutation==='objects-null')return null;
 const values=ids.map(id=>structuredClone(rows.find(c=>c.oid===id)));
 if(input.mutation==='object-null')values[0]=null;
 if(input.mutation==='object-missing')values.pop();
 if(input.mutation==='object-oid')values[0].oid=oid(40001);
 if(calls.objects===1){
  if(input.mutation==='object-identity')values[0].author.user.databaseId=2;
  if(input.mutation==='object-tree')values[0].tree.oid=oid(40002);
  if(input.mutation==='object-name')values[0].author.name='Different metadata';
 }
 return values;
}
const github={rest:{pulls:{get:async()=>{
 tick('pull');const value=structuredClone(before);
 if(calls.pull>1){
  if(input.mutation==='after-head')value.head.sha=oid(30001);
  if(input.mutation==='after-base')value.base.sha=oid(30002);
  if(input.mutation==='after-state')value.state='closed';
  if(input.mutation==='after-count')value.commits++;
  if(input.mutation==='after-ref')value.base.ref='other';
  if(input.mutation==='after-repository')value.base.repo.full_name='other/repo';
 }
 return {data:value};
}},repos:{compareCommitsWithBasehead:async args=>{
 if(args.basehead!==before.base.sha+'...'+before.head.sha||args.per_page!==100||
    !Number.isInteger(args.page)||args.page<1||args.page>20)throw Error('Unbound compare request');
 return {data:await comparison(args.page)};
},getBranch:async()=>{
 tick('branch');const changed=input.mutation==='protected-base'&&
  (input.mode==='final'||calls.branch>1);
 return {data:{protected:!changed,commit:{sha:changed?oid(30003):before.base.sha}}};
}}},graphql:async(query,args)=>{
 if(query.includes('pullRequest('))return {repository:{pullRequest:await page(args.cursor)}};
 const ids=[...query.matchAll(/object\(oid:"([a-f0-9]{40})"\)/g)].map(v=>v[1]);
 if(!ids.length||ids.length>100)throw Error('Unbounded object request');
 const values=await objects(ids);return {repository:values&&Object.fromEntries(values.map((c,i)=>['c'+i,c]))};
}};
(async()=>{
 const outputs={};
 try{
  let commits;
  if(input.mode==='qualify')await m.qualify({github,context:{repo:{owner:'owned',repo:'repo'},issue:{number:1}},
   core:{setOutput:(k,v)=>{outputs[k]=v;},info:()=>{},warning:()=>{}},ownerAllowlist:'owner-fixture'});
  else if(input.mode==='final')await m.verifyFinalBinding({github,
   context:{repo:{owner:'owned',repo:'repo'},issue:{number:1}},snapshot});
  else commits=await m.completeCommits(before,{owner:'owned',repo:'repo'},page,
   input.fallback===false?{}:{getComparePage:comparison,getCommitObjects:objects});
  process.stdout.write(JSON.stringify({accepted:true,count:commits?.length,calls,outputs,
   prefix_matches:commits&&JSON.stringify(commits.slice(0,100).map(c=>c.oid))===
    JSON.stringify(ordered().slice(0,100).map(c=>c.oid))}));
 }catch(e){process.stdout.write(JSON.stringify({accepted:false,error:e.message,calls,outputs}));}
})();
'''


class CompareFallbackTests(unittest.TestCase):
    def run_case(self, **values):
        run = subprocess.run(['node', '-e', SCRIPT, str(HELPER)],
                             input=json.dumps(values), text=True, capture_output=True,
                             timeout=8, check=True)
        return json.loads(run.stdout)

    def test_capped250_fails_without_fallback_then_reads_all665(self):
        old = self.run_case(fallback=False)
        complete = self.run_case()
        self.assertFalse(old['accepted'])
        self.assertEqual((complete['accepted'], complete['count'], complete['prefix_matches']),
                         (True, 665, True))
        self.assertEqual(complete['calls'], {'graph': 3, 'compare': 7, 'objects': 7,
                                            'pull': 0, 'branch': 0})

    def test_transport_and_binding_failures_cannot_look_complete(self):
        for mutation in ['graph-api', 'graph-null', 'graph-duplicate', 'graph-head',
                         'graph-base', 'compare-api', 'compare-null', 'compare-cap250',
                         'compare-duplicate', 'compare-short', 'compare-invalid',
                         'compare-no-head', 'compare-base', 'compare-total', 'objects-api',
                         'objects-null', 'object-null', 'object-missing', 'object-oid',
                         'object-identity', 'object-tree', 'object-name']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.run_case(mutation=mutation)['accepted'])

    def test_first100_cannot_be_invented_from_rest(self):
        observed = self.run_case(cap=50)
        self.assertEqual((observed['accepted'], observed['calls']['compare']), (False, 0))

    def test_existing_action_still_refuses_uncovered_or_unattested_people(self):
        for mutation in ['late-actor', 'late-reused-login', 'late-unknown']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.run_case(mutation=mutation)['accepted'])
        refused = self.run_case(mutation='late-actor')
        self.assertEqual(refused['error'], 'Pinned CLA action cannot cover every contributor')
        self.assertTrue(self.run_case(mutation='covered-late-actor')['accepted'])

    def test_preflight_and_final_use_the_same_bounded_fallback(self):
        for mode in ['qualify', 'final']:
            with self.subTest(mode=mode):
                self.assertTrue(self.run_case(mode=mode)['accepted'])
                for mutation in ['after-head', 'after-base', 'after-state', 'after-count',
                                 'after-ref', 'after-repository', 'protected-base', 'deadline']:
                    with self.subTest(mutation=mutation):
                        self.assertFalse(self.run_case(mode=mode, mutation=mutation)['accepted'])
        self.assertFalse(self.run_case(mode='final', mutation='snapshot-attribution')['accepted'])

    def test_missing_actor_fields_are_not_explicit_null_attribution(self):
        self.assertFalse(self.run_case(mutation='all-author-user-missing')['accepted'])
        self.assertTrue(self.run_case(mutation='all-author-user-null')['accepted'])

    def test_max2000_and48_calls_remain_real_limits(self):
        accepted = self.run_case(mode='qualify', count=2000)
        self.assertTrue(accepted['accepted'])
        self.assertLessEqual(sum(accepted['calls'].values()), 48)
        rejected = self.run_case(mode='qualify', count=2000, cap=1900)
        self.assertEqual((rejected['accepted'], sum(rejected['calls'].values())), (False, 48))
        self.assertIn('budget', rejected['error'])
        too_many = self.run_case(mode='qualify', count=2001)
        self.assertEqual((too_many['accepted'], too_many['calls']['graph']), (False, 0))


if __name__ == '__main__':
    unittest.main()
