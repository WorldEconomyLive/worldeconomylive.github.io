"""Offline test: replace every network source with synthetic data and run the full pipeline.
Usage: python tests/mock_run.py [--fail-oecd]"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import registry as R  # noqa: E402
import sources as S  # noqa: E402

rng = np.random.default_rng(1)
today = pd.Timestamp.today().normalize()
months = pd.date_range("2010-01-01", today - pd.Timedelta(days=40), freq="MS")
quarters = pd.date_range("2010-01-01", today - pd.Timedelta(days=120), freq="QS")
days = pd.date_range(today - pd.Timedelta(days=430), today)
FAIL = "--fail-oecd" in sys.argv


def fake_batch(spec, areas, start="2012-01"):
    if FAIL:
        raise RuntimeError("HTTP 429")
    out = {}
    for a in areas[:-3]:  # last few economies "missing" to exercise fallbacks
        f = spec["flow"]
        if "QNA" in f:
            s = pd.Series(100 + np.cumsum(rng.normal(0.5, 0.4, len(quarters))), index=quarters)
        elif "UNE" in f:
            s = pd.Series(5 + np.sin(np.arange(len(months)) / 15), index=months)
        elif "PRICES" in f:
            s = pd.Series(2.5 + rng.normal(0, 0.6, len(months)), index=months)
        elif "FINMARK" in f:
            s = pd.Series(3 + rng.normal(0, 0.2, len(months)), index=months)
        elif "IMTS" in f:
            s = pd.Series(rng.uniform(10, 200, len(months)) * 1e3, index=months)
        else:
            s = pd.Series(100 + np.cumsum(rng.normal(0.1, 0.8, len(months))), index=months)
        out[a] = (s, {"UNIT_MULT": "6"} if "IMTS" in f else {})
    return out


S.oecd_batch = fake_batch
S.dbnomics = lambda sid: (_ for _ in ()).throw(RuntimeError("not found"))
ALL = ["USA", "CHN", "JPN", "DEU", "IND", "GBR", "FRA", "BRA", "NGA", "KEN", "PER", "VNM", "EGY", "ARG", "ZAF", "AUS", "KOR", "MEX"] + list(R.ECONOMIES)
S.weo_all = lambda code, rels: ({i: pd.Series(rng.uniform(-5, 120, 12), index=pd.to_datetime([f"{y}-07-01" for y in range(2015, 2027)])) for i in set(ALL)}, "WEO:latest")
S.bis_batch = lambda codes: {c: pd.Series(3 + rng.normal(0, 0.2, len(months)), index=months) for c in codes if c not in ("IS", "CR")}
S.worldbank_all = lambda ind, since=2005: pd.DataFrame([{"iso3": i, "year": y, "value": float(rng.uniform(1, 80)) * (1e11 if "CD" in ind else 1)} for i in set(ALL) for y in range(2005, 2026)])
pink_cols = ["Crude oil, average", "Crude oil, Brent", "Crude oil, WTI", "Natural gas, US", "Natural gas, Europe", "Liquefied natural gas, Japan",
             "Coal, Australian", "Iron ore, cfr spot", "Copper", "Aluminum", "Nickel", "Wheat, US HRW", "Maize", "Rice, Thai 5%", "Soybeans",
             "Sugar, world", "Coffee, Arabica", "Cocoa", "Cotton, A Index", "Beef", "Urea", "Gold", "Silver"]
S.pink_sheet = lambda: pd.DataFrame({c: 50 + np.cumsum(rng.normal(0, 2, len(months))) for c in pink_cols}, index=months)
S.ecb_fx = lambda cur, start: pd.DataFrame({c: (1.1 if c == "USD" else rng.uniform(0.5, 150)) + np.cumsum(rng.normal(0, .005, len(days))) for c in cur}, index=days)
S.treasury_curve = lambda kind="daily_treasury_yield_curve", years=None: pd.DataFrame(
    {c: 3 + np.cumsum(rng.normal(0, .02, len(days))) for c in (["3 Mo", "2 Yr", "10 Yr", "30 Yr"] if "real" not in kind else ["10 YR"])}, index=days)
S.treasury_debt = lambda: pd.Series(3.6e13 + np.cumsum(rng.uniform(0, 5e9, len(days))), index=days)
S.nyfed_effr = lambda: pd.Series(3.9 + rng.normal(0, .01, len(days)), index=days)
ports = []
for i, iso in enumerate(["CHN", "HKG", "JPN", "KOR", "SGP", "IND", "ARE", "SAU", "NLD", "DEU", "FRA", "ITA", "GBR", "USA", "CAN", "BRA", "ZAF", "AUS", "MEX", "ESP"]):
    for k in range(4):
        ports.append({"portid": f"port{i}_{k}", "portname": f"{iso} port {k}", "ISO3": iso, "vessel_count_total": 1000 - k})
PORTS = pd.DataFrame(ports)
S.portwatch_ports = lambda: PORTS.copy()
PIDX = PORTS.set_index("portid")


def fake_port(pid, start):
    df = pd.DataFrame({"date": days, "portid": pid, "portcalls": rng.integers(5, 30, len(days)), "ISO3": PIDX.loc[pid, "ISO3"], "portname": PIDX.loc[pid, "portname"]})
    for f in ("import", "export"):
        for p in ("tanker", "container", "dry_bulk", "general_cargo", "roro"):
            df[f"{f}_{p}"] = rng.uniform(1000, 5000, len(days))
    return df


S.portwatch_port_daily = fake_port
S.portwatch_chokepoint_daily = lambda cid, start: pd.DataFrame({"date": days, "n_total": rng.integers(20, 80, len(days)), "n_tanker": rng.integers(5, 20, len(days)), "capacity": rng.uniform(1e5, 5e5, len(days))})

import run  # noqa: E402

run.OUT = ROOT / "tests" / "mock_heartbeat.json"
run.HIST = ROOT / "tests" / "mock_history.csv"
run.main()
d = json.loads(run.OUT.read_text())
print("world:", d["world"])
for e in d["economies"][:2] + d["economies"][-2:]:
    print(e["name"], e["score"], e["coverage"], sorted(e["indicators"]), "| fund", len(e["fundamentals"]), "| vit", len(e["vitals"]), "| derived", sorted(e["derived"]))
print("prices", len(d["prices"]), "fx", len(d["markets"]["fx"]), d["markets"]["fx"][1]["pair"], d["markets"]["fx"][1]["meaning"],
      "| rates", len(d["markets"]["rates"]), "| global rates", len(d["markets"]["global_rates"]), "| map", len(d["map"]), "| chokepoints", len(d["trade"]["chokepoints"]))
