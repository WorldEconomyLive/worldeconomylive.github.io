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

# IMF routes: DataMapper down -> IMF data portal (SDMX CSV); both down -> DBnomics flagged as an older copy
def sdmx_get(u, **k):
    if "datamapper" in u:
        raise RuntimeError("HTTP 403")
    if "api.imf.org" in u:
        lines = ["DATAFLOW,COUNTRY,INDICATOR,FREQUENCY,TIME_PERIOD,OBS_VALUE"] + [f"IMF.RES:WEO,{c},PCPIPCH,A,{y},{v}" for c in ["ARG", "UVK"] + [f"X{i:02d}" for i in range(60)] for y, v in ((2024, 219.9), (2025, 41.9))]
        return types.SimpleNamespace(headers={}, text="\n".join(lines))
    raise RuntimeError("unexpected " + u)
S._get = sdmx_get
S.REL.pop("weo", None); S._WEO_FAIL.clear(); S._WEO_OK.clear()
d, rel = S.weo_all("PCPIPCH.pcent_change", ["WEO:latest"])
assert d["ARG"][pd.Timestamp("2025-07-01")] == 41.9 and "XKX" in d and "UVK" not in d, sorted(d)[:5]
assert "weo.imf_datamapper" in S.STATUS and not S.STATUS["weo.imf_datamapper"]["ok"] and "403" in S.STATUS["weo.imf_datamapper"]["note"]


def dbn_get(u, **k):
    if "api.db.nomics.world/v22/series" in u:
        return types.SimpleNamespace(headers={}, json=lambda: {"series": {"docs": [{"series_code": f"{c}.PCPIPCH.pcent_change", "period": ["2024", "2025"], "value": [219.9, 35.9]} for c in ["ARG"] + [f"X{i:02d}" for i in range(60)]]}})
    if "api.db.nomics.world/v22/datasets" in u:
        return types.SimpleNamespace(headers={}, json=lambda: {"datasets": {"docs": [{"name": "World Economic Outlook (WEO) - April 2025", "updated_at": "2025-04-22"}]}})
    raise RuntimeError("HTTP 403")
S._get = dbn_get
S.REL.pop("weo", None); S._WEO_FAIL.clear(); S._WEO_OK.clear()
d, rel = S.weo_all("PCPIPCH.pcent_change", ["WEO:latest"])
assert S.REL["weo"]["stale"] and "older copy via DBnomics" in S.REL["weo"]["label"], S.REL["weo"]
assert not S.STATUS["weo.fallback"]["ok"] and "imf_sdmx" in "".join(S.STATUS), S.STATUS.get("weo.fallback")
print("imf routes ok:", S.REL["weo"]["label"])

# OWID grapher CSV: countries only, OWID region codes dropped, Kosovo mapped to XKX
csv = "Entity,Code,Year,hdi\n" + "\n".join(f"C{i},{('X%02d' % i)},2023,0.{i:02d}" for i in range(40)) + "\nWorld,OWID_WRL,2023,0.75\nKosovo,OWID_KOS,2023,0.8"
S._get = lambda u, **k: types.SimpleNamespace(headers={}, text=csv) if u.split("?")[0].endswith(".csv") else types.SimpleNamespace(headers={}, json=lambda: {"columns": {"hdi": {"lastUpdated": "2025-05-07", "citationShort": "UNDP, Human Development Report (2025)"}}})
o = S.owid_grapher("human-development-index")
assert "OWID_WRL" not in set(o.iso3) and "XKX" in set(o.iso3) and len(o) == 41, o.tail()
assert S.REL["owid:human-development-index"]["released"] == "2025-05-07"
print("owid ok")

# Ember low-carbon share: complete years only
rows = []
for c in ["USA"] + [f"X{i:02d}" for i in range(60)]:
    for m in pd.date_range("2024-01-01", "2025-06-01", freq="MS"):
        rows += [{"ISO 3 code": c, "Date": m, "Variable": "Clean", "Unit": "TWh", "Value": 40}, {"ISO 3 code": c, "Date": m, "Variable": "Total Generation", "Unit": "TWh", "Value": 100},
                 {"ISO 3 code": c, "Date": m, "Variable": "Demand", "Unit": "TWh", "Value": 98}]
df = pd.DataFrame(rows)
cols = {str(c).lower().strip(): c for c in df.columns}
S._ember_clean(df, cols, "Date", "Variable", "Value")
e = S.EMBER_CLEAN["df"]
assert set(e.year) == {2024} and abs(e.value.iloc[0] - 40) < 1e-9, e.head()
print("ember clean share ok")

# Kosovo has a map key; headline leads with the band
assert RUN.cty("XKX") == ("XKX", "Kosovo") and RUN.cty("GRL")[0] == 304
h = RUN.headline(25.0, {"A": {"score": 30, "pillars": {"labor": -2.0, "prices": 0.5}}}, [], None)
assert h.startswith("Global economy under stress (25).") and "Main drag: jobs" in h, h
# completed years only: the current-year forecast is ignored
y0 = RUN.TODAY.year
sr = pd.Series([1.0] * 20 + [9.0], index=pd.to_datetime([f"{y}-07-01" for y in range(y0 - 20, y0 + 1)]))
assert RUN.done_years(sr).index[-1].year == y0 - 1
print("kosovo, headline, completed years ok")

# IMF data portal sends GDP in US$ (not billions): converted to the DataMapper convention (billions)
def sdmx_gdp(u, **k):
    if "datamapper" in u:
        raise RuntimeError("HTTP 403")
    lines = ["DATAFLOW,COUNTRY,INDICATOR,FREQUENCY,TIME_PERIOD,OBS_VALUE"] + [f"IMF.RES:WEO,{c},NGDPD,A,2025,{v}" for c, v in [("USA", 30861300000000), ("COD", 122280664000)] + [(f"X{i:02d}", 1e11) for i in range(60)]]
    return types.SimpleNamespace(headers={}, text="\n".join(lines))
S._get = sdmx_gdp
S.REL.pop("weo", None); S._WEO_FAIL.clear(); S._WEO_OK.clear()
d, rel = S.weo_all("NGDPD.us_dollars", ["WEO:latest"])
assert abs(d["USA"].iloc[-1] - 30861.3) < 1e-6 and abs(d["COD"].iloc[-1] - 122.280664) < 1e-9, (d["USA"], d["COD"])
print("imf portal gdp units ok")

# EIA bulk INTL: consumption (activity 2) in quad Btu, split by fuel; production and per-capita series ignored
import io, json as _json, zipfile  # noqa: E402
lines = ['{"category_id":"1","name":"cat"}']
for c in ["USA"] + [f"X{i:02d}" for i in range(60)]:
    for prod, nm, v in (("44", "Total energy consumption", 100), ("5", "Petroleum and other liquids consumption", 36), ("26", "Dry natural gas consumption", 33),
                        ("7", "Coal consumption", 10), ("27", "Nuclear consumption", 8), ("29", "Renewables and other consumption", 13)):
        lines.append(_json.dumps({"series_id": f"INTL.{prod}-2-{c}-QBTU.A", "name": f"{nm}, {c}, Annual", "units": "quadrillion Btu", "data": [["2023", v], ["2022", v]]}))
    lines.append(_json.dumps({"series_id": f"INTL.44-1-{c}-QBTU.A", "name": f"Total energy production, {c}, Annual", "data": [["2023", 999]]}))
    lines.append(_json.dumps({"series_id": f"INTL.44-2-{c}-MBTUPP.A", "name": f"Total energy consumption per capita, {c}, Annual", "data": [["2023", 999]]}))
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("INTL.txt", "\n".join(lines))
S._get = lambda u, **k: types.SimpleNamespace(headers={"Last-Modified": "Thu, 05 Nov 2026 10:00:00 GMT"}, content=buf.getvalue())
e = S.eia_energy()
u = e[(e.iso3 == "USA") & (e.year == 2023)].set_index("fuel").qbtu
assert u.to_dict() == {"oil": 36, "gas": 33, "coal": 10, "nuclear": 8, "renewables": 13, "total": 100}, u.to_dict()
print("eia energy ok")

# Ember yearly (2026 wide format): generation by source, aggregates dropped
rows = []
for c in ["USA"] + [f"X{i:02d}" for i in range(60)]:
    for srcname, twh, agg in (("Coal", 600, False), ("Gas", 1800, False), ("Nuclear", 780, False), ("Wind", 450, False), ("Solar", 300, False), ("Clean", 1530, True), ("Total generation", 3930, True)):
        rows.append({"Area": c, "ISO 3 code": c, "Year": 2025, "Electricity source": srcname, "Is aggregated source": agg, "Generation (TWh)": twh, "Share of generation (%)": 0})
csv = pd.DataFrame(rows).to_csv(index=False).encode()
S._get = lambda u, **k: types.SimpleNamespace(headers={}, content=csv)
y = S.ember_yearly()
u = y[y.iso3 == "USA"].set_index("source").twh
assert u.to_dict() == {"coal": 600, "gas": 1800, "nuclear": 780, "solar": 300, "wind": 450}, u.to_dict()
print("ember yearly ok")

# EIA names as 'Nuclear, renewables, and other consumption': fossil share still right, low-carbon kept as one group
lines = []
for c in ["USA"] + [f"X{i:02d}" for i in range(60)]:
    for prod, nm, v in (("44", "Total energy consumption", 100), ("5", "Petroleum and other liquids consumption", 36), ("26", "Natural gas consumption", 33),
                        ("7", "Coal consumption", 10), ("79", "Nuclear, renewables, and other consumption", 21)):
        lines.append(_json.dumps({"series_id": f"INTL.{prod}-2-{c}-QBTU.A", "name": f"{nm}, {c}, Annual", "data": [["2023", v]]}))
buf2 = io.BytesIO()
with zipfile.ZipFile(buf2, "w") as z:
    z.writestr("INTL.txt", "\n".join(lines))
S._get = lambda u, **k: types.SimpleNamespace(headers={}, content=buf2.getvalue())
e = S.eia_energy()
u = e[(e.iso3 == "USA") & (e.year == 2023)].set_index("fuel").qbtu.to_dict()
assert u == {"oil": 36, "gas": 33, "coal": 10, "lowcarbon": 21, "total": 100}, u
# portal GDP that carries a scale flag that does not match its values
def sdmx_gdp2(u, **k):
    if "datamapper" in u:
        raise RuntimeError("HTTP 403")
    lines = ["DATAFLOW,COUNTRY,INDICATOR,FREQUENCY,SCALE,TIME_PERIOD,OBS_VALUE"] + [f"IMF.RES:WEO,{c},NGDPD,A,9,2025,{v}" for c, v in [("USA", 30861300000000)] + [(f"X{i:02d}", 1e11) for i in range(60)]]
    return types.SimpleNamespace(headers={}, text="\n".join(lines))
S._get = sdmx_gdp2
S.REL.pop("weo", None); S._WEO_FAIL.clear(); S._WEO_OK.clear()
d, rel = S.weo_all("NGDPD.us_dollars", ["WEO:latest"])
assert abs(d["USA"].iloc[-1] - 30861.3) < 1e-6, d["USA"]
print("eia grouped low-carbon + portal scale flag ok")

# CFTC Commitments of Traders (Socrata JSON): numbers arrive as strings
rows = [{"cftc_contract_market_code": c, "report_date_as_yyyy_mm_dd": f"2026-11-{d:02d}T00:00:00.000", "open_interest_all": str(1000 + d), "m_money_positions_long_all": "300",
         "m_money_positions_short_all": "100", "market_and_exchange_names": f"MKT {c}"} for c in ("067651", "088691", "002602") for d in (3, 10)]
S._get = lambda u, **k: types.SimpleNamespace(headers={}, json=lambda: rows)
cf = S.cftc_cot(["067651", "088691", "002602"], "72hh-3qpy", "2026-01-01")
assert len(cf) == 6 and cf.oi.max() == 1010 and S.REL["cftc"]["released"] == "2026-11-13", (cf.tail(), S.REL.get("cftc"))
print("cftc ok")
