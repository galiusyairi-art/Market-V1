# Scheduled runs: how to update TradePilot

Dashboard artifact: https://claude.ai/artifact/AMqT7GGi3A6ZtCNFoxrHRs (Dashboard type, Hebrew RTL).
The page (`files/index.html`) is final: **never edit or republish it**. A run only replaces data files.
Never touch `datasets/quotes`, `datasets/daily`, `datasets/earnings` (live connector queries) or `dash/params`.

## Who does what
The page computes every number from live data itself:
- prices by session, indices, sectors and the market light;
- day-trade entry, stop and targets (formula below), trend score, earnings dates.

Runs supply what only research can:
- which stocks are in play and why (catalyst, news);
- grades;
- commentary text (`brief`, `regime` text, `outlook`, `macro`, `social`, `chatter`, `calendar`);
- the journal and lessons.

The page shows run-written text with its time stamp, and with whether its prices were verified.

## 0. Should this run do anything?
Check the New York date and time. On a weekend or NYSE holiday, stop and reply in one line.

## 1. Prices: the feed, never guesses
Run `python3 dashboard/tools/feed.py check` first.

**Exit 0: the feed works.** Use it for every number:
- `feed.py quotes SYM,...` gives session-aware quotes.
  - `price`, `price_session`, `change_pct` vs the previous close.
  - `pm_high`/`pm_low` before the open.
  - `or_high`/`or_low` (first 5 minutes) and `vwap` after 09:35.
  - Today's `high`/`low`/`open`.
- `feed.py daily SYM,...` gives one-year statistics: `atr14`, the 50/150/200-day averages, the 52-week high, week/month refs and `trend_score`.
- `feed.py earnings SYM,...`, `feed.py news SYM`.
- Write `price_source: feed` in `brief`.

**Any other exit: no live prices** (the reason is printed).
- Do research with WebSearch only.
- Write `price_source: web`, or `none` if you found no dated prices.
- Write no number you can't tie to a dated source.
- Say so in the reply.

How to read the quote fields:
- **Pre-market:** `price` is the latest pre-market trade, and `change_pct` is that trade vs yesterday's close.
- **No trade yet:** `price_session: "prev_close"` means no trade yet today. `change_pct` is then null, and never 0%.
- **After the close:** `day_change_pct` is the regular-session move, and `ext_change_pct` is the after-hours move.
- **Finnhub-only rows** (`source: "finnhub"` while `session` is `pre` or `post`) have no extended-hours data.
- **`check: "mismatch"`** means the sources disagree: verify against a third source before using the number.

## 2. The day-trade level formula (the page and the review use exactly this)
Let ATR be `daily.atr14`.
- **Before 09:35 NY** (provisional levels):
  - On a gap of 2% or more (`|change_pct|` ≥ 2): entry = `pm_high`, and the floor = `pm_low`.
  - Otherwise: entry = max(`daily.prev_high`, `pm_high`), and the floor = `pm_low` (or `daily.prev_low` with no pre-market trades).
- **From 09:35:** entry = `or_high` (high of 09:30–09:35), and the floor = `or_low`.
- stop = max(floor, entry − 0.5·ATR). If entry − stop < 0.15·ATR, then stop = entry − 0.15·ATR.
- R = entry − stop. T1 = entry + 1.5R, and T2 = entry + 3R.
- Rounding: cents (4 decimals under $1).

When the feed works, write these values into `daytrade` (`trigger`, `stop`, `t1`, `t2`) using the pre-market numbers. Without the feed, write the levels you can source, and say in `plan` that they are unverified.

## 3. Data files
The schemas are in `dashboard/build_data.py`, and the latest values are in `dashboard/data/*.json`. Keep **every field name and type**.

`brief` rows:
- `as_of`: ISO time with offset, the actual time of the run.
- `price_source`: `feed` | `web` | `none`.
- `headline`, `today`, `week`, `month`, `social`.

Write text so it stays true when read later: name the date of every close you cite ("סגירת 20.10").

| dataset id | what it holds |
|---|---|
| brief | the rows above |
| outlook | p_up for today/week/month with drivers (an estimate: say what it rests on) |
| indices | SPX/IXIC/DJI last_close, pre_pct, day_pct, wtd_pct, mtd_pct (fallback only; the page computes these live) |
| regime | overall status/title/text/exposures plus factors (shown as commentary next to the computed light) |
| daytrade | 2–6 stocks in play: symbol, name, side 1, prev_close, pm_price, gap_pct, trigger, stop, t1, t2, r_t1 1.5, r_t2 3, grade A/B/C, catalyst, checks, plan, avoid |
| swing_setups | 3–6 names: last, pivot, zone_top (+5%), stop (≈−7%), target (+20%), status, trend, earnings, verdict, action, reason |
| sectors, macro, social, chatter, calendar, sources, methods | as before |

## 4. Publish
1. Upload each changed JSON: Artifact `publish`, `url` = the artifact url, `asset: true`, `file_path` = the file. The reply gives `/_blob/<id>`.
2. ArtifactData `list` on `datasets` to get the current versions.
3. One ArtifactData `batch` of `update` writes on `datasets/<id>`, each pinned with `if_version`.
   - Data: `{source: {kind: "file", url: "/_blob/<id>", name: "<file>.json"}, updated: {at: <ISO UTC now>, by: "Claude (scheduled)"}}`.

## 5. Save to git
Copy the JSON files into `dashboard/data/`, and commit on `claude/stock-market-analysis-app-em3rok` with the message "Scheduled cockpit refresh <date> <time> NY". Then push.

## 6. Reply
In Hebrew, at most 5 lines:
- The price source.
- The market light and why.
- The top 2–3 names.
- What changed.

## Learning loop (journal + lessons)
**Morning and midday runs:**
- Read `datasets/lessons` first, and apply every `active` lesson.
- Name the lesson that changed the picks in `brief.today`.
- Never write `journal` or `lessons`.

**End-of-day review (16:20 NY):**
1. **Grade each `daytrade` signal with the feed.**
   - Take `quotes` after the close (`or_high`, `or_low`, `high`, `low`, `price` = close) and `daily.atr14`.
   - Rebuild the levels with the formula in section 2, using the opening range.
   - **Triggered** = `high` > `or_high`. The entry is `or_high`.
   - Results: `no_trigger`, `stop`, `t1`, `t2`, `eod`, `ambiguous` (stop and T1 both hit; order unknown; not scored).
   - R uses the exit plan: half at T1, then the stop moves to the entry, the rest at T2 or the close.
   - Journal row fields: `{id:"<date>|day|<sym>", date, kind, symbol, grade, trigger, stop, t1, t2, result, r, day_high, day_low, close, scored, note}`.
   - **Without the feed, do not grade from memory or headlines.** Add the rows with `result: "open"` and `scored: false`, and the note "ממתין לנתוני מחיר". The next review with the feed grades them from `daily` data.
2. **Learn.** Write 1–3 lessons: `{id, date, type: rule|observation, status: active|retired, text, evidence, applies_to}`.
   - A rule needs ≥3 scored cases, or one extremely clear-cut case.
   - At most 8 active rules.
3. **After the close, also refresh the commentary.**
   - `brief`: today's close with its date, plus a new `as_of` and `price_source`.
   - `regime`: the text and status for tomorrow.
   - `indices` and `outlook`.

   This way the evening page never describes the previous day as the latest close.
4. Publish `journal`, `lessons` and the refreshed files in one batch.
