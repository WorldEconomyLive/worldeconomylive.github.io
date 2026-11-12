# World Economy Live

The world economy in plain English. A free, open site that pulls public data every day,
scores major economies, and shows what changed: jobs, prices, factory output, trade,
shipping chokepoints, commodity prices, people and health.

## Deploy (free, about 10 minutes)

1. Create a GitHub account (use a fresh one with no personal details if you want to stay anonymous).
2. New repository → name it `worldeconomylive.github.io` → **Public** → Create.
3. Upload every file in this folder (drag the contents into "uploading an existing file"), keeping the folder structure, including `.github/workflows/update.yml`.
4. Settings → Pages → Source: **GitHub Actions**.
5. Actions tab → enable workflows if asked → "Daily update" → **Run workflow**.
6. After ~10–20 minutes the site is live at `https://worldeconomylive.github.io`.

It then refreshes itself every day at 07:17 UTC. Every run commits the data, which also keeps
GitHub's scheduler active.

## What it tracks

- **9 economies** (US, China, Japan, Germany, UK, France, Italy, Canada, India): GDP growth, inflation,
  unemployment, factory output, central bank rate, 10-year bond yield, plus a 0–100 score.
- **Markets**: 11 currencies, 9 US rates and spreads, 5 equity indices (% changes only), 22 commodities.
- **Trade**: ~60 ports by region and product, 24 shipping chokepoints (IMF PortWatch).
- **US fast signals**: jobless claims, rail, freight, consumer sentiment.
- **People and health**: population, aging, births, life expectancy, health spending, migration,
  income, inequality (World Bank).

To add anything: put it in `pipeline/registry.py`. It flows through to the site.

## Run locally

```
pip install -r requirements.txt
python pipeline/run.py                 # writes site/data/heartbeat.json
python -m http.server -d site 8000     # open http://localhost:8000
python tests/mock_run.py               # offline test with synthetic data
```

## How it is built

| Part | File |
|---|---|
| What we track (economies, indicators, prices, regions) | `pipeline/registry.py` |
| Data clients (FRED, DBnomics, World Bank, IMF PortWatch) | `pipeline/sources.py` |
| Pull, score, write JSON | `pipeline/run.py` |
| Website (no build step, no frameworks) | `site/` |
| Daily automation | `.github/workflows/update.yml` |

Every monthly indicator has a list of candidate sources tried in order; the first one with
fresh data wins. A failed source never breaks the site. It is listed under
"Data sources and status".

## The score

Up to four pillars per economy, each a z-score against that country's last 10 years,
signed so higher = healthier: activity (factory output growth), jobs (12-month change in
unemployment, inverted), prices (distance of inflation from 2%, inverted), trade (port cargo
vs a year ago, scaled). Score = 50 + 15 × mean pillar, clipped to 0–100.

## Data and licensing

Public-domain and open-licensed sources only on the public site: IMF PortWatch, U.S. federal
agencies via FRED, Eurostat / OECD / BIS via DBnomics, World Bank (CC BY 4.0). Some FRED series
are owned by third parties (e.g. Cass, ATA). They are deliberately excluded. Check each
series' notes before adding new ones.

Not investment advice.

## Roadmap

- v2: ripple engine (OECD input-output tables) and "your wallet" household cost impact;
  automated nowcasts; food and energy import vulnerability by country.
- v3: electricity demand, satellite night lights and NO₂, conflict and attention signals,
  alerts and a weekly note.
