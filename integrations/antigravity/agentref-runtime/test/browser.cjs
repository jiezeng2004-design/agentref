// Isolated Chromium DOM/real-CDP checks; not a real AGY model acceptance test.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const source = await fs.readFile(path.join(root, 'client.js'), 'utf8');
  const { createBroker, fixtureClient } = await import('../broker.mjs');
  const calls = []; let delay = 0;
  const base = fixtureClient();
  const broker = createBroker({
    async sessions(...args) { calls.push('sessions'); if (delay) await new Promise(r => setTimeout(r, delay)); return base.sessions(...args); },
    async context(...args) { calls.push('context'); if (delay) await new Promise(r => setTimeout(r, delay)); return base.context(...args); },
  });
  const server = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(`<!doctype html><title>Antigravity</title><style>body{font:16px system-ui;padding:25px}main{margin-top:380px;width:700px}[contenteditable]{min-height:90px;white-space:pre-wrap;border:1px solid #888;padding:12px}#typeahead-menu{height:70px;background:#eee}</style>
      <h1>AgentRef AGY isolated fixture</h1><p>Synthetic data; no model</p><main>
      <div id="typeahead-menu">FILE RESULTS</div><div role="combobox" aria-label="Message input" aria-controls="typeahead-menu" data-lexical-editor="true" contenteditable="true"></div></main>
      <script>window.electronNative={};window.sent=0;window.modelText='';const e=document.querySelector('[contenteditable]');e.addEventListener('input',()=>window.modelText=e.textContent);e.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();window.sent++}});</script>`);
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'agentref-agy-browser-'));
  let context, helper, heartbeat;
  const errors = [];
  try {
    context = await chromium.launchPersistentContext(temporary, { headless: true, viewport: { width: 1000, height: 800 },
      args: ['--remote-debugging-port=0'], ...(process.env.AGENTREF_BROWSER_CHANNEL ? { channel: process.env.AGENTREF_BROWSER_CHANNEL } : {}) });
    const page = context.pages()[0]; page.on('pageerror', e => errors.push(e.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.exposeFunction('__fixtureBridge', async payload => {
      const request = JSON.parse(payload); let response;
      try { response = { id: request.id, ok: true, value: await broker.call(request) }; }
      catch { response = { id: request.id, ok: false }; }
      await page.evaluate(response => window.__agentrefAgyRuntime?.deliver(response), response);
    });
    await page.addScriptTag({ content: `${source}(${JSON.stringify({ origin: new URL(page.url()).origin, id: 'fixture', binding: '__fixtureBridge', fixture: true })});` });
    heartbeat = setInterval(() => page.evaluate(() => window.__agentrefAgyRuntime?.ping()).catch(() => {}), 1500);
    const editor = page.locator('[contenteditable=true]'); const panel = page.locator('#agentref-agy-runtime .panel');
    for (const agent of ['claude', 'codex', 'grok', 'opencode', 'antigravity', 'dsh']) {
      await editor.fill('@' + agent); await editor.press('Tab');
      await panel.locator('[role=option]').first().waitFor();
      assert.equal(calls.filter(c => c === 'context').length, 0);
      assert.equal(await page.locator('#typeahead-menu').evaluate(e => e.style.visibility), 'hidden');
      await editor.press('Escape'); assert.equal(await editor.textContent(), '@' + agent);
      assert.equal(await panel.isVisible(), false);
      assert.equal(await page.locator('#typeahead-menu').evaluate(e => e.style.visibility), '');
    }
    await editor.fill('中文😀 prefix @codex'); await editor.press('Tab');
    await panel.locator('[role=option]').first().waitFor();
    await editor.press('ArrowDown'); await editor.press('Enter');
    await page.waitForFunction(() => document.querySelector('[contenteditable]').textContent.includes('SYNTHETIC CONTEXT'));
    assert.match(await editor.textContent(), /^中文😀 prefix 【AgentRef/);
    assert.match(await editor.textContent(), /codex:2222222222222222/);
    assert.equal(await page.evaluate(() => window.sent), 0);
    assert.equal(await page.evaluate(() => window.modelText), await editor.textContent());
    const reads = calls.filter(c => c === 'context').length;
    delay = 200;
    await editor.fill('@codex'); await editor.press('Tab'); await editor.press('Escape');
    await page.waitForTimeout(350); assert.equal(await panel.isVisible(), false);
    await editor.fill('@codex'); await editor.press('Tab'); await panel.locator('[role=option]').first().waitFor();
    await editor.press('Enter'); await editor.fill('USER CHANGED DRAFT');
    await page.waitForTimeout(550); assert.equal(await editor.textContent(), 'USER CHANGED DRAFT');
    assert.equal(await page.evaluate(() => window.sent), 0);
    delay = 0;
    await editor.fill('keep @claude'); await editor.press('Tab'); await panel.locator('[role=option]').first().waitFor();
    await panel.locator('[role=option]').first().click();
    await page.waitForFunction(() => document.querySelector('[contenteditable]').textContent.includes('SYNTHETIC CONTEXT'));
    assert.match(await editor.textContent(), /^keep 【AgentRef/);
    clearInterval(heartbeat);
    await page.evaluate(() => window.__agentrefAgyRuntime.dispose());
    assert.equal(await page.locator('#agentref-agy-runtime').count(), 0);
    // Real helper process and WebSocket transport, against our own synthetic
    // Chromium profile. Never uses the installed AGY or its port file.
    await editor.fill('@dsh');
    helper = spawn(process.execPath, [path.join(root, 'runtime.mjs'), '--apply', '--fixture', '--port-file', path.join(temporary, 'DevToolsActivePort')], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = ''; helper.stdout.on('data', data => { output += data; });
    helper.stderr.on('data', () => {});
    await page.waitForFunction(() => Boolean(window.__agentrefAgyRuntime), null, { timeout: 10000 });
    await editor.press('Tab'); await panel.locator('[role=option]').first().waitFor();
    await editor.press('Enter');
    await page.waitForFunction(() => document.querySelector('[contenteditable]').textContent.includes('SYNTHETIC CONTEXT dsh:'));
    assert.equal(await page.evaluate(() => window.sent), 0);
    assert.match(output, /"attached":true/);
    await page.evaluate(() => window.__agentrefAgyRuntime.dispose());
    await new Promise((resolve, reject) => {
      if (helper.exitCode !== null) return resolve();
      const timeout = setTimeout(() => reject(new Error('Helper did not exit after stop')), 10000);
      helper.once('exit', code => { clearTimeout(timeout); code === 0 ? resolve() : reject(new Error('Helper exited nonzero')); });
    });
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, sixSourceMenus: true, cancelAndStaleDraft: true, mouseAndKeyboard: true,
      preservesPrefix: true, noAutoSubmit: true, realCdpFixture: true, helperStopped: true, actualAgyOrModelTested: false }));
  } finally {
    clearInterval(heartbeat); broker.cancel();
    if (helper && helper.exitCode === null) helper.kill();
    await context?.close(); await new Promise(r => server.close(r));
    // Only the exact empty-profile directory created by this invocation.
    if (path.dirname(temporary) !== os.tmpdir() || !path.basename(temporary).startsWith('agentref-agy-browser-')) throw new Error('Unexpected fixture directory');
    await fs.rm(temporary, { recursive: true, force: true });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
