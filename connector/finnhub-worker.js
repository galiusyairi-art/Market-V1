// Finnhub market-data connector for Claude (remote MCP server on Cloudflare Workers).
//
// Endpoint:  https://<worker>.workers.dev/mcp/<ACCESS_TOKEN>
// Secrets (Cloudflare → Worker → Settings → Variables and Secrets):
//   FINNHUB_KEY   your Finnhub API key
//   ACCESS_TOKEN  a long random string; only URLs that contain it are answered
//
// Tools return plain row objects ({rows: [...]}) so the Market Cockpit dashboard can read them as tables.

const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];
const FINNHUB = "https://finnhub.io/api/v1";

const TOOLS = [
  {
    name: "get_quotes",
    description: "Real-time quotes for US stocks/ETFs: price, change, % change, day high/low/open, previous close, quote time (New York).",
    inputSchema: {
      type: "object",
      properties: { symbols: { type: "string", description: "Comma-separated tickers, e.g. \"AAPL,NVDA,SPY\" (max 30)" } },
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
const tickers = (s, max = 30) =>
  [...new Set(String(s || "").toUpperCase().split(/[\s,]+/).filter((t) => /^[A-Z][A-Z0-9.\-]{0,9}$/.test(t)))].slice(0, max);

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

const TOOL_IMPL = {
  async get_quotes(env, args) {
    const list = tickers(args.symbols);
    if (!list.length) throw new Error("Give at least one ticker in `symbols`.");
    const rows = await Promise.all(
      list.map(async (symbol) => {
        try {
          const q = await finnhub(env, "/quote", { symbol });
          if (!q || (q.c === 0 && q.pc === 0)) return { symbol, price: null, change: null, change_pct: null, high: null, low: null, open: null, prev_close: null, time_ny: null, error: "unknown symbol" };
          return { symbol, price: q.c, change: q.d, change_pct: q.dp, high: q.h, low: q.l, open: q.o, prev_close: q.pc, time_ny: nyTime(q.t), error: null };
        } catch (e) {
          return { symbol, price: null, change: null, change_pct: null, high: null, low: null, open: null, prev_close: null, time_ny: null, error: e.message };
        }
      }),
    );
    return { rows };
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
        serverInfo: { name: "finnhub-market-data", version: "1.0.0" },
        instructions: "US stock market data from Finnhub: real-time quotes, company news, earnings calendar, market status.",
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
