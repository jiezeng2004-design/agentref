import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

test('pending selections cannot overwrite edits, cancellation, submission or newer choices', async () => {
  class Element {
    constructor() { this.children = []; this.handlers = {}; this.parts = {}; this.style = {}; this.isConnected = true; }
    appendChild(child) { this.children.push(child); }
    setAttribute() {}
    querySelector(key) { return this.parts[key] ??= new Element(); }
    addEventListener(key, handler) { this.handlers[key] = handler; }
    remove() { this.isConnected = false; }
  }
  class Textarea extends Element {
    get value() { return this.text ?? ''; }
    set value(value) { this.text = value; }
    dispatchEvent() {}
    setSelectionRange() {}
    focus() {}
    getBoundingClientRect() { return { left: 20, bottom: 20 }; }
  }
  const source = await readFile(new URL('../src/client/index.js', import.meta.url), 'utf8');
  for (const action of ['edit', 'cancel', 'outside', 'submit', 'detach', 'newer', 'unchanged']) {
    const requests = [];
    const runtime = vm.createContext({ module: { exports: {} }, HTMLTextAreaElement: Textarea,
      Event: class {}, window: { innerHeight: 900 },
      document: { createElement: () => new Element(), body: new Element() },
      fetch: () => new Promise(resolve => requests.push(resolve)) });
    vm.runInContext(source + '\nmodule.exports.testing = { STATE, renderMenu, activeMention, removeMenu, flushSelection };', runtime);
    const { STATE, renderMenu, activeMention, removeMenu, flushSelection } = runtime.module.exports.testing;
    const input = new Textarea(); input.value = '@dsh';
    const state = { request: 0, mention: activeMention(input.value, 4) }; STATE.set(input, state);
    renderMenu(input, state.mention, [
      { ref: 'dsh:11111111', agent: 'dsh', title: 'old' },
      { ref: 'dsh:22222222', agent: 'dsh', title: 'new' }
    ]);
    const menu = state.menu;
    const old = menu.children[1].handlers.click();
    let newer;
    if (action === 'edit') input.value = 'USER_CHANGED_INPUT';
    if (action === 'cancel') removeMenu(state);
    if (action === 'outside') menu.remove();
    if (action === 'submit') flushSelection(input);
    if (action === 'detach') input.isConnected = false;
    if (action === 'newer') newer = menu.children[2].handlers.click();
    const respond = (n, context) => requests[n]({ ok: true, json: async () => ({ ok: true, context }) });
    if (newer) { respond(1, 'NEW_CONTEXT'); await newer; }
    respond(0, 'OLD_CONTEXT'); await old;
    flushSelection(input);
    if (action === 'unchanged') assert.ok(input.value.includes('OLD_CONTEXT'));
    else {
      assert.ok(!input.value.includes('OLD_CONTEXT'), action);
      if (action === 'newer') assert.ok(input.value.includes('NEW_CONTEXT'));
      else assert.equal(input.value, action === 'edit' ? 'USER_CHANGED_INPUT' : '@dsh', action);
    }
  }
});

test('DSH mention can be filtered and selected without changing another source', async () => {
  const runtime = vm.createContext({ module: { exports: {} } });
  const source = await readFile(new URL('../src/client/index.js', import.meta.url), 'utf8');
  vm.runInContext(source + '\nmodule.exports.testing = { activeMention, selectionMarker };', runtime);
  const { activeMention, selectionMarker } = runtime.module.exports.testing;
  const text = 'continue @dsh:登录';
  const mention = activeMention(text, text.length);
  assert.equal(mention.agent, 'dsh');
  assert.equal(mention.query, '登录');
  assert.equal(text.slice(mention.start, mention.end), '@dsh:登录');
  assert.equal(activeMention('@unknown', 8), null);
  assert.ok(selectionMarker({agent: 'dsh', title: '历史任务'}).includes('DSH · 历史任务'));
});

test('deleting a marker does not block a later selection or append stale context', async () => {
  class Textarea {
    get value() { return this.text ?? ''; }
    set value(value) { this.text = value; }
    dispatchEvent() {}
  }
  const runtime = vm.createContext({ module: { exports: {} }, HTMLTextAreaElement: Textarea, Event: class {} });
  const source = await readFile(new URL('../src/client/index.js', import.meta.url), 'utf8');
  vm.runInContext(source + '\nmodule.exports.testing = { STATE, flushSelection, selectionMarker };', runtime);
  const { STATE, flushSelection, selectionMarker } = runtime.module.exports.testing;
  const input = new Textarea();
  const state = { selection: { agent: 'claude', title: 'old', context: 'STALE_CONTEXT' }, flushing: false };
  STATE.set(input, state);
  input.value = 'marker was deleted';
  flushSelection(input);
  assert.equal(input.value, 'marker was deleted');
  assert.equal(state.flushing, false);
  assert.equal(state.selection, undefined);
  state.selection = { agent: 'codex', title: 'new', context: 'NEW_CONTEXT' };
  input.value = selectionMarker(state.selection);
  flushSelection(input);
  const sent = input.value;
  assert.ok(sent.includes('NEW_CONTEXT'));
  assert.ok(!sent.includes('STALE_CONTEXT'));
  flushSelection(input);
  assert.equal(input.value, sent);
  assert.equal(state.flushing, false);
});
