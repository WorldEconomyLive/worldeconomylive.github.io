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

# DBnomics dimension query (Eurostat freight) and StatCan zip parsing
import json as _j, zipfile as _z
def fake_get(url, timeout=60, **k):
    if "db.nomics" in url:
        docs = [{"series_code": f"M.T.FRM_LD_NLD.TOT.TOTAL.{g}", "dimensions": {"geo": g},
                 "period": [f"2024-{m:02d}" for m in range(1, 13)], "value": [100 + m for m in range(12)]} for g in ["DE", "EL", "EU27_2020"]]
        return types.SimpleNamespace(json=lambda: {"series": {"docs": docs, "num_found": 3}})
    if "getFullTableDownloadCSV" in url:
        return types.SimpleNamespace(json=lambda: {"status": "SUCCESS", "object": "https://x/23100216-eng.zip"})
    rows = []
    for d in pd.date_range("2022-01-01", "2026-08-01", freq="MS"):
        for comp, v in [("Total traffic carried", 30e6), ("Intermodal traffic loaded", 3e6)]:
            rows.append({"REF_DATE": d.strftime("%Y-%m"), "GEO": "Canada", "DGUID": "x", "Railway carloadings components": comp,
                         "UOM": "Tonnes", "VALUE": v, "VECTOR": "v1"})
        rows.append({"REF_DATE": d.strftime("%Y-%m"), "GEO": "Eastern Division", "DGUID": "x", "Railway carloadings components": "Total traffic carried", "UOM": "Tonnes", "VALUE": 1, "VECTOR": "v2"})
    buf = io.BytesIO(); zf = _z.ZipFile(buf, "w"); zf.writestr("23100216.csv", pd.DataFrame(rows).to_csv(index=False)); zf.writestr("23100216_MetaData.csv", "x"); zf.close()
    return types.SimpleNamespace(content=buf.getvalue())
S._get = fake_get
a = S.eu_air_freight(); assert set(a) == {"DEU", "GRC"}, a.keys()
c = S.canada_rail(); assert len(c) == 56 and c.iloc[-1] == 30e6, (len(c), c.iloc[-1])
print("freight ok")
