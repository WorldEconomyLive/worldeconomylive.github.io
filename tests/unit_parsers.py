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
S._get = lambda u, timeout=60, **k: types.SimpleNamespace(headers={}, content=csv_new)
e = S.ember_monthly()
assert set(e.iso3) == {"USA", "TUR", "DEU"} and (e.value == 300).all(), e.iso3.unique()
S._get = lambda u, timeout=60, **k: types.SimpleNamespace(headers={}, content=csv_old if "long" in u else b"<html>moved</html>")
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
        return types.SimpleNamespace(headers={}, json=lambda: {"series": {"docs": docs, "num_found": 3}})
    if "getFullTableDownloadCSV" in url:
        return types.SimpleNamespace(headers={}, json=lambda: {"status": "SUCCESS", "object": "https://x/23100216-eng.zip"})
    rows = []
    for d in pd.date_range("2022-01-01", "2026-08-01", freq="MS"):
        for comp, v in [("Total traffic carried", 30e6), ("Intermodal traffic loaded", 3e6)]:
            rows.append({"REF_DATE": d.strftime("%Y-%m"), "GEO": "Canada", "DGUID": "x", "Railway carloadings components": comp,
                         "UOM": "Tonnes", "VALUE": v, "VECTOR": "v1"})
        rows.append({"REF_DATE": d.strftime("%Y-%m"), "GEO": "Eastern Division", "DGUID": "x", "Railway carloadings components": "Total traffic carried", "UOM": "Tonnes", "VALUE": 1, "VECTOR": "v2"})
    buf = io.BytesIO(); zf = _z.ZipFile(buf, "w"); zf.writestr("23100216.csv", pd.DataFrame(rows).to_csv(index=False)); zf.writestr("23100216_MetaData.csv", "x"); zf.close()
    return types.SimpleNamespace(headers={}, content=buf.getvalue())
S._get = fake_get
a = S.eu_air_freight(); assert set(a) == {"DEU", "GRC"}, a.keys()
c = S.canada_rail(); assert len(c) == 56 and c.iloc[-1] == 30e6, (len(c), c.iloc[-1])
print("freight ok")

# release-date parsing from each source's own metadata format
for raw, want in [("2026-11-04T09:15:00Z", "2026-11-04"), ("Wed, 05 Nov 2026 08:01:02 GMT", "2026-11-05"), (1793460631, "2026-10-31"),
                  (1793460631000, "2026-10-31"), ("November 4, 2026", "2026-11-04"), ("2026-10-28T23:00:00+0100", "2026-10-28"),
                  ("2026-10-27T08:30", "2026-10-27"), (None, None), ("garbage", None)]:
    got = S.parse_when(raw)
    assert got == want, (raw, got, want)
S.REL.clear()
S._get = lambda u, **k: types.SimpleNamespace(headers={}, text='<str:ContentConstraint id="CR_A_DF" validFrom="2026-11-04T09:15:00" validTo="9999">')
S.oecd_release("OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", "oecd:x")
assert S.REL["oecd:x"]["released"] == "2026-11-04", S.REL
print("release dates ok")

# US fiscal years from MTS Table 1 'Year-to-Date' lines: current FY is the last line printed in each statement
rows = []
for rd, fy, prior, cur in [("2025-09-30", 2025, (4.9e12, 6.75e12), (5.23e12, 7.01e12)), ("2026-10-31", 2027, (5.23e12, 7.01e12), (0.40e12, 0.69e12))]:
    rows.append({"record_date": rd, "record_fiscal_year": str(fy), "record_calendar_month": rd[5:7], "classification_desc": "Year-to-Date", "print_order_nbr": "13",
                 "current_month_gross_rcpt_amt": str(prior[0]), "current_month_gross_outly_amt": str(prior[1]), "current_month_dfct_sur_amt": "0"})
    rows.append({"record_date": rd, "record_fiscal_year": str(fy), "record_calendar_month": rd[5:7], "classification_desc": "Year-to-Date", "print_order_nbr": "27",
                 "current_month_gross_rcpt_amt": str(cur[0]), "current_month_gross_outly_amt": str(cur[1]), "current_month_dfct_sur_amt": "0"})
S._get = lambda u, **k: types.SimpleNamespace(headers={"Last-Modified": "Thu, 12 Nov 2026 19:00:00 GMT"}, json=lambda: {"data": rows})
fy = S.us_fiscal_years()
assert list(fy.fy) == [2025, 2027] and fy.iloc[0].receipts == 5.23e12 and fy.iloc[1].outlays == 0.69e12, fy
assert S.REL["mts"]["released"] == "2026-11-12"
print("us fiscal years ok")

# IMF DataMapper (current WEO): values by country and year, edition from the indicator's source text
def dm_get(u, **k):
    if u.endswith("/indicators"):
        return types.SimpleNamespace(headers={}, json=lambda: {"indicators": {"PCPIPCH": {"source": "World Economic Outlook (October 2026)"}}})
    vals = {iso: {"2024": 58.5 if iso == "TUR" else 219.9, "2025": 34.9 if iso == "TUR" else 41.9, "2026": 28.6 if iso == "TUR" else 30.4} for iso in ["TUR", "ARG"] + [f"X{i:02d}" for i in range(60)]}
    vals["ADVEC"] = {"2025": 2.0}
    return types.SimpleNamespace(headers={}, json=lambda: {"values": {"PCPIPCH": vals}})
S._get = dm_get
S.REL.pop("weo", None)
S._DM_LABEL.clear()
d, rel = S.weo_all("PCPIPCH.pcent_change", ["WEO:latest"])
assert rel == "WEO October 2026" and S.REL["weo"]["label"] == "WEO October 2026", (rel, S.REL["weo"])
assert d["TUR"][pd.Timestamp("2025-07-01")] == 34.9 and d["ARG"][pd.Timestamp("2025-07-01")] == 41.9 and "ADVEC" not in d
print("imf datamapper ok")

# Sahm rule: 3-month average vs its lowest 3-month average over the PRIOR 12 months (monthly data only)
from pathlib import Path  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import run as RUN  # noqa: E402
u = pd.Series([4.0] * 14 + [4.3, 4.6, 4.9], index=pd.date_range("2024-01-01", periods=17, freq="MS"))
e = {"indicators": {"inflation": {"latest": 2.0, "annual": False}, "unemployment": {"latest": 4.9, "annual": False}}, "_series": {"unemployment": pd.concat([pd.Series([4.0] * 10, index=pd.date_range("2023-03-01", periods=10, freq="MS")), u])}}
m = RUN.macro_math(e)
assert abs(m["sahm"] - (4.6 - 4.0)) < 1e-9, m["sahm"]      # (4.3+4.6+4.9)/3 = 4.6 vs prior low 4.0
e["_series"]["unemployment"] = None
assert "sahm" not in RUN.macro_math(e)                    # annual-only unemployment: no Sahm
print("sahm ok")
