import { randomUUID } from 'node:crypto';

export const SOURCES = ['claude', 'codex', 'grok', 'opencode', 'antigravity', 'dsh'];
const clean = value => String(value ?? '').replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g, ' ').slice(0, 240);

// The renderer can choose only an expiring ticket from the current list, never
// provide a path, executable, arbitrary ref, workspace, or shell command.
export function createBroker(client, now = Date.now) {
  let generation = 0;
  let controller;
  let tickets = new Map();
  const cancel = () => { generation++; controller?.abort(); controller = undefined; tickets.clear(); };
  return {
    cancel,
    async call(request) {
      if (!request || !['sessions', 'context', 'cancel'].includes(request.method)) throw new Error('Invalid request');
      if (request.method === 'cancel') { cancel(); return {}; }
      if (request.method === 'sessions') {
        if (!SOURCES.includes(request.agent) || typeof request.query !== 'string' || request.query.length > 120) throw new Error('Invalid source or query');
        cancel(); const own = generation; controller = new AbortController();
        const result = await client.sessions(request.agent, controller.signal, request.query);
        if (own !== generation) throw new Error('Cancelled');
        const query = request.query.toLowerCase();
        const rows = result.rows.filter(row => row.agent === request.agent &&
          typeof row.ref === 'string' && new RegExp('^' + request.agent + ':[a-f0-9]{16}$').test(row.ref) &&
          (result.queryApplied || !query || [row.title, row.cwd, row.ref].some(value => String(value ?? '').toLowerCase().includes(query))));
        const hasMore = Boolean(result.hasMore) || rows.length > 50;
        const items = rows.slice(0, 50).map(row => {
          const ticket = randomUUID(); tickets.set(ticket, { row, until: now() + 120000 });
          return { ticket, title: clean(row.title || row.ref), detail: clean(`${row.cwd || ''} · ${row.updatedAt || ''}`) };
        });
        const total = result.total ?? (result.queryApplied && hasMore ? null : rows.length);
        return { items, total, hasMore, incomplete: Boolean(result.incomplete) };
      }
      const selected = tickets.get(request.ticket);
      if (!selected || selected.until < now()) throw new Error('Selection expired; reopen the list');
      tickets.clear(); const own = ++generation; controller?.abort(); controller = new AbortController();
      const current = await client.sessions(selected.row.agent, controller.signal, selected.row.ref);
      if (own !== generation || !current.rows.some(row => row.agent === selected.row.agent && row.ref === selected.row.ref)) throw new Error('Selection changed; reopen the list');
      const context = await client.context(selected.row, controller.signal);
      if (own !== generation) throw new Error('Cancelled');
      if (typeof context !== 'string' || !context.trim() || Buffer.byteLength(context) > 256 * 1024) throw new Error('Invalid or oversized context');
      return { context, agent: selected.row.agent, ref: selected.row.ref,
        title: clean(selected.row.title || selected.row.ref), incomplete: Boolean(current.incomplete) };
    },
  };
}

export function fixtureClient() {
  return {
    async sessions(agent) { return { incomplete: false, rows: [1, 2].map(n => ({ agent,
      ref: `${agent}:${String(n).repeat(16)}`, title: `合成测试会话 ${n}`, cwd: 'SYNTHETIC ONLY', updatedAt: '2026-09-17' })) }; },
    async context(row) { return `SYNTHETIC CONTEXT ${row.ref}\n这是合成数据，不是真实会话。`; },
  };
}
