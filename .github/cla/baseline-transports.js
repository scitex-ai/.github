'use strict';

const {createHash} = require('crypto');
const OID = /^[0-9a-f]{40}$/;
const LOGIN = /^[A-Za-z0-9][A-Za-z0-9-]{0,38}$/;
const ACTION_LOGIN = /^[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?$/;
const MAX_COMMITS = 2000;
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

const COMMIT_FIELDS = `oid tree { oid }
  author { name user { login databaseId } }
  committer { name user { login databaseId } }
  parents(first:3) { totalCount nodes { oid tree { oid } } }`;
const PULL_QUERY = `query($owner:String!,$name:String!,$number:Int!,$cursor:String) {
  repository(owner:$owner,name:$name) { pullRequest(number:$number) {
    baseRefOid headRefOid commits(first:100,after:$cursor) {
      totalCount pageInfo { hasNextPage endCursor } nodes { commit {
        ${COMMIT_FIELDS}
      } }
    }
  } }
}`;

function commitObjectQuery(ids) {
  if (!Array.isArray(ids) || !ids.length || ids.length > 100 ||
      ids.some(id => !OID.test(id)) || new Set(ids).size !== ids.length) {
    throw new Error('Invalid canonical commit batch');
  }
  return `query($owner:String!,$name:String!) { repository(owner:$owner,name:$name) {
    ${ids.map((id, i) => `c${i}:object(oid:"${id}") {... on Commit {${COMMIT_FIELDS}}}`).join('\n')}
  } }`;
}

function boundedReaders(github, repo) {
  let calls = 0;
  const deadline = Date.now() + 30000;
  async function request(operation) {
    if (++calls > 48 || Date.now() >= deadline) throw new Error('Proof budget exhausted');
    const value = await operation();
    if (Date.now() >= deadline) throw new Error('Proof deadline exhausted');
    return value;
  }
  return {
    read: (method, args) => request(async () =>
      (await method({...repo, ...args, request: {timeout: 4000}})).data),
    query: (text, args) => request(() => github.graphql(text, {
      ...args, request: {timeout: 4000},
    })),
  };
}

function attributionTransports(github, before, repo, number, read, query) {
  return {
    getPage: async cursor => {
      const data = await query(PULL_QUERY, {owner: repo.owner, name: repo.repo, number, cursor});
      return data.repository?.pullRequest;
    },
    getComparePage: page => read(github.rest.repos.compareCommitsWithBasehead, {
      basehead: before.base.sha + '...' + before.head.sha, per_page: 100, page,
    }),
    getCommitObjects: async ids => {
      const data = await query(commitObjectQuery(ids), {owner: repo.owner, name: repo.repo});
      return ids.map((_, index) => data.repository?.['c' + index]);
    },
  };
}

function checkedCommits(before, pull, repo) {
  const connection = pull.commits;
  if (connection.pageInfo.hasNextPage || connection.totalCount !== before.commits ||
      !Number.isInteger(connection.totalCount) || connection.totalCount < 0 ||
      connection.totalCount > MAX_COMMITS || connection.nodes.length !== connection.totalCount ||
      pull.baseRefOid !== before.base.sha || pull.headRefOid !== before.head.sha ||
      before.base.repo.full_name !== repo.owner + '/' + repo.repo) {
    throw new Error('Incomplete or changed PR proof');
  }
  const commits = connection.nodes.map(row => row.commit);
  if (new Set(commits.map(c => c.oid)).size !== commits.length ||
      commits.some(c => !OID.test(c.oid))) throw new Error('Invalid PR commit identities');
  return commits;
}

function actionIdentity(commit) {
  // Exactly the pinned action's author-user / committer-user precedence. Raw
  // names have no attested numeric identity and cannot prove action coverage.
  const user = commit.author?.user || commit.committer?.user;
  if (!user || !ACTION_LOGIN.test(user.login || '') ||
      !Number.isSafeInteger(user.databaseId) || user.databaseId <= 0) {
    throw new Error('Unknown contributor cannot prove complete CLA coverage');
  }
  return user.databaseId + ':' + user.login;
}

function requireActionCoverage(commits) {
  if (commits.length <= 100) return;
  const identities = commits.map(actionIdentity);
  const logins = new Map();
  const ids = new Map();
  for (const identity of identities) {
    const [id, login] = identity.split(':');
    if ((logins.has(login) && logins.get(login) !== id) ||
        (ids.has(id) && ids.get(id) !== login)) {
      throw new Error('Contributor identity mapping changed during attribution');
    }
    logins.set(login, id);
    ids.set(id, login);
  }
  const covered = new Set(identities.slice(0, 100));
  if (identities.some(identity => !covered.has(identity))) {
    throw new Error('Pinned CLA action cannot cover every contributor');
  }
}

function commitProof(commit) {
  if (!commit || !OID.test(commit.oid) || !OID.test(commit.tree?.oid) ||
      !commit.parents || !Number.isSafeInteger(commit.parents.totalCount) ||
      commit.parents.totalCount < 0 || !Array.isArray(commit.parents.nodes) ||
      commit.parents.nodes.length !== Math.min(3, commit.parents.totalCount) ||
      commit.parents.nodes.some(p => !OID.test(p?.oid) || !OID.test(p.tree?.oid)) ||
      commit.author === undefined || commit.committer === undefined) {
    throw new Error('Incomplete canonical commit object');
  }
  const actor = value => {
    if (value === null) return null;
    const owns = key => Object.prototype.hasOwnProperty.call(value, key);
    if (typeof value !== 'object' || Array.isArray(value) || !owns('name') ||
        !(value.name === null || typeof value.name === 'string') || !owns('user')) {
      throw new Error('Incomplete canonical actor fields');
    }
    const user = value.user;
    if (user !== null && (!user || typeof user !== 'object' || Array.isArray(user) ||
        !Object.prototype.hasOwnProperty.call(user, 'login') || typeof user.login !== 'string' ||
        !Object.prototype.hasOwnProperty.call(user, 'databaseId') ||
        !(user.databaseId === null || (Number.isSafeInteger(user.databaseId) && user.databaseId > 0)))) {
      throw new Error('Incomplete canonical actor identity');
    }
    return {name: value.name,
      user: user === null ? null : {login: user.login, databaseId: user.databaseId}};
  };
  return JSON.stringify({oid: commit.oid, tree: {oid: commit.tree.oid},
    author: actor(commit.author), committer: actor(commit.committer),
    parents: {totalCount: commit.parents.totalCount,
      nodes: commit.parents.nodes.map(p => ({oid: p.oid, tree: {oid: p.tree.oid}}))}});
}

async function compareComplete(before, nodes, getComparePage, getCommitObjects) {
  // REST pagination, unlike its unpaged 250-commit response, covers the full set:
  // https://github.blog/changelog/2021-03-22-compare-rest-api-now-supports-pagination/
  const original = nodes.map(row => row.commit);
  if (original.length < 100 || new Set(original.map(c => c.oid)).size !== original.length ||
      original.some(c => !OID.test(c.oid))) throw new Error('Incomplete original action page');
  const ids = [], seen = new Set();
  for (let page = 1; ids.length < before.commits && page <= 20; page++) {
    const result = await getComparePage(page);
    if (result?.base_commit?.sha !== before.base.sha ||
        result.total_commits !== before.commits || !Array.isArray(result.commits) ||
        result.commits.length !== Math.min(100, before.commits - ids.length)) {
      throw new Error('Incomplete immutable comparison page');
    }
    for (const commit of result.commits) {
      if (!OID.test(commit?.sha) || seen.has(commit.sha)) throw new Error('Invalid comparison identities');
      ids.push(commit.sha); seen.add(commit.sha);
    }
  }
  if (ids.length !== before.commits || !seen.has(before.head.sha)) {
    throw new Error('Comparison does not cover declared PR commits and head');
  }
  const canonical = new Map();
  for (let offset = 0; offset < ids.length; offset += 100) {
    const batch = ids.slice(offset, offset + 100), objects = await getCommitObjects(batch);
    if (!Array.isArray(objects) || objects.length !== batch.length) throw new Error('Incomplete commit object batch');
    objects.forEach((commit, index) => {
      if (commit?.oid !== batch[index]) throw new Error('Canonical commit identity changed');
      commitProof(commit); canonical.set(commit.oid, commit);
    });
  }
  for (const commit of original) {
    if (!canonical.has(commit.oid) || commitProof(commit) !== commitProof(canonical.get(commit.oid))) {
      throw new Error('Original GraphQL attribution changed in canonical proof');
    }
  }
  // The pinned action reads these exact first 100, NOT REST chronological order.
  const covered = original.slice(0, 100), prefix = new Set(covered.map(c => c.oid));
  return [...covered, ...ids.filter(id => !prefix.has(id)).map(id => canonical.get(id))];
}

async function completeCommits(before, repo, getPage, fallback = {}) {
  if (!Number.isInteger(before.commits) || before.commits < 0 ||
      before.commits > MAX_COMMITS) throw new Error('PR exceeds complete attribution budget');
  if (!OID.test(before.base?.sha) || !OID.test(before.head?.sha) ||
      before.base?.repo?.full_name !== repo.owner + '/' + repo.repo) {
    throw new Error('Invalid immutable PR binding');
  }
  let cursor = null;
  const cursors = new Set();
  const nodes = [];
  for (let page = 0; page < 20; page++) {
    const pull = await getPage(cursor);
    const connection = pull?.commits;
    if (!connection || !Array.isArray(connection.nodes) || !connection.pageInfo ||
        typeof connection.pageInfo.hasNextPage !== 'boolean' ||
        connection.totalCount !== before.commits ||
        pull.baseRefOid !== before.base.sha || pull.headRefOid !== before.head.sha ||
        connection.nodes.length > 100 ||
        connection.nodes.some(row => !row || !row.commit)) {
      throw new Error('Incomplete or changed PR page');
    }
    nodes.push(...structuredClone(connection.nodes));
    if (nodes.length > before.commits) throw new Error('PR commit pages exceed declared total');
    if (!connection.pageInfo.hasNextPage) {
      let complete = nodes;
      if (nodes.length < before.commits && typeof fallback.getComparePage === 'function' &&
          typeof fallback.getCommitObjects === 'function') {
        complete = (await compareComplete(before, nodes,
          fallback.getComparePage, fallback.getCommitObjects)).map(commit => ({commit}));
      }
      const commits = checkedCommits(before, {...pull, commits: {
        totalCount: connection.totalCount, nodes: complete, pageInfo: {hasNextPage: false},
      }}, repo);
      requireActionCoverage(commits);
      return commits;
    }
    const next = connection.pageInfo.endCursor;
    if (connection.nodes.length !== 100 || typeof next !== 'string' ||
        !next || next.length > 2048 || cursors.has(next) || nodes.length >= before.commits) {
      throw new Error('PR cursor did not advance completely');
    }
    cursors.add(next);
    cursor = next;
  }
  throw new Error('PR attribution page budget exhausted');
}

function snapshotFor(before, commits, baselineProtected) {
  const identities = commits.map(c => ({oid: c.oid, author: c.author, committer: c.committer}));
  return {
    base: before.base.sha, head: before.head.sha, baseRef: before.base.ref,
    repository: before.base.repo.full_name, baselineProtected,
    identities: createHash('sha256').update(JSON.stringify(identities)).digest('hex'),
  };
}

async function verifyFinalBinding({github, context, snapshot}) {
  const repo = context.repo;
  const {read, query} = boundedReaders(github, repo);
  const before = await read(github.rest.pulls.get, {pull_number: context.issue.number});
  const transport = attributionTransports(github, before, repo, context.issue.number, read, query);
  const commits = await completeCommits(before, repo, transport.getPage, transport);
  const after = await read(github.rest.pulls.get, {pull_number: context.issue.number});
  if (!samePull(before, after)) throw new Error('PR changed during final attribution');
  const current = snapshotFor(before, commits, snapshot.baselineProtected);
  if (before.state !== 'open' || JSON.stringify(current) !== JSON.stringify(snapshot)) {
    throw new Error('CLA attribution snapshot changed during action');
  }
  if (snapshot.baselineProtected) {
    const branch = await read(github.rest.repos.getBranch, {branch: before.base.ref});
    if (branch.protected !== true || branch.commit.sha !== before.base.sha) {
      throw new Error('CLA protected baseline changed during action');
    }
  }
}

async function qualify({github, context, core, ownerAllowlist}) {
  const original = ownerAllowlist;
  const repo = context.repo;
  const number = context.issue.number;
  const {read, query} = boundedReaders(github, repo);
  const before = await read(github.rest.pulls.get, {pull_number: number});
  if (before.state !== 'open') {
    core.setOutput('allowlist', original);
    return;
  }
  if (context.payload?.pull_request?.head?.sha &&
      context.payload.pull_request.head.sha !== before.head.sha) {
    throw new Error('Triggered PR head no longer current');
  }
  const transport = attributionTransports(github, before, repo, number, read, query);
  const commits = await completeCommits(before, repo, transport.getPage, transport);
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
  core.setOutput('proof', JSON.stringify(snapshotFor(before, commits, baselineProtected)));
  core.info('Qualified baseline-only transport actors: ' + extras.length);
}

module.exports = {leafTree, isBaselineTransport, attributedLogin, transportOnlyLogins,
  samePull, checkedCommits, snapshotFor, verifyFinalBinding, qualify,
  actionIdentity, requireActionCoverage, completeCommits, PULL_QUERY, commitObjectQuery};
