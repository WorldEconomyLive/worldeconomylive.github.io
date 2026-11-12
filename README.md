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
| Inflation, unemployment, factory output, GDP, interest rates, merchandise trade in US$ (45 economies) | OECD Data Explorer (CC BY 4.0) |
| Euro-area fallbacks | Eurostat (via DBnomics) |
| Central bank policy rates | Bank for International Settlements |
| Debt, deficits, current account (incl. current-year estimates) | IMF World Economic Outlook (via DBnomics) |
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
| What we track | `pipeline/registry.py` |
| Data clients | `pipeline/sources.py` |
| Pull, compute, score, write JSON | `pipeline/run.py` |
| Website (static, D3 map, no build step) | `site/` |
| Offline test with synthetic data | `python tests/mock_run.py` |

## Run locally

```
pip install -r requirements.txt
python pipeline/run.py
python -m http.server -d site 8000
```

Not investment advice.
