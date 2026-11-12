"""Thin, fault-tolerant clients for free public data sources."""
import io
import time
from datetime import datetime

import pandas as pd
import requests

S = requests.Session()
S.headers["User-Agent"] = "worldeconomylive-open-data/0.1"
STATUS: dict = {}  # source key -> {"ok": bool, "note": str}


DEAD_HOSTS: dict = {}  # circuit breaker: host -> consecutive connection failures


def _get(url, timeout=45, tries=3):
    host = url.split("/")[2]
    if DEAD_HOSTS.get(host, 0) >= 3:
        raise RuntimeError(f"{host} unreachable (skipped)")
    last = None
    for i in range(tries):
        try:
            r = S.get(url, timeout=timeout)
            if r.status_code == 200:
                DEAD_HOSTS[host] = 0
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (400, 404):
                break  # bad code, don't retry
        except Exception as e:  # network errors
            last = str(e)[:120]
            DEAD_HOSTS[host] = DEAD_HOSTS.get(host, 0) + 1
            if DEAD_HOSTS[host] >= 3:
                break
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(last)


def log(key, ok, note=""):
    STATUS[key] = {"ok": ok, "note": note}


# ---------------- FRED (CSV endpoint, no key) ----------------
def fred(sid: str) -> pd.Series:
    r = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "v"]
    s = pd.Series(pd.to_numeric(df["v"], errors="coerce").values,
                  index=pd.to_datetime(df["date"]), name=sid).dropna()
    if s.empty:
        raise RuntimeError("empty")
    return s


# ---------------- DBnomics (IMF, OECD, Eurostat, BIS, ECB, national) ----------------
def dbnomics(series_id: str) -> pd.Series:
    r = _get(f"https://api.db.nomics.world/v22/series/{series_id}?observations=1&format=json")
    docs = r.json().get("series", {}).get("docs", [])
    if not docs:
        raise RuntimeError("not found")
    d = docs[0]
    vals = pd.to_numeric(pd.Series(d["value"]).replace("NA", None), errors="coerce")
    idx = pd.to_datetime(pd.Series(d["period"]).astype(str), errors="coerce")
    s = pd.Series(vals.values, index=idx, name=series_id).dropna()
    s = s[~s.index.isna()]
    if s.empty:
        raise RuntimeError("empty")
    return s.sort_index()


# ---------------- World Bank (annual, very stable codes) ----------------
def worldbank(indicator: str, iso3s: list) -> pd.DataFrame:
    url = (f"https://api.worldbank.org/v2/country/{';'.join(iso3s)}/indicator/{indicator}"
           f"?format=json&per_page=20000&date=1990:{datetime.utcnow().year}")
    j = _get(url).json()
    if not isinstance(j, list) or len(j) < 2 or j[1] is None:
        raise RuntimeError("no data")
    rows = [{"iso3": x["countryiso3code"], "year": int(x["date"]), "value": x["value"]}
            for x in j[1] if x.get("value") is not None]
    return pd.DataFrame(rows)


# ---------------- IMF PortWatch (ArcGIS feature services) ----------------
ARC = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"


def _arcgis(service: str, where: str, fields="*", order=None) -> list:
    out, offset = [], 0
    while True:
        url = (f"{ARC}/{service}/FeatureServer/0/query?where={requests.utils.quote(where)}"
               f"&outFields={fields}&returnGeometry=false&resultOffset={offset}"
               f"&resultRecordCount=1000&f=json")
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


def portwatch_ports() -> pd.DataFrame:
    return pd.DataFrame(_arcgis("PortWatch_ports_database", "1=1",
                                order="vessel_count_total DESC"))


def portwatch_port_daily(port_id: str, start: str) -> pd.DataFrame:
    where = f"portid = '{port_id.upper()}' AND date >= TIMESTAMP '{start} 00:00:00'"
    return _dated(_arcgis("Daily_Ports_Data", where))


def portwatch_chokepoint_daily(cp_id: str, start: str) -> pd.DataFrame:
    where = f"portid = '{cp_id.upper()}' AND date >= TIMESTAMP '{start} 00:00:00'"
    return _dated(_arcgis("Daily_Chokepoints_Data", where))
