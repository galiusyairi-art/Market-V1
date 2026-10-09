import { chromium } from 'playwright';
import fs from 'fs';
const D = '/tmp/claude-0/-home-user-Market-V1/3ac42b4a-496c-5a7a-93b5-649a669f647c/scratchpad/dash/';
const page_html = fs.readFileSync(D + 'index.html', 'utf8');
const files = ['brief','outlook','indices','regime','timing','daytrade','swing_setups','sectors','macro','social','chatter','methods','sources','calendar'];
const data = Object.fromEntries(files.map((f) => [f, JSON.parse(fs.readFileSync(D + f + '.json', 'utf8'))]));
data.quotes = JSON.parse(fs.readFileSync('quotes.json', 'utf8'));
const d3src = fs.readFileSync('node_modules/d3/dist/d3.min.js', 'utf8');
const theme = process.argv[2] || 'dark';
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>:root{--font-anthropic-sans:system-ui,sans-serif;--font-anthropic-serif:Georgia,serif;--cds-font-size-caption:12px;--cds-font-size-body:14px;--cds-font-size-heading:16px;--cds-font-size-title:26px;--cds-font-weight-medium:500;--cds-gap-xs:4px;--cds-gap-sm:8px;--cds-gap-md:14px;--cds-gap-lg:20px;--cds-pad-xs:4px;--cds-pad-sm:8px;--cds-pad-md:12px;--cds-pad-lg:16px;--cds-radius:10px;--color-bg:#fff;--color-panel:#fff;--color-fg:#111;--color-fg-muted:#666;--color-border-line:#ddd;--color-ok:green;--color-warn:orange;--color-bad:red;--cds-dur-slow:.3s;--cds-ease-out:ease-out}
body{margin:0;background:#fff}#dash-root{padding:var(--dash-gutter,16px)}.dash-skeleton{background:#eee;color:transparent}</style>
<script>${d3src}</script>
<script>
const DATA = ${JSON.stringify(data)};
let params = {account:100000, risk_pct:0.5, theme:'${theme}', symbols:'SPY'};
const calcs = {}; const subs = [];
window.dash = {
  data(id){ if (calcs[id]) { const c = calcs[id]; try { return {status:'ok', data:c.fn(...c.inputs.map((i)=>dash.data(i).data))}; } catch(e){ console.error('calc '+id+': '+e.message); return {status:'error', data:[]}; } }
    return DATA[id] ? {status:'ok', data:DATA[id], columns:Object.keys(DATA[id][0]||{}), refreshing:false} : {status:'missing', data:[]}; },
  onData(fn){ subs.push(fn); fn(); },
  calc(id, o){ calcs[id] = o; },
  params(){ return params; },
  setParams(o){ params = {...params, ...o}; setTimeout(()=>subs.forEach((f)=>f()),0); },
  resetParams(){}, refresh(id){ setTimeout(()=>subs.forEach((f)=>f()),0); }, setLink(){}, colors:['#36c','#c63']
};
</script></head><body><div id="dash-root"></div></body></html>`;
fs.writeFileSync('h.html', html);
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell' });
const errors = [];
for (const [w, h, tag] of [[1400, 900, 'desk'], [400, 860, 'mob']]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  page.on('pageerror', (e) => errors.push(tag + ' pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(tag + ' console: ' + m.text()); });
  await page.goto('file://' + process.cwd() + '/h.html');
  // inject page like the dashboard does: html then run scripts in order
  await page.evaluate((src) => {
    const root = document.getElementById('dash-root');
    const tpl = document.createElement('template'); tpl.innerHTML = src;
    const scripts = [...tpl.content.querySelectorAll('script')]; scripts.forEach((s) => s.remove());
    root.append(tpl.content);
    for (const s of scripts) { try { (new Function(s.textContent))(); } catch (e) { console.error('script: ' + e.message + ' ' + e.stack); } }
  }, page_html);
  await page.waitForTimeout(600);
  for (const tab of ['decide', 'day', 'swing', 'market']) {
    await page.click(`#tabs [data-page=${tab}]`);
    await page.waitForTimeout(300);
    if (tab === 'day') { await page.click('#day-HUM summary'); await page.waitForTimeout(200); }
    await page.screenshot({ path: `${tag}-${tab}.png`, fullPage: tab !== 'market' });
  }
  if (tag === 'desk') {
    const txt = await page.evaluate(() => [...document.querySelectorAll('#daycards .mc-do, #swingcards .mc-do')].map((e) => e.closest('article').id + ' | ' + e.textContent.trim()).join('\n'));
    console.log(txt);
    console.log('strip:', await page.evaluate(() => document.getElementById('strip').textContent));
    console.log('next:', await page.evaluate(() => document.getElementById('next-upd').textContent));
    console.log('qtime:', await page.evaluate(() => document.getElementById('quotes-time').textContent));
    console.log('pulse HUM:', await page.evaluate(() => (document.querySelector('#day-HUM .mc-note')||{}).textContent));
    const ow = await page.evaluate(() => document.documentElement.scrollWidth);
    console.log('desk scrollWidth', ow);
  } else {
    console.log('mob scrollWidth', await page.evaluate(() => document.documentElement.scrollWidth));
  }
  await page.close();
}
await browser.close();
console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
