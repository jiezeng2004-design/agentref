import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const SOURCES = ['claude', 'codex', 'grok', 'opencode', 'antigravity', 'dsh'];
const clean = value => String(value ?? '').replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g, ' ').slice(0, 240);
const graphemes = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
function promptWidth(value, measure) {
  // OpenTUI offsets use display cells, including one position per newline.
  // Match OpenCode's prompt/display.ts rather than JavaScript UTF-16 length.
  let size = 0;
  for (const { segment } of graphemes.segment(value)) size += segment === '\n' ? 1 : measure(segment);
  return size;
}

export function mentionAtEnd(input) {
  const match = /(?:^|\s)@(claude|codex|grok|opencode|antigravity|dsh)(?::([^\s@]*))?$/i.exec(input);
  if (!match) return;
  return { agent: match[1].toLowerCase(), query: match[2] ?? '', start: input.lastIndexOf('@'), end: input.length };
}

export function sessionArgs(agent, query) {
  if (!SOURCES.includes(agent)) throw new Error('Unknown source');
  const args = ['sessions', '--agent', agent, '--json'];
  const bounded = typeof query === 'string' && query.length <= 120;
  if (bounded) args.push('--query', query, '--limit', '51');
  return { args, bounded };
}

export function localClient(options = {}) {
  const linked = fileURLToPath(new URL('../../../.venv/' + (process.platform === 'win32' ? 'Scripts/agentref.exe' : 'bin/agentref'), import.meta.url));
  const command = options.command || process.env.AGENTREF_COMMAND || (existsSync(linked) ? linked : 'agentref');
  const prefix = options.args ?? [];
  const invoke = options.execFile || execFile;
  if (typeof command !== 'string' || !Array.isArray(prefix) || prefix.some(x => typeof x !== 'string')) {
    throw new Error('AgentRef command/args configuration is invalid');
  }
  const run = (args, signal) => new Promise((resolve, reject) => {
    invoke(command, [...prefix, ...args], { encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 8 * 1024 * 1024, signal }, (error, stdout, stderr) => {
      if (error) {
        const failure = new Error(signal?.aborted ? '已取消' : `AgentRef 执行失败 (${error.code ?? 'unknown'})；请检查本机 command 配置。`);
        failure.paginationUnsupported = /unrecognized arguments:.*(?:--query|--limit)/.test(stderr);
        return reject(failure);
      }
      resolve({ stdout, incomplete: Boolean(stderr.trim()) });
    });
  });
  return {
    async sessions(agent, signal, query) {
      const request = sessionArgs(agent, query);
      let result;
      let queryApplied = request.bounded;
      try {
        result = await run(request.args, signal);
      } catch (error) {
        if (!request.bounded || !error.paginationUnsupported) throw error;
        queryApplied = false;
        result = await run(['sessions', '--agent', agent, '--json'], signal);
      }
      const rows = JSON.parse(result.stdout);
      if (!Array.isArray(rows) || rows.some(row => row.agent !== agent || typeof row.ref !== 'string' || !row.ref.startsWith(agent + ':'))) {
        throw new Error('AgentRef 返回了无效的会话列表');
      }
      return { rows, incomplete: result.incomplete, queryApplied, hasMore: rows.length > 50,
        total: queryApplied ? undefined : rows.length };
    },
    async context(row, signal) {
      const result = await run(['context', row.ref, '--agent', row.agent], signal);
      if (!result.stdout.trim()) throw new Error('所选会话没有可引用的上下文');
      return result.stdout;
    },
  };
}

// Only documented TUI slots, Prompt refs, dialogs and keymaps are used.
export function install(api, client, measure = value => globalThis.Bun.stringWidth(value)) {
  let prompt;
  let request;
  let disposed = false;
  const notice = (message, variant = 'info') => api.ui.toast({ title: 'AgentRef', message: clean(message), variant });
  const cancel = () => {
    request?.controller.abort();
    request = undefined;
  };
  const bindPrompt = props => {
    let owned;
    return api.ui.Prompt({
      get sessionID() { return props.session_id; },
      get visible() { return props.visible; },
      get disabled() { return props.disabled; },
      get onSubmit() { return props.on_submit; },
      ref(value) {
        if (value) prompt = owned = value;
        else if (prompt === owned) { prompt = undefined; cancel(); }
        props.ref?.(value);
      },
    });
  };
  api.slots.register({ slots: { home_prompt: bindPrompt, session_prompt: bindPrompt } });
  const unchanged = token => !disposed && request === token && prompt === token.prompt
    && JSON.stringify(prompt.current) === token.snapshot;

  async function open(token) {
    try {
      const result = await client.sessions(token.mention.agent, token.controller.signal, token.mention.query);
      if (!unchanged(token)) return;
      const query = token.mention.query.toLowerCase();
      const rows = result.queryApplied ? result.rows
        : result.rows.filter(row => !query || [row.title, row.cwd, row.ref].some(value => String(value ?? '').toLowerCase().includes(query)));
      token.loading = false;
      if (!rows.length) {
        notice(result.incomplete ? '索引不完整，未找到匹配会话；请运行 agentref doctor。' : '没有匹配会话，可使用 @agent:关键词 筛选。');
        cancel();
        return;
      }
      const options = rows.slice(0, 50).map((row, index) => ({
        title: `${index + 1}. ${clean(row.title || row.ref)}`,
        description: clean(`${row.cwd || '未知工作区'} · ${row.updatedAt || ''}`),
        value: row.ref,
      }));
      const selectedRows = new Map(rows.slice(0, 50).map(row => [row.ref, row]));
      const count = result.queryApplied && result.hasMore ? '51+' : rows.length;
      api.ui.dialog.replace(() => api.ui.DialogSelect({
        title: `@${token.mention.agent} 会话 (${options.length}/${count})${result.incomplete ? ' · 索引不完整' : ''}`,
        placeholder: '搜索会话 · ↑↓ 移动 · Enter/Tab 选择 · Esc 取消',
        options,
        onSelect(option) {
          if (!unchanged(token) || token.selecting) return;
          const row = selectedRows.get(option.value);
          if (!row) return;
          token.selecting = true;
          notice('正在读取所选会话…');
          void client.context(row, token.controller.signal).then(context => {
            if (!unchanged(token)) return;
            const original = JSON.parse(token.snapshot);
            const marker = `【AgentRef ${row.agent} · ${clean(row.title || row.ref)}】`;
            const start = token.mention.start;
            const offset = promptWidth(original.input.slice(0, start), measure);
            const part = { type: 'text', text: context, source: { text: { start: offset, end: offset + promptWidth(marker, measure), value: marker } } };
            token.prompt.set({ ...original, input: original.input.slice(0, start) + marker + ' ', parts: [...original.parts, part] });
            api.ui.dialog.clear();
            token.prompt.focus();
          }).catch(error => {
            if (unchanged(token)) notice(error.message, 'error');
          }).finally(() => { token.selecting = false; });
        },
      }), () => { if (request === token) cancel(); });
      token.dialogDepth = api.ui.dialog.depth;
    } catch (error) {
      if (unchanged(token)) { notice(error.message, 'error'); cancel(); }
    } finally {
      // Discard an obsolete search even when the user edited the draft.
      if (request === token && token.loading) cancel();
    }
  }

  function tab() {
    if (disposed) return false;
    if (api.ui.dialog.open) {
      if (!request || request.loading || !unchanged(request) || api.ui.dialog.depth !== request.dialogDepth) return false;
      if (!request.selecting) api.keymap.dispatchCommand('dialog.select.submit');
      return true;
    }
    // 1.18.16 exposes shell state through the editor's public status trait;
    // PromptRef.current.mode is optional and may not reflect live mode changes.
    if (!prompt?.focused || prompt.current.mode === 'shell' || api.renderer.currentFocusedEditor?.traits?.status === 'SHELL') return false;
    const current = prompt.current;
    const mention = mentionAtEnd(current.input);
    const cursor = api.renderer.currentFocusedEditor?.cursorOffset;
    if (!mention || (typeof cursor === 'number' && cursor !== promptWidth(current.input, measure))) return false;
    if (request?.loading && unchanged(request)) return true;
    cancel();
    const token = { prompt, mention, snapshot: JSON.stringify(current), loading: true, controller: new AbortController() };
    request = token;
    notice('正在读取本机会话目录…');
    void open(token);
    return true;
  }
  const off = api.keymap.registerLayer({
    priority: 1000,
    bindings: [
      { key: 'tab', cmd: tab },
      { key: 'escape', cmd: () => { if (!request?.loading) return false; cancel(); return true; } },
      { key: 'return', cmd: () => { if (!request?.loading || !prompt?.focused) return false; cancel(); return true; } },
    ],
  });
  api.lifecycle.onDispose(() => { disposed = true; cancel(); off(); });
}

export default { id: 'agentref.sessions', tui: async (api, options) => install(api, localClient(options)) };
