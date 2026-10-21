// Session-honesty check: renders the page at fixed New York times with quotes from the old connector (Finnhub only)
// and from connector v2 (pre-market / regular / after-hours), and asserts what the trader sees.
// usage: node session_check.mjs <dir with index.html> dashboard/test/fixtures   (run where node_modules has playwright + d3)
import { chromium } from 'playwright';
import fs from 'fs';
const [PAGE_DIR, DATA_DIR] = process.argv.slice(2);
const pageSrc = fs.readFileSync(PAGE_DIR + '/index.html', 'utf8');
const rd = (f) => JSON.parse(fs.readFileSync(DATA_DIR + '/' + f + '.json', 'utf8'));
const base = Object.fromEntries(['journal', 'lessons', 'brief', 'outlook', 'indices', 'regime', 'timing', 'daytrade', 'swing_setups', 'sectors', 'macro', 'social', 'chatter', 'methods', 'sources', 'calendar'].map((f) => [f, rd(f)]));
const legacyPre = rd('legacy_pre');
const d3src = fs.readFileSync('node_modules/d3/dist/d3.min.js', 'utf8');
let fails = 0;
const check = (c, m, extra) => { if (!c) { fails++; console.error('  FAIL', m, extra ?? ''); } else console.log('  ok  ', m); };

// connector-v2 rows derived from yesterday's closes
const PM = { CLF: -1.99, SPY: -0.30, QQQ: -0.45, NBIS: 2.2 };
function v2(session, opts = {}) {
  return legacyPre.map((r) => {
    const prev = r.price, chg = PM[r.symbol] ?? 0.2, sym = r.symbol;
    const row = { symbol: sym, session, trade_date: '2026-10-20', source: 'yahoo', check: 'ok', alt_price: prev, error: null,
      prev_close: prev, ext_session: null, ext_price: null, ext_change_pct: null, ext_time_ny: null, pm_high: null, pm_low: null, ah_high: null, ah_low: null };
    const pm = +(prev * (1 + chg / 100)).toFixed(4);
    row.pm_high = +(Math.max(prev, pm) * 1.006).toFixed(4); row.pm_low = +(Math.min(prev, pm) * 0.994).toFixed(4);
    if (session === 'pre') Object.assign(row, { price: pm, price_session: 'pre', time_ny: '2026-10-20T07:38:00', change_pct: chg, change: pm - prev,
      reg_price: null, day_change_pct: null, open: null, high: null, low: null, ext_session: 'pre', ext_price: pm, ext_change_pct: chg, ext_time_ny: '2026-10-20T07:38:00' });
    if (session === 'regular' || session === 'post') {
      const reg = +(prev * (1 + (chg + 1) / 100)).toFixed(4);
      Object.assign(row, { reg_price: reg, day_change_pct: chg + 1, open: prev, high: +(reg * 1.01).toFixed(4), low: +(prev * 0.985).toFixed(4) });
      if (session === 'regular') Object.assign(row, { price: reg, price_session: 'regular', time_ny: '2026-10-20T10:59:00', change_pct: chg + 1 });
      else { const ah = +(reg * 0.99).toFixed(4); Object.assign(row, { price: ah, price_session: 'post', time_ny: '2026-10-20T17:09:00', change_pct: +((ah / prev - 1) * 100).toFixed(4), ext_session: 'post', ext_price: ah, ext_change_pct: -1, ext_time_ny: '2026-10-20T17:09:00' }); }
    }
    if (opts.mismatch === sym) { row.check = 'mismatch'; row.alt_price = +(row.reg_price * 1.03).toFixed(2); }
    return row;
  });
}
const brief = (asOf) => base.brief.map((r) => (r.key === 'as_of' ? { ...r, text: asOf } : r));

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell' });
async function render(name, nyTime, data) {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, timezoneId: 'Asia/Jerusalem' });
  await page.clock.setFixedTime(new Date(nyTime));
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>:root{--color-bg:#111;--color-panel:#1a1a1a;--color-fg:#eee;--color-fg-muted:#999;--color-border-line:#333;--color-ok:#3a3;--color-warn:#e90;--color-bad:#e33;--cds-radius:10px;--cds-font-size-caption:12px;--cds-font-size-body:14px}body{margin:0;background:#111}</style>
<script>${d3src}</script><script>
const DATA = ${JSON.stringify(data)};
let params = {account:100000, risk_pct:0.5, theme:'dark', symbols:'SPY'};
const calcs = {}; const subs = [];
window.dash = {
  data(id){ if (calcs[id]) { const c = calcs[id]; try { return {status:'ok', data:c.fn(...c.inputs.map((i)=>dash.data(i).data))}; } catch(e){ console.error('calc '+id+': '+e.message); return {status:'error', data:[]}; } }
    return DATA[id] ? {status:'ok', data:DATA[id], refreshing:false} : {status:'missing', data:[]}; },
  onData(fn){ subs.push(fn); fn(); }, calc(id, o){ calcs[id] = o; }, params(){ return params; },
  setParams(o){ params = {...params, ...o}; setTimeout(()=>subs.forEach((f)=>f()),0); }, resetParams(){}, refresh(){}, setLink(){}, colors:['#36c','#c63']
};</script></head><body><div id="dash-root"></div></body></html>`;
  fs.writeFileSync('sess_h.html', html);
  await page.goto('file://' + process.cwd() + '/sess_h.html');
  await page.evaluate((src) => {
    const root = document.getElementById('dash-root'); const tpl = document.createElement('template'); tpl.innerHTML = src;
    const sc = [...tpl.content.querySelectorAll('script')]; sc.forEach((s) => s.remove()); root.append(tpl.content);
    for (const s of sc) (new Function(s.textContent))();
  }, pageSrc);
  await page.waitForTimeout(300);
  const grab = async () => page.evaluate(() => {
    const t = (sel) => [...document.querySelectorAll(sel)].map((e) => e.textContent.replace(/\s+/g, ' ').trim());
    const card = (id) => { const c = document.getElementById(id); if (!c) return null; return { head: c.querySelector('.mc-sc-px')?.textContent.replace(/\s+/g, ' ').trim(), todo: c.querySelector('.mc-do')?.textContent.trim(), range: [...c.querySelectorAll('.mc-note')].map((e) => e.textContent).join(' | '), band: c.querySelector('.mc-rng')?.title || null }; };
    const al = document.getElementById('data-alert'); return { alert: al.offsetHeight === 0 ? '' : al.textContent || '(empty box visible)', strip: document.getElementById('strip').textContent, qtime: document.getElementById('quotes-time').textContent, decisions: t('#decisions .mc-drow').join(' || '), cards: Object.fromEntries([...document.querySelectorAll('#daycards article, #swingcards article')].map((a) => [a.id, null])), body: document.body.textContent };
  });
  const out = { errors };
  out.decide = await grab();
  out.decide.body = await page.evaluate(() => document.getElementById('decide').textContent + ' ' + document.getElementById('top').textContent);
  await page.click('#tabs [data-page=day]'); await page.waitForTimeout(150);
  out.day = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#daycards article')].map((c) => [c.id, { head: c.querySelector('.mc-sc-px')?.textContent.replace(/\s+/g, ' ').trim(), todo: c.querySelector('.mc-do')?.textContent.trim(), notes: [...c.querySelectorAll(':scope > .mc-note')].map((e) => e.textContent).join(' | '), band: c.querySelector('.mc-rng')?.title || null, text: c.textContent }])));
  await page.screenshot({ path: `sess-${name}-day.png`, fullPage: true });
  await page.click('#tabs [data-page=swing]'); await page.waitForTimeout(150);
  out.swing = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#swingcards article')].map((c) => [c.id, { head: c.querySelector('.mc-sc-px')?.textContent.replace(/\s+/g, ' ').trim(), todo: c.querySelector('.mc-do')?.textContent.trim(), band: c.querySelector('.mc-rng')?.title || null }])));
  await page.close();
  return out;
}
const ALL = (o) => JSON.stringify(o);

console.log('S1 old connector, 07:39 NY pre-market, plan from yesterday (the reported CLF case)');
let o = await render('legacy-pre', '2026-10-20T07:39:00-04:00', { ...base, brief: brief('2026-10-19T12:10:00-04:00'), quotes: legacyPre });
check(!o.errors.length, 'no JS errors', o.errors);
check(!ALL(o).includes('16.34'), 'yesterday\'s +16.34% for CLF is not shown anywhere');
check(/סגירה אחרונה/.test(o.day['day-CLF'].head) && o.day['day-CLF'].head.includes('$14.10'), 'CLF header: last close $14.10, labelled as close', o.day['day-CLF'].head);
check(/אין נתוני פרה-מרקט/.test(o.decide.alert) && /התוכנית מ-19.10/.test(o.decide.alert), 'alert: no pre-market data + plan is from 19.10', o.decide.alert);
check(Object.values(o.day).every((c) => /לא לפעול/.test(c.todo)), 'every day card says: plan from yesterday, do not act', Object.values(o.day).map((c) => c.todo));
check(Object.values(o.day).every((c) => c.band === null), 'no "today\'s range" band from yesterday\'s session');
check(Object.values(o.day).every((c) => !/R \(|נכנסת בטריגר/.test(c.text)), 'no "if you entered" R read-out on a stale plan');
check(/סגירה/.test(o.decide.strip) && !/0\.42%/.test(o.decide.strip), 'strip shows closes, not yesterday\'s % as today', o.decide.strip);

console.log('S2 connector v2, 07:39 NY pre-market, fresh plan');
o = await render('v2-pre', '2026-10-20T07:39:00-04:00', { ...base, brief: brief('2026-10-20T07:30:00-04:00'), quotes: v2('pre') });
check(!o.errors.length, 'no JS errors', o.errors);
check(o.day['day-CLF'].head.includes('−1.99%') && /פרה-מרקט/.test(o.day['day-CLF'].head) && o.day['day-CLF'].head.includes('$13.82'), 'CLF header: $13.82, −1.99% pre-market', o.day['day-CLF'].head);
check(!o.decide.alert, 'no alert', o.decide.alert);
check(/טווח הפרה-מרקט/.test(o.day['day-CLF'].band || '') && /טווח הפרה-מרקט/.test(o.day['day-CLF'].notes), 'band and caption are the pre-market range', o.day['day-CLF']);
check(/חכה לפתיחה|בוטל|קפץ/.test(o.day['day-CLF'].todo), 'CLF instruction is a pre-open instruction', o.day['day-CLF'].todo);
check(!/נכנסת בטריגר/.test(o.day['day-CLF'].text) && /לא נכנסים לפני הפתיחה/.test(o.day['day-CLF'].text), 'pre-market read-out: no R, says no entry before the open', o.day['day-CLF'].notes);
check(/−0\.30%פרה/.test(o.decide.strip.replace(/\s/g, '')), 'strip: SPY −0.30% marked פרה', o.decide.strip);
check(/Yahoo \+ Finnhub/.test(o.decide.qtime), 'header names the sources', o.decide.qtime);
check(Object.values(o.swing).every((c) => !/אפשר לקנות/.test(c.todo)), 'no swing "buy now" before the open', Object.values(o.swing).map((c) => c.todo));

console.log('S3 connector v2, 11:00 NY regular, one source mismatch');
o = await render('v2-reg', '2026-10-20T11:00:00-04:00', { ...base, brief: brief('2026-10-20T08:45:00-04:00'), quotes: v2('regular', { mismatch: 'INTC' }) });
check(!o.errors.length, 'no JS errors', o.errors);
check(/היום/.test(o.day['day-CLF'].head) && o.day['day-CLF'].head.includes('−0.99%'), 'CLF header: today\'s regular change', o.day['day-CLF'].head);
check(/טווח היום/.test(o.day['day-CLF'].band || ''), 'band is today\'s range');
check(/פער בין מקורות/.test(o.decide.alert) && /INTC/.test(o.decide.alert) && /פער בין מקורות/.test(o.day['day-INTC'].head), 'mismatch shown in alert and on the INTC card', o.decide.alert);

console.log('S4 connector v2, 17:10 NY after-hours');
o = await render('v2-post', '2026-10-20T17:10:00-04:00', { ...base, brief: brief('2026-10-20T11:57:00-04:00'), quotes: v2('post') });
check(!o.errors.length, 'no JS errors', o.errors);
check(/בסגירה · אפטר/.test(o.day['day-CLF'].head) && /אפטר-מרקט/.test(o.day['day-CLF'].head), 'CLF header: close change + after-hours change', o.day['day-CLF'].head);
check(!o.decide.alert, 'no alert', o.decide.alert);

console.log('S5 old connector, 11:00 NY regular (today\'s quote)');
const legacyReg = legacyPre.map((r) => ({ ...r, time_ny: '2026-10-20T10:59:00' }));
o = await render('legacy-reg', '2026-10-20T11:00:00-04:00', { ...base, brief: brief('2026-10-20T08:45:00-04:00'), quotes: legacyReg });
check(!o.errors.length, 'no JS errors', o.errors);
check(o.day['day-CLF'].head.includes('+16.34%') && /היום/.test(o.day['day-CLF'].head), 'a quote stamped today is today\'s change', o.day['day-CLF'].head);
check(!o.decide.alert, 'no alert during the regular session', o.decide.alert);

console.log('S6 old connector, Saturday');
o = await render('legacy-sat', '2026-10-24T12:00:00-04:00', { ...base, brief: brief('2026-10-23T11:57:00-04:00'), quotes: legacyPre.map((r) => ({ ...r, time_ny: '2026-10-23T16:00:00' })) });
check(!o.errors.length, 'no JS errors', o.errors);
check(/סגירה אחרונה/.test(o.day['day-CLF'].head) && !/לא לפעול/.test(o.day['day-CLF'].todo), 'weekend: last close, Friday plan not flagged stale', o.day['day-CLF']);

// ---------- connector v3: daily stats, opening range, earnings ----------
const SECT = ['XLK', 'XLC', 'XLY', 'XLF', 'XLI', 'XLV', 'XLE', 'XLB', 'XLP', 'XLU', 'XLRE'];
const dRow = (symbol, close, o = {}) => ({ symbol, as_of: '2026-10-19', close, prev_high: close * 1.01, prev_low: close * 0.99, sma20: close * 0.98, sma50: close * 0.96, sma150: close * 0.92,
  sma200: close * 0.9, atr14: close * 0.03, atr_pct: 3, avg_vol20: 2e7, high_52w: close * 1.05, low_52w: close * 0.6, high_20d: close * 1.03, low_20d: close * 0.95,
  ref_week: close * 0.99, ref_month: close * 0.98, ref_year: close * 0.85, chg_5d: 1, chg_20d: 2, rsi14: 55, trend_score: 7, trend_max: 7, bars: 252, source: 'yahoo', error: null, ...o });
const daily = [...legacyPre.map((r) => dRow(r.symbol, r.price, r.symbol === 'QQQ' ? { chg_20d: 3 } : {})),
  ...SECT.map((e, i) => dRow(e, 100, { sma50: i < 8 ? 96 : 105, chg_20d: e === 'XLY' ? 3 : e === 'XLP' ? 1 : 2 })),
  dRow('^VIX', 16, { sma50: null }), dRow('^TNX', 4.2, { chg_20d: 1 })];
const earnings = [{ symbol: 'MU', date: '2026-10-23', hour: 'amc', eps_estimate: null, revenue_estimate: null }];
const v3 = (session) => v2(session).map((r) => (r.symbol === 'CLF' && session === 'regular' ? { ...r, or_high: 14.05, or_low: 13.8, vwap: 13.95, volume: 2e7 } : { ...r, or_high: null, or_low: null, vwap: null }));
const near2 = (txt, v) => txt.includes('$' + v.toFixed(2));

console.log('S7 connector v3, 10:30 NY regular: computed levels, light, indices, sectors, earnings');
o = await render('v3-reg', '2026-10-20T10:30:00-04:00', { ...base, swing_setups: base.swing_setups.map((r) => (r.symbol === 'MU' ? { ...r, stop: 800 } : r)), brief: brief('2026-10-20T08:45:00-04:00'), quotes: v3('regular'), daily, earnings });
check(!o.errors.length, 'no JS errors', o.errors);
let clf = o.day['day-CLF'];
check(near2(clf.text, 14.05) && near2(clf.text, 13.84) && near2(clf.text, 14.37) && near2(clf.text, 14.68), 'CLF levels = opening range 14.05, stop 13.84 (½ ATR), T1 14.37, T2 14.68', clf.text.slice(0, 400));
check(/רמות מחושבות מהמסחר החי/.test(clf.text), 'CLF says its levels are computed from live trading');
check(/פרץ ונכשל/.test(clf.todo), 'CLF: traded above the opening range and fell back = failed breakout', clf.todo);
check(/רמות הניתוח של הבוקר/.test(clf.text) && /נזילות/.test(clf.text) && /VWAP/.test(clf.text), 'see-more shows the analysis levels and live checks');
check(/מחושב מנתונים חיים/.test(o.decide.body) && /ירוק/.test(o.decide.body) && /75%/.test(o.decide.body), 'light computed live: green, 75% day exposure');
check(/8 מתוך 11 סקטורים/.test(o.decide.body) && /VIX 16\.0/.test(o.decide.body) && /4\.20%/.test(o.decide.body), 'factors: breadth 8/11, VIX 16.0, 10-year 4.20%');
check(/פרשנות הניתוח/.test(o.decide.body), 'the analysis regime is shown as commentary');
check(/דוח ב-ו׳ 23\.10/.test(o.swing['swing-MU'].todo), 'MU swing blocked: earnings Fri 23.10', o.swing['swing-MU'].todo);

console.log('S8 connector v3, 08:00 NY pre-market: provisional levels from the pre-market range');
o = await render('v3-pre', '2026-10-20T08:00:00-04:00', { ...base, brief: brief('2026-10-20T07:45:00-04:00'), quotes: v3('pre'), daily, earnings });
check(!o.errors.length, 'no JS errors', o.errors);
clf = o.day['day-CLF'];
check(near2(clf.text, 14.24) && near2(clf.text, 14.03) && /שיא אתמול/.test(clf.text), 'CLF (gap −1.99%, under 2%): entry = yesterday high 14.24, stop 14.03, provisional', clf.text.slice(0, 400));
const nb = o.day['day-NBIS'];
check(/שיא הפרה-מרקט/.test(nb.text) && near2(nb.text, 175.03), 'NBIS (gap +2.2%): entry = pre-market high 175.03', nb.text.slice(0, 400));

console.log('S9 01:32 Israel on 21.10 = 18:32 New York on 20.10 (the reported date confusion)');
o = await render('v3-night', '2026-10-20T18:32:00-04:00', { ...base, brief: brief('2026-10-20T08:45:00-04:00'), quotes: v3('post'), daily, earnings });
check(!o.errors.length, 'no JS errors', o.errors);
check(/ד׳ 21\.10/.test(o.decide.body) && /ג׳ 20\.10/.test(o.decide.body), 'header shows Israel Wed 21.10 and New York Tue 20.10', '');
check(/לפני הסגירה של ג׳ 20\.10/.test(o.decide.body), 'the morning analysis is stamped as written before the 20.10 close');
check(!/לא לפעול/.test(o.day['day-CLF'].todo), 'the 20.10 plan is not called stale on the evening of 20.10 NY');

await browser.close();
console.log(fails ? `${fails} check(s) failed` : 'all session checks passed');
process.exit(fails ? 1 : 0);
