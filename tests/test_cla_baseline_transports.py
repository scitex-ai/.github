"""Actual owned Git histories for the trusted CLA attribution helper."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / ".github/cla/baseline-transports.js"


class BaselineTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="cla-owned-git-")
        cls.root = Path(cls.tmp.name)
        cls.env = os.environ.copy()
        names = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--local-env-vars"],
            check=True, capture_output=True, text=True, timeout=3,
        ).stdout.splitlines()
        for name in names:
            cls.env.pop(name, None)
        cls.repo = cls.root / "transport"
        cls.repo.mkdir()
        cls.git("init", "--initial-branch=main")
        cls.git("config", "user.name", "Owned fixture")
        cls.git("config", "user.email", "fixture@example.invalid")
        (cls.repo / "common.txt").write_text("initial\n")
        (cls.repo / "deleted.txt").write_text("baseline removal\n")
        cls.commit("initial")
        cls.initial = cls.git("rev-parse", "HEAD").strip()
        cls.git("checkout", "-b", "feature")
        (cls.repo / "feature.txt").write_text("feature-owned\n")
        cls.commit("feature")
        cls.git("checkout", "main")
        (cls.repo / "baseline.txt").write_text("already canonical\n")
        (cls.repo / "baseline.txt").chmod(0o755)
        (cls.repo / "deleted.txt").unlink()
        cls.commit("baseline")
        cls.baseline = cls.git("rev-parse", "HEAD").strip()
        cls.git("checkout", "feature")
        cls.git("merge", "--no-ff", "main", "-m", "transport baseline")
        cls.transport = cls.git("rev-parse", "HEAD").strip()
        cls.node = cls.node_at(cls.transport)
        cls.parent1, cls.parent2 = cls.node["parents"]["nodes"]
        cls.trees = [cls.tree_at(c["tree"]["oid"]) for c in
                     (cls.node, cls.parent1, cls.parent2)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def git(cls, *args, allow=(0,)):
        result = subprocess.run(
            ["git", "-C", str(cls.repo), *args], env=cls.env,
            capture_output=True, text=True, timeout=3, check=False,
        )
        if result.returncode not in allow:
            raise AssertionError(result.stderr)
        return result.stdout

    @classmethod
    def commit(cls, message):
        cls.git("add", "--all")
        cls.git("commit", "-m", message)

    @classmethod
    def node_at(cls, oid):
        fields = cls.git("show", "--no-patch", "--format=%H%n%T%n%P", oid).splitlines()
        parents = []
        for parent in fields[2].split():
            tree = cls.git("show", "--no-patch", "--format=%T", parent).strip()
            parents.append({"oid": parent, "tree": {"oid": tree}})
        return {"oid": fields[0], "tree": {"oid": fields[1]},
                "author": {"user": {"login": "transport-fixture"}},
                "parents": {"totalCount": len(parents), "nodes": parents}}

    @classmethod
    def tree_at(cls, oid):
        rows = []
        for line in cls.git("ls-tree", "-r", oid).splitlines():
            fields, name = line.split("\t", 1)
            mode, kind, sha = fields.split()
            rows.append({"path": name, "mode": mode, "type": kind, "sha": sha})
        return {"sha": oid, "truncated": False, "tree": rows}

    def call(self, expression, payload):
        result = subprocess.run(
            ["node", "-e", "const m=require(process.argv[1]);"
             "const d=JSON.parse(require('fs').readFileSync(0,'utf8'));"
             "process.stdout.write(JSON.stringify(" + expression + "));", str(HELPER)],
            input=json.dumps(payload), capture_output=True, text=True, timeout=3, check=False,
        )
        return result

    def transport_result(self, node=None, trees=None, baseline=True):
        result = self.call(
            "m.isBaselineTransport(d.node,...d.trees,d.baseline)",
            {"node": node or self.node, "trees": trees or self.trees, "baseline": baseline},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_genuine_baseline_merge_has_no_authored_material(self):
        self.assertTrue(self.transport_result())

    def test_baseline_executable_mode_is_matched_losslessly(self):
        entries = [r for r in self.trees[0]["tree"] if r["path"] == "baseline.txt"]
        self.assertEqual(entries[0]["mode"], "100755")
        self.assertTrue(self.transport_result())

    def test_baseline_deletion_is_matched_losslessly(self):
        self.assertIn("deleted.txt", [r["path"] for r in self.trees[1]["tree"]])
        self.assertNotIn("deleted.txt", [r["path"] for r in self.trees[0]["tree"]])
        self.assertTrue(self.transport_result())

    def test_new_source_parent_is_not_baseline(self):
        result = subprocess.run(
            ["git", "-C", str(self.repo), "merge-base", "--is-ancestor",
             self.parent2["oid"], self.initial],
            env=self.env, capture_output=True, timeout=3, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.transport_result(baseline=result.returncode == 0))

    def test_single_parent_source_commit_remains_checked(self):
        node = self.node_at(self.parent1["oid"])
        self.assertEqual(node["parents"]["totalCount"], 1)
        self.assertFalse(self.transport_result(node=node))

    def test_genuine_conflict_resolution_remains_checked(self):
        original = self.repo
        try:
            self.__class__.repo = self.root / "resolution"
            self.repo.mkdir()
            self.git("init", "--initial-branch=main")
            self.git("config", "user.name", "Owned fixture")
            self.git("config", "user.email", "fixture@example.invalid")
            (self.repo / "common").write_text("initial\n")
            self.commit("initial")
            self.git("checkout", "-b", "feature")
            (self.repo / "common").write_text("feature\n")
            self.commit("feature")
            self.git("checkout", "main")
            (self.repo / "common").write_text("canonical\n")
            self.commit("canonical")
            self.git("checkout", "feature")
            self.git("merge", "--no-ff", "main", allow=(1,))
            (self.repo / "common").write_text("new merge resolution\n")
            self.commit("resolution")
            node = self.node_at(self.git("rev-parse", "HEAD").strip())
            trees = [self.tree_at(c["tree"]["oid"]) for c in
                     (node, *node["parents"]["nodes"])]
            self.assertFalse(self.transport_result(node=node, trees=trees))
        finally:
            self.__class__.repo = original

    def test_same_actor_new_commit_prevents_actor_exclusion(self):
        new = self.node_at(self.parent1["oid"])
        result = self.call(
            "m.transportOnlyLogins(d.commits,new Map(d.proofs))",
            {"commits": [self.node, new], "proofs": [[self.transport, True]]},
        )
        self.assertEqual(json.loads(result.stdout), [])

    def test_only_proven_transport_actor_can_be_excluded(self):
        result = self.call(
            "m.transportOnlyLogins(d.commits,new Map(d.proofs))",
            {"commits": [self.node], "proofs": [[self.transport, True]]},
        )
        self.assertEqual(json.loads(result.stdout), ["transport-fixture"])

    def test_missing_proof_retains_actor(self):
        result = self.call(
            "m.transportOnlyLogins(d.commits,new Map())", {"commits": [self.node]},
        )
        self.assertEqual(json.loads(result.stdout), [])

    def test_author_login_precedence_matches_pinned_action(self):
        result = self.call("m.attributedLogin(d)", {
            "author": {"user": {"login": "author-fixture"}},
            "committer": {"user": {"login": "committer-fixture"}},
        })
        self.assertEqual(json.loads(result.stdout), "author-fixture")

    def test_unknown_raw_name_cannot_create_allowlist_entry(self):
        result = self.call("m.attributedLogin(d)", {"author": {"name": "Raw Name"}})
        self.assertIsNone(json.loads(result.stdout))

    def test_wildcard_login_cannot_create_allowlist_entry(self):
        result = self.call("m.attributedLogin(d)", {"author": {"user": {"login": "*"}}})
        self.assertIsNone(json.loads(result.stdout))

    def test_incomplete_tree_refuses(self):
        trees = json.loads(json.dumps(self.trees))
        trees[0]["truncated"] = True
        result = self.call("m.isBaselineTransport(d.node,...d.trees,true)",
                           {"node": self.node, "trees": trees})
        self.assertNotEqual(result.returncode, 0)

    def test_changed_tree_identity_refuses(self):
        trees = json.loads(json.dumps(self.trees))
        trees[0]["sha"] = "f" * 40
        result = self.call("m.isBaselineTransport(d.node,...d.trees,true)",
                           {"node": self.node, "trees": trees})
        self.assertNotEqual(result.returncode, 0)

    def test_duplicate_tree_path_refuses(self):
        trees = json.loads(json.dumps(self.trees))
        trees[0]["tree"].append(trees[0]["tree"][0])
        result = self.call("m.isBaselineTransport(d.node,...d.trees,true)",
                           {"node": self.node, "trees": trees})
        self.assertNotEqual(result.returncode, 0)

    def test_unknown_leaf_mode_refuses(self):
        trees = json.loads(json.dumps(self.trees))
        trees[0]["tree"][0]["mode"] = "999999"
        result = self.call("m.isBaselineTransport(d.node,...d.trees,true)",
                           {"node": self.node, "trees": trees})
        self.assertNotEqual(result.returncode, 0)

    def test_changed_mode_remains_source_contribution(self):
        trees = json.loads(json.dumps(self.trees))
        target = next(r for r in trees[0]["tree"] if r["path"] == "baseline.txt")
        target["mode"] = "100644"
        self.assertFalse(self.transport_result(trees=trees))

    def test_escape_path_refuses(self):
        trees = json.loads(json.dumps(self.trees))
        trees[0]["tree"][0]["path"] = "../outside"
        result = self.call("m.isBaselineTransport(d.node,...d.trees,true)",
                           {"node": self.node, "trees": trees})
        self.assertNotEqual(result.returncode, 0)

    def test_changed_head_refuses_final_binding(self):
        before = {"state": "open", "base": {"sha": "a", "ref": "main",
                  "repo": {"full_name": "org/repo"}}, "head": {"sha": "b"}, "commits": 1}
        after = json.loads(json.dumps(before))
        after["head"]["sha"] = "c"
        result = self.call("m.samePull(d.before,d.after)", {"before": before, "after": after})
        self.assertFalse(json.loads(result.stdout))

    def test_unchanged_open_pull_preserves_binding(self):
        before = {"state": "open", "base": {"sha": "a", "ref": "main",
                  "repo": {"full_name": "org/repo"}}, "head": {"sha": "b"}, "commits": 1}
        result = self.call("m.samePull(d.before,d.before)", {"before": before})
        self.assertTrue(json.loads(result.stdout))



    def connection(self):
        before = {"state": "open", "base": {"sha": self.baseline, "ref": "main",
                  "repo": {"full_name": "org/repo"}}, "head": {"sha": self.transport},
                  "commits": 1}
        pull = {"baseRefOid": self.baseline, "headRefOid": self.transport,
                "commits": {"totalCount": 1, "pageInfo": {"hasNextPage": False},
                            "nodes": [{"commit": self.node}]}}
        return before, pull

    def test_actual_git_commit_connection_is_complete(self):
        before, pull = self.connection()
        result = self.call("m.checkedCommits(d.before,d.pull,{owner:'org',repo:'repo'})",
                           {"before": before, "pull": pull})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["oid"], self.transport)

    def test_partial_commit_page_refuses(self):
        before, pull = self.connection()
        pull["commits"]["pageInfo"]["hasNextPage"] = True
        result = self.call("m.checkedCommits(d.before,d.pull,{owner:'org',repo:'repo'})",
                           {"before": before, "pull": pull})
        self.assertNotEqual(result.returncode, 0)

    def test_commit_count_mismatch_refuses(self):
        before, pull = self.connection()
        before["commits"] = 2
        result = self.call("m.checkedCommits(d.before,d.pull,{owner:'org',repo:'repo'})",
                           {"before": before, "pull": pull})
        self.assertNotEqual(result.returncode, 0)

    def test_changed_graphql_head_refuses(self):
        before, pull = self.connection()
        pull["headRefOid"] = self.initial
        result = self.call("m.checkedCommits(d.before,d.pull,{owner:'org',repo:'repo'})",
                           {"before": before, "pull": pull})
        self.assertNotEqual(result.returncode, 0)

    def test_changed_author_identity_changes_final_snapshot(self):
        before, _ = self.connection()
        other = json.loads(json.dumps(self.node))
        other["author"]["user"]["login"] = "new-source-actor"
        result = self.call(
            "JSON.stringify(m.snapshotFor(d.before,[d.original],true))==="
            "JSON.stringify(m.snapshotFor(d.before,[d.other],true))",
            {"before": before, "original": self.node, "other": other},
        )
        self.assertFalse(json.loads(result.stdout))

    def test_changed_database_id_changes_final_snapshot(self):
        before, _ = self.connection()
        original = json.loads(json.dumps(self.node))
        original["author"]["user"]["databaseId"] = 100
        other = json.loads(json.dumps(original))
        other["author"]["user"]["databaseId"] = 101
        result = self.call(
            "JSON.stringify(m.snapshotFor(d.before,[d.original],true))==="
            "JSON.stringify(m.snapshotFor(d.before,[d.other],true))",
            {"before": before, "original": original, "other": other},
        )
        self.assertFalse(json.loads(result.stdout))

    def test_current_snapshot_is_stable(self):
        before, _ = self.connection()
        result = self.call(
            "JSON.stringify(m.snapshotFor(d.before,[d.original],true))==="
            "JSON.stringify(m.snapshotFor(d.before,[d.original],true))",
            {"before": before, "original": self.node},
        )
        self.assertTrue(json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
