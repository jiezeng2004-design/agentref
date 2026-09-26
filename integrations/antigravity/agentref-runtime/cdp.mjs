// Minimal, bounded CDP transport. It never opens or changes a debugging port.
import { readFile } from 'node:fs/promises';
import path from 'node:path';

export function loopback(value, protocols = ['http:', 'https:']) {
  const url = new URL(value);
  if (!protocols.includes(url.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
      || url.username || url.password || !url.port) throw new Error('Expected an explicit loopback endpoint');
  return url;
}

export async function discover(portFile = path.join(process.env.APPDATA || '', 'antigravity', 'DevToolsActivePort')) {
  const port = Number((await readFile(portFile, 'utf8')).split('\n')[0].trim());
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid AGY debugging port');
  const endpoint = `http://127.0.0.1:${port}`;
  let response;
  try { response = await fetch(endpoint + '/json/list', { signal: AbortSignal.timeout(3000), redirect: 'error' }); }
  catch { throw new Error(`AGY DevTools endpoint is unavailable at ${endpoint}; restart AGY with the existing debugging option`); }
  if (!response.ok) throw new Error('AGY debugging discovery failed');
  const rows = await response.json();
  const pages = rows.filter(row => {
    try { loopback(row.url); return row.type === 'page' && row.title === 'Antigravity'; } catch { return false; }
  });
  if (pages.length !== 1) throw new Error('Expected exactly one AGY page; no page was changed');
  const socket = loopback(pages[0].webSocketDebuggerUrl, ['ws:']);
  if (Number(socket.port) !== port) throw new Error('Debugger endpoint mismatch');
  return { socket: socket.href, origin: new URL(pages[0].url).origin };
}

export async function connect(url) {
  loopback(url, ['ws:']);
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { socket.close(); reject(new Error('CDP connect timeout')); }, 5000);
    socket.onopen = () => { clearTimeout(timer); resolve(); };
    socket.onerror = () => { clearTimeout(timer); reject(new Error('CDP connection failed')); };
  });
  let next = 0;
  const pending = new Map();
  const listeners = new Set();
  socket.onmessage = event => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    if (message.id && pending.has(message.id)) {
      const task = pending.get(message.id); pending.delete(message.id); clearTimeout(task.timer);
      if (message.error) task.reject(new Error('CDP command failed: ' + task.method));
      else task.resolve(message.result);
    } else for (const listener of listeners) listener(message);
  };
  socket.onclose = () => {
    for (const task of pending.values()) { clearTimeout(task.timer); task.reject(new Error('AGY disconnected')); }
    pending.clear();
    for (const listener of listeners) listener({ method: 'disconnected' });
  };
  return {
    onEvent(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    call(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = ++next;
        const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP command timeout')); }, 7000);
        pending.set(id, { resolve, reject, timer, method });
        try { socket.send(JSON.stringify({ id, method, params })); }
        catch { clearTimeout(timer); pending.delete(id); reject(new Error('CDP send failed')); }
      });
    },
    async evaluate(expression, contextId) {
      const result = await this.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true,
        ...(contextId === undefined ? {} : { contextId }) });
      if (result.exceptionDetails) throw new Error('AGY renderer compatibility check failed');
      return result.result?.value;
    },
    close() { socket.close(); },
  };
}
