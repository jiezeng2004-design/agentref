// Opt-in runtime adapter: no installation patch, token read, HTTP server, or model.
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { discover, connect } from './cdp.mjs';
import { createBroker, fixtureClient } from './broker.mjs';
import { localClient } from '../../opencode/agentref-tui/tui.mjs';

const probe = `({native:typeof window.electronNative==='object',origin:location.origin,
  editors:[...document.querySelectorAll('[contenteditable="true"][data-lexical-editor="true"][aria-label="Message input"]')].filter(e=>e.getBoundingClientRect().height>0).length,
  runtime:window.__agentrefAgyRuntime?.status()||null})`;

export async function run(options) {
  const target = await discover(options['port-file']);
  const cdp = await connect(target.socket);
  let closed = false, timer, contextId, installedContext, stopResolve, checking = false;
  const id = randomUUID(); const binding = '__agentrefAgy_' + id.replaceAll('-', '');
  const client = options.fixture ? fixtureClient() : localClient({ args: [
    '--data-dir', fileURLToPath(new URL('../../../.agentref/agy-runtime', import.meta.url)),
  ] });
  const broker = createBroker(client);
  async function cleanup() {
    if (closed) return; closed = true; clearInterval(timer); broker.cancel();
    try { await cdp.evaluate(`if(window.__agentrefAgyRuntime?.id===${JSON.stringify(id)})window.__agentrefAgyRuntime.dispose()`); } catch {}
    try { await cdp.call('Runtime.removeBinding', { name: binding }); } catch {}
    cdp.close(); stopResolve?.();
  }
  try {
    const state = await cdp.evaluate(probe);
    if (!state?.native || state.origin !== target.origin) throw new Error('This is not the expected AGY renderer');
    if (options.stop) {
      await cdp.evaluate('window.__agentrefAgyRuntime?.dispose()');
      console.log(JSON.stringify({ stopped: true, draftChanged: false })); return;
    }
    if (options.status || !options.apply) {
      console.log(JSON.stringify({ mode: options.status ? 'status' : 'preview', compatibleComposerVisible: state.editors === 1,
        runtime: state.runtime, changesApplied: false, usage: 'node runtime.mjs --apply | --status | --stop' })); return;
    }
    if (state.runtime?.healthy) throw new Error('AgentRef is already attached; use --stop before replacing it');
    if (state.editors !== 1) throw new Error('Open one AGY conversation composer first; no draft was changed');
    if (state.runtime) await cdp.evaluate('window.__agentrefAgyRuntime?.dispose()');
    const tree = await cdp.call('Page.getFrameTree'); const mainFrame = tree.frameTree.frame.id;
    const source = await readFile(new URL('./client.js', import.meta.url), 'utf8');
    const script = `${source}(${JSON.stringify({ id, binding, origin: target.origin, fixture: Boolean(options.fixture) })});`;
    cdp.onEvent(message => {
      if (message.method === 'disconnected') { void cleanup(); return; }
      if (message.method === 'Runtime.executionContextsCleared') { contextId = undefined; broker.cancel(); return; }
      if (message.method === 'Runtime.executionContextCreated') {
        const context = message.params.context;
        if (context.auxData?.isDefault && context.auxData?.frameId === mainFrame && context.origin === target.origin) contextId = context.id;
        return;
      }
      if (message.method !== 'Runtime.bindingCalled' || message.params.name !== binding || message.params.executionContextId !== contextId) return;
      const owner = contextId;
      void (async () => {
        let request;
        try {
          if (message.params.payload.length > 4096) return;
          request = JSON.parse(message.params.payload);
          if (!Number.isSafeInteger(request.id) || request.id < 1) return;
          const value = await broker.call(request);
          if (closed || owner !== contextId) return;
          await cdp.evaluate(`window.__agentrefAgyRuntime?.id===${JSON.stringify(id)}&&window.__agentrefAgyRuntime.deliver(${JSON.stringify({ id: request.id, ok: true, value })})`, owner);
        } catch {
          if (!closed && owner === contextId && request?.id) {
            try { await cdp.evaluate(`window.__agentrefAgyRuntime?.id===${JSON.stringify(id)}&&window.__agentrefAgyRuntime.deliver(${JSON.stringify({ id: request.id, ok: false })})`, owner); } catch {}
          }
        }
      })();
    });
    await cdp.call('Runtime.enable');
    await cdp.call('Runtime.addBinding', { name: binding });
    if (contextId === undefined) throw new Error('AGY main context was not identified');
    if (!await cdp.evaluate(script, contextId)) throw new Error('AGY adapter could not attach');
    installedContext = contextId;
    console.log(JSON.stringify({ attached: true, mode: options.fixture ? 'synthetic' : 'local-sessions', pid: process.pid,
      interaction: '@agent then Tab; explicit selection inserts text; never auto-send', installationPatched: false }));
    timer = setInterval(async () => {
      if (closed || checking || contextId === undefined) return;
      checking = true;
      try {
        if (contextId !== installedContext) {
          const current = await cdp.evaluate(probe, contextId);
          if (!current?.native || current.origin !== target.origin) { await cleanup(); return; }
          if (!await cdp.evaluate(script, contextId)) { await cleanup(); return; }
          installedContext = contextId;
        }
        const healthy = await cdp.evaluate(`window.__agentrefAgyRuntime?.id===${JSON.stringify(id)}&&window.__agentrefAgyRuntime.ping()`, contextId);
        if (!healthy?.installed) await cleanup();
      } catch { await cleanup(); }
      finally { checking = false; }
    }, 1500);
    const onSignal = () => void cleanup();
    process.once('SIGINT', onSignal); process.once('SIGTERM', onSignal);
    await new Promise(resolve => { stopResolve = resolve; if (closed) resolve(); });
    process.removeListener('SIGINT', onSignal); process.removeListener('SIGTERM', onSignal);
  } finally { await cleanup(); cdp.close(); }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  try {
    const { values } = parseArgs({ options: { apply: { type: 'boolean' }, status: { type: 'boolean' }, stop: { type: 'boolean' },
      fixture: { type: 'boolean' }, 'port-file': { type: 'string' } }, allowPositionals: false });
    if ([values.apply, values.status, values.stop].filter(Boolean).length > 1 || values.fixture && !values.apply) throw new Error('Choose one mode; --fixture requires --apply');
    await run(values);
  } catch (error) { console.error('AgentRef AGY: ' + error.message); process.exitCode = 1; }
}
