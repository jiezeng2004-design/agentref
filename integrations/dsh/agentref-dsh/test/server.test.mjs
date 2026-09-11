import assert from 'node:assert/strict';
import test from 'node:test';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { createRoutes, sanitizeRows, validAgent, validRef } from '../src/index.js';

async function requestRoute(url, { host = 'localhost:3000', origin, encrypted = false, connection, remoteAddress = '127.0.0.1' } = {}) {
  const request = { method: 'GET', url, headers: { host, ...(origin === undefined ? {} : { origin }) }, socket: { remoteAddress, encrypted } };
  const response = { writeHead(status) { this.status = status; }, end(body) { this.body = JSON.parse(body); } };
  await createRoutes({ command: 'synthetic-agentref', connection })[0].handler(request, response);
  return response;
}

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
  assert.deepEqual(calls.filter(args => args[0] === 'context'), [['context', rows[50].ref]]);
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
