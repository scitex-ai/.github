"""Only independently reviewed immutable action contracts can widen coverage."""

import json
import subprocess
import unittest

import test_cla_compare_fallback as fixture

HELPER = fixture.HELPER

LEGACY = 'scitex-ai/github-action@114064adf09afb0c8c04703c060862a29ae82c7d'
FULL = 'scitex-ai/github-action@6a20f5856a730d19a19b3130fe94c7af8a3a9ba8'


class ActionCoverageContractTests(unittest.TestCase):
    def run_case(self, **values):
        return fixture.CompareFallbackTests.run_case(self, **values)

    def test_legacy_first100_still_refuses_late_identity(self):
        observed = self.run_case(actionRef=LEGACY, mutation='late-actor')
        self.assertFalse(observed['accepted'])
        self.assertEqual(observed['error'], 'Pinned CLA action cannot cover every contributor')
        legacy = self.run_case(actionRef=LEGACY, mutation='all-author-user-missing', cap=665)
        self.assertTrue(legacy['accepted'])

    def test_reviewed_full_collector_covers_late_identity_only_after_complete_proof(self):
        complete = self.run_case(actionRef=FULL, mutation='late-actor')
        self.assertEqual((complete['accepted'], complete['count']), (True, 665))
        self.assertEqual(complete['calls']['compare'], 7)
        self.assertEqual(complete['calls']['objects'], 7)
        direct = self.run_case(actionRef=FULL, mutation='late-actor', cap=665)
        self.assertEqual((direct['accepted'], direct['count']), (True, 665))
        refused = self.run_case(actionRef=FULL, mutation='late-actor', fallback=False)
        self.assertFalse(refused['accepted'])

    def test_full_contract_still_refuses_unsupported_or_conflicting_identity(self):
        for mutation in ['late-reused-login', 'late-reused-id', 'late-unknown']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.run_case(actionRef=FULL, mutation=mutation)['accepted'])
        for cap in [250, 665]:
            for mutation in ['all-author-user-missing', 'all-committer-user-missing',
                             'all-author-name-missing']:
                with self.subTest(cap=cap, mutation=mutation):
                    self.assertFalse(self.run_case(actionRef=FULL, mutation=mutation,
                                                   cap=cap)['accepted'])
        script = """
const m=require(process.argv[1]);
const bad={oid:'a'.repeat(40),tree:{oid:'b'.repeat(40)},parents:{totalCount:0,nodes:[]},
 author:{name:'Unlinked author',user:null},committer:{name:'Raw committer',user:null}};
try{m.requireActionCoverage([bad],m.FULL_ACTION_REF);process.stdout.write('accepted');}
catch(e){process.stdout.write(e.message);}
"""
        observed = subprocess.run(['node', '-e', script, str(HELPER)], text=True,
                                  capture_output=True, timeout=5, check=True)
        self.assertIn('Unknown contributor', observed.stdout)

    def test_full_contract_preserves_all_partial_transport_refusals(self):
        for mutation in ['graph-api', 'graph-null', 'graph-duplicate', 'graph-head',
                         'graph-base', 'compare-api', 'compare-null', 'compare-cap250',
                         'compare-duplicate', 'compare-short', 'compare-invalid',
                         'compare-no-head', 'compare-base', 'compare-total', 'objects-api',
                         'objects-null', 'object-null', 'object-missing', 'object-oid',
                         'object-identity', 'object-tree', 'object-name']:
            with self.subTest(mutation=mutation):
                self.assertFalse(self.run_case(actionRef=FULL, mutation=mutation)['accepted'])

    def test_full_preflight_final_and_snapshot_contract_are_bound(self):
        for mode in ['qualify', 'final']:
            with self.subTest(mode=mode):
                accepted = self.run_case(actionRef=FULL, mode=mode,
                                         mutation='late-actor', currentSnapshot=True)
                self.assertTrue(accepted['accepted'])
                for mutation in ['after-head', 'after-base', 'after-state', 'after-count',
                                 'after-ref', 'after-repository', 'protected-base', 'deadline']:
                    with self.subTest(mutation=mutation):
                        self.assertFalse(self.run_case(actionRef=FULL, mode=mode,
                                                       mutation=mutation)['accepted'])
        for mutation in ['snapshot-contract', 'snapshot-bundle', 'snapshot-action-ref']:
            with self.subTest(mutation=mutation):
                rejected = self.run_case(actionRef=FULL, mode='final', mutation=mutation)
                self.assertFalse(rejected['accepted'])
                self.assertEqual(sum(rejected['calls'].values()), 0)
        crossed = self.run_case(actionRef=FULL, snapshotActionRef=LEGACY, mode='final')
        self.assertFalse(crossed['accepted'])

    def test_only_exact_two_refs_are_supported(self):
        script = """
const m=require(process.argv[1]), refs=JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(refs.map(ref=>{
 try{return {ref,contract:m.actionCoverageContract(ref)}}
 catch(e){return {ref,error:e.message}}
})));
"""
        refs = [LEGACY, FULL, 'scitex-ai/github-action@node24-v2.6.1',
                'scitex-ai/github-action@73e9b0b1f4c895c2fafaeeb16212880204e75b03',
                'other/github-action@6a20f5856a730d19a19b3130fe94c7af8a3a9ba8',
                None, {'coverage': 'full-immutable-pr-attribution-v1'}]
        result = subprocess.run(['node', '-e', script, str(HELPER), json.dumps(refs)],
                                text=True, capture_output=True, timeout=5, check=True)
        rows = json.loads(result.stdout)
        self.assertEqual(rows[0]['contract']['coverage'], 'first-100')
        self.assertEqual(rows[1]['contract']['bundleSha256'],
                         '6eaab719f46f0ed4b2d7cff57022b745f1bb4d239c7d715c7d77c88967c69662')
        self.assertTrue(all('error' in row for row in rows[2:]))

    def test_full_contract_keeps_request_and_count_limits(self):
        accepted = self.run_case(actionRef=FULL, mode='qualify', count=2000)
        self.assertTrue(accepted['accepted'])
        capped = self.run_case(actionRef=FULL, mode='qualify', count=2000, cap=1900)
        self.assertFalse(capped['accepted'])
        self.assertEqual(sum(capped['calls'].values()), 48)
        excessive = self.run_case(actionRef=FULL, mode='qualify', count=2001)
        self.assertEqual(excessive['calls']['graph'], 0)

    def test_unknown_contract_refuses_before_any_transport_or_output(self):
        script = """
const m=require(process.argv[1]);let calls=0;
const touched=()=>{calls++;throw Error('Unexpected transport or output');};
const requests=[
 ()=>m.completeCommits({}, {}, touched, {}, 'unknown'),
 ()=>m.qualify({github:{},context:{},core:{setOutput:touched},actionRef:'unknown'}),
 ()=>m.verifyFinalBinding({github:{},context:{},snapshot:{},actionRef:'unknown'})
];
(async()=>{
const rows=[];for(const request of requests){
 try{await request();rows.push({accepted:true});}
 catch(e){rows.push({error:e.message});}
}process.stdout.write(JSON.stringify({rows,calls}));})();
"""
        result = subprocess.run(['node', '-e', script, str(HELPER)], text=True,
                                capture_output=True, timeout=5, check=True)
        observed = json.loads(result.stdout)
        self.assertEqual(observed['calls'], 0)
        self.assertTrue(all('Unsupported immutable' in row['error']
                            for row in observed['rows']))


if __name__ == '__main__':
    unittest.main()
