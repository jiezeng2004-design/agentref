import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

async function searchHarness() {
  class Element {
    constructor() { this.children = []; this.handlers = {}; this.parts = {}; this.style = {}; this.isConnected = true; }
    appendChild(child) { this.children.push(child); }
    setAttribute() {}
    querySelector(key) { return this.parts[key] ??= new Element(); }
    addEventListener(key, handler) { this.handlers[key] = handler; }
    click() { if (!this.disabled) return this.handlers.click?.(); }
    remove() { this.isConnected = false; }
    closest() { return null; }
  }
  class Textarea extends Element {
    get value() { return this.text ?? ''; }
    set value(value) { this.text = value; }
    dispatchEvent(event) { this.handlers[event.type]?.(event); }
    setSelectionRange(start) { this.selectionStart = start; }
    focus() {}
    getBoundingClientRect() { return { left: 20, bottom: 20 }; }
  }
  const input = new Textarea();
  input.value = '@dsh'; input.selectionStart = 4;
  const timers = new Map(), requests = [], handlers = {};
  const runtime = vm.createContext({ module: { exports: {} }, HTMLTextAreaElement: Textarea, Element,
    Event: class { constructor(type) { this.type = type; } }, AbortController,
    window: { innerHeight: 900 }, MutationObserver: class { observe() {} disconnect() {} },
    setTimeout: (callback) => { const key = {}; timers.set(key, callback); return key; },
    clearTimeout: (key) => timers.delete(key),
    document: { createElement: () => new Element(), body: new Element(), documentElement: new Element(),
      getElementById: () => ({}), querySelectorAll: () => [input],
      addEventListener: (key, callback) => { handlers[key] = callback; },
      removeEventListener: (key) => { delete handlers[key]; } },
    fetch: (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })) });
  const source = await readFile(new URL('../src/client/index.js', import.meta.url), 'utf8');
  vm.runInContext(source + '\nmodule.exports.testing = { STATE, activeMention, replaceMention };', runtime);
  const dispose = runtime.module.exports.apply();
  return { input, requests, timers, handlers, dispose, ...runtime.module.exports.testing,
    runTimers() { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(callback => callback()); } };
}

test('mention replacement preserves every leading whitespace character and trailing text', async () => {
  const { input, activeMention, replaceMention } = await searchHarness();
  for (const prefix of ['', 'task ', 'task\n', 'task\r\n', 'task\t', 'task\u3000']) {
    input.value = `${prefix}@dsh:query trailing`;
    const mention = activeMention(input.value, prefix.length + '@dsh:query'.length);
    replaceMention(input, mention, '[selected]');
    assert.equal(input.value, `${prefix}[selected] trailing`);
  }
});

function press(h, key, extra = {}) {
  let stopped = false;
  h.input.handlers.keydown({ key, preventDefault() { stopped = true; }, stopImmediatePropagation() {}, ...extra });
  return stopped;
}

const choices = [
  { agent: 'dsh', ref: 'dsh:11111111', title: 'First synthetic session' },
  { agent: 'dsh', ref: 'dsh:22222222', title: 'Second synthetic session' },
];

test('Tab opens immediately, arrows browse metadata, second Tab selects only the highlighted ref', async () => {
  const h = await searchHarness();
  h.input.handlers.input();
  assert.equal(press(h, 'Tab'), true);
  assert.equal(h.requests.length, 1);
  assert.equal(h.timers.size, 0);
  h.requests[0].resolve({ ok: true, json: async () => ({ ok: true, sessions: choices }) });
  await new Promise(setImmediate);
  assert.equal(h.STATE.get(h.input).activeIndex, 0);
  assert.equal(h.requests.length, 1, 'opening must not read context');
  assert.equal(press(h, 'ArrowDown'), true);
  assert.equal(h.STATE.get(h.input).activeIndex, 1);
  assert.equal(press(h, 'Tab'), true);
  assert.equal(h.requests.length, 2);
  assert.ok(h.requests[1].url.includes('dsh%3A22222222'));
  press(h, 'Enter');
  assert.equal(h.requests.length, 2, 'pending selection is not read twice or sent');
  h.requests[1].resolve({ ok: true, json: async () => ({ ok: true, context: 'SYNTHETIC_SELECTED_CONTEXT' }) });
  await new Promise(setImmediate);
  assert.ok(h.input.value.includes('Second synthetic session'));
  assert.ok(!h.input.value.includes('SYNTHETIC_SELECTED_CONTEXT'), 'context stays out of composer until submission');
});

test('first Tab on an automatically shown list activates navigation without selecting a lone candidate', async () => {
  const h = await searchHarness();
  h.input.handlers.input(); h.runTimers();
  h.requests[0].resolve({ ok: true, json: async () => ({ ok: true, sessions: choices.slice(0, 1) }) });
  await new Promise(setImmediate);
  press(h, 'Tab');
  assert.equal(h.requests.length, 1);
  press(h, 'Escape');
  assert.equal(h.STATE.get(h.input).menu, undefined);
  assert.equal(h.input.value, '@dsh');
});

test('Tab during an in-flight search does not restart it and stale response cannot reopen after Escape', async () => {
  const h = await searchHarness();
  h.input.handlers.input(); h.runTimers();
  press(h, 'Tab'); press(h, 'Tab');
  assert.equal(h.requests.length, 1);
  press(h, 'Escape');
  h.requests[0].resolve({ ok: true, json: async () => ({ ok: true, sessions: choices }) });
  await new Promise(setImmediate);
  assert.equal(h.STATE.get(h.input).menu, undefined);
  h.input.value = 'ordinary text'; h.input.selectionStart = h.input.value.length;
  assert.equal(press(h, 'Tab'), false);
  h.input.value = '@dsh'; h.input.selectionStart = 4;
  assert.equal(press(h, 'Tab', { shiftKey: true }), false);
  assert.equal(press(h, 'Tab', { isComposing: true }), false);
});

test('closing a pending search prevents delayed success or error from reopening the menu', async () => {
  for (const action of ['escape', 'submit', 'outside', 'dispose', 'detach']) {
    for (const reject of [false, true]) {
      const h = await searchHarness();
      h.input.handlers.input(); h.runTimers();
      assert.equal(h.requests.length, 1);
      if (action === 'escape') h.input.handlers.keydown({ key: 'Escape' });
      if (action === 'submit') h.input.handlers.keydown({ key: 'Enter' });
      if (action === 'outside') h.handlers.pointerdown({ target: null });
      if (action === 'dispose') h.dispose();
      if (action === 'detach') h.input.isConnected = false;
      if (action !== 'detach') assert.equal(h.requests[0].options.signal.aborted, true);
      if (reject) h.requests[0].reject(new Error('late failure'));
      else h.requests[0].resolve({ ok: true, json: async () => ({ ok: true, sessions: [] }) });
      await new Promise(setImmediate);
      assert.equal(h.STATE.get(h.input).menu, undefined, `${action}: ${reject}`);
    }
  }
});

test('typing is debounced and old results cannot replace the newest search', async () => {
  const h = await searchHarness();
  for (const value of ['@dsh', '@dsh:a', '@dsh:ab']) {
    h.input.value = value; h.input.selectionStart = value.length; h.input.handlers.input();
  }
  assert.equal(h.requests.length, 0);
  h.runTimers();
  assert.equal(h.requests.length, 1);
  assert.ok(h.requests[0].url.endsWith('query=ab'));
  h.input.value = '@dsh:abc'; h.input.selectionStart = h.input.value.length; h.input.handlers.input();
  assert.equal(h.requests[0].options.signal.aborted, true);
  h.runTimers();
  h.requests[1].resolve({ ok: true, json: async () => ({ ok: true, sessions: [] }) });
  await new Promise(setImmediate);
  const newest = h.STATE.get(h.input).menu;
  assert.ok(newest?.isConnected);
  h.requests[0].resolve({ ok: true, json: async () => ({ ok: true, sessions: [] }) });
  await new Promise(setImmediate);
  assert.equal(h.STATE.get(h.input).menu, newest);
  h.input.handlers.input();
  h.input.handlers.keydown({ key: 'Escape' });
  h.runTimers();
  assert.equal(h.requests.length, 2);
});

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
