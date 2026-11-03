"""Complete controlled GraphQL pages, with the unchanged action's signer bound."""
import json
import subprocess
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / '.github/cla/baseline-transports.js'
SCRIPT = r'''
const m = require(process.argv[1]);
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const oid = n => n.toString(16).padStart(40, '0');
const before = {state:'open', base:{sha:oid(10001),ref:'main',repo:{full_name:'owned/repo'}},
                head:{sha:oid(10002)},commits:input.count};
const user = {login:'fixture-user',databaseId:1};
const rows = Array.from({length:input.count}, (_,i)=>({commit:{oid:oid(i+1),
 author:{user:{...user}},committer:{user:{...user}},tree:{oid:oid(10003)},
 parents:{totalCount:0,nodes:[]}}}));
if (input.mutation==='late-actor') rows.at(-1).commit.author.user={login:'late-user',databaseId:2};
if (input.mutation==='late-reused-login') rows.at(-1).commit.author.user.databaseId=2;
if (input.mutation==='late-unknown') {
 rows.at(-1).commit.author={name:'Unlinked fixture'};
 rows.at(-1).commit.committer={name:'Unlinked fixture'};
}
if (input.mutation==='covered-late-actor') {
 rows[99].commit.author.user={login:'late-user',databaseId:2};
 rows.at(-1).commit.author.user={login:'late-user',databaseId:2};
}
let calls=0;
const page=async cursor=>{
 const start=cursor===null?0:Number(cursor.slice(1));
 calls++;
 if(input.mutation==='api-error')throw new Error('Owned transport refusal');
 if(input.mutation==='null')return null;
 const end=Math.min(start+100,rows.length);
 const connection={totalCount:input.count,nodes:structuredClone(rows.slice(start,end)),
  pageInfo:{hasNextPage:end<rows.length,endCursor:end?'p'+end:null}};
 const pull={baseRefOid:before.base.sha,headRefOid:before.head.sha,commits:connection};
 if(input.mutation==='missing-cursor')connection.pageInfo.endCursor=null;
 if(input.mutation==='short-page'&&start===0)connection.nodes.pop();
 if(input.mutation==='partial')connection.nodes=null;
 if(start>0){
  if(input.mutation==='duplicate')connection.nodes[0]=structuredClone(rows[0]);
  if(input.mutation==='missing')connection.nodes.pop();
  if(input.mutation==='repeat-cursor')connection.pageInfo.endCursor=cursor;
  if(input.mutation==='head-change')pull.headRefOid=oid(20001);
  if(input.mutation==='base-change')pull.baseRefOid=oid(20002);
  if(input.mutation==='total-change')connection.totalCount++;
 }
 return pull;
};
(async()=>{
 try{
  const commits=await m.completeCommits(before,{owner:'owned',repo:'repo'},page);
  process.stdout.write(JSON.stringify({accepted:true,count:commits.length,calls}));
 }catch(error){process.stdout.write(JSON.stringify({accepted:false,calls,error:error.message}));}
})();
'''


class CompletePaginationTests(unittest.TestCase):
    def collect(self, count, mutation=None):
        run = subprocess.run(['node', '-e', SCRIPT, str(HELPER)],
                             input=json.dumps({'count': count, 'mutation': mutation}),
                             text=True, capture_output=True, timeout=5, check=True)
        return json.loads(run.stdout)

    def test_every_commit_is_read_when_the_action_covers_every_person(self):
        for count in [0, 1, 100, 101, 174, 250, 624, 2000]:
            with self.subTest(count=count):
                observed = self.collect(count)
                self.assertEqual((observed['accepted'], observed.get('count'), observed['calls']),
                                 (True, count, max(1, (count + 99) // 100)))

    def test_malformed_or_changing_pages_cannot_be_declared_complete(self):
        for mutation in ['missing-cursor', 'short-page', 'partial', 'null', 'api-error',
                         'duplicate', 'missing', 'repeat-cursor', 'head-change',
                         'base-change', 'total-change']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.collect(250, mutation)['accepted'])

    def test_an_uncovered_late_person_cannot_escape_signature_checking(self):
        # Even an already-signed late person is refused: this bridge cannot prove
        # the pinned action checked them. It never adds a signature or exemption.
        for mutation in ['late-actor', 'late-reused-login', 'late-unknown']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.collect(624, mutation)['accepted'])

    def test_a_late_commit_by_a_person_already_checked_remains_covered(self):
        self.assertTrue(self.collect(624, 'covered-late-actor')['accepted'])

    def test_resource_limit_refuses_before_the_transport_is_called(self):
        observed = self.collect(2001)
        self.assertEqual((observed['accepted'], observed['calls']), (False, 0))


if __name__ == '__main__':
    unittest.main()
