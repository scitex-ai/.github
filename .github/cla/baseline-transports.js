'use strict';

const OID = /^[0-9a-f]{40}$/;
const LOGIN = /^[A-Za-z0-9][A-Za-z0-9-]{0,38}$/;
const MODES = new Map([
  ['100644', 'blob'], ['100755', 'blob'], ['120000', 'blob'], ['160000', 'commit'],
]);

function leafTree(response, expected) {
  if (!OID.test(expected) || response.sha !== expected || response.truncated !== false ||
      !Array.isArray(response.tree) || response.tree.length > 100000) {
    throw new Error('Incomplete Git tree proof');
  }
  const rows = new Map();
  const names = new Set();
  for (const row of response.tree) {
    if (typeof row.path !== 'string' || !row.path || row.path.includes('\0') ||
        row.path.startsWith('/') || row.path.split('/').some(p => !p || p === '.' || p === '..') ||
        names.has(row.path) || !OID.test(row.sha)) {
      throw new Error('Invalid Git tree entry');
    }
    names.add(row.path);
    if (row.type === 'tree') {
      if (row.mode !== '040000') throw new Error('Invalid Git directory');
      continue;
    }
    if (MODES.get(row.mode) !== row.type) throw new Error('Unknown Git leaf');
    rows.set(row.path, row.mode + ':' + row.type + ':' + row.sha);
  }
  return rows;
}

function isBaselineTransport(commit, mergeTree, firstTree, secondTree, secondIsBaseline) {
  if (!commit || !OID.test(commit.oid) || commit.parents.totalCount !== 2 ||
      commit.parents.nodes.length !== 2 || !secondIsBaseline) return false;
  const [first, second] = commit.parents.nodes;
  if (!OID.test(first.oid) || !OID.test(second.oid) ||
      first.oid === second.oid || [first.oid, second.oid].includes(commit.oid)) return false;
  const merge = leafTree(mergeTree, commit.tree.oid);
  const parent1 = leafTree(firstTree, first.tree.oid);
  const parent2 = leafTree(secondTree, second.tree.oid);
  // Only the exact first-parent delta matters for this commit's contribution.
  // A deletion is an absent entry, and mode/link/gitlink changes remain distinct.
  for (const path of new Set([...merge.keys(), ...parent1.keys()])) {
    const entry = merge.get(path);
    if (entry !== parent1.get(path) && entry !== parent2.get(path)) return false;
  }
  return true;
}

function attributedLogin(commit) {
  // Keep the pinned CLA action's precedence; raw names are never new allowlist entries.
  const identity = commit.author?.user || commit.committer?.user || commit.author || commit.committer;
  return identity && LOGIN.test(identity.login || '') ? identity.login : null;
}

function transportOnlyLogins(commits, proofs) {
  const actors = new Map();
  for (const commit of commits) {
    const login = attributedLogin(commit);
    if (!login) continue;
    const allProven = proofs.get(commit.oid) === true;
    actors.set(login, (actors.get(login) ?? true) && allProven);
  }
  return [...actors].filter(([, allProven]) => allProven).map(([login]) => login).sort();
}

function samePull(before, after) {
  return before.state === 'open' && after.state === 'open' &&
    before.base.sha === after.base.sha && before.head.sha === after.head.sha &&
    before.base.ref === after.base.ref && before.base.repo.full_name === after.base.repo.full_name &&
    before.commits === after.commits;
}

async function qualify({github, context, core, ownerAllowlist}) {
  const original = ownerAllowlist;
  const repo = context.repo;
  const number = context.issue.number;
  let calls = 0;
  const deadline = Date.now() + 30000;
  async function read(method, args) {
    if (++calls > 48 || Date.now() >= deadline) throw new Error('Proof budget exhausted');
    const response = await method({...repo, ...args, request: {timeout: 4000}});
    if (Date.now() >= deadline) throw new Error('Proof deadline exhausted');
    return response.data;
  }
  const before = await read(github.rest.pulls.get, {pull_number: number});
  if (before.state !== 'open') {
    core.setOutput('allowlist', original);
    return;
  }
  const query = `query($owner:String!,$name:String!,$number:Int!) {
    repository(owner:$owner,name:$name) { pullRequest(number:$number) {
      baseRefOid headRefOid commits(first:100) {
        totalCount pageInfo { hasNextPage } nodes { commit {
          oid tree { oid } author { user { login } } committer { user { login } }
          parents(first:3) { totalCount nodes { oid tree { oid } } }
        } }
      }
    } }
  }`;
  if (++calls > 48) throw new Error('Proof budget exhausted');
  const data = await github.graphql(query, {
    owner: repo.owner, name: repo.repo, number, request: {timeout: 4000},
  });
  const pull = data.repository.pullRequest;
  const connection = pull.commits;
  // The pinned action reads only its first 100 commits. Never label a truncated
  // actor set as complete, even if that first page contains a transport merge.
  if (connection.pageInfo.hasNextPage || connection.totalCount !== before.commits ||
      connection.totalCount > 100 || connection.nodes.length !== connection.totalCount ||
      pull.baseRefOid !== before.base.sha || pull.headRefOid !== before.head.sha ||
      before.base.repo.full_name !== repo.owner + '/' + repo.repo) {
    throw new Error('Incomplete or changed PR proof');
  }
  const commits = connection.nodes.map(row => row.commit);
  if (new Set(commits.map(c => c.oid)).size !== commits.length ||
      commits.some(c => !OID.test(c.oid))) throw new Error('Invalid PR commit identities');
  const proofs = new Map();
  const treeCache = new Map();
  async function getTree(oid) {
    if (!treeCache.has(oid)) treeCache.set(oid, await read(github.rest.git.getTree, {
      tree_sha: oid, recursive: '1',
    }));
    return treeCache.get(oid);
  }
  let baselineProtected = false;
  try {
    const branch = await read(github.rest.repos.getBranch, {branch: before.base.ref});
    baselineProtected = branch.protected === true && branch.commit.sha === before.base.sha;
  } catch (_) {
    // An unknown baseline supplies no exclusion. The canonical CLA action still runs.
  }
  for (const commit of commits) {
    if (!baselineProtected || commit.parents.totalCount !== 2 ||
        commit.parents.nodes.length !== 2 || !attributedLogin(commit)) continue;
    // A genuine contribution anywhere in this actor's PR commits already
    // prevents exclusion; do not spend proof requests on its other merges.
    if (commits.some(other => attributedLogin(other) === attributedLogin(commit) &&
        (other.parents.totalCount !== 2 || other.parents.nodes.length !== 2))) continue;
    try {
      const [first, second] = commit.parents.nodes;
      if (![commit.tree.oid, first.oid, second.oid, first.tree.oid, second.tree.oid].every(s => OID.test(s))) {
        throw new Error('Invalid merge identities');
      }
      const comparison = await read(github.rest.repos.compareCommitsWithBasehead, {
        basehead: second.oid + '...' + before.base.sha,
      });
      const inBaseline = ['ahead', 'identical'].includes(comparison.status) &&
        comparison.merge_base_commit.sha === second.oid;
      if (!inBaseline) continue;
      proofs.set(commit.oid, isBaselineTransport(commit,
        await getTree(commit.tree.oid), await getTree(first.tree.oid),
        await getTree(second.tree.oid), true));
    } catch (_) {
      core.warning('Baseline transport proof unavailable; canonical CLA checking retained.');
    }
  }
  const after = await read(github.rest.pulls.get, {pull_number: number});
  if (!samePull(before, after)) throw new Error('PR changed during attribution proof');
  if (baselineProtected) {
    const branch = await read(github.rest.repos.getBranch, {branch: before.base.ref});
    if (branch.protected !== true || branch.commit.sha !== before.base.sha) {
      throw new Error('Protected baseline changed during attribution proof');
    }
  }
  const extras = transportOnlyLogins(commits, proofs);
  core.setOutput('allowlist', [original, ...extras].filter(Boolean).join(','));
  core.info('Qualified baseline-only transport actors: ' + extras.length);
}

module.exports = {leafTree, isBaselineTransport, attributedLogin, transportOnlyLogins, samePull, qualify};
