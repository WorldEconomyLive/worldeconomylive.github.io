"""Offline checks for the OECD batch parser and the Ember parser."""
import sys, io, types
sys.path.insert(0, "pipeline")
import numpy as np, pandas as pd
import sources as S

# OECD: key-based spec whose CSV has empty attribute columns (the bug that zeroed inflation)
rows = []
for a in ["USA", "JPN"]:
    for k, p in enumerate(pd.period_range("2023-01", "2026-09", freq="M")):
        rows.append({"STRUCTURE": "DATAFLOW", "STRUCTURE_ID": "X", "ACTION": "I", "REF_AREA": a, "FREQ": "M",
                     "METHODOLOGY": "N", "MEASURE": "CPI", "UNIT_MEASURE": "PA", "EXPENDITURE": "_T",
                     "ADJUSTMENT": "N", "TRANSFORMATION": "GY", "TIME_PERIOD": str(p), "OBS_VALUE": 2 + k / 100,
                     "OBS_STATUS": "A" if k % 3 else np.nan, "UNIT_MULT": 0, "DECIMALS": 2, "BASE_PER": np.nan})
df = pd.DataFrame(rows).astype(str).replace("nan", np.nan)
S.oecd_frame = lambda flow, key, start: df
S.oecd_dims = lambda flow: (_ for _ in ()).throw(RuntimeError("offline"))   # force column fallback
out = S.oecd_batch({"flow": "F", "key": "{areas}.M.N.CPI.PA._T.N.GY"}, ["USA", "JPN"])
assert set(out) == {"USA", "JPN"} and len(out["USA"][0]) == 45, {k: len(v[0]) for k, v in out.items()}
S.oecd_dims = lambda flow: ["REF_AREA", "FREQ", "METHODOLOGY", "MEASURE", "UNIT_MEASURE", "EXPENDITURE", "ADJUSTMENT", "TRANSFORMATION"]
out = S.oecd_batch({"flow": "F", "key": "{areas}.M.N.CPI.PA._T.N.GY"}, ["USA", "JPN"])
assert len(out["JPN"][0]) == 45
print("oecd ok")

# Ember new wide format (July 2026)
months = pd.date_range("2022-01-01", "2026-09-01", freq="MS")
new = []
for area in ["United States", "Türkiye", "Germany", "World", "EU"]:
    for d in months:
        for src, v in [("Demand", 300.0), ("Coal", 50.0), ("Total generation", 310.0)]:
            new.append({"Area": area, "Area type": "Country", "Date": d.strftime("%Y-%m-%d"), "Electricity source": src,
                        "Is aggregated source": src == "Total generation", "Generation (TWh)": v,
                        "Share of generation (%)": 10, "Generation YoY change (TWh)": 1, "EU member": False})
csv_new = pd.DataFrame(new).to_csv(index=False).encode()
old = [{"Area": n, "ISO 3 code": c, "Date": d.strftime("%Y-%m-%d"), "Variable": "Demand", "Unit": "TWh",
        "Value": 40} for d in months for n, c in [("France", "FRA"), ("Spain", "ESP")]]
csv_old = pd.DataFrame(old).to_csv(index=False).encode()
S._get = lambda u, timeout=60, **k: types.SimpleNamespace(content=csv_new)
e = S.ember_monthly()
assert set(e.iso3) == {"USA", "TUR", "DEU"} and (e.value == 300).all(), e.iso3.unique()
S._get = lambda u, timeout=60, **k: types.SimpleNamespace(content=csv_old if "long" in u else b"<html>moved</html>")
e = S.ember_monthly()
assert set(e.iso3) == {"FRA", "ESP"}
print("ember ok")

# FX wording
import registry as R
assert all(c in R.FX_UNITS for c in R.FX if c != "USD")
print("fx ok")
