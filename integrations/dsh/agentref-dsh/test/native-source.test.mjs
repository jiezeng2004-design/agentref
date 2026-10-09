import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

async function harness(responder) {
  const requests = [];
  const runtime = vm.createContext({ module: { exports: {} }, AbortController,
    fetch: async (url, options) => { requests.push({ url, options }); return responder(url, options); } });
  vm.runInContext(await readFile(new URL('../src/client/index.js', import.meta.url), 'utf8'), runtime);
  return { source: runtime.module.exports.createNativeSource(), api: runtime.module.exports, requests };
}
const reply = body => ({ ok: true, json: async () => body });
const row = { agent: 'dsh', ref: 'dsh:11111111', title: 'Synthetic native session', cwd: 'fixture' };
const request = query => ({ query, signal: new AbortController().signal });

test('native registration uses the host registry and returns its disposer', async () => {
  const h = await harness(() => { throw new Error('Unexpected read'); });
  let registered;
  const off = () => {};
  assert.equal(h.api.apply({ inputTriggers: { registerSource(source) { registered = source; return off; } } }), off);
  assert.equal(registered.name, 'agentref');
  assert.equal(registered.trigger, '@');
});

test('agent menu and drill are metadata-free; session candidate and selection never read context', async () => {
  const h = await harness(() => reply({ ok: true, sessions: [row] }));
  const agents = await h.source.candidates({}, request('ds'));
  assert.equal(agents.length, 1);
  assert.equal(h.requests.length, 0);
  assert.equal(h.source.onPick({ candidate: agents[0] }).text, '@dsh:');
  const rows = await h.source.candidates({}, request('dsh:Synthetic'));
  assert.match(h.requests[0].url, /agent=dsh&query=Synthetic/);
  const inserted = h.source.onPick({ candidate: rows[0] }).insert;
  assert.equal(inserted.source, 'agentref');
  assert.equal(inserted.ref, row.ref);
  assert.equal(inserted.appearance, 'session');
  assert.equal(h.requests.length, 1);
  assert.ok(!JSON.stringify(inserted).includes('context'));
});

test('native codec reads only the selected ref at submit and forwards cancellation', async () => {
  const h = await harness(() => reply({ ok: true, context: 'SELECTED_CONTEXT' }));
  const controller = new AbortController();
  const serialized = await h.source.codec.serialize(row.ref, controller.signal);
  assert.match(h.requests[0].url, /ref=dsh%3A11111111/);
  assert.equal(h.requests[0].options.signal, controller.signal);
  assert.ok(serialized.includes('SELECTED_CONTEXT'));
  assert.ok(serialized.includes('只读历史证据'));
  controller.abort();
  await assert.rejects(h.source.codec.serialize(row.ref, controller.signal));
  assert.equal(h.requests.length, 1);
});

test('stale or unavailable context fails serialization instead of sending clipboard text', async () => {
  const h = await harness(() => ({ ok: false, json: async () => ({ ok: false, error: 'selected session is no longer available' }) }));
  await assert.rejects(h.source.codec.serialize(row.ref, request('').signal), /no longer available/);
  await assert.rejects(h.source.codec.serialize('foreign:11111111', request('').signal), /Invalid/);
  assert.equal(h.requests.length, 1);
});

test('incomplete empty inventories show an unselectable warning', async () => {
  const h = await harness(() => reply({ ok: true, sessions: [], incomplete: true }));
  const rows = await h.source.candidates({}, request('dsh'));
  assert.equal(rows.length, 1);
  assert.match(rows[0].label, /不代表来源中没有会话/);
  assert.equal(h.source.onPick({ candidate: rows[0] }), undefined);
  assert.equal(h.requests.length, 1);
});

test('foreign and malformed candidate refs cannot become native chips', async () => {
  const h = await harness(() => reply({ ok: true, sessions: [row,
    { ...row, agent: 'codex', ref: 'codex:22222222' }, { ...row, ref: 'dsh:../secret' }] }));
  const rows = await h.source.candidates({}, request('dsh'));
  assert.equal(rows.length, 1);
  assert.equal(h.source.onPick({ candidate: { value: JSON.stringify({ kind: 'session', ref: 'dsh:../secret', title: 'invalid' }) } }), undefined);
});
