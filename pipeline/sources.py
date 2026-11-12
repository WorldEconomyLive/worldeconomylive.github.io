"""Fault-tolerant clients for open, republishable public data sources.

Every source here allows free reuse with attribution (public domain or open licence):
OECD (CC BY 4.0), ECB, BIS, IMF (via DBnomics), Eurostat, World Bank (CC BY 4.0),
US Treasury and NY Fed (US government), IMF PortWatch.
"""
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import requests

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 worldeconomylive",
    "Accept-Language": "en-US,en;q=0.9",
})
STATUS: dict = {}          # key -> {"ok": bool, "note": str}
DEAD_HOSTS: dict = {}      # circuit breaker: host -> consecutive connection failures
MIN_GAP = {"sdmx.oecd.org": 4.0, "api.db.nomics.world": 0.4, "api.worldbank.org": 0.3, "stats.bis.org": 1.0}  # polite pacing (seconds)
_LAST: dict = {}


def log(key, ok, note=""):
    STATUS[key] = {"ok": bool(ok), "note": str(note)[:160]}


def _get(url, timeout=60, tries=4, headers=None):
    host = url.split("/")[2]
    if DEAD_HOSTS.get(host, 0) >= 8:
        raise RuntimeError(f"{host} unreachable")
    last = None
    for i in range(tries):
        gap = MIN_GAP.get(host, 0) - (time.time() - _LAST.get(host, 0))
        if gap > 0:
            time.sleep(gap)
        _LAST[host] = time.time()
        try:
            r = S.get(url, timeout=timeout, headers=headers)
            if r.status_code == 200:
                DEAD_HOSTS[host] = 0
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code == 429:  # rate limited: wait and retry
                wait = r.headers.get("Retry-After")
                time.sleep(min(float(wait), 120) if wait and wait.isdigit() else 45 * (i + 1))
                continue
            if r.status_code in (400, 401, 403, 404, 422):
                break
        except Exception as e:
            last = type(e).__name__
            DEAD_HOSTS[host] = DEAD_HOSTS.get(host, 0) + 1
            if DEAD_HOSTS[host] >= 8:
                break
        time.sleep(2 * (i + 1))
    raise RuntimeError(last or "failed")


def _series(values, dates, name):
    s = pd.Series(pd.to_numeric(pd.Series(values), errors="coerce").values,
                  index=pd.to_datetime(pd.Series(dates).astype(str), errors="coerce"), name=name)
    s = s[~s.index.isna()].dropna().sort_index()
    if s.empty:
        raise RuntimeError("empty")
    return s[~s.index.duplicated(keep="last")]


def _period_to_ts(p):
    p = str(p)
    m = re.match(r"^(\d{4})-?Q([1-4])$", p)
    if m:
        return f"{m.group(1)}-{3 * int(m.group(2)) - 2:02d}-01"
    m = re.match(r"^(\d{4})-?M?(\d{2})$", p)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    if re.match(r"^\d{4}$", p):
        return f"{p}-07-01"
    return p


# ---------------- OECD (SDMX REST, CC BY 4.0) ----------------
OECD = "https://sdmx.oecd.org/public/rest"
_DIMS: dict = {}


def oecd_dims(flow):
    """Dimension order for an OECD dataflow, e.g. 'OECD.SDD.STES,DSD_STES@DF_FINMARK'."""
    if flow in _DIMS:
        return _DIMS[flow]
    agency, fid = flow.split(",")[:2]
    r = _get(f"{OECD}/dataflow/{agency}/{fid}/latest?references=datastructure")
    root = ET.fromstring(r.content)
    dims = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "Dimension" and el.get("id"):
            dims.append((int(el.get("position") or len(dims) + 1), el.get("id")))
    if not dims:
        raise RuntimeError("no dimensions")
    _DIMS[flow] = [d for _, d in sorted(set(dims))]
    return _DIMS[flow]


_FRAMES: dict = {}


def oecd_frame(flow, key, start="2012-01"):
    if (flow, key, start) in _FRAMES:
        return _FRAMES[(flow, key, start)]
    r = _get(f"{OECD}/data/{flow}/{key}?startPeriod={start}&dimensionAtObservation=AllDimensions&format=csvfile",
             timeout=90)
    df = pd.read_csv(io.StringIO(r.text), dtype=str)
    if df.empty or "OBS_VALUE" not in df.columns:
        raise RuntimeError("empty")
    _FRAMES[(flow, key, start)] = df
    return df


def oecd_pick(flow, filters, prefer=None, start="2012-01"):
    """Fetch with known dimension filters, then choose the best single series using
    `prefer` = {column: [ordered acceptable values]}. Returns (series, chosen_attrs)."""
    dims = oecd_dims(flow)
    key = ".".join(filters.get(d, "") for d in dims)
    df = oecd_frame(flow, key, start)
    prefer = dict(prefer or {})
    req = prefer.pop("_require", None)
    if req and not any(c in df.columns for c in req):
        raise RuntimeError("required dimension missing")
    for col, wanted in prefer.items():
        if col in df.columns:
            sub = None
            for w in wanted:
                cand = df[df[col] == w]
                if len(cand):
                    sub = cand
                    break
            if sub is not None:
                df = sub
            elif req and col in req:
                raise RuntimeError(f"no {col} match")
    sk = [c for c in dims if c in df.columns and c != "TIME_PERIOD"]
    if sk:
        first = df.groupby(sk, dropna=False).size().sort_values(ascending=False).index[0]
        first = first if isinstance(first, tuple) else (first,)
        for c, v in zip(sk, first):
            df = df[df[c] == v]
    s = _series(df["OBS_VALUE"], df["TIME_PERIOD"].map(_period_to_ts), flow)
    attrs = {c: df[c].iloc[0] for c in df.columns if c not in ("OBS_VALUE", "TIME_PERIOD")}
    return s, attrs


def _choose(df, prefer, dims):
    prefer = dict(prefer or {})
    strict = prefer.pop("_strict", [])
    for col, wanted in prefer.items():
        if col not in df.columns:
            continue
        sub = None
        for w in wanted:
            cand = df[df[col] == w]
            if len(cand):
                sub = cand
                break
        if sub is not None:
            df = sub
        elif col in strict:
            return None
    sk = [c for c in dims if c in df.columns and c not in ("TIME_PERIOD", "REF_AREA")]
    if sk and len(df):
        first = df.groupby(sk, dropna=False).size().sort_values(ascending=False).index[0]
        first = first if isinstance(first, tuple) else (first,)
        for c, v in zip(sk, first):
            df = df[df[c] == v]
    return df if len(df) else None


def oecd_batch(spec, areas, start="2012-01"):
    """One request for all economies. Returns {iso3: (series, attrs)}."""
    flow = spec["flow"]
    variants = spec.get("filters_alt") or [spec.get("filters", {})]
    df, dims, last = None, None, None
    for filt in variants:
        try:
            if "key" in spec:
                key, dims = spec["key"].format(areas="+".join(areas)), []
            else:
                dims = oecd_dims(flow)
                f = dict(filt, REF_AREA="+".join(areas))
                key = ".".join(f.get(d, "") for d in dims)
            df = oecd_frame(flow, key, start)
            break
        except Exception as e:
            last = e
    if df is None:
        raise RuntimeError(str(last)[:60])
    dims = dims or [c for c in df.columns if c not in ("OBS_VALUE", "TIME_PERIOD")]
    out = {}
    for area, g in df.groupby("REF_AREA"):
        g = _choose(g, spec.get("prefer"), dims)
        if g is None:
            continue
        try:
            s = _series(g["OBS_VALUE"], g["TIME_PERIOD"].map(_period_to_ts), area)
        except RuntimeError:
            continue
        out[area] = (s, {c: g[c].iloc[0] for c in g.columns if c not in ("OBS_VALUE", "TIME_PERIOD")})
    return out


# ---------------- DBnomics (IMF WEO, Eurostat, BIS mirrors) ----------------
def dbnomics(series_id: str) -> pd.Series:
    r = _get(f"https://api.db.nomics.world/v22/series/{series_id}?observations=1&format=json")
    docs = r.json().get("series", {}).get("docs", [])
    if not docs:
        raise RuntimeError("not found")
    d = docs[0]
    vals = [None if v == "NA" else v for v in d["value"]]
    return _series(vals, [_period_to_ts(p) for p in d["period"]], series_id)


def weo_all(code, releases):
    """All countries for one WEO subject.unit. Returns ({iso3: series}, release_used)."""
    subj, unit = code.split(".")
    dims = json.dumps({"weo-subject": [subj], "unit": [unit]})
    for rel in releases:
        try:
            url = (f"https://api.db.nomics.world/v22/series/IMF/{rel}?dimensions={requests.utils.quote(dims)}"
                   f"&observations=1&limit=1000&format=json")
            docs = _get(url, timeout=90).json().get("series", {}).get("docs", [])
            out = {}
            for d in docs:
                iso = d.get("series_code", "").split(".")[0]
                try:
                    out[iso] = _series([None if v == "NA" else v for v in d["value"]],
                                       [_period_to_ts(p) for p in d["period"]], iso)
                except RuntimeError:
                    pass
            if out:
                return out, rel
        except Exception:
            continue
    raise RuntimeError("WEO unavailable")


# ---------------- BIS (central bank policy rates) ----------------
def bis_batch(codes):
    key = "+".join(sorted(set(codes)))
    for url in (f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{key}/all?detail=dataonly&format=csv",
                f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.{key}?format=csv"):
        try:
            df = pd.read_csv(io.StringIO(_get(url, timeout=90).text), dtype=str)
            area = "REF_AREA" if "REF_AREA" in df.columns else next(c for c in df.columns if "AREA" in c.upper())
            tcol = "TIME_PERIOD" if "TIME_PERIOD" in df.columns else df.columns[-2]
            out = {}
            for a, g in df.groupby(area):
                try:
                    out[a] = _series(g["OBS_VALUE"], g[tcol].map(_period_to_ts), a)
                except RuntimeError:
                    pass
            if out:
                return out
        except Exception:
            continue
    raise RuntimeError("BIS unavailable")

def bis_policy_rate(cc: str) -> pd.Series:
    for url in (f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{cc}/all?detail=dataonly&format=csv",
                f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.{cc}?format=csv"):
        try:
            df = pd.read_csv(io.StringIO(_get(url).text), dtype=str)
            tcol = "TIME_PERIOD" if "TIME_PERIOD" in df.columns else df.columns[-2]
            return _series(df["OBS_VALUE"], df[tcol].map(_period_to_ts), f"BIS {cc}")
        except Exception:
            continue
    raise RuntimeError("BIS unavailable")


# ---------------- World Bank (annual, CC BY 4.0) ----------------
def worldbank_all(indicator: str, since=2005) -> pd.DataFrame:
    """Every country for one indicator (one request). Columns: iso3, year, value."""
    url = (f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
           f"?format=json&per_page=20000&date={since}:{datetime.utcnow().year}")
    j = _get(url, timeout=150).json()
    if not isinstance(j, list) or len(j) < 2 or j[1] is None:
        raise RuntimeError("no data")
    rows = [{"iso3": x["countryiso3code"], "year": int(x["date"]), "value": x["value"]}
            for x in j[1] if x.get("value") is not None and x.get("countryiso3code")]
    if not rows:
        raise RuntimeError("no data")
    return pd.DataFrame(rows)


def worldbank(indicator: str, iso3s: list) -> pd.DataFrame:
    url = (f"https://api.worldbank.org/v2/country/{';'.join(iso3s)}/indicator/{indicator}"
           f"?format=json&per_page=20000&date=1995:{datetime.utcnow().year}")
    j = _get(url, timeout=120).json()
    if not isinstance(j, list) or len(j) < 2 or j[1] is None:
        raise RuntimeError("no data")
    rows = [{"iso3": x["countryiso3code"], "year": int(x["date"]), "value": x["value"]}
            for x in j[1] if x.get("value") is not None]
    if not rows:
        raise RuntimeError("no data")
    return pd.DataFrame(rows)


# ---------------- World Bank Pink Sheet (monthly commodity prices, CC BY 4.0) ----------------
PINK_URLS = [
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx",
    "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx",
    "https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx",
]


def pink_sheet() -> pd.DataFrame:
    urls = list(PINK_URLS)
    try:  # discover the current link from the commodity-markets page first
        html = _get("https://www.worldbank.org/en/research/commodity-markets", timeout=30).text
        found = re.findall(r'https?://[^"\']+CMO-Historical-Data-Monthly\.xlsx', html)
        urls = found[:1] + urls
    except Exception:
        pass
    last = None
    for u in urls:
        try:
            raw = pd.read_excel(io.BytesIO(_get(u, timeout=90).content), sheet_name="Monthly Prices", header=None)
            hdr = next(i for i in range(15) if raw.iloc[i].astype(str).str.contains("Crude oil", case=False).any())
            cols = [str(c).strip() for c in raw.iloc[hdr]]
            df = raw.iloc[hdr + 1:].copy()
            df.columns = cols
            first = df.columns[0]
            df = df[df[first].astype(str).str.match(r"^\d{4}M\d{2}$")]
            df.index = pd.to_datetime(df[first].astype(str).str.replace("M", "-") + "-01")
            df = df.drop(columns=[first]).apply(pd.to_numeric, errors="coerce")
            df = df.loc[:, [c for c in df.columns if c and c != "nan"]]
            if len(df) > 100:
                return df
        except Exception as e:
            last = str(e)[:80]
    raise RuntimeError(last or "pink sheet unavailable")


# ---------------- ECB exchange rates (per 1 EUR) ----------------
def ecb_fx(currencies: list, start: str) -> pd.DataFrame:
    url = (f"https://data-api.ecb.europa.eu/service/data/EXR/D.{'+'.join(currencies)}.EUR.SP00.A"
           f"?startPeriod={start}&format=csvdata&detail=dataonly")
    df = pd.read_csv(io.StringIO(_get(url, timeout=60).text))
    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])
    out = df.pivot_table(index="TIME_PERIOD", columns="CURRENCY", values="OBS_VALUE").sort_index()
    if out.empty:
        raise RuntimeError("empty")
    return out


# ---------------- US Treasury (daily yield curves, public domain) ----------------
def treasury_curve(kind="daily_treasury_yield_curve", years=None) -> pd.DataFrame:
    years = years or [datetime.utcnow().year - 1, datetime.utcnow().year]
    frames = []
    for y in years:
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
               f"daily-treasury-rates.csv/{y}/all?type={kind}&field_tdr_date_value={y}&page&_format=csv")
        try:
            frames.append(pd.read_csv(io.StringIO(_get(url, timeout=60).text)))
        except Exception:
            continue
    if not frames:
        raise RuntimeError("treasury unavailable")
    df = pd.concat(frames)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index().apply(pd.to_numeric, errors="coerce")


def treasury_debt() -> pd.Series:
    url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
           "?fields=record_date,tot_pub_debt_out_amt&sort=-record_date&page[size]=800")
    d = _get(url).json()["data"]
    return _series([x["tot_pub_debt_out_amt"] for x in d], [x["record_date"] for x in d], "US debt")


def nyfed_effr() -> pd.Series:
    d = _get("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/500.json").json()["refRates"]
    return _series([x["percentRate"] for x in d], [x["effectiveDate"] for x in d], "EFFR")


# ---------------- IMF PortWatch (ArcGIS) ----------------
ARC = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"


def _arcgis(service, where, order=None):
    out, offset = [], 0
    while True:
        url = (f"{ARC}/{service}/FeatureServer/0/query?where={requests.utils.quote(where)}"
               f"&outFields=*&returnGeometry=false&resultOffset={offset}&resultRecordCount=1000&f=json")
        if order:
            url += f"&orderByFields={requests.utils.quote(order)}"
        j = _get(url).json()
        feats = j.get("features", [])
        out += [f["attributes"] for f in feats]
        if not j.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
    return out


def _dated(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=df["day"]))
    return df


def portwatch_ports():
    return pd.DataFrame(_arcgis("PortWatch_ports_database", "1=1", order="vessel_count_total DESC"))


def portwatch_port_daily(pid, start):
    return _dated(_arcgis("Daily_Ports_Data", f"portid = '{pid.upper()}' AND date >= TIMESTAMP '{start} 00:00:00'"))


def portwatch_chokepoint_daily(cid, start):
    return _dated(_arcgis("Daily_Chokepoints_Data", f"portid = '{cid.upper()}' AND date >= TIMESTAMP '{start} 00:00:00'"))
