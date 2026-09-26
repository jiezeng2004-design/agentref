/**
 * DSH host half for AgentRef.
 *
 * It exposes only authenticated loopback HTTP endpoints to the matching browser
 * half. Each endpoint spawns the local AgentRef CLI with an argument array;
 * selected source-session text is never cached or written by this plugin.
 */
import { execFile } from 'node:child_process';
import { existsSync, realpathSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const name = 'dsh-agentref';
export const inject = ['webServer', 'connection'];
export const API_PREFIX = '/_dsh/agentref';
export const AGENTS = Object.freeze(['claude', 'codex', 'grok', 'opencode', 'antigravity', 'dsh']);
const MAX_QUERY_LENGTH = 120;
const MAX_CONTEXT_BYTES = 256 * 1024;
const MAX_METADATA_BYTES = 8 * 1024 * 1024;
const MAX_STDERR_BYTES = 8 * 1024;

function isLoopbackAddress(address = '') {
  return address === '127.0.0.1' || address === '::1' || address === '::ffff:127.0.0.1';
}

function loopbackOrigin(host, protocol) {
  if (typeof host !== 'string' || !/^(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?$/i.test(host)) return undefined;
  try {
    return new URL(`${protocol}//${host}`).origin;
  } catch {
    return undefined;
  }
}

export function validAgent(value) {
  return typeof value === 'string' && AGENTS.includes(value);
}

export function validRef(value) {
  if (typeof value !== 'string' || value.length > 256) return false;
  const match = /^([a-z]+):([a-zA-Z0-9_-]{8,128})$/.exec(value);
  return match !== null && validAgent(match[1]);
}

export function sanitizeRows(value, agent, query = '') {
  if (!Array.isArray(value)) throw new Error('AgentRef returned an invalid session list');
  const needle = query.trim().toLocaleLowerCase();
  return value.filter((row) => {
    if (!row || typeof row !== 'object' || row.agent !== agent || !validRef(row.ref)) return false;
    return !needle || [row.title, row.cwd, row.ref].some((part) => String(part ?? '').toLocaleLowerCase().includes(needle));
  }).slice(0, 50).map((row) => ({
    ref: row.ref,
    agent: row.agent,
    title: String(row.title ?? '未命名会话').slice(0, 160),
    cwd: String(row.cwd ?? '').slice(0, 500),
    updatedAt: String(row.updatedAt ?? '').slice(0, 80),
    latestAgentState: String(row.latestAgentState ?? 'unknown').slice(0, 80)
  }));
}

function localCandidate() {
  // In a local `link:` install Node resolves this module to the repository
  // source. This makes the checkout's own venv a safe convenience fallback;
  // a configured command or PATH entry always wins.
  try {
    const moduleRoot = dirname(fileURLToPath(import.meta.url));
    const candidate = join(moduleRoot, '..', '..', '..', '..', '.venv', 'Scripts', 'agentref.exe');
    return existsSync(candidate) ? realpathSync(candidate) : undefined;
  } catch {
    return undefined;
  }
}

export function resolveCommand(config = {}) {
  if (typeof config.command === 'string' && config.command.trim() !== '') return config.command.trim();
  if (typeof process.env.AGENTREF_COMMAND === 'string' && process.env.AGENTREF_COMMAND.trim() !== '') return process.env.AGENTREF_COMMAND.trim();
  return localCandidate() ?? 'agentref';
}

function runAgentRefResult(command, args, maxBuffer) {
  return new Promise((resolve, reject) => {
    execFile(command, args, {
      windowsHide: true,
      timeout: 15_000,
      maxBuffer,
      encoding: 'utf8'
    }, (error, stdout, stderr) => {
      if (error) {
        if (error.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER') {
          reject(new Error(args[0] === 'sessions'
            ? 'AgentRef session metadata exceeds the 8 MiB limit; the list was not loaded. CLI-side pagination is required for larger inventories.'
            : 'AgentRef selected context exceeds the local safety limit'));
          return;
        }
        const detail = String(stderr ?? '').replace(/[\r\n]+/g, ' ').slice(0, MAX_STDERR_BYTES);
        reject(new Error(detail ? `AgentRef unavailable: ${detail}` : 'AgentRef command failed'));
        return;
      }
      // Do not forward raw diagnostics (which can contain local paths) to the UI.
      resolve({ stdout: String(stdout), incomplete: Boolean(String(stderr ?? '').trim()) });
    });
  });
}

export async function runAgentRef(command, args, maxBuffer = MAX_CONTEXT_BYTES) {
  return (await runAgentRefResult(command, args, maxBuffer)).stdout;
}

function sendJson(res, status, body) {
  const encoded = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(encoded)
  });
  res.end(encoded);
}

function trusted(connection, request) {
  const rejected = typeof connection?.requestRejection === 'function' ? connection.requestRejection(request) : undefined;
  if (rejected !== undefined) return { ok: false, status: rejected };
  if (!isLoopbackAddress(request.socket?.remoteAddress)) return { ok: false, status: 403 };
  const expectedOrigin = loopbackOrigin(request.headers.host, request.socket?.encrypted ? 'https:' : 'http:');
  if (!expectedOrigin) return { ok: false, status: 403 };
  const origin = request.headers.origin;
  if (origin !== undefined) {
    try {
      if (typeof origin !== 'string' || !/^https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?$/i.test(origin)
          || new URL(origin).origin !== expectedOrigin) return { ok: false, status: 403 };
    } catch {
      return { ok: false, status: 403 };
    }
  }
  return { ok: true };
}

async function readSessionRows(command, agent, query = '', limit = 50) {
  const read = async (args) => {
    const { stdout, incomplete } = await runAgentRefResult(command, args, MAX_METADATA_BYTES);
    let decoded;
    try {
      decoded = JSON.parse(stdout);
    } catch {
      throw new Error('AgentRef returned invalid JSON');
    }
    if (!Array.isArray(decoded)) throw new Error('AgentRef returned an invalid session list');
    return { rows: decoded, incomplete };
  };
  const args = ['sessions', '--agent', agent, '--json', '--limit', String(limit)];
  if (query) args.push('--query', query);
  try {
    return await read(args);
  } catch (error) {
    // Older installed CLIs do not know the bounded query flags. Preserve their
    // previous behavior for inventories that still fit the existing byte cap.
    if (!/unrecognized arguments|unrecognized option/i.test(String(error?.message ?? ''))) throw error;
    return read(['sessions', '--agent', agent, '--json']);
  }
}

export function createRoutes(config = {}) {
  const command = resolveCommand(config);
  const pendingLists = new Map();
  const listSessions = async (agent, query, exactRef) => {
    // Merge overlapping metadata searches by source, but revalidate selections
    // with a fresh read. Completed results and selected context are not retained.
    let pending;
    if (exactRef !== undefined) {
      pending = readSessionRows(command, agent, exactRef, 1);
    } else {
      const key = `${agent}\0${query}`;
      pending = pendingLists.get(key);
      if (!pending) {
        pending = readSessionRows(command, agent, query).finally(() => pendingLists.delete(key));
        pendingLists.set(key, pending);
      }
    }
    const { rows, incomplete } = await pending;
    return { sessions: sanitizeRows(exactRef === undefined ? rows : rows.filter(row => row?.ref === exactRef), agent, query), incomplete };
  };
  return [{
    kind: 'prefix',
    path: API_PREFIX,
    handler: async (request, response) => {
      const trust = trusted(config.connection, request);
      if (!trust.ok) {
        sendJson(response, trust.status, { ok: false, error: 'forbidden' });
        return;
      }
      if (request.method !== 'GET') {
        sendJson(response, 405, { ok: false, error: 'method-not-allowed' });
        return;
      }
      let url;
      try {
        url = new URL(request.url ?? '/', `http://${request.headers.host}`);
      } catch {
        sendJson(response, 400, { ok: false, error: 'invalid-url' });
        return;
      }
      try {
        if (url.pathname === `${API_PREFIX}/sessions`) {
          const agent = url.searchParams.get('agent') ?? '';
          const query = url.searchParams.get('query') ?? '';
          if (!validAgent(agent) || query.length > MAX_QUERY_LENGTH) throw new Error('invalid session search');
          sendJson(response, 200, { ok: true, ...await listSessions(agent, query) });
          return;
        }
        if (url.pathname === `${API_PREFIX}/context`) {
          const ref = url.searchParams.get('ref') ?? '';
          if (!validRef(ref)) throw new Error('invalid session reference');
          const agent = ref.split(':', 1)[0];
          const listed = await listSessions(agent, '', ref);
          if (!listed.sessions.some((row) => row.ref === ref)) throw new Error('selected session is no longer available');
          const text = await runAgentRef(command, ['context', ref, '--agent', agent]);
          if (Buffer.byteLength(text, 'utf8') > MAX_CONTEXT_BYTES) throw new Error('selected context exceeds the local safety limit');
          sendJson(response, 200, { ok: true, ref, context: text });
          return;
        }
        sendJson(response, 404, { ok: false, error: 'not-found' });
      } catch (error) {
        sendJson(response, 503, { ok: false, error: error instanceof Error ? error.message : 'AgentRef unavailable' });
      }
    }
  }];
}

export function apply(ctx, config = {}) {
  ctx.inject(['webServer'], (webCtx) => {
    if (!webCtx.webServer) return () => {};
    const routes = createRoutes({ ...config, connection: webCtx.connection ?? ctx.connection });
    const disposers = routes.map((route) => webCtx.webServer.register(route));
    return () => disposers.reverse().forEach((dispose) => dispose());
  });
}
