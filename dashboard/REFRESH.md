# Scheduled refresh: how to update the Market Cockpit

Dashboard artifact: https://claude.ai/artifact/AMqT7GGi3A6ZtCNFoxrHRs (Dashboard type, Hebrew RTL).
The page (`files/index.html`) is final: **never edit or republish it**. A refresh only replaces the data files.
Never touch `datasets/quotes` (the live Finnhub query) or `dash/params`. The page keeps the quote symbol list in sync with `daytrade` and `swing_setups` by itself.

## 0. Should this run do anything?
Check the New York date and time. If it is a weekend or a NYSE holiday, stop and reply in one line that there was no trading today.

## 1. Research
**Prices come from the Finnhub connector** (tools `mcp__Finhub__get_quotes`, `get_company_news`, `get_earnings_calendar`, `get_market_status`; load them with ToolSearch "finnhub"). It gives real-time quotes: use it for every price, prev close, day high/low and earnings date. Use WebSearch for news, catalysts, macro and social (WebFetch usually can't reach finance sites from this environment). If Finnhub is unavailable, fall back to dated web sources.
Gather only numbers you can confirm from a dated source. If you can't confirm a number, leave it out or keep the previous value and say how old it is. Never invent prices.
- Index futures or levels (S&P 500, Nasdaq, Dow), the previous close, and closes for the start of the week and the start of the month.
- Premarket / intraday movers with catalysts (CNBC "stocks making the biggest moves", Benzinga movers, Reuters, Yahoo).
- Macro releases today and upcoming (Fed, CPI, jobs, Michigan, GDP), 10Y yield, Brent/WTI, gold, bitcoin.
- Social chatter: Stocktwits trending, WallStreetBets/Reddit mentions (AltIndex, Tradestie), X.
- Sector strength (week and YTD).
- Prices for every day-trade and swing candidate you keep or add: previous close, premarket/last price, 52-week high where relevant, next earnings date.

## 2. Rewrite the data files
The schemas are in `dashboard/build_data.py`, and the latest values are in `dashboard/data/*.json`. Keep **every field name and type** the page reads.
Simplest path: edit `build_data.py` with the new values, then run `python3 build_data.py` inside `dashboard/data/`. Note: it writes JSON into the current directory.

| dataset id | file | what it holds |
|---|---|---|
| brief | brief.json | key/text rows: as_of (ISO, New York time), headline, today, week, month, social |
| outlook | outlook.json | p_up for today/week/month |
| indices | indices.json | SPX/IXIC/DJI: last_close, pre_pct, day_pct, wtd_pct, mtd_pct |
| regime | regime.json | overall (status go/caution/stop, day_exposure, swing_exposure) and 6 factors |
| timing | timing.json | session windows (normally unchanged) |
| daytrade | daytrade.json | 3–6 stocks in play: prev_close, pm_price, trigger, stop, t1, t2, grade A/B/C, checks, plan, avoid |
| swing_setups | swing_setups.json | 3–6 swing names: last, pivot, stop (≈7% below pivot), target (≈+20%), status, trend X/5, earnings, verdict watch/conditional/avoid, action wait/buy_close/avoid |
| sectors | sectors.json | sector ETF week_pct / ytd_pct |
| macro | macro.json | 12 tiles |
| social, chatter | social.json, chatter.json | WSB mentions, cross-platform chatter |
| calendar, sources, methods | … | events, sources read this run, method reads |

Rules:
- Levels must be internally consistent: for a long, stop < trigger < t1 < t2.
- Grade honestly. Mark gap-fades and earnings risk.
- Set `as_of` to the actual research time.

## 3. Publish
For each changed file:
1. Upload it: Artifact tool, `action: publish`, `url` = the artifact url, `asset: true`, `file_path` = the JSON file. The reply gives `/_blob/<id>`.
2. Read the dataset docs first: ArtifactData `list` on collection `datasets`. You need their current versions.
3. Write all the updates in one ArtifactData `batch`. Each entry is `op: update` on `datasets/<id>`, pinned with `if_version`, with data `{source: {kind: "file", url: "/_blob/<id>", name: "<file>.json"}, updated: {at: <ISO UTC now>, by: "Claude (scheduled)"}}`.

## 4. Save to git
Copy the new JSON files and build_data.py into `dashboard/`. Commit on branch `claude/stock-market-analysis-app-em3rok` with message "Scheduled cockpit refresh <date> <time> NY", then push.

## 5. Reply
In Hebrew, at most 5 lines:
- The market light (רמזור) and why.
- The top 2–3 decisions (symbol, trigger, stop).
- Anything that changed since the last run.
