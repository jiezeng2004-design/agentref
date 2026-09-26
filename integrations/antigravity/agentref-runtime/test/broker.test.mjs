import test from 'node:test';
import assert from 'node:assert/strict';
import { createBroker, fixtureClient, SOURCES } from '../broker.mjs';
import { loopback } from '../cdp.mjs';

test('all six sources require an offered ticket, revalidate and read only the selected context', async () => {
  for (const agent of SOURCES) {
    const base = fixtureClient(); let reads = 0, lists = 0;
    const broker = createBroker({ async sessions(...args) { lists++; return base.sessions(...args); }, async context(...args) { reads++; return base.context(...args); } });
    const list = await broker.call({ method: 'sessions', agent, query: '' });
    assert.equal(reads, 0); assert.equal(list.items.length, 2);
    const result = await broker.call({ method: 'context', ticket: list.items[1].ticket });
    assert.equal(reads, 1); assert.equal(lists, 2); assert.equal(result.ref, agent + ':' + '2'.repeat(16));
    await assert.rejects(broker.call({ method: 'context', ticket: list.items[1].ticket }));
  }
});

test('invalid sources, arbitrary refs, cancelled and expired tickets fail closed', async () => {
  let now = 1; const broker = createBroker(fixtureClient(), () => now);
  await assert.rejects(broker.call({ method: 'sessions', agent: '../../escape', query: '' }));
  await assert.rejects(broker.call({ method: 'context', ref: 'codex:' + '1'.repeat(16) }));
  let list = await broker.call({ method: 'sessions', agent: 'codex', query: '' });
  now += 120001;
  await assert.rejects(broker.call({ method: 'context', ticket: list.items[0].ticket }));
  list = await broker.call({ method: 'sessions', agent: 'codex', query: '' });
  broker.cancel(); await assert.rejects(broker.call({ method: 'context', ticket: list.items[0].ticket }));
});

test('stale list results and removed selected sources cannot produce context', async () => {
  let finish; const broker = createBroker({ sessions: () => new Promise(resolve => { finish = resolve; }) });
  const waiting = broker.call({ method: 'sessions', agent: 'codex', query: '' });
  broker.cancel(); finish({ rows: [] }); await assert.rejects(waiting);
  let count = 0, read = false;
  const base = fixtureClient();
  const changed = createBroker({ sessions: agent => ++count === 1 ? base.sessions(agent) : { rows: [] }, context: () => { read = true; } });
  const list = await changed.call({ method: 'sessions', agent: 'codex', query: '' });
  await assert.rejects(changed.call({ method: 'context', ticket: list.items[0].ticket })); assert.equal(read, false);
});

test('query filters before fifty row limit; warnings and size limits are preserved', async () => {
  const rows = Array.from({ length: 100 }, (_, n) => ({ agent: 'codex', ref: 'codex:' + n.toString(16).padStart(16, '0'), title: 'sample-' + n }));
  const broker = createBroker({ sessions: async () => ({ rows, incomplete: true }), context: async () => 'x'.repeat(256 * 1024 + 1) });
  let list = await broker.call({ method: 'sessions', agent: 'codex', query: '' });
  assert.equal(list.items.length, 50); assert.equal(list.total, 100); assert.equal(list.incomplete, true);
  list = await broker.call({ method: 'sessions', agent: 'codex', query: 'sample-99' });
  assert.equal(list.items.length, 1); await assert.rejects(broker.call({ method: 'context', ticket: list.items[0].ticket }));
});

test('bounded indexed queries pass through and selected refs are revalidated exactly', async () => {
  const base = fixtureClient(); const queries = [];
  const broker = createBroker({
    async sessions(agent, signal, query) {
      queries.push(query);
      const result = await base.sessions(agent, signal);
      return { ...result, queryApplied: true, hasMore: query === '' };
    },
    context: base.context,
  });
  const list = await broker.call({ method: 'sessions', agent: 'codex', query: '' });
  assert.equal(list.items.length, 2);
  assert.equal(list.hasMore, true);
  assert.equal(list.total, null);
  const selected = await broker.call({ method: 'context', ticket: list.items[1].ticket });
  assert.equal(selected.ref, 'codex:' + '2'.repeat(16));
  assert.deepEqual(queries, ['', 'codex:' + '2'.repeat(16)]);
});

test('only explicit loopback debugger endpoints are accepted', () => {
  assert.equal(loopback('http://127.0.0.1:1234/json/list').port, '1234');
  for (const url of ['https://example.com:443/', 'http://user:pass@localhost:1234/', 'file:///tmp', 'http://localhost/', 'ws://127.0.0.1:1234/']) assert.throws(() => loopback(url));
});
