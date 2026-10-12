import { chromium } from 'playwright';
import fs from 'fs';
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell' });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const errs = []; page.on('pageerror', (e) => errs.push(e.message));
await page.goto('file://' + process.cwd() + '/h.html');
const src = fs.readFileSync(process.argv[2] + '/index.html', 'utf8');
await page.evaluate((src) => { const root = document.getElementById('dash-root'); const tpl = document.createElement('template'); tpl.innerHTML = src; const sc=[...tpl.content.querySelectorAll('script')]; sc.forEach((s)=>s.remove()); root.append(tpl.content); for (const s of sc) (new Function(s.textContent))(); }, src);
await page.waitForTimeout(500);
const quotes = JSON.parse(fs.readFileSync('quotes.json','utf8'));
const Q = Object.fromEntries(quotes.map((q) => [q.symbol, q]));
for (const tab of ['day', 'swing']) {
  await page.click(`#tabs [data-page=${tab}]`); await page.waitForTimeout(300);

  await page.waitForTimeout(200);
  const res = await page.evaluate(() => [...document.querySelectorAll(`#${window.mcPage === 'day' ? 'daycards' : 'swingcards'} article`)].map((a) => {
    const bar = a.querySelector('.mc-bar'); if (!bar) return {id: a.id, bar: false};
    const br = bar.getBoundingClientRect();
    const rng = bar.querySelector('.mc-rng');
    const marks = [...bar.querySelectorAll('.mc-mk')].map((m) => m.getBoundingClientRect().left + m.getBoundingClientRect().width / 2);
    const labels = [...bar.querySelectorAll('.mc-mk-l')].map((l) => l.textContent);
    const dot = bar.querySelector('.mc-cur'); const dr = dot && dot.getBoundingClientRect();
    return {id: a.id, bar: true, rng: rng ? {l: rng.getBoundingClientRect().left, r: rng.getBoundingClientRect().right, title: rng.title} : null, marks, labels, dot: dr ? dr.left + dr.width / 2 : null, bl: br.left, bw: br.width};
  }));
  // values per card from data files
  const data = JSON.parse(fs.readFileSync(process.argv[2] + '/' + (tab === 'day' ? 'daytrade' : 'swing_setups') + '.json', 'utf8'));
  for (const r of res) {
    const sym = r.id.split('-')[1]; const q = Q[sym]; const row = data.find((x) => x.symbol === sym);
    if (!r.bar) { console.log(tab, sym, 'NO LADDER'); continue; }
    if (!r.rng) { console.log(tab, sym, 'NO RANGE BAND', q ? '' : '(no quote)'); continue; }
    const vals = tab === 'day' ? [row.stop, row.prev_close, row.trigger, row.t1, row.t2] : [row.stop, row.pivot, row.zone_top, row.target];
    // linear fit px = a + b*v using first and last markers
    const i0 = vals.indexOf(Math.min(...vals)), i1 = vals.indexOf(Math.max(...vals));
    const b = (r.marks[i1] - r.marks[i0]) / (vals[i1] - vals[i0]), a = r.marks[i0] - b * vals[i0];
    const expL = a + b * q.low, expR = a + b * q.high, expDot = a + b * q.price;
    const ok = Math.abs(expL - r.rng.l) < 2 && Math.abs(expR - r.rng.r) < 2 && Math.abs(expDot - r.dot) < 2;
    console.log(tab, sym, ok ? 'OK ' : 'MISMATCH', `low ${q.low} high ${q.high} price ${q.price} | band px ${r.rng.l.toFixed(1)}-${r.rng.r.toFixed(1)} expected ${expL.toFixed(1)}-${expR.toFixed(1)} | dot ${r.dot?.toFixed(1)} exp ${expDot.toFixed(1)} | title "${r.rng.title}"`);
  }
}
console.log('errors:', errs.length ? errs : 'none');
await browser.close();
