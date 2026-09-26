// Runs the built DSH client in a real browser with synthetic local HTTP data.
// Requires Playwright on NODE_PATH. This is a DOM integration test, not a DSH
// model/provider test or a claim that every downstream composer version works.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const evidenceRoot = path.join(root, 'output/native-mentions');
  await fs.mkdir(evidenceRoot, { recursive: true });
  const output = await fs.mkdtemp(path.join(evidenceRoot, 'dsh-browser-'));
  const bundle = await fs.readFile(path.join(root, 'integrations/dsh/agentref-dsh/lib/client.js'));
  const calls = [];
  let incomplete = false;
  let empty = false;
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/client.js') { res.setHeader('Content-Type', 'text/javascript'); return res.end(bundle); }
    if (url.pathname.startsWith('/_dsh/agentref/')) {
      calls.push({ path: url.pathname, query: Object.fromEntries(url.searchParams) });
      res.setHeader('Content-Type', 'application/json');
      if (url.pathname.endsWith('/sessions')) {
        const agent = url.searchParams.get('agent');
        return res.end(JSON.stringify({ ok: true, incomplete, sessions: (empty ? [] : ['1','2']).map(x => ({ agent, ref: `${agent}:${x.repeat(16)}`, title: `合成会话 ${x}`, cwd: `D:/fixture/${x}`, updatedAt: '2026-09-13' })) }));
      }
      return res.end(JSON.stringify({ ok: true, context: 'SYNTHETIC CONTEXT ' + url.searchParams.get('ref') }));
    }
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(`<!doctype html><html><meta charset="utf-8"><title>AgentRef DSH browser validation</title>
      <style>body{background:#151619;color:#eee;font:18px sans-serif;padding:32px}form{position:fixed;bottom:30px;left:40px;right:40px}textarea{box-sizing:border-box;width:100%;height:110px;background:#25262b;color:white;border:1px solid #666;border-radius:12px;padding:20px;font:20px sans-serif}</style>
      <h1>AgentRef · DSH 浏览器交互验收</h1><p>合成会话数据 · 不连接模型</p>
      <form data-slot="conversation.composer"><textarea data-dsh-part="composer-input" aria-label="消息"></textarea></form>
      <script>window.sent=[];window.__ModuleLoader__={load:({factory})=>factory().apply()};</script>
      <script src="/client.js"></script>
      <script>document.querySelector('textarea').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();window.sent.push(e.target.value)}});</script></html>`);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, ...(process.env.AGENTREF_BROWSER_CHANNEL ? { channel: process.env.AGENTREF_BROWSER_CHANNEL } : {}) });
    const page = await browser.newPage({ viewport: { width: 1100, height: 720 } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    const input = page.locator('textarea');
    const countContext = () => calls.filter(x => x.path.endsWith('/context')).length;
    incomplete = true;
    for (const noRows of [false, true]) {
      empty = noRows;
      await input.fill('@claude');
      await input.press('Tab');
      await page.locator('[role=status]').waitFor();
      assert.match(await page.locator('[role=status]').textContent(), /索引可能不完整/);
      if (empty) assert.match(await page.locator('[role=listbox]').textContent(), /不代表来源中没有会话/);
      assert.equal(countContext(), 0);
      await page.screenshot({ path: path.join(output, empty ? 'dsh-incomplete-empty.png' : 'dsh-incomplete-menu.png') });
      await input.press('Escape');
      await page.locator('[role=listbox]').waitFor({ state: 'detached' });
    }
    incomplete = false; empty = false;
    for (const agent of ['claude','codex','grok','opencode','antigravity','dsh']) {
      await input.fill('@' + agent);
      await input.press('Tab');
      await page.locator('[role=option][aria-selected=true]').waitFor();
      assert.equal(await page.locator('[role=status]').count(), 0);
      assert.equal(countContext(), 0);
      assert.equal(await page.evaluate(() => sent.length), 0);
      await input.press('Escape');
      await page.locator('[role=listbox]').waitFor({ state: 'detached' });
    }
    await input.fill('@grok');
    // Exercise first Tab on the automatically displayed list as well.
    await page.locator('[role=listbox]').waitFor();
    await input.press('Tab');
    await input.press('ArrowDown');
    assert.ok((await page.locator('[aria-selected=true]').textContent()).includes('合成会话 2'));
    const bounds = await page.locator('[role=listbox]').boundingBox();
    assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 720, JSON.stringify(bounds));
    await page.screenshot({ path: path.join(output, 'dsh-keyboard-menu.png') });
    await input.press('Enter');
    await page.locator('[role=listbox]').waitFor({ state: 'detached' });
    assert.equal(countContext(), 1);
    assert.equal(calls.at(-1).query.ref, 'grok:' + '2'.repeat(16));
    assert.equal(await page.evaluate(() => sent.length), 0);
    assert.ok((await input.inputValue()).includes('合成会话 2'));
    assert.ok(!(await input.inputValue()).includes('SYNTHETIC CONTEXT'));
    await input.press('Enter');
    const sent = await page.evaluate(() => window.sent);
    assert.equal(sent.length, 1);
    assert.ok(sent[0].includes('SYNTHETIC CONTEXT'));
    assert.deepEqual(errors, []);
    const result = { passed: true, synthetic: true, modelCalled: false, output, incompleteWarnings: true, sources: 6, contextReads: countContext(), syntheticSubmissions: sent.length, menuBounds: bounds, pageErrors: errors };
    await fs.writeFile(path.join(output, 'dsh-browser-result.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
