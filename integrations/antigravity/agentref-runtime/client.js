/* Runtime-only AGY 2.14 Lexical composer adapter. No fetch, storage, or model call. */
(function installAgentRef(config) {
  'use strict';
  if (location.origin !== config.origin || typeof window.electronNative !== 'object') return false;
  if (window.__agentrefAgyRuntime) return false;
  const selector = '[contenteditable="true"][data-lexical-editor="true"][aria-label="Message input"]';
  let disposed = false, heartbeat = Date.now(), serial = 0, token, timer, active = 0;
  const pending = new Map();
  const host = document.createElement('div'); host.id = 'agentref-agy-runtime';
  const shadow = host.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = ':host{all:initial} .panel{position:fixed;z-index:2147483647;box-sizing:border-box;background:#fff;color:#17212e;border:1px solid #b7c7dd;border-radius:12px;box-shadow:0 8px 32px #0003;font:13px/1.5 system-ui;overflow:auto;max-height:310px;padding:8px}.head{font-weight:650;padding:5px 8px}.status{padding:5px 8px;color:#775000;white-space:pre-wrap}button{font:inherit;display:block;background:transparent;color:inherit;text-align:left;border:0;border-radius:6px;padding:7px 9px;width:100%;cursor:pointer}button[aria-selected=true]{background:#dfeeff}small{display:block;color:#637081;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.foot{padding:6px 8px;color:#637081;font-size:11px}';
  const panel = document.createElement('div'); panel.className = 'panel'; panel.hidden = true; panel.setAttribute('role', 'listbox');
  shadow.append(style, panel); document.documentElement.append(host);
  let hiddenMenu, previousVisibility, previousPointer;
  function restoreNative() {
    if (hiddenMenu) { hiddenMenu.style.visibility = previousVisibility; hiddenMenu.style.pointerEvents = previousPointer; }
    hiddenMenu = undefined;
  }
  function suppressNative(editor) {
    const menu = document.getElementById(editor.getAttribute('aria-controls'));
    if (!menu || menu === hiddenMenu) return;
    restoreNative(); hiddenMenu = menu; previousVisibility = menu.style.visibility; previousPointer = menu.style.pointerEvents;
    menu.style.visibility = 'hidden'; menu.style.pointerEvents = 'none';
  }
  function rpc(method, args = {}) {
    if (disposed || Date.now() - heartbeat > 8000) return Promise.reject(new Error('桥接已断开'));
    return new Promise((resolve, reject) => {
      const id = ++serial;
      const timeout = setTimeout(() => { pending.delete(id); reject(new Error('请求超时，请重试')); }, 65000);
      pending.set(id, { resolve, reject, timeout });
      try { window[config.binding](JSON.stringify({ id, method, ...args })); }
      catch { clearTimeout(timeout); pending.delete(id); reject(new Error('桥接已断开')); }
    });
  }
  function close() {
    clearTimeout(timer); token = undefined; panel.hidden = true; restoreNative();
    if (!disposed) void rpc('cancel').catch(() => {});
  }
  function mention(editor) {
    const selection = getSelection();
    if (!editor?.matches(selector) || !selection?.isCollapsed || !selection.rangeCount) return;
    const caret = selection.getRangeAt(0);
    if (!editor.contains(caret.endContainer)) return;
    const prefix = caret.cloneRange(); prefix.selectNodeContents(editor); prefix.setEnd(caret.endContainer, caret.endOffset);
    const match = /(?:^|\s)@(claude|codex|grok|opencode|antigravity|dsh)(?::([^\s@]{0,120}))?$/i.exec(prefix.toString());
    if (!match) return;
    const length = match[0].length - (match[0].startsWith('@') ? 0 : 1);
    const range = caret.cloneRange();
    const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    let end = prefix.toString().length, start = end - length, offset = 0;
    for (const node of nodes) {
      if (start >= offset && start < offset + node.length) { range.setStart(node, start - offset); break; }
      offset += node.length;
    }
    if (range.toString() !== '@' + match[1] + (match[2] === undefined ? '' : ':' + match[2])) return;
    return { editor, agent: match[1].toLowerCase(), query: match[2] || '', range,
      html: editor.innerHTML, anchor: caret.endContainer, offset: caret.endOffset };
  }
  function unchanged(own) {
    if (disposed || token !== own || !own.editor.isConnected || own.editor.innerHTML !== own.html) return false;
    const selection = getSelection();
    return selection?.isCollapsed && selection.anchorNode === own.anchor && selection.anchorOffset === own.offset;
  }
  function position(own) {
    const rect = own.editor.getBoundingClientRect();
    panel.style.width = Math.max(240, Math.min(rect.width, innerWidth - 24)) + 'px';
    panel.style.left = Math.max(12, Math.min(rect.left, innerWidth - parseFloat(panel.style.width) - 12)) + 'px';
    panel.style.top = Math.max(8, rect.top - Math.min(310, panel.scrollHeight) - 8) + 'px';
    suppressNative(own.editor);
  }
  function node(tag, text, cls) { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; return e; }
  function render(own, message) {
    panel.replaceChildren(node('div', `${config.fixture ? '合成测试 · ' : ''}AgentRef · @${own.agent} 会话`, 'head'));
    if (message) panel.append(node('div', message, 'status'));
    if (own.result) {
      if (own.result.incomplete) panel.append(node('div', '索引可能不完整，列表不是全部会话。', 'status'));
      if (own.result.hasMore) panel.append(node('div', '当前展示前 50 条；可继续输入 @来源:关键词 筛选更早会话。', 'status'));
      own.result.items.forEach((item, index) => {
        const button = node('button', item.title); button.type = 'button'; button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', String(index === active)); button.append(node('small', item.detail));
        button.addEventListener('mousedown', event => event.preventDefault());
        button.addEventListener('click', event => { if (event.isTrusted) void choose(own, index); });
        panel.append(button);
      });
      if (!own.result.items.length) panel.append(node('div', '没有匹配会话。可使用 @agent:关键词。', 'status'));
    }
    panel.append(node('div', '↑↓ 浏览 · Enter / Tab 附加 · Esc 取消 · 不自动发送', 'foot'));
    panel.hidden = false; position(own);
  }
  async function open(editor) {
    const own = mention(editor); if (!own) { close(); return; }
    close(); token = own; own.busy = true; active = 0; render(own, '正在列出本地会话…');
    try {
      const result = await rpc('sessions', { agent: own.agent, query: own.query });
      if (!unchanged(own)) return;
      own.result = result; own.busy = false; render(own);
    } catch { if (unchanged(own)) { own.busy = false; render(own, '会话列表读取失败；请检查 AgentRef，重新按 Tab。'); } }
  }
  async function choose(own, index) {
    if (!unchanged(own) || own.busy || !own.result?.items[index]) return;
    own.busy = true; render(own, '正在读取明确选中的会话…');
    try {
      const result = await rpc('context', { ticket: own.result.items[index].ticket });
      if (!unchanged(own)) return;
      const insertion = `【AgentRef 只读历史引用 · ${result.agent} · ${result.ref}】\n${result.context}\n【AgentRef 引用结束】\n`;
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(own.range);
      // Native editing participates in Lexical's input/undo handling. Never
      // assign innerHTML/textContent or replace the whole editor/draft.
      token = undefined;
      const inserted = document.execCommand('insertText', false, insertion);
      panel.hidden = true; restoreNative();
      if (!inserted) {
        token = mention(own.editor);
        if (token) render(token, 'AGY 拒绝插入；草稿未主动覆盖。请取消并检查版本兼容性。');
      }
    } catch { if (unchanged(own)) { own.busy = false; own.result = undefined; render(own, '引用读取失败或已过期；重新按 Tab 列出会话。'); } }
  }
  function input(event) {
    if (!event.isTrusted || !event.target.matches?.(selector)) return;
    close(); const editor = event.target;
    if (mention(editor)) timer = setTimeout(() => void open(editor), 180);
  }
  function keydown(event) {
    if (!event.isTrusted || event.isComposing || !event.target.matches?.(selector)) return;
    if (token && !unchanged(token)) close();
    if (token && ['Escape', 'ArrowDown', 'ArrowUp', 'Enter', 'Tab'].includes(event.key)) {
      event.preventDefault(); event.stopImmediatePropagation();
      if (event.key === 'Escape') close();
      else if (!token.busy && ['ArrowDown', 'ArrowUp'].includes(event.key) && token.result?.items.length) {
        active = (active + (event.key === 'ArrowDown' ? 1 : -1) + token.result.items.length) % token.result.items.length;
        render(token); panel.querySelector('[aria-selected=true]')?.scrollIntoView({ block: 'nearest' });
      } else if (!token.busy && ['Enter', 'Tab'].includes(event.key)) {
        if (token.result?.items.length) void choose(token, active); else void open(event.target);
      }
      return;
    }
    if (event.key === 'Tab' && mention(event.target)) {
      event.preventDefault(); event.stopImmediatePropagation(); clearTimeout(timer); void open(event.target);
    }
  }
  function pointer(event) { if (!event.composedPath().includes(host)) close(); }
  function selectionChanged() { if (token && !unchanged(token)) close(); }
  document.addEventListener('input', input, true);
  document.addEventListener('keydown', keydown, true);
  document.addEventListener('pointerdown', pointer, true);
  document.addEventListener('selectionchange', selectionChanged);
  const watcher = setInterval(() => {
    if (Date.now() - heartbeat > 8000) api.dispose();
    else if (token && !unchanged(token)) close();
    else if (token) position(token);
  }, 500);
  const api = {
    id: config.id,
    status() { return { installed: !disposed, healthy: !disposed && Date.now() - heartbeat <= 8000, fixture: config.fixture, menuOpen: !panel.hidden }; },
    ping() { heartbeat = Date.now(); return api.status(); },
    deliver(response) {
      const job = pending.get(response.id); if (!job) return;
      clearTimeout(job.timeout); pending.delete(response.id);
      if (response.ok) job.resolve(response.value); else job.reject(new Error('AgentRef request failed'));
    },
    dispose() {
      if (disposed) return; close(); disposed = true; clearInterval(watcher);
      document.removeEventListener('input', input, true); document.removeEventListener('keydown', keydown, true);
      document.removeEventListener('pointerdown', pointer, true); document.removeEventListener('selectionchange', selectionChanged);
      for (const job of pending.values()) { clearTimeout(job.timeout); job.reject(new Error('Disposed')); }
      pending.clear(); host.remove();
      if (window.__agentrefAgyRuntime === api) delete window.__agentrefAgyRuntime;
    },
  };
  window.__agentrefAgyRuntime = api;
  return true;
})
