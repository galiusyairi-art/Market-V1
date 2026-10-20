#!/usr/bin/env python3
"""Market data for scheduled runs: calls the TradePilot worker (the same server behind the Finhub connector) over HTTPS.

Scheduled runs can't use claude.ai connectors, so they read the worker directly. The worker's full URL, including the
access token, comes from the environment variable TRADEPILOT_FEED_URL (set in the cloud environment's settings; the
worker's host must also be allowed in the environment's network access).

  python3 dashboard/tools/feed.py check                      # is the feed reachable? (exit 0 = yes)
  python3 dashboard/tools/feed.py quotes SPY,QQQ,CLF         # session-aware quotes (max 30)
  python3 dashboard/tools/feed.py daily SPY,^VIX,NVDA        # one-year daily statistics (max 40)
  python3 dashboard/tools/feed.py news NVDA [days]           # company news
  python3 dashboard/tools/feed.py earnings NVDA,MU [days]    # earnings dates
  python3 dashboard/tools/feed.py status                     # market session

Prints the rows as JSON. Exit code 2 = no URL configured, 3 = feed unreachable or returned an error.
"""
import json
import os
import sys
import urllib.error
import urllib.request

TOOLS = {"quotes": "get_quotes", "daily": "get_daily", "news": "get_company_news", "earnings": "get_earnings_calendar", "status": "get_market_status"}


def call(url, tool, args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=60) as r:
        reply = json.loads(r.read().decode())
    if "error" in reply:
        raise RuntimeError(reply["error"].get("message", "error"))
    res = reply["result"]
    if res.get("isError"):
        raise RuntimeError(res["content"][0]["text"])
    return res.get("structuredContent") or json.loads(res["content"][0]["text"])


def main(argv):
    if len(argv) < 2 or argv[1] not in TOOLS and argv[1] != "check":
        print(__doc__.strip(), file=sys.stderr)
        return 1
    url = os.environ.get("TRADEPILOT_FEED_URL", "").strip()
    if not url:
        print("TRADEPILOT_FEED_URL is not set: no live prices in this run. Do not publish price levels.", file=sys.stderr)
        return 2
    cmd, rest = argv[1], argv[2:]
    try:
        if cmd == "check":
            rows = call(url, "get_quotes", {"symbols": "SPY"})["rows"]
            ok = bool(rows and rows[0].get("price") is not None)
            print(json.dumps({"ok": ok, "spy": rows[0] if rows else None}, ensure_ascii=False))
            return 0 if ok else 3
        if cmd in ("quotes", "daily"):
            args = {"symbols": rest[0] if rest else ""}
        elif cmd == "news":
            args = {"symbol": rest[0] if rest else "", **({"days": int(rest[1])} if len(rest) > 1 else {})}
        elif cmd == "earnings":
            args = {**({"symbols": rest[0]} if rest else {}), **({"days": int(rest[1])} if len(rest) > 1 else {})}
        else:
            args = {}
        print(json.dumps(call(url, TOOLS[cmd], args)["rows"], ensure_ascii=False, indent=1))
        return 0
    except (urllib.error.URLError, OSError, RuntimeError, ValueError, KeyError) as e:
        print(f"feed unavailable: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
