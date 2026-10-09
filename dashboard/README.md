# Market Cockpit

One-page market dashboard (Hebrew, RTL), published as a Claude Dashboard artifact:
https://claude.ai/artifact/AMqT7GGi3A6ZtCNFoxrHRs

- `index.html` – the page (runs inside the Dashboard type; uses `dash` + `d3`).
- `build_data.py` – writes the datasets for one analysis run into `data/`.
- `data/*.json` – snapshot of 2026-10-09 pre-market analysis.

Each "תן ניתוח" run re-researches the sources, rewrites the JSON files and re-uploads them to the dashboard.
