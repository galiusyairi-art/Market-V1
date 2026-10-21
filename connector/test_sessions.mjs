// Session-aware quote tests: Yahoo (pre/regular/post) + Finnhub cross-check and fallback, with a fixed clock.
const { default: worker } = await import(process.env.W || "./finnhub-worker.js");
const env = { FINNHUB_KEY: 'k', ACCESS_TOKEN: 'tok' };
const assert = (c, m, extra) => { if (!c) { console.error('FAIL', m, extra === undefined ? '' : JSON.stringify(extra, null, 1)); process.exit(1); } };
const near = (a, b, eps = 0.011) => a != null && Math.abs(a - b) <= eps;

// 2026-10-20 (EDT = UTC-4): pre 04:00, regular 09:30-16:00, post until 20:00
const T = (hhmm, day = '2026-10-20') => Date.parse(`${day}T${hhmm}:00-04:00`) / 1000;
const period = (day) => ({ pre: { start: T('04:00', day), end: T('09:30', day) }, regular: { start: T('09:30', day), end: T('16:00', day) }, post: { start: T('16:00', day), end: T('20:00', day) } });

let yahoo = {};        // symbol -> chart result | 'down' | 'unknown'
let yahooD = {};       // symbol -> daily chart result
let fin = {};          // symbol -> finnhub quote
let finStatus = { isOpen: false, session: 'pre-market', holiday: null, t: 0 };
let calls = [];
globalThis.fetch = async (u) => {
  calls.push(String(u));
  const url = new URL(u);
  const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'content-type': 'application/json' } });
  if (url.hostname.endsWith('yahoo.com')) {
    const s = decodeURIComponent(url.pathname.split('/').pop());
    const y = url.searchParams.get('interval') === '1d' ? (yahooD[s] ?? (yahoo.__down ? 'down' : undefined)) : yahoo[s];
    if (y === 'down' || yahoo.__down) return new Response('blocked', { status: 403 });
    if (!y || y === 'unknown') return json({ chart: { result: null, error: { code: 'Not Found', description: 'No data found, symbol may be delisted' } } }, 404);
    return json({ chart: { result: [y], error: null } });
  }
  if (url.pathname.endsWith('/quote')) {
    const q = fin[url.searchParams.get('symbol')];
    return json(q || { c: 0, d: null, dp: null, h: 0, l: 0, o: 0, pc: 0, t: 0 });
  }
  if (url.pathname.endsWith('/stock/market-status')) return json(finStatus);
  return json({}, 404);
};
const realNow = Date.now;
const at = (unix) => { Date.now = () => unix * 1000; };

// build a Yahoo chart result
function chart({ day = '2026-10-20', regPrice, regTime, prevClose, open, high, low, vol, bars = [] }) {
  return {
    meta: { regularMarketPrice: regPrice, regularMarketTime: regTime, previousClose: prevClose, chartPreviousClose: prevClose,
      regularMarketDayHigh: high, regularMarketDayLow: low, regularMarketOpen: open, regularMarketVolume: vol, currentTradingPeriod: period(day) },
    timestamp: bars.map((b) => b[0]),
    indicators: { quote: [{ open: bars.map((b) => b[1]), high: bars.map((b) => b[2]), low: bars.map((b) => b[3]), close: bars.map((b) => b[4]), volume: bars.map((b) => b[5] ?? 100) }] },
  };
}
async function quotes(symbols) {
  calls = [];
  const r = await worker.fetch(new Request('https://w.dev/mcp/tok', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_quotes', arguments: { symbols } } }) }), env);
  const j = await r.json();
  assert(!j.result.isError, 'tool error', j);
  return j.result.structuredContent.rows;
}
const yClose = T('16:00', '2026-10-19');
const finYesterday = { c: 14.1, d: 1.98, dp: 16.3366, h: 14.58, l: 12.9403, o: 14.2, pc: 12.12, t: yClose };

// A. pre-market 07:39 — the CLF case: Finnhub says +16.34% (yesterday), the real pre-market move is -1.99%
at(T('07:39'));
yahoo = { CLF: chart({ regPrice: 14.1, regTime: yClose, prevClose: 12.12, bars: [[T('04:01'), 14.0, 14.05, 13.9, 13.95], [T('07:12'), 13.9, 13.98, 13.7, 13.75], [T('07:38'), 13.8, 13.84, 13.79, 13.8194]] }) };
fin = { CLF: finYesterday };
let [r] = await quotes('CLF');
assert(r.session === 'pre' && r.price_session === 'pre', 'A session', r);
assert(near(r.price, 13.8194, 1e-4) && near(r.change_pct, -1.99, 0.005), 'A pre-market price and change vs yesterday close', r);
assert(r.prev_close === 14.1 && r.high === null && r.low === null && r.open === null, 'A: no regular range before the open', r);
assert(r.pm_high === 14.05 && r.pm_low === 13.7 && r.ext_session === 'pre', 'A pre-market range', r);
assert(r.check === 'ok' && r.alt_price === 14.1 && r.source === 'yahoo', 'A cross-check of the reference close', r);
assert(r.time_ny === '2026-10-20T07:38:00', 'A time', r);
console.log('A pre-market CLF:', r.price, r.change_pct + '%', '(Finnhub alone would say +16.34%)');

// B. pre-market, no trades yet: price is the last close, change unknown (null, not 0)
yahoo = { CLF: chart({ regPrice: 14.1, regTime: yClose, prevClose: 12.12, bars: [] }) };
[r] = await quotes('CLF');
assert(r.session === 'pre' && r.price_session === 'prev_close' && r.price === 14.1 && r.change_pct === null && r.change === null, 'B no pre-market trades', r);

// C. regular session 11:00
at(T('11:00'));
yahoo = { CLF: chart({ regPrice: 14.5, regTime: T('10:59'), prevClose: 14.1, open: 13.9, high: 14.62, low: 13.71, vol: 9e6, bars: [[T('07:00'), 13.8, 13.85, 13.75, 13.8], [T('09:30'), 13.9, 14, 13.71, 13.95], [T('10:59'), 14.4, 14.62, 14.4, 14.5]] }) };
fin = { CLF: { c: 14.49, d: 0.39, dp: 2.77, h: 14.62, l: 13.71, o: 13.9, pc: 14.1, t: T('10:59') } };
[r] = await quotes('CLF');
assert(r.session === 'regular' && r.price_session === 'regular' && r.price === 14.5 && near(r.change_pct, 2.84, 0.01), 'C regular', r);
assert(r.high === 14.62 && r.low === 13.71 && r.open === 13.9 && r.ext_price === null && r.pm_high === 13.85, 'C regular range + pre range kept', r);
assert(r.check === 'ok', 'C check ok', r);
fin.CLF.c = 15.2; [r] = await quotes('CLF');
assert(r.check === 'mismatch' && r.alt_price === 15.2, 'C mismatch flagged', r);

// D. after-hours 17:10: regular close 14.30, after-hours 14.00
at(T('17:10'));
yahoo = { CLF: chart({ regPrice: 14.3, regTime: T('16:00'), prevClose: 14.1, open: 13.9, high: 14.62, low: 13.71, bars: [[T('15:59'), 14.3, 14.31, 14.28, 14.3], [T('16:30'), 14.2, 14.2, 14.1, 14.1], [T('17:09'), 14.05, 14.06, 13.98, 14.0]] }) };
fin = { CLF: { c: 14.3, d: 0.2, dp: 1.4184, h: 14.62, l: 13.71, o: 13.9, pc: 14.1, t: T('16:00') } };
[r] = await quotes('CLF');
assert(r.session === 'post' && r.price_session === 'post' && r.price === 14 && r.reg_price === 14.3, 'D post', r);
assert(near(r.day_change_pct, 1.42) && near(r.ext_change_pct, -2.1, 0.01) && near(r.change_pct, -0.71, 0.01), 'D post changes', r);
assert(r.high === 14.62 && r.ah_low === 13.98 && r.check === 'ok', 'D ranges + check', r);

// E. Saturday: last session is Friday 16.10, after-hours included
at(T('12:00', '2026-10-24'));
const fri = '2026-10-23';
yahoo = { CLF: chart({ day: fri, regPrice: 14.3, regTime: T('16:00', fri), prevClose: 14.1, open: 13.9, high: 14.62, low: 13.71, bars: [[T('17:09', fri), 14.05, 14.06, 13.98, 14.0]] }) };
fin = { CLF: { c: 14.3, d: 0.2, dp: 1.4184, h: 14.62, l: 13.71, o: 13.9, pc: 14.1, t: T('16:00', fri) } };
[r] = await quotes('CLF');
assert(r.session === 'closed' && r.trade_date === fri && r.price === 14 && r.price_session === 'post' && r.high === 14.62, 'E weekend', r);
assert(r.check === 'ok', 'E check compares Friday close', r);

// F. Yahoo blocked, pre-market: Finnhub fallback must NOT present yesterday's +16.34% as today's move
at(T('07:39'));
yahoo = { __down: true };
fin = { CLF: finYesterday, SPY: { c: 766.48, d: 3.23, dp: 0.4232, h: 770.46, l: 765.82, o: 767.23, pc: 763.25, t: yClose } };
finStatus = { isOpen: false, session: 'pre-market', holiday: null, t: T('07:39') };
let rows = await quotes('SPY,CLF');
r = rows[1];
assert(r.source === 'finnhub' && r.session === 'pre' && r.price_session === 'prev_close' && r.price === 14.1, 'F fallback row', r);
assert(r.change_pct === null && r.high === null && r.last_session_change_pct === 16.3366 && /no pre-market/.test(r.note), 'F no fake move', r);
assert(calls.filter((c) => c.includes('yahoo')).length === 2, 'F only the probe hits Yahoo when it is down', calls);

// G. Yahoo blocked, regular session: Finnhub regular row with today's numbers
at(T('11:00'));
finStatus = { isOpen: true, session: 'regular', holiday: null, t: T('11:00') };
fin = { CLF: { c: 14.49, d: 0.39, dp: 2.77, h: 14.62, l: 13.71, o: 13.9, pc: 14.1, t: T('10:59') } };
[r] = await quotes('CLF');
assert(r.source === 'finnhub' && r.price_session === 'regular' && r.change_pct === 2.77 && r.high === 14.62, 'G fallback regular', r);

// H. 30 symbols stay under Cloudflare's 50-subrequest limit, Yahoo up or down
const syms = Array.from({ length: 30 }, (_, i) => 'S' + String.fromCharCode(65 + (i % 26)) + (i >= 26 ? 'X' : ''));
yahoo = Object.fromEntries(syms.map((s) => [s, chart({ regPrice: 10, regTime: T('10:59'), prevClose: 9.5, open: 9.6, high: 10.2, low: 9.4, bars: [[T('10:59'), 10, 10, 10, 10]] })]));
fin = Object.fromEntries(syms.map((s) => [s, { c: 10, d: 0.5, dp: 5.26, h: 10.2, l: 9.4, o: 9.6, pc: 9.5, t: T('10:59') }]));
rows = await quotes(syms.join(','));
assert(rows.length === 30 && rows.every((x) => x.price === 10 && x.source === 'yahoo') && calls.length <= 46, 'H 30 via Yahoo', calls.length);
assert(rows[29].check === 'ok' && rows.filter((x) => x.check).length === 12, 'H cross-check: 12 at most, the end of the list (cards) first', rows.map((x) => x.check));
yahoo.__down = true;
rows = await quotes(syms.join(','));
assert(rows.every((x) => x.price === 10 && x.source === 'finnhub') && calls.length <= 46, 'H 30 via Finnhub fallback', calls.length);
delete yahoo.__down;

// I. unknown symbol
yahoo = {}; fin = {};
[r] = await quotes('ZZZZ');
assert(r.error === 'unknown symbol' && r.price === null, 'I unknown', r);

// J. opening range (first 5 minutes) and VWAP during the regular session
at(T('11:00'));
yahoo = { CLF: chart({ regPrice: 14.5, regTime: T('10:59'), prevClose: 14.1, open: 13.9, high: 14.62, low: 13.71, bars: [
  [T('09:30'), 13.9, 14.0, 13.85, 13.95, 1000], [T('09:32'), 13.95, 14.05, 13.8, 14.0, 1000], [T('09:34'), 14.0, 14.02, 13.9, 13.92, 1000], [T('09:35'), 13.9, 14.3, 13.9, 14.25, 1000], [T('10:59'), 14.4, 14.62, 14.4, 14.5, 2000]] }) };
fin = { CLF: { c: 14.5, d: 0.4, dp: 2.84, h: 14.62, l: 13.71, o: 13.9, pc: 14.1, t: T('10:59') } };
[r] = await quotes('CLF');
assert(r.or_high === 14.05 && r.or_low === 13.8, 'J opening range = first 5 minutes only', r);
const tp = (h, l, c) => (h + l + c) / 3;
const vw = (tp(14, 13.85, 13.95) + tp(14.05, 13.8, 14) + tp(14.02, 13.9, 13.92) + tp(14.3, 13.9, 14.25) + 2 * tp(14.62, 14.4, 14.5)) * 1000 / 6000;
assert(near(r.vwap, vw, 1e-3), 'J VWAP', [r.vwap, vw]);
at(T('09:33')); [r] = await quotes('CLF');
assert(r.or_high === null, 'J no opening range before 09:35', r);

// K. get_daily: one year of synthetic sessions, today's forming bar excluded
function dailyChart(days, todayBar, regDay = '2026-10-20') {
  const ts = [], o = [], h = [], l = [], c = [], v = [];
  days.forEach((d) => { ts.push(T('09:30', d.d)); o.push(d.c); h.push(d.h ?? d.c + 1); l.push(d.l ?? d.c - 1); c.push(d.c); v.push(d.v ?? 1e6); });
  if (todayBar) { ts.push(T('09:30', regDay)); o.push(todayBar); h.push(todayBar + 50); l.push(todayBar - 50); c.push(todayBar); v.push(5e6); }
  return { meta: { currentTradingPeriod: period(regDay) }, timestamp: ts, indicators: { quote: [{ open: o, high: h, low: l, close: c, volume: v }] } };
}
// 252 weekdays ending Mon 2026-10-19, closes rising 1 per day from 100
const days = []; { let d = new Date('2026-10-19T12:00:00Z'); const tmp = []; while (tmp.length < 252) { const w = d.getUTCDay(); if (w && w < 6) tmp.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() - 1); } tmp.reverse().forEach((dd, i) => days.push({ d: dd, c: 100 + i })); }
yahooD = { NVDA: dailyChart(days, 999), '^VIX': dailyChart(days.map((x) => ({ ...x, c: 20, h: 21, l: 19 }))) };
yahoo = {};
const daily = async (symbols) => {
  const res = await worker.fetch(new Request('https://w.dev/mcp/tok', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_daily', arguments: { symbols } } }) }), env);
  const j = await res.json(); assert(!j.result.isError, 'daily tool error', j); return j.result.structuredContent.rows;
};
at(T('11:00'));
let [dn, dv] = await daily('NVDA,^vix');
assert(dn.as_of === '2026-10-19' && dn.close === 351 && dn.bars === 252, 'K today\'s forming bar is excluded', dn);
assert(dn.sma20 === 341.5 && dn.sma50 === 326.5 && dn.sma200 === 251.5 && dn.atr14 === 2 && dn.prev_high === 352, 'K SMA / ATR / prev high', dn);
assert(dn.ref_week === 350 && dn.ref_month === 338 && dn.ref_year === 143, 'K week ref = Fri 16.10 close, month ref = 30.9 close, year ref = 31.12', dn);   // 16.10 is index 250, 30.9 index 238, 31.12.2025 index 43
assert(dn.trend_score === 7 && dn.chg_5d === pct5(dn) && dn.rsi14 === 100, 'K trend template + RSI', dn);
assert(dv.symbol === '^VIX' && dv.close === 20 && dv.atr14 === 2, 'K ^VIX accepted', dv);
at(T('17:00'));
yahooD.NVDA = dailyChart(days, 999);
[dn] = await daily('NVDA');
assert(dn.as_of === '2026-10-20' && dn.close === 999 && dn.ref_week === 350, 'K after the close today counts as completed; week ref still last Friday', dn);
at(T('12:00', '2026-10-24'));
yahooD.NVDA = dailyChart(days.concat([{ d: '2026-10-20', c: 352 }, { d: '2026-10-21', c: 353 }, { d: '2026-10-22', c: 354 }, { d: '2026-10-23', c: 355 }]), null, '2026-10-23');
[dn] = await daily('NVDA');
assert(dn.as_of === '2026-10-23' && dn.ref_week === 350, 'K weekend: week-to-date is the week that just ended (ref = previous Friday)', dn);
yahooD = {}; yahoo = { __down: true };
[dn] = await daily('NVDA');
assert(dn.close === null && /Yahoo/.test(dn.error), 'K Yahoo down -> explicit error row', dn);
delete yahoo.__down;
function pct5(r) { return Math.round((351 / 346 - 1) * 1e6) / 1e4; }

Date.now = realNow;
console.log('all session tests passed');
