import worker from './finnhub-worker.js';
const env = { FINNHUB_KEY: 'k', ACCESS_TOKEN: 'tok' };
let calls = [];
globalThis.fetch = async (u) => {
  calls.push(u);
  const url = new URL(u);
  const p = url.pathname;
  const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'content-type': 'application/json' } });
  if (p.endsWith('/quote')) {
    const s = url.searchParams.get('symbol');
    if (s === 'ZZZZ') return json({ c: 0, d: null, dp: null, h: 0, l: 0, o: 0, pc: 0, t: 0 });
    return json({ c: 450.5, d: 63.38, dp: 16.37, h: 452, l: 440, o: 447, pc: 387.12, t: 1791560000 });
  }
  if (p.endsWith('/company-news')) return json([{ datetime: 1791550000, headline: 'H', source: 'Reuters', summary: 'S', url: 'https://x' }]);
  if (p.endsWith('/calendar/earnings')) return json({ earningsCalendar: [{ symbol: 'AMT', date: '2026-10-27', hour: 'bmo', epsEstimate: 2.5, revenueEstimate: 1e9 }] });
  if (p.endsWith('/stock/market-status')) return json({ isOpen: true, session: 'regular', holiday: null, t: 1791560000 });
  return json({}, 404);
};
const post = (path, body) => worker.fetch(new Request('https://w.dev' + path, { method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream' }, body: JSON.stringify(body) }), env);
const show = async (r) => { const t = await r.text(); let o = null; try { o = t ? JSON.parse(t) : null; } catch { o = t; } return [r.status, o]; };
const assert = (c, m) => { if (!c) { console.error('FAIL', m); process.exit(1); } };

let [st, j] = await show(await post('/mcp/wrong', { jsonrpc: '2.0', id: 1, method: 'initialize' }));
assert(st === 404, 'wrong token 404');
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'c', version: '1' } } }));
assert(st === 200 && j.result.protocolVersion === '2025-06-18' && j.result.capabilities.tools, 'initialize');
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', method: 'notifications/initialized' }));
assert(st === 202, 'notification 202');
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', id: 2, method: 'tools/list' }));
assert(j.result.tools.length === 4, 'tools/list');
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'get_quotes', arguments: { symbols: 'hum, lite,ZZZZ,bad$' } } }));
const rows = j.result.structuredContent.rows;
assert(rows.length === 3 && rows[0].symbol === 'HUM' && rows[0].price === 450.5 && rows[2].error === 'unknown symbol', 'quotes');
assert(JSON.parse(j.result.content[0].text).rows.length === 3, 'text content json');
console.log('quote row:', rows[0]);
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'get_company_news', arguments: { symbol: 'HUM' } } }));
assert(j.result.structuredContent.rows[0].headline === 'H', 'news');
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'get_earnings_calendar', arguments: { symbols: 'AMT' } } }));
assert(j.result.structuredContent.rows[0].date === '2026-10-27', 'earnings');
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', id: 6, method: 'tools/call', params: { name: 'get_market_status', arguments: {} } }));
assert(j.result.structuredContent.rows[0].is_open === true, 'status');
[st, j] = await show(await post('/mcp/tok', { jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name: 'nope' } }));
assert(j.error && j.error.code === -32602, 'unknown tool');
[st, j] = await show(await post('/mcp/tok', [{ jsonrpc: '2.0', id: 8, method: 'ping' }, { jsonrpc: '2.0', method: 'notifications/x' }]));
assert(Array.isArray(j) && j.length === 1, 'batch');
const g = await worker.fetch(new Request('https://w.dev/mcp/tok'), env);
assert(g.status === 405, 'GET 405');
assert(!calls.some((c) => !c.includes('token=k')), 'api key sent');
console.log('all worker tests passed');
