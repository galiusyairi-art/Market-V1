// Finnhub market-data connector for Claude (remote MCP server on Cloudflare Workers).
//
// Endpoint:  https://<worker>.workers.dev/mcp/<ACCESS_TOKEN>
// Secrets (Cloudflare → Worker → Settings → Variables and Secrets):
//   FINNHUB_KEY   your Finnhub API key
//   ACCESS_TOKEN  a long random string; only URLs that contain it are answered
//
// Tools return plain row objects ({rows: [...]}) so the TradePilot dashboard can read them as tables.
//
// Quotes are session-aware. Finnhub's free /quote only knows the regular session: before 09:30 New York it still
// returns yesterday's close and yesterday's % change. So get_quotes reads Yahoo Finance's 1-minute chart (which has
// pre-market and after-hours trades) as the primary source, cross-checks it against Finnhub, and falls back to
// Finnhub alone (clearly labelled, with no extended-hours numbers) only when Yahoo can't be reached.

const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];
const FINNHUB = "https://finnhub.io/api/v1";

const TOOLS = [
  {
    name: "get_quotes",
    description:
      "Session-aware quotes for US stocks/ETFs (max 30). Each row says which session the market is in (pre / regular / post / closed) " +
      "and which session the price comes from. price = latest trade in any session; change_pct = price vs the previous regular close " +
      "(null when there has been no trade yet today); day_change_pct = regular-session change; ext_price / ext_change_pct = pre-market " +
      "or after-hours trade vs its reference close; high/low/open = today's regular session only (null before 09:30); pm_high/pm_low = " +
      "pre-market range; or_high/or_low = first 5 minutes of the regular session (after 09:35); vwap = regular-session VWAP. Primary source Yahoo Finance (includes extended hours), cross-checked with Finnhub; `check` is 'ok', 'mismatch' " +
      "(sources disagree, see alt_price) or null (not checked).",
    inputSchema: {
      type: "object",
      properties: { symbols: { type: "string", description: "Comma-separated tickers, e.g. \"AAPL,NVDA,SPY\" (max 30)" } },
      required: ["symbols"],
    },
  },
  {
    name: "get_daily",
    description:
      "Daily statistics from one year of completed sessions (today's bar is left out until the close), per symbol (max 40, " +
      "indices like ^VIX/^TNX allowed): last completed close and its date, previous day high/low, SMA 20/50/150/200, ATR(14), " +
      "average volume (20d), 52-week high/low, 20-day high/low, reference closes for week/month/year-to-date changes, 5d/20d % change, " +
      "RSI(14), and the trend-template score (0-7: price above 150/200-day, 150 above 200, 200-day rising, 50 above 150 and 200, " +
      "price above 50-day, 30% above the 52-week low, within 25% of the 52-week high). Source: Yahoo Finance.",
    inputSchema: {
      type: "object",
      properties: { symbols: { type: "string", description: "Comma-separated tickers, e.g. \"SPY,QQQ,^VIX,NVDA\" (max 40)" } },
      required: ["symbols"],
    },
  },
  {
    name: "get_company_news",
    description: "Recent company news headlines for one ticker.",
    inputSchema: {
      type: "object",
      properties: {
        symbol: { type: "string" },
        days: { type: "number", description: "How many days back (default 3, max 14)" },
        limit: { type: "number", description: "Max headlines (default 10, max 30)" },
      },
      required: ["symbol"],
    },
  },
  {
    name: "get_earnings_calendar",
    description: "Upcoming earnings dates. Optionally filter to a comma-separated list of tickers.",
    inputSchema: {
      type: "object",
      properties: {
        symbols: { type: "string", description: "Optional comma-separated tickers" },
        days: { type: "number", description: "How many days ahead (default 21, max 60)" },
      },
    },
  },
  {
    name: "get_market_status",
    description: "Whether the US market is open now, and the current session (pre-market, regular, post-market).",
    inputSchema: { type: "object", properties: {} },
  },
];

const ymd = (d) => d.toISOString().slice(0, 10);
const nyTime = (unix) =>
  unix ? new Date(unix * 1000).toLocaleString("sv-SE", { timeZone: "America/New_York" }).replace(" ", "T") : null;
const clamp = (v, lo, hi, dflt) => {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : dflt;
};
// plain tickers, Yahoo indices (^VIX, ^TNX) and futures (ES=F)
const tickers = (s, max = 30) =>
  [...new Set(String(s || "").toUpperCase().split(/[\s,]+/).filter((t) => /^\^?[A-Z][A-Z0-9.\-]{0,9}(=F)?$/.test(t)))].slice(0, max);
const yahooOnly = (s) => s.startsWith("^") || s.endsWith("=F");

async function finnhub(env, path, params) {
  const url = new URL(FINNHUB + path);
  for (const [k, v] of Object.entries(params || {})) if (v != null && v !== "") url.searchParams.set(k, v);
  url.searchParams.set("token", env.FINNHUB_KEY);
  const r = await fetch(url.toString(), { headers: { accept: "application/json" } });
  if (r.status === 429) throw new Error("Finnhub rate limit reached (free plan: about 60 calls a minute). Try again in a minute.");
  if (r.status === 401 || r.status === 403) throw new Error("Finnhub rejected the API key (check the FINNHUB_KEY secret).");
  if (!r.ok) throw new Error(`Finnhub error ${r.status}`);
  return r.json();
}

// ---------- session-aware quotes ----------
// Cloudflare's free plan allows 50 outbound requests per invocation; keep a margin.
const SUBREQUEST_BUDGET = 46;
const YAHOO = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"];
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";
const MISMATCH_PCT = 0.75; // sources further apart than this are flagged

const r2 = (v) => (v == null || !Number.isFinite(v) ? null : Math.round(v * 10000) / 10000);
const pct = (a, b) => (a == null || b == null || !b ? null : Math.round((a / b - 1) * 1e6) / 1e4);
const nyDate = (unix) => new Date(unix * 1000).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
const nyMinutes = (unix) => {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date(unix * 1000)).map((x) => [x.type, x.value]),
  );
  return +p.hour * 60 + +p.minute;
};
const isWeekend = (unix) => ["Sat", "Sun"].includes(new Date(unix * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short" }));
// Session by the New York clock (used when Yahoo, which reports its own trading periods, is unavailable).
const clockSession = (unix, holiday) => {
  if (holiday || isWeekend(unix)) return "closed";
  const m = nyMinutes(unix);
  return m >= 240 && m < 570 ? "pre" : m >= 570 && m < 960 ? "regular" : m >= 960 && m < 1200 ? "post" : "closed";
};

function makeBudget(n) {
  return { left: n, take() { if (this.left <= 0) return false; this.left -= 1; return true; } };
}

async function yahooChart(host, symbol) {
  const url = `${host}/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1m&range=1d&includePrePost=true`;
  const r = await fetch(url, { headers: { "user-agent": UA, accept: "application/json" } });
  let j = null;
  try { j = await r.json(); } catch { /* not JSON */ }
  const res = j && j.chart && j.chart.result && j.chart.result[0];
  if (r.ok && res && res.meta) return res;
  const desc = j && j.chart && j.chart.error && (j.chart.error.description || j.chart.error.code);
  const e = new Error(desc ? `Yahoo: ${desc}` : `Yahoo HTTP ${r.status}`);
  e.unknown = r.status === 404 || /no data found|delisted/i.test(desc || "");
  throw e;
}

// One Yahoo chart -> one session-aware row.
function fromYahoo(symbol, res, nowUnix) {
  const m = res.meta;
  const P = m.currentTradingPeriod || {};
  const pre = P.pre || {}, reg = P.regular || {}, post = P.post || {};
  const ts = res.timestamp || [];
  const q = (res.indicators && res.indicators.quote && res.indicators.quote[0]) || {};
  const bars = ts
    .map((t, i) => ({ t, h: q.high && q.high[i], l: q.low && q.low[i], c: q.close && q.close[i], v: (q.volume && q.volume[i]) || 0 }))
    .filter((b) => b.c != null && Number.isFinite(b.c));
  const inP = (b, p) => p.start != null && b.t >= p.start && b.t < p.end;
  const preBars = bars.filter((b) => inP(b, pre));
  const postBars = bars.filter((b) => inP(b, post));
  const hi = (bs) => (bs.length ? Math.max(...bs.map((b) => b.h ?? b.c)) : null);
  const lo = (bs) => (bs.length ? Math.min(...bs.map((b) => b.l ?? b.c)) : null);

  const session = !reg.start ? clockSession(nowUnix)
    : nowUnix < pre.start ? "closed" : nowUnix < reg.start ? "pre" : nowUnix < reg.end ? "regular" : nowUnix < post.end ? "post" : "closed";
  const tradeDate = reg.start ? nyDate(reg.start) : null;
  const regToday = m.regularMarketTime != null && reg.start != null && m.regularMarketTime >= reg.start;
  // reference close: before today's first regular trade it is the last regular price itself
  const prev = regToday ? (m.previousClose ?? m.chartPreviousClose ?? null) : (m.regularMarketPrice ?? m.previousClose ?? m.chartPreviousClose ?? null);
  const regPrice = regToday ? m.regularMarketPrice : null;
  const regBars = bars.filter((b) => inP(b, reg));
  const orBars = reg.start != null ? regBars.filter((b) => b.t < reg.start + 300) : []; // first 5 minutes
  const vSum = regBars.reduce((a, b) => a + b.v, 0);
  const vwap = vSum > 0 ? regBars.reduce((a, b) => a + ((b.h ?? b.c) + (b.l ?? b.c) + b.c) / 3 * b.v, 0) / vSum : null;

  // extended-hours trade that matters now: pre-market before the open, after-hours once the regular session is over
  let ext = null, extSession = null, extRef = null;
  if (!regToday && preBars.length) { ext = preBars[preBars.length - 1]; extSession = "pre"; extRef = prev; }
  else if (regToday && session !== "regular" && postBars.length) { ext = postBars[postBars.length - 1]; extSession = "post"; extRef = regPrice; }

  const price = ext ? ext.c : regPrice ?? prev;
  const priceSession = ext ? extSession : regPrice != null ? "regular" : "prev_close";
  const priceUnix = ext ? ext.t : regPrice != null ? m.regularMarketTime : null;
  return {
    symbol,
    session,
    trade_date: tradeDate,
    price: r2(price),
    price_session: priceSession,
    time_ny: priceUnix ? nyTime(priceUnix) : null,
    change: price != null && prev != null && priceSession !== "prev_close" ? r2(price - prev) : null,
    change_pct: priceSession !== "prev_close" ? pct(price, prev) : null,
    prev_close: r2(prev),
    reg_price: r2(regPrice),
    day_change_pct: regPrice != null ? pct(regPrice, prev) : null,
    open: regToday ? r2(m.regularMarketOpen ?? (regBars[0] && regBars[0].c) ?? null) : null,
    high: regToday ? r2(m.regularMarketDayHigh ?? hi(regBars)) : null,
    low: regToday ? r2(m.regularMarketDayLow ?? lo(regBars)) : null,
    volume: regToday ? (m.regularMarketVolume ?? null) : null,
    or_high: regToday && orBars.length && nowUnix >= reg.start + 300 ? r2(hi(orBars)) : null,
    or_low: regToday && orBars.length && nowUnix >= reg.start + 300 ? r2(lo(orBars)) : null,
    vwap: regToday ? r2(vwap) : null,
    ext_session: extSession,
    ext_price: ext ? r2(ext.c) : null,
    ext_change_pct: ext ? pct(ext.c, extRef) : null,
    ext_time_ny: ext ? nyTime(ext.t) : null,
    pm_high: r2(hi(preBars)),
    pm_low: r2(lo(preBars)),
    pm_volume: preBars.length ? preBars.reduce((s, b) => s + b.v, 0) : null,
    ah_high: r2(hi(postBars)),
    ah_low: r2(lo(postBars)),
    source: "yahoo",
    check: null,
    alt_price: null,
    error: null,
  };
}

// Finnhub alone (fallback): regular session only, so nothing about pre-market / after-hours.
function fromFinnhub(symbol, q, nowUnix, marketSession) {
  const session = marketSession || clockSession(nowUnix);
  const today = nyDate(nowUnix);
  const isToday = q.t && nyDate(q.t) === today && nyMinutes(q.t) >= 570;
  const base = {
    symbol, session, trade_date: q.t ? nyDate(q.t) : null, source: "finnhub", check: null, alt_price: null,
    ext_session: null, ext_price: null, ext_change_pct: null, ext_time_ny: null, pm_high: null, pm_low: null, pm_volume: null, ah_high: null, ah_low: null,
    or_high: null, or_low: null, vwap: null, volume: null, error: null,
  };
  if (isToday) {
    return { ...base, price: q.c, price_session: "regular", time_ny: nyTime(q.t), change: q.d, change_pct: q.dp, prev_close: q.pc,
      reg_price: q.c, day_change_pct: q.dp, open: q.o, high: q.h, low: q.l,
      note: session === "post" ? "no after-hours data (Finnhub fallback)" : null };
  }
  // the quote is from an earlier session: its close is today's reference, and today's move is unknown
  return { ...base, price: q.c, price_session: "prev_close", time_ny: nyTime(q.t), change: null, change_pct: null, prev_close: q.c,
    reg_price: null, day_change_pct: null, open: null, high: null, low: null,
    last_session_change_pct: q.dp, note: session === "pre" ? "no pre-market data (Finnhub fallback): price is the last regular close" : "last regular close" };
}

const emptyRow = (symbol, error) => ({
  symbol, session: null, trade_date: null, price: null, price_session: null, time_ny: null, change: null, change_pct: null, prev_close: null,
  reg_price: null, day_change_pct: null, open: null, high: null, low: null, volume: null, ext_session: null, ext_price: null, ext_change_pct: null,
  ext_time_ny: null, pm_high: null, pm_low: null, pm_volume: null, ah_high: null, ah_low: null, or_high: null, or_low: null, vwap: null,
  source: null, check: null, alt_price: null, error,
});

async function finnhubQuote(env, symbol) {
  const q = await finnhub(env, "/quote", { symbol });
  if (!q || (q.c === 0 && q.pc === 0)) { const e = new Error("unknown symbol"); e.unknown = true; throw e; }
  return q;
}

async function sessionQuotes(env, list) {
  const budget = makeBudget(SUBREQUEST_BUDGET);
  const nowUnix = Math.floor(Date.now() / 1000);
  const out = new Map();
  const yahooErr = new Map();

  // 1. probe Yahoo with the first symbol, trying both hosts; then the rest in parallel on the host that answered
  let host = null;
  for (const h of YAHOO) {
    if (!budget.take()) break;
    try { out.set(list[0], fromYahoo(list[0], await yahooChart(h, list[0]), nowUnix)); host = h; break; }
    catch (e) { yahooErr.set(list[0], e); if (e.unknown) { host = h; break; } }
  }
  if (host) {
    await Promise.all(list.slice(1).map(async (s) => {
      if (!budget.take()) return;
      try { out.set(s, fromYahoo(s, await yahooChart(host, s), nowUnix)); } catch (e) { yahooErr.set(s, e); }
    }));
  }

  // 2. Finnhub: fallback for symbols Yahoo missed, then a cross-check for the rest (cards first: the list ends with them)
  let marketSession = null;
  const missing = list.filter((s) => !out.has(s));
  if (missing.length && budget.take()) {
    try { const st = await finnhub(env, "/stock/market-status", { exchange: "US" }); marketSession = st.holiday ? "closed" : st.session === "post-market" ? "post" : st.session === "pre-market" ? "pre" : st.session === "regular" ? "regular" : st.isOpen ? "regular" : "closed"; }
    catch { /* clock fallback */ }
  }
  await Promise.all(missing.map(async (s) => {
    if (yahooOnly(s)) { out.set(s, emptyRow(s, `no quote (${(yahooErr.get(s) || {}).message || "Yahoo unavailable"})`)); return; }
    if (!budget.take()) { out.set(s, emptyRow(s, "too many symbols in one call")); return; }
    try { out.set(s, fromFinnhub(s, await finnhubQuote(env, s), nowUnix, marketSession)); }
    catch (e) { out.set(s, emptyRow(s, e.unknown ? "unknown symbol" : `no quote (${[(yahooErr.get(s) || {}).message, e.message].filter(Boolean).join("; ")})`)); }
  }));
  const toCheck = [...list].reverse().filter((s) => !yahooOnly(s) && out.get(s) && out.get(s).source === "yahoo");
  await Promise.all(toCheck.map(async (s) => {
    if (!budget.take()) return;
    const row = out.get(s);
    try {
      const q = await finnhubQuote(env, s);
      const fSame = q.t && nyDate(q.t) === row.trade_date && nyMinutes(q.t) >= 570; // Finnhub quote is from the same session
      // compare like with like: that session's regular price once it trades, otherwise the reference close
      const mine = row.reg_price != null ? row.reg_price : row.prev_close;
      const theirs = row.reg_price != null ? (fSame ? q.c : null) : (fSame ? q.pc : q.c);
      if (mine == null || theirs == null) return;
      row.alt_price = theirs;
      row.check = Math.abs(pct(mine, theirs)) > MISMATCH_PCT ? "mismatch" : "ok";
    } catch { /* leave unchecked */ }
  }));
  return list.map((s) => out.get(s) || emptyRow(s, "not fetched"));
}

// ---------- daily statistics ----------
async function yahooDaily(host, symbol) {
  const url = `${host}/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=1y`;
  const r = await fetch(url, { headers: { "user-agent": UA, accept: "application/json" } });
  let j = null;
  try { j = await r.json(); } catch { /* not JSON */ }
  const res = j && j.chart && j.chart.result && j.chart.result[0];
  if (r.ok && res && res.meta) return res;
  const desc = j && j.chart && j.chart.error && (j.chart.error.description || j.chart.error.code);
  const e = new Error(desc ? `Yahoo: ${desc}` : `Yahoo HTTP ${r.status}`);
  e.unknown = r.status === 404 || /no data found|delisted/i.test(desc || "");
  throw e;
}

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const smaAt = (closes, n, end = closes.length) => (end >= n ? mean(closes.slice(end - n, end)) : null);
const addDays = (ymdStr, d) => { const t = new Date(ymdStr + "T12:00:00Z"); t.setUTCDate(t.getUTCDate() + d); return t.toISOString().slice(0, 10); };

function fromDaily(symbol, res, nowUnix) {
  const m = res.meta;
  const reg = (m.currentTradingPeriod && m.currentTradingPeriod.regular) || {};
  const q = (res.indicators && res.indicators.quote && res.indicators.quote[0]) || {};
  const sessionDate = reg.start ? nyDate(reg.start) : nyDate(nowUnix);
  const sessionDone = reg.end ? nowUnix >= reg.end : true;
  // completed sessions only: today's bar is still forming until 16:00 New York
  const bars = (res.timestamp || [])
    .map((t, i) => ({ d: nyDate(t), o: q.open && q.open[i], h: q.high && q.high[i], l: q.low && q.low[i], c: q.close && q.close[i], v: (q.volume && q.volume[i]) || 0 }))
    .filter((b) => b.c != null && Number.isFinite(b.c) && b.h != null && b.l != null)
    .filter((b) => !(b.d >= sessionDate && !sessionDone));
  const n = bars.length;
  if (!n) return { ...emptyDaily(symbol), error: "no completed sessions" };
  const C = bars.map((b) => b.c), last = bars[n - 1];
  // the session these references belong to: today while it trades, the next one once it closed is not known, so use the session date
  const refDay = sessionDone ? addDays(last.d, 1) : sessionDate;
  const wd = new Date(refDay + "T12:00:00Z").getUTCDay(); // 0 Sunday
  const monday = addDays(refDay, -((wd + 6) % 7));
  const lastBefore = (day) => { for (let i = n - 1; i >= 0; i--) if (bars[i].d < day) return bars[i].c; return null; };
  const tr = bars.map((b, i) => (i ? Math.max(b.h - b.l, Math.abs(b.h - bars[i - 1].c), Math.abs(b.l - bars[i - 1].c)) : b.h - b.l));
  const atr = n >= 15 ? mean(tr.slice(n - 14)) : null;
  let rsi = null;
  if (n >= 15) { // Wilder RSI(14)
    let g = 0, l = 0;
    for (let i = 1; i <= 14; i++) { const d = C[i] - C[i - 1]; if (d > 0) g += d; else l -= d; }
    g /= 14; l /= 14;
    for (let i = 15; i < n; i++) { const d = C[i] - C[i - 1]; g = (g * 13 + Math.max(d, 0)) / 14; l = (l * 13 + Math.max(-d, 0)) / 14; }
    rsi = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  }
  const s50 = smaAt(C, 50), s150 = smaAt(C, 150), s200 = smaAt(C, 200), s200prev = smaAt(C, 200, n - 20);
  const hi52 = Math.max(...bars.map((b) => b.h)), lo52 = Math.min(...bars.map((b) => b.l));
  const last20 = bars.slice(-20);
  const c = last.c;
  const tt = s200 == null || s150 == null || s50 == null ? null : [
    c > s150 && c > s200, s150 > s200, s200prev != null && s200 > s200prev, s50 > s150 && s50 > s200, c > s50, c >= lo52 * 1.3, c >= hi52 * 0.75,
  ].filter(Boolean).length;
  const vols = bars.slice(-20).map((b) => b.v).filter((v) => v > 0);
  return {
    symbol, as_of: last.d, close: r2(c), prev_high: r2(last.h), prev_low: r2(last.l),
    sma20: r2(smaAt(C, 20)), sma50: r2(s50), sma150: r2(s150), sma200: r2(s200),
    atr14: r2(atr), atr_pct: atr != null ? Math.round((atr / c) * 1e4) / 100 : null,
    avg_vol20: vols.length ? Math.round(mean(vols)) : null,
    high_52w: r2(hi52), low_52w: r2(lo52), high_20d: r2(Math.max(...last20.map((b) => b.h))), low_20d: r2(Math.min(...last20.map((b) => b.l))),
    ref_week: r2(lastBefore(monday)), ref_month: r2(lastBefore(refDay.slice(0, 8) + "01")), ref_year: r2(lastBefore(refDay.slice(0, 5) + "01-01")),
    chg_5d: n > 5 ? pct(c, C[n - 6]) : null, chg_20d: n > 20 ? pct(c, C[n - 21]) : null,
    rsi14: rsi != null ? Math.round(rsi * 10) / 10 : null, trend_score: tt, trend_max: 7, bars: n, source: "yahoo", error: null,
  };
}
const emptyDaily = (symbol, error = null) => ({
  symbol, as_of: null, close: null, prev_high: null, prev_low: null, sma20: null, sma50: null, sma150: null, sma200: null, atr14: null, atr_pct: null,
  avg_vol20: null, high_52w: null, low_52w: null, high_20d: null, low_20d: null, ref_week: null, ref_month: null, ref_year: null, chg_5d: null,
  chg_20d: null, rsi14: null, trend_score: null, trend_max: 7, bars: 0, source: null, error,
});

async function dailyStats(list) {
  const budget = makeBudget(SUBREQUEST_BUDGET);
  const nowUnix = Math.floor(Date.now() / 1000);
  const out = new Map();
  let host = null, probeErr = null;
  for (const h of YAHOO) {
    if (!budget.take()) break;
    try { out.set(list[0], fromDaily(list[0], await yahooDaily(h, list[0]), nowUnix)); host = h; break; }
    catch (e) { probeErr = e; if (e.unknown) { out.set(list[0], emptyDaily(list[0], "unknown symbol")); host = h; break; } }
  }
  if (host) {
    await Promise.all(list.slice(1).map(async (s) => {
      if (!budget.take()) { out.set(s, emptyDaily(s, "too many symbols in one call")); return; }
      try { out.set(s, fromDaily(s, await yahooDaily(host, s), nowUnix)); }
      catch (e) { out.set(s, emptyDaily(s, e.unknown ? "unknown symbol" : e.message)); }
    }));
  }
  return list.map((s) => out.get(s) || emptyDaily(s, `no data (${probeErr ? probeErr.message : "Yahoo unavailable"})`));
}

const TOOL_IMPL = {
  async get_quotes(env, args) {
    const list = tickers(args.symbols);
    if (!list.length) throw new Error("Give at least one ticker in `symbols`.");
    return { rows: await sessionQuotes(env, list) };
  },

  async get_daily(env, args) {
    const list = tickers(args.symbols, 40);
    if (!list.length) throw new Error("Give at least one ticker in `symbols`.");
    return { rows: await dailyStats(list) };
  },

  async get_company_news(env, args) {
    const symbol = tickers(args.symbol, 1)[0];
    if (!symbol) throw new Error("Give a ticker in `symbol`.");
    const days = clamp(args.days, 1, 14, 3);
    const limit = clamp(args.limit, 1, 30, 10);
    const to = new Date();
    const from = new Date(to.getTime() - days * 864e5);
    const items = await finnhub(env, "/company-news", { symbol, from: ymd(from), to: ymd(to) });
    const rows = (Array.isArray(items) ? items : []).slice(0, limit).map((n) => ({
      symbol, time_ny: nyTime(n.datetime), headline: n.headline, source: n.source, summary: (n.summary || "").slice(0, 400), url: n.url,
    }));
    return { rows };
  },

  async get_earnings_calendar(env, args) {
    const days = clamp(args.days, 1, 60, 21);
    const from = new Date();
    const to = new Date(from.getTime() + days * 864e5);
    const only = tickers(args.symbols, 100);
    const fetchOne = (symbol) => finnhub(env, "/calendar/earnings", { from: ymd(from), to: ymd(to), symbol });
    const parts = only.length ? await Promise.all(only.map(fetchOne)) : [await fetchOne(undefined)];
    const rows = parts
      .flatMap((p) => (p && p.earningsCalendar) || [])
      .map((e) => ({ symbol: e.symbol, date: e.date, hour: e.hour || null, eps_estimate: e.epsEstimate ?? null, revenue_estimate: e.revenueEstimate ?? null }))
      .sort((a, b) => a.date.localeCompare(b.date));
    return { rows: only.length ? rows : rows.slice(0, 300) };
  },

  async get_market_status(env) {
    const s = await finnhub(env, "/stock/market-status", { exchange: "US" });
    return { rows: [{ exchange: "US", is_open: !!s.isOpen, session: s.session || null, holiday: s.holiday || null, time_ny: nyTime(s.t) }] };
  },
};

function rpc(id, result) {
  return { jsonrpc: "2.0", id, result };
}
function rpcError(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

async function handleMessage(env, msg) {
  const { id, method, params } = msg || {};
  const isNotification = id === undefined || id === null;
  switch (method) {
    case "initialize": {
      const asked = params && params.protocolVersion;
      return rpc(id, {
        protocolVersion: PROTOCOLS.includes(asked) ? asked : PROTOCOLS[0],
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "finnhub-market-data", version: "3.0.0" },
        instructions: "US stock market data: session-aware quotes with pre-market and after-hours (Yahoo Finance, cross-checked with Finnhub), one-year daily statistics (get_daily), company news, earnings calendar, market status (Finnhub).",
      });
    }
    case "ping":
      return rpc(id, {});
    case "tools/list":
      return rpc(id, { tools: TOOLS });
    case "tools/call": {
      const name = params && params.name;
      const impl = TOOL_IMPL[name];
      if (!impl) return rpcError(id, -32602, `Unknown tool: ${name}`);
      try {
        const data = await impl(env, (params && params.arguments) || {});
        return rpc(id, { content: [{ type: "text", text: JSON.stringify(data) }], structuredContent: data, isError: false });
      } catch (e) {
        return rpc(id, { content: [{ type: "text", text: String(e.message || e) }], isError: true });
      }
    }
    default:
      if (isNotification) return null; // e.g. notifications/initialized
      return rpcError(id, -32601, `Method not found: ${method}`);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] !== "mcp") return new Response("Not found", { status: 404 });
    if (!env.ACCESS_TOKEN || !env.FINNHUB_KEY) return new Response("Server not configured: set FINNHUB_KEY and ACCESS_TOKEN", { status: 500 });
    if (parts[1] !== env.ACCESS_TOKEN) return new Response("Not found", { status: 404 });

    if (request.method === "GET") return new Response("Method not allowed", { status: 405, headers: { allow: "POST" } });
    if (request.method === "DELETE") return new Response(null, { status: 204 });
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

    let body;
    try {
      body = await request.json();
    } catch {
      return Response.json(rpcError(null, -32700, "Parse error"), { status: 400 });
    }
    const batch = Array.isArray(body);
    const replies = (await Promise.all((batch ? body : [body]).map((m) => handleMessage(env, m)))).filter(Boolean);
    if (!replies.length) return new Response(null, { status: 202 });
    return Response.json(batch ? replies : replies[0], { headers: { "cache-control": "no-store" } });
  },
};
