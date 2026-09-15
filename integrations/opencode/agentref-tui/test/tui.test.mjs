import test from 'node:test';
import assert from 'node:assert/strict';
import { install, mentionAtEnd, localClient } from '../tui.mjs';

const tick = () => new Promise(setImmediate);
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; };
const rows = ['a', 'b'].map((x,i) => ({ agent: 'codex', ref: `codex:${x.repeat(8)}`, title: `测试 ${i + 1}`, cwd: 'D:/fixture', updatedAt: '2026-09-12' }));
function harness() {
  let slots, layer, dispose, view, onClose;
  const searches = [], reads = [], notices = [];
  const prompt = { focused: true, current: { input: '@codex', parts: [] }, set(value) { this.current = value; }, focus() { this.focused = true; } };
  const dialog = { open: false, replace(render, close) { this.open = true; onClose = close; view = render(); }, clear() { this.open = false; onClose?.(); } };
  const api = {
    renderer: {}, slots: { register(value) { slots = value.slots; } },
    lifecycle: { onDispose(fn) { dispose = fn; } },
    keymap: { registerLayer(value) { layer = value; return () => {}; }, dispatchCommand(name) { assert.equal(name, 'dialog.select.submit'); view.onSelect(view.options[0]); } },
    ui: { dialog, toast(value) { notices.push(value); }, DialogSelect(props) { return props; }, Prompt(props) { props.ref(prompt); return props; } },
  };
  install(api, {
    sessions(agent, signal) { const d = deferred(); searches.push({ ...d, agent, signal }); return d.promise; },
    context(row, signal) { const d = deferred(); reads.push({ ...d, row, signal }); return d.promise; },
  }, segment => /[\u3000-\u9fff]|\p{Extended_Pictographic}/u.test(segment) ? 2 : segment.length);
  const props = slots.home_prompt({});
  return { prompt, api, props, searches, reads, notices, dispose: () => dispose(),
    press: key => layer.bindings.find(x => x.key === key)?.cmd(),
    get view() { return view; },
    async list() { this.press('tab'); searches.at(-1).resolve({ rows, incomplete: false }); await tick(); },
  };
}

test('Tab lists metadata, Enter/Tab selects one exact ref and only inserts a draft attachment', async () => {
  const h = harness();
  await h.list();
  assert.equal(h.reads.length, 0);
  assert.equal(h.view.options.length, 2);
  h.view.onSelect(h.view.options[1]);
  h.view.onSelect(h.view.options[0]);
  assert.equal(h.reads.length, 1);
  assert.equal(h.reads[0].row.ref, rows[1].ref);
  h.reads[0].resolve('SYNTHETIC_CONTEXT'); await tick();
  assert.ok(h.prompt.current.input.includes('测试 2'));
  assert.ok(!h.prompt.current.input.includes('SYNTHETIC_CONTEXT'));
  assert.equal(h.prompt.current.parts[0].text, 'SYNTHETIC_CONTEXT');
  assert.equal(h.api.ui.dialog.open, false);
});

test('cancel, edited draft, unmounted prompt and disposal discard pending results', async () => {
  for (const phase of ['search', 'context']) {
    for (const action of ['cancel', 'edit', 'unmount', 'dispose']) {
      const h = harness();
      if (phase === 'context') { await h.list(); h.view.onSelect(h.view.options[0]); }
      else h.press('tab');
      if (action === 'cancel') phase === 'search' ? h.press('escape') : h.api.ui.dialog.clear();
      if (action === 'edit') h.prompt.current = { input: 'USER_EDIT', parts: [] };
      if (action === 'unmount') h.props.ref(undefined);
      if (action === 'dispose') h.dispose();
      if (phase === 'context') h.reads[0].resolve('MUST_NOT_INSERT');
      else h.searches[0].resolve({ rows, incomplete: false });
      await tick();
      assert.equal(h.prompt.current.parts.length, 0, `${phase}/${action}`);
      assert.equal(h.prompt.current.input, action === 'edit' ? 'USER_EDIT' : '@codex');
      if (phase === 'search') assert.equal(h.api.ui.dialog.open, false);
    }
  }
});

test('ordinary Tab passes through, repeated Tab does not duplicate scans, empty results never auto-read', async () => {
  const h = harness();
  for (const input of ['ordinary', '@unknown', '@codex-no', 'email@codex']) {
    h.prompt.current.input = input; assert.equal(h.press('tab'), false);
  }
  h.prompt.current.input = '@codex';
  h.api.renderer.currentFocusedEditor = { traits: { status: 'SHELL' } }; assert.equal(h.press('tab'), false);
  h.api.renderer.currentFocusedEditor = { cursorOffset: 0 }; assert.equal(h.press('tab'), false);
  h.api.renderer.currentFocusedEditor.cursorOffset = 6;
  h.press('tab'); h.press('tab'); assert.equal(h.searches.length, 1);
  h.searches[0].resolve({ rows: [], incomplete: true }); await tick();
  assert.equal(h.reads.length, 0); assert.equal(h.api.ui.dialog.open, false);
  assert.ok(h.notices.at(-1).message.includes('索引不完整'));
});

test('failed context can be retried, pre-existing draft parts survive selection', async () => {
  const h = harness(); const attachment = { type: 'file', filename: 'synthetic.txt', url: 'data:text/plain,hello', mime: 'text/plain' };
  h.prompt.current = { input: '继续 @codex', parts: [attachment] };
  await h.list(); h.view.onSelect(h.view.options[0]);
  h.reads[0].reject(new Error('retry')); await tick();
  h.view.onSelect(h.view.options[1]); assert.equal(h.reads.length, 2);
  h.reads[1].resolve('CONTEXT'); await tick();
  assert.deepEqual(h.prompt.current.parts[0], attachment);
  assert.equal(h.prompt.current.parts[1].source.text.start, 5);
});

test('all six source mentions and literal metadata filters are recognized', () => {
  for (const agent of ['claude','codex','grok','opencode','antigravity','dsh']) {
    assert.deepEqual(mentionAtEnd(`继续 @${agent}:登录`), { agent, query: '登录', start: 3, end: agent.length + 7 });
  }
  assert.throws(() => localClient({ args: 'unsafe' }));
});

test('second Tab dispatches the native select command only inside our dialog', async () => {
  const h = harness(); await h.list();
  h.press('tab'); assert.equal(h.reads.length, 1);
  h.press('tab'); assert.equal(h.reads.length, 1);
  h.api.ui.dialog.clear();
  h.api.ui.dialog.open = true;
  assert.equal(h.press('tab'), false);
  h.reads[0].resolve('CANCELLED'); await tick();
  assert.equal(h.prompt.current.parts.length, 0);
});

test('Chinese, emoji and newline prefixes use terminal cells for cursor and attachment ranges', async () => {
  const h = harness();
  h.prompt.current.input = '🙂\n继续 @codex';
  h.api.renderer.currentFocusedEditor = { cursorOffset: 14 };
  await h.list(); assert.equal(h.view.options.length, 2);
  h.view.onSelect(h.view.options[0]); h.reads[0].resolve('UNICODE_CONTEXT'); await tick();
  assert.ok(h.prompt.current.input.startsWith('🙂\n继续 【AgentRef'));
  const part = h.prompt.current.parts[0];
  assert.equal(part.source.text.start, 8);
  assert.equal(part.source.text.end - part.source.text.start, 27);
});
