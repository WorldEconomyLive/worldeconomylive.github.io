"""Offline test: replace every network source with synthetic data and run the full pipeline.
Usage: python tests/mock_run.py [--fail-oecd]"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import sources as S  # noqa: E402

rng = np.random.default_rng(1)
today = pd.Timestamp.today().normalize()
months = pd.date_range("2010-01-01", today, freq="MS")
days = pd.date_range(today - pd.Timedelta(days=430), today)


def frame(vals, idx):
    return pd.DataFrame({"TIME_PERIOD": [d.strftime("%Y-%m") for d in idx], "OBS_VALUE": [str(v) for v in vals]})


def fake_oecd_frame(flow, key, start="2012-01"):
    if "--fail-oecd" in sys.argv:
        raise RuntimeError("HTTP 404")
    if "UNE" in key:
        return frame(5 + np.sin(np.arange(len(months)) / 15), months)
    return frame(2.5 + rng.normal(0, 0.6, len(months)), months)


def fake_oecd_pick(flow, filters, prefer=None, start="2012-01"):
    if "--fail-oecd" in sys.argv or "IMTS" in flow:
        raise RuntimeError("required dimension missing")
    if "QNA" in flow:
        q = pd.date_range("2010-01-01", today, freq="QS")
        return pd.Series(100 + np.cumsum(rng.normal(0.5, 0.4, len(q))), index=q), {}
    if "FINMARK" in flow:
        return pd.Series(3 + rng.normal(0, 0.2, len(months)), index=months), {}
    return pd.Series(100 + np.cumsum(rng.normal(0.1, 0.8, len(months))), index=months), {}


S.oecd_frame, S.oecd_pick = fake_oecd_frame, fake_oecd_pick
S.dbnomics = lambda sid: (_ for _ in ()).throw(RuntimeError("not found")) if "WEO" not in sid else \
    pd.Series(rng.uniform(-5, 120, 12), index=pd.to_datetime([f"{y}-07-01" for y in range(2015, 2027)]))
S.bis_policy_rate = lambda cc: pd.Series(3 + rng.normal(0, 0.2, len(months)), index=months)
S.worldbank = lambda ind, isos: pd.DataFrame([{"iso3": i, "year": y, "value": float(rng.uniform(1, 80)) * (1e12 if "CD" in ind else 1)}
                                             for i in isos for y in range(2000, 2026)])
pink_cols = ["Crude oil, average", "Crude oil, Brent", "Crude oil, WTI", "Natural gas, US", "Natural gas, Europe",
             "Liquefied natural gas, Japan", "Coal, Australian", "Iron ore, cfr spot", "Copper", "Aluminum", "Nickel",
             "Wheat, US HRW", "Maize", "Rice, Thai 5%", "Soybeans", "Sugar, world", "Coffee, Arabica", "Cocoa",
             "Cotton, A Index", "Beef", "Urea", "Gold", "Silver"]
S.pink_sheet = lambda: pd.DataFrame({c: 50 + np.cumsum(rng.normal(0, 2, len(months))) for c in pink_cols}, index=months)
S.ecb_fx = lambda cur, start: pd.DataFrame({c: 1 + rng.uniform(0.5, 150) + np.cumsum(rng.normal(0, .01, len(days))) for c in cur}, index=days)
S.treasury_curve = lambda kind="daily_treasury_yield_curve", years=None: pd.DataFrame(
    {c: 3 + np.cumsum(rng.normal(0, .02, len(days))) for c in (["3 Mo", "2 Yr", "10 Yr", "30 Yr"] if "real" not in kind else ["10 YR"])}, index=days)
S.treasury_debt = lambda: pd.Series(3.6e13 + np.cumsum(rng.uniform(0, 5e9, len(days))), index=days)
S.nyfed_effr = lambda: pd.Series(3.9 + rng.normal(0, .01, len(days)), index=days)


def fake_ports():
    rows, n = [], 0
    for iso in ["CHN", "HKG", "JPN", "KOR", "SGP", "IND", "ARE", "SAU", "NLD", "DEU", "FRA", "ITA", "GBR", "USA", "CAN", "BRA", "ZAF"]:
        for k in range(6):
            n += 1
            rows.append({"portid": f"port{n}", "portname": f"{iso} port {k}", "ISO3": iso, "vessel_count_total": 1000 - k})
    return pd.DataFrame(rows)


PORTS = fake_ports().set_index("portid")
S.portwatch_ports = fake_ports


def fake_port(pid, start):
    df = pd.DataFrame({"date": days, "portid": pid, "portcalls": rng.integers(5, 30, len(days)),
                       "ISO3": PORTS.loc[pid, "ISO3"], "portname": PORTS.loc[pid, "portname"]})
    for f in ("import", "export"):
        for p in ("tanker", "container", "dry_bulk", "general_cargo", "roro"):
            df[f"{f}_{p}"] = rng.uniform(1000, 5000, len(days))
    return df


S.portwatch_port_daily = fake_port
S.portwatch_chokepoint_daily = lambda cid, start: pd.DataFrame({"date": days, "n_total": rng.integers(20, 80, len(days)),
                                                                "n_tanker": rng.integers(5, 20, len(days)), "capacity": rng.uniform(1e5, 5e5, len(days))})

import run  # noqa: E402

run.OUT = ROOT / "tests" / "mock_heartbeat.json"
run.HIST = ROOT / "tests" / "mock_history.csv"
run.main()
d = json.loads(run.OUT.read_text())
print("world:", d["world"])
e = d["economies"][0]
print(e["name"], e["score"], e["coverage"], sorted(e["indicators"]), sorted(e["math"]), sorted(e["derived"]))
print("prices", len(d["prices"]), "fx", len(d["markets"]["fx"]), "rates", len(d["markets"]["rates"]), "map", len(d["map"]),
      "chokepoints", len(d["trade"]["chokepoints"]))
