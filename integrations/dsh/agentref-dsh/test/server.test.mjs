import assert from 'node:assert/strict';
import test from 'node:test';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { createRoutes, runAgentRef, sanitizeRows, validAgent, validRef } from '../src/index.js';

async function requestRoute(url, { host = 'localhost:3000', origin, encrypted = false, connection, remoteAddress = '127.0.0.1', handler } = {}) {
  const request = { method: 'GET', url, headers: { host, ...(origin === undefined ? {} : { origin }) }, socket: { remoteAddress, encrypted } };
  const response = { writeHead(status) { this.status = status; }, end(body) { this.body = JSON.parse(body); } };
  await (handler ?? createRoutes({ command: 'synthetic-agentref', connection })[0].handler)(request, response);
  return response;
}

test('large metadata crosses the real child-process boundary without raising the context limit', async (t) => {
  const exec = childProcess.execFile;
  const limits = [];
  const allRows = Array.from({ length: 1000 }, (_, i) => ({ agent: 'codex', ref: 'codex:' + String(i).padStart(8, '0'),
    title: i === 999 ? 'last-match' : 'x'.repeat(80), cwd: 'x'.repeat(100), sourcePath: 'x'.repeat(100) }));
  t.mock.method(childProcess, 'execFile', (_command, args, options, callback) => {
    limits.push({ args, maxBuffer: options.maxBuffer });
    if (args[0] !== 'sessions') return exec(process.execPath, ['-e', "process.stdout.write('selected synthetic context')"], options, callback);
    const query = args.includes('--query') ? args[args.indexOf('--query') + 1].toLowerCase() : '';
    const limit = Number(args[args.indexOf('--limit') + 1]);
    const rows = allRows.filter(row => !query || [row.title, row.cwd, row.ref].some(value => value.toLowerCase().includes(query))).slice(0, limit);
    return exec(process.execPath, ['-e', `process.stdout.write(${JSON.stringify(JSON.stringify(rows))})`], options, callback);
  });
  syncBuiltinESMExports();
  t.after(() => { t.mock.restoreAll(); syncBuiltinESMExports(); });
  const list = await requestRoute('/_dsh/agentref/sessions?agent=codex');
  assert.equal(list.status, 200);
  assert.equal(list.body.sessions.length, 50);
  assert.equal(list.body.incomplete, false);
  assert.ok(list.body.sessions.every(row => !('sourcePath' in row)));
  const search = await requestRoute('/_dsh/agentref/sessions?agent=codex&query=last-match');
  assert.equal(search.body.sessions[0].ref, 'codex:00000999');
  assert.ok(limits.every(call => call.args[0] === 'sessions'), 'metadata validation does not read context');
  const selected = await requestRoute('/_dsh/agentref/context?ref=codex:00000999');
  assert.equal(selected.status, 200);
  assert.equal(selected.body.context, 'selected synthetic context');
  const sessionCalls = limits.filter(call => call.args[0] === 'sessions');
  assert.ok(sessionCalls.every(call => call.maxBuffer === 8 * 1024 * 1024));
  assert.deepEqual(sessionCalls.map(call => call.args.slice(call.args.indexOf('--limit'), call.args.indexOf('--limit') + 2)),
    [['--limit', '50'], ['--limit', '50'], ['--limit', '1']]);
  assert.ok(sessionCalls[1].args.includes('last-match'), 'search is delegated to the CLI before serialization');
  assert.ok(sessionCalls[2].args.includes('codex:00000999'), 'selected ref is revalidated with an exact query');
  assert.equal(limits.at(-1).maxBuffer, 256 * 1024);
});

test('metadata overflow fails explicitly, clears in-flight state, and can be retried', async (t) => {
  const exec = childProcess.execFile;
  let oversized = true;
  t.mock.method(childProcess, 'execFile', (_command, _args, options, callback) => exec(process.execPath,
    ['-e', oversized ? "process.stdout.write('x'.repeat(8*1024*1024+1))" : "process.stdout.write('[]')"], options, callback));
  syncBuiltinESMExports();
  t.after(() => { t.mock.restoreAll(); syncBuiltinESMExports(); });
  const handler = createRoutes({ command: 'synthetic-only' })[0].handler;
  const failed = await requestRoute('/_dsh/agentref/sessions?agent=codex', { handler });
  assert.equal(failed.status, 503);
  assert.match(failed.body.error, /metadata exceeds the 8 MiB limit/);
  assert.equal(failed.body.sessions, undefined);
  oversized = false;
  const retry = await requestRoute('/_dsh/agentref/sessions?agent=codex', { handler });
  assert.deepEqual(retry.body, { ok: true, sessions: [], incomplete: false });
});

test('older AgentRef CLIs fall back to their compatible full-list command', async (t) => {
  const calls = [];
  t.mock.method(childProcess, 'execFile', (_command, args, _options, callback) => {
    calls.push(args);
    if (args.includes('--limit')) callback(Object.assign(new Error('unsupported option'), { code: 2 }), '', 'unrecognized arguments: --limit');
    else callback(null, '[]', '');
  });
  syncBuiltinESMExports();
  t.after(() => { t.mock.restoreAll(); syncBuiltinESMExports(); });
  const result = await requestRoute('/_dsh/agentref/sessions?agent=claude&query=legacy');
  assert.equal(result.status, 200);
  assert.deepEqual(result.body.sessions, []);
  assert.equal(calls.length, 2);
  assert.ok(calls[0].includes('--query'));
  assert.deepEqual(calls[1], ['sessions', '--agent', 'claude', '--json']);
});

test('real context output above 256 KiB is still rejected', async () => {
  await assert.rejects(runAgentRef(process.execPath, ['-e', "process.stdout.write('x'.repeat(256*1024+1))"]), /context exceeds the local safety limit/);
});

test('successful metadata warnings remain visible without forwarding raw stderr', async (t) => {
  let warned = true;
  t.mock.method(childProcess, 'execFile', (_command, _args, _options, callback) => callback(null, '[]', warned
    ? 'agentref: index incomplete; synthetic-private-path; synthetic-sensitive-detail' : ''));
  syncBuiltinESMExports();
  t.after(() => { t.mock.restoreAll(); syncBuiltinESMExports(); });
  const handler = createRoutes({ command: 'synthetic-only' })[0].handler;
  const partial = await requestRoute('/_dsh/agentref/sessions?agent=claude', { handler });
  assert.deepEqual(partial.body, { ok: true, sessions: [], incomplete: true });
  assert.ok(!JSON.stringify(partial.body).includes('synthetic-private-path'));
  warned = false;
  const healthy = await requestRoute('/_dsh/agentref/sessions?agent=claude', { handler });
  assert.equal(healthy.body.incomplete, false, 'completed diagnostics are not cached');
});

test('a searched session beyond the first fifty can be read, but a missing ref cannot', async (t) => {
  const rows = Array.from({ length: 51 }, (_, i) => ({ agent: 'claude', ref: `claude:${String(i).padStart(8, '0')}`, title: i === 50 ? 'older-match' : 'recent' }));
  const calls = [];
  t.mock.method(childProcess, 'execFile', (_command, args, _options, callback) => {
    calls.push(args);
    callback(null, args[0] === 'sessions' ? JSON.stringify(rows) : 'synthetic selected context', '');
  });
  syncBuiltinESMExports();
  t.after(() => { t.mock.restoreAll(); syncBuiltinESMExports(); });
  const found = await requestRoute('/_dsh/agentref/sessions?agent=claude&query=older-match');
  assert.equal(found.body.sessions[0].ref, rows[50].ref);
  const selected = await requestRoute(`/_dsh/agentref/context?ref=${rows[50].ref}`);
  assert.equal(selected.status, 200);
  assert.equal(selected.body.context, 'synthetic selected context');
  const missing = await requestRoute('/_dsh/agentref/context?ref=claude:99999999');
  assert.equal(missing.status, 503);
  assert.deepEqual(calls.filter(args => args[0] === 'context'), [['context', rows[50].ref, '--agent', 'claude']]);
});

test('same-query searches share only in-flight metadata, while different queries and selections are independent', async (t) => {
  const calls = [];
  t.mock.method(childProcess, 'execFile', (_command, args, _options, callback) => calls.push({ args, callback }));
  syncBuiltinESMExports();
  t.after(() => { t.mock.restoreAll(); syncBuiltinESMExports(); });
  const handler = createRoutes({ command: 'synthetic-agentref' })[0].handler;
  const request = (path) => requestRoute('/_dsh/agentref/' + path, { handler });
  const first = request('sessions?agent=claude&query=alpha');
  const duplicate = request('sessions?agent=claude&query=alpha');
  assert.equal(calls.length, 1);
  const different = request('sessions?agent=claude&query=beta');
  assert.equal(calls.length, 2);
  const foreign = request('sessions?agent=dsh');
  assert.equal(calls.length, 3);
  const selection = request('context?ref=claude:11111111');
  assert.equal(calls.length, 4);
  calls[3].callback(null, '[]', '');
  assert.equal((await selection).status, 503);
  assert.ok(calls.every(call => call.args[0] === 'sessions'));
  calls[0].callback(null, JSON.stringify([{ agent: 'claude', ref: 'claude:11111111', title: 'alpha' }]), '');
  calls[1].callback(null, JSON.stringify([{ agent: 'claude', ref: 'claude:22222222', title: 'beta' }]), '');
  calls[2].callback(null, '[]', '');
  assert.equal((await first).body.sessions[0].title, 'alpha');
  assert.equal((await duplicate).body.sessions[0].title, 'alpha');
  assert.equal((await different).body.sessions[0].title, 'beta');
  await foreign;
  const failure = request('sessions?agent=claude');
  assert.equal(calls.length, 5);
  calls[4].callback(new Error('synthetic failure'), '', '');
  assert.equal((await failure).status, 503);
  const retry = request('sessions?agent=claude');
  assert.equal(calls.length, 6);
  calls[5].callback(null, '[]', '');
  assert.equal((await retry).status, 200);
});

test('origin validation rejects different ports, schemes, aliases and malformed origins', async () => {
  for (const origin of ['http://localhost:9999', 'https://localhost:3000', 'http://127.0.0.1:3000', 'null', 'not a URL', 'http://localhost:3000/path', 'http://user@localhost:3000', 'http://localhost:3000?x=1', 'http://localhost:3000#x', 'ftp://localhost:3000', ['http://localhost:3000']]) {
    assert.equal((await requestRoute('/_dsh/agentref/unknown', { origin })).status, 403, origin);
  }
});

test('same-origin HTTP and TLS, default ports, IPv6 and origin-less local requests remain allowed', async () => {
  for (const options of [{}, { origin: 'http://localhost:3000' }, { host: 'LOCALHOST:3000', origin: 'http://localhost:3000' }, { host: 'localhost:80', origin: 'http://localhost' }, { host: 'localhost:443', origin: 'https://localhost', encrypted: true }, { host: '[::1]:3000', origin: 'http://[::1]:3000' }, { host: '[::1]', origin: 'http://[::1]', remoteAddress: '::1' }]) {
    assert.equal((await requestRoute('/_dsh/agentref/unknown', options)).status, 404, JSON.stringify(options));
  }
  assert.equal((await requestRoute('/_dsh/agentref/unknown', { connection: { requestRejection: () => 401 } })).status, 401);
});

test('malformed hosts and non-loopback peers stay forbidden even when the host auth allows them', async () => {
  for (const options of [{ remoteAddress: '192.0.2.1' }, ...['example.com', 'localhost:65536', 'localhost/path', 'user@localhost', 'localhost?x', '[::1]:999999', ['localhost:3000']].map(host => ({ host }))]) {
    assert.equal((await requestRoute('/_dsh/agentref/unknown', { ...options, connection: { requestRejection: () => undefined } })).status, 403);
  }
  assert.equal((await requestRoute('/_dsh/agentref/unknown', { origin: 'http://localhost:9999', connection: { requestRejection: () => undefined } })).status, 403);
});

test('accepts only the supported local source agents and exact-looking refs', () => {
  assert.equal(validAgent('claude'), true);
  assert.equal(validAgent('dsh'), true);
  assert.equal(validAgent('unsupported'), false);
  assert.equal(validRef('claude:6a1319104e1b7350'), true);
  assert.equal(validRef('claude:bad ref'), false);
  assert.equal(validRef('dsh:6a1319104e1b7350'), true);
  assert.equal(validRef('unsupported:6a1319104e1b7350'), false);
});

test('returns metadata-only, source-filtered, bounded session rows', () => {
  const rows = sanitizeRows([
    { ref: 'claude:6a1319104e1b7350', agent: 'claude', title: '修复登录', cwd: 'D:/work', updatedAt: '2026-09-08T00:00:00Z', latestAgentState: 'turn-ended', sourcePath: 'secret-source-path' },
    { ref: 'codex:1234567890abcdef', agent: 'codex', title: '不应出现', cwd: 'D:/other' },
    { ref: 'claude:too short', agent: 'claude', title: '不应出现', cwd: 'D:/bad' }
  ], 'claude', '登录');
  assert.deepEqual(rows, [{
    ref: 'claude:6a1319104e1b7350', agent: 'claude', title: '修复登录', cwd: 'D:/work', updatedAt: '2026-09-08T00:00:00Z', latestAgentState: 'turn-ended'
  }]);
  assert.equal('sourcePath' in rows[0], false);
});
