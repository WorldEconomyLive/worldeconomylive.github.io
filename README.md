# World Economy Live

The world economy's vital signs, in plain English. A free, open site that pulls public data
every day and shows growth, jobs, inflation, trade, shipping chokepoints, commodity prices,
currencies, interest rates, government debt and deficits, people and health, with a live
world map and a 0–100 score for each major economy.

## How it runs

A free GitHub Actions job (`.github/workflows/update.yml`) runs `pipeline/run.py` every day at
07:17 UTC, writes `site/data/heartbeat.json`, commits it, and republishes the site on GitHub Pages.
Any push that changes `pipeline/` or `site/` also triggers a run.

## Sources (all open and republishable, with attribution)

| Data | Source |
|---|---|
| Inflation, unemployment, factory output, GDP, interest rates, merchandise trade | OECD Data Explorer (CC BY 4.0) |
| Euro-area fallbacks | Eurostat (via DBnomics) |
| Central bank policy rates | Bank for International Settlements |
| Debt, deficits, current account (incl. current-year estimates) | IMF World Economic Outlook (IMF DataMapper; DBnomics mirror as fallback) |
| People, health, GDP composition, trade in US$ | World Bank WDI (CC BY 4.0) |
| Commodity prices | World Bank Commodity Price Data, "Pink Sheet" (CC BY 4.0) |
| Exchange rates | European Central Bank reference rates |
| US Treasury yields, real yields, federal debt | U.S. Department of the Treasury |
| Effective fed funds rate | Federal Reserve Bank of New York |
| Ports and chokepoints | IMF PortWatch |

FRED is deliberately not used: its terms do not allow republishing or storing its data on a
public site. Equity index levels (S&P, Nasdaq, Nikkei) are licensed by their owners and excluded.

## Files

| Part | File |
|---|---|
| What we track, release delays for past dates | `pipeline/registry.py` |
| Data clients | `pipeline/sources.py` |
| Pull, compute, score, write JSON | `pipeline/run.py` |
| Change-over-period engine | `pipeline/changes.py` |
| Score history rebuilt for every past day | `pipeline/history.py` |
| Past-date data and the daily archive | `pipeline/packs.py` |
| Website (static, D3 map, no build step) | `site/` (`site/engine.js` rebuilds the site for a past date in the browser) |
| d3, topojson, KaTeX, world-atlas (hosted with the site) | `site/vendor/` |
| Offline test with synthetic data | `python tests/mock_run.py` |
| Score rebuild = today's live scores | `python tests/history_check.py` |
| Browser engine = Python pipeline | `node tests/engine_parity.js` (after the mock run) |
| Daily archive | `python tests/archive_check.py` |

## Past dates and the archive

Every run keeps the site exactly as shown that day (`site/data/archive/`) and every input series as fetched, as
daily files of new or revised observations (`data/archive/inputs/`). Dates before the archive begins are rebuilt
in the browser from `site/data/packs/` (written by every run, deployed, not committed), counting each figure as
released after its source's usual delay (`LAGS` in `pipeline/registry.py`).

## Run locally

```
pip install -r requirements.txt
python pipeline/run.py
python -m http.server -d site 8000
```

Not investment advice.
