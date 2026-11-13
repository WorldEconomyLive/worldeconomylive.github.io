"""Fault-tolerant clients for open, republishable public data sources.

Every source here allows free reuse with attribution (public domain or open licence):
OECD (CC BY 4.0), ECB, BIS, IMF (via DBnomics), Eurostat, World Bank (CC BY 4.0),
US Treasury and NY Fed (US government), IMF PortWatch.
"""
import io
import zipfile
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
MIN_GAP = {"ec.europa.eu": 0.5, "sdmx.oecd.org": 4.0, "api.db.nomics.world": 0.4, "api.worldbank.org": 0.3, "stats.bis.org": 1.0}  # polite pacing (seconds)
_LAST: dict = {}
import threading
_LOCK = threading.Lock()
_HOST_LOCKS: dict = {}


def _pace(host):
    with _LOCK:
        lk = _HOST_LOCKS.setdefault(host, threading.Lock())
    with lk:
        gap = MIN_GAP.get(host, 0) - (time.time() - _LAST.get(host, 0))
        if gap > 0:
            time.sleep(gap)
        _LAST[host] = time.time()


REL: dict = {}      # release metadata per source key: {"source", "released" (YYYY-MM-DD from the source), "basis", "label"}


def parse_when(x):
    """ISO string, epoch seconds/ms, or HTTP date -> 'YYYY-MM-DD' (None if unparseable)."""
    if x in (None, "", 0):
        return None
    try:
        if isinstance(x, (int, float)) or (isinstance(x, str) and x.isdigit()):
            v = float(x)
            v = v / 1000 if v > 1e11 else v
            return datetime.utcfromtimestamp(v).strftime("%Y-%m-%d")
        if isinstance(x, str) and re.match(r"^[A-Za-z]{3}, \d", x):
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(x).strftime("%Y-%m-%d")
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    except Exception:
        return None


def set_rel(key, source, released=None, basis="source", label=None):
    """Record when the source itself published the data. basis: 'source' (date from the source's own metadata),
    'daily' (source publishes each business day; the latest observation date is the publication day), or None."""
    cur = REL.get(key)
    released = parse_when(released) if released else None
    if released and released > (datetime.utcnow() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"):
        released = None                     # never trust a date in the future
    if cur and cur.get("released") and (not released or cur["released"] >= released):
        return
    REL[key] = {"source": source, "released": released, "basis": basis if released else None, "label": label}


def log(key, ok, note=""):
    STATUS[key] = {"ok": bool(ok), "note": str(note)[:160]}


def _get(url, timeout=60, tries=4, headers=None):
    host = url.split("/")[2]
    if DEAD_HOSTS.get(host, 0) >= 8:
        raise RuntimeError(f"{host} unreachable")
    last = None
    for i in range(tries):
        _pace(host)
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
            if r.status_code >= 500 and i >= 2:   # server error twice more: give up, fallbacks take over
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


def oecd_release(flow, key):
    """OECD publishes each dataflow's last-update time as validFrom on its content constraint."""
    agency, fid = flow.split(",")[:2]
    try:
        r = _get(f"{OECD}/contentconstraint/{agency}/CR_A_{fid}/", timeout=60, tries=2)
        found = re.findall(r'validFrom="([^"]+)"', r.text) or re.findall(r"<(?:\w+:)?ValidFrom>([^<]+)<", r.text)
        set_rel(key, "OECD", max(found) if found else None, basis="dataset")
    except Exception:
        set_rel(key, "OECD", None)


def oecd_frame(flow, key, start="2003-01"):
    if (flow, key, start) in _FRAMES:
        return _FRAMES[(flow, key, start)]
    r = _get(f"{OECD}/data/{flow}/{key}?startPeriod={start}&dimensionAtObservation=AllDimensions&format=csvfile",
             timeout=90)
    df = pd.read_csv(io.StringIO(r.text), dtype=str)
    if df.empty or "OBS_VALUE" not in df.columns:
        raise RuntimeError("empty")
    _FRAMES[(flow, key, start)] = df
    return df


def oecd_pick(flow, filters, prefer=None, start="2003-01"):
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
            df = df[df[c].isna()] if pd.isna(v) else df[df[c] == v]
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


_NOT_DIMS = {"OBS_VALUE", "TIME_PERIOD", "STRUCTURE", "STRUCTURE_ID", "STRUCTURE_NAME", "ACTION", "OBS_STATUS",
             "OBS_STATUS_2", "UNIT_MULT", "DECIMALS", "BASE_PER", "CONF_STATUS", "PRICE_BASE_ATTR", "TIME_FORMAT"}


def oecd_batch(spec, areas, start="2003-01"):
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
    if not dims:
        try:
            dims = oecd_dims(flow)
        except Exception:
            dims = [c for c in df.columns if c not in _NOT_DIMS and df[c].notna().all()]
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
    set_rel("dbn:" + series_id.split("/")[0] + "/" + series_id.split("/")[1], series_id.split("/")[0] + " (via DBnomics)",
            d.get("provider_updated_at") or d.get("updated_at"))
    vals = [None if v == "NA" else v for v in d["value"]]
    return _series(vals, [_period_to_ts(p) for p in d["period"]], series_id)


_DM_LABEL = {}
ALIAS3 = {"UVK": "XKX", "KOS": "XKX"}   # the IMF codes Kosovo UVK; the World Bank (and this site) use XKX


def weo_datamapper(subj):
    """IMF DataMapper API: the current WEO edition, served by the IMF itself. Returns {iso3: annual series}."""
    base = "https://www.imf.org/external/datamapper/api/v1"
    hdr = dict(IMF_HDR, Accept="application/json")
    j = _get(f"{base}/{subj}", timeout=90, tries=3, headers=hdr).json()
    vals = (j.get("values") or {}).get(subj) or {}
    out = {}
    for iso, by in vals.items():
        iso = ALIAS3.get(iso, iso)
        if len(iso) != 3 or not by:
            continue
        try:
            out[iso] = _series(list(by.values()), [f"{y}-07-01" for y in by.keys()], iso)
        except RuntimeError:
            pass
    if len(out) < 50:
        raise RuntimeError("DataMapper returned too few countries")
    if not _DM_LABEL:
        try:
            ind = _get(f"{base}/indicators", timeout=60, tries=2, headers=hdr).json().get("indicators", {})
            src = str((ind.get(subj) or {}).get("source", ""))
            m = re.search(r"(January|April|July|October)\s+(\d{4})", src)
            _DM_LABEL["label"] = f"WEO {m.group(1)} {m.group(2)}" if m else "WEO (current edition)"
        except Exception:
            _DM_LABEL["label"] = "WEO (current edition)"
        set_rel("weo", "IMF World Economic Outlook (IMF DataMapper)", None, label=_DM_LABEL["label"])
    return out


IMF_HDR = {"User-Agent": "Mozilla/5.0 (compatible; WorldEconomyLive/1.0)"}
_WEO_OK = set()
_WEO_FAIL = {}     # route -> first error, so a dead route is tried once per run and its error reaches the status panel


def _weo_label_now():
    """WEO editions come out in April and October: name the edition current today."""
    t = datetime.utcnow()
    if (t.month, t.day) >= (10, 15):
        return f"WEO October {t.year}"
    if (t.month, t.day) >= (4, 15):
        return f"WEO April {t.year}"
    return f"WEO October {t.year - 1}"


DM_BILLIONS = {"NGDPD", "PPPGDP", "NGDP"}   # WEO subjects DataMapper (and the registry scales) report in billions
_MULT_WORDS = {"units": 0, "thousands": 3, "millions": 6, "billions": 9, "trillions": 12}


def _sdmx_mult(df):
    """Per-row multiplier from an SDMX unit-multiplier / scale column (exponent or word); 1 when absent."""
    col = next((c for c in df.columns if c.upper() in ("UNIT_MULT", "SCALE", "UNIT_MULTIPLIER")), None)
    if col is None:
        return 1.0

    def one(x):
        x = str(x).strip().lower()
        if x in _MULT_WORDS:
            return 10.0 ** _MULT_WORDS[x]
        try:
            return 10.0 ** int(float(x))
        except ValueError:
            return 1.0
    return df[col].map(one).astype(float)


def weo_sdmx(subj):
    """IMF data portal (SDMX), the WEO's home since October 2025: COUNTRY.INDICATOR.FREQUENCY, all countries."""
    tries = [
        (f"https://api.imf.org/external/sdmx/2.1/data/IMF.RES,WEO/.{subj}.A?startPeriod=1980",
         "application/vnd.sdmx.data+csv;version=1.0.0"),
        (f"https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/*.{subj}.A?c[TIME_PERIOD]=ge:1980",
         "application/vnd.sdmx.data+csv;version=2.0.0"),
    ]
    last = None
    for url, acc in tries:
        try:
            r = _get(url, timeout=120, tries=2, headers=dict(IMF_HDR, Accept=acc))
            df = pd.read_csv(io.StringIO(r.text), dtype=str)
            cc = next(c for c in df.columns if c.upper() in ("COUNTRY", "REF_AREA") or c.upper().startswith("COUNTRY"))
            tc = next(c for c in df.columns if c.upper() == "TIME_PERIOD")
            vc = next(c for c in df.columns if c.upper() == "OBS_VALUE")
            df[vc] = pd.to_numeric(df[vc], errors="coerce")
            if subj in DM_BILLIONS:
                # DataMapper (and the registry scales) use billions. The portal's scale flag has not matched its values
                # in practice, so decide by size: no country's GDP reaches a million billion dollars.
                if df[vc].abs().median() > 1e6:
                    df[vc] = df[vc] / 1e9
            else:
                df[vc] = df[vc] * _sdmx_mult(df)
            out = {}
            for iso, g in df.groupby(cc):
                iso = ALIAS3.get(str(iso), str(iso))
                if len(iso) != 3:
                    continue
                try:
                    out[iso] = _series(g[vc], [f"{str(y)[:4]}-07-01" for y in g[tc]], iso)
                except RuntimeError:
                    pass
            if len(out) < 50:
                raise RuntimeError(f"only {len(out)} countries")
            set_rel("weo", "IMF World Economic Outlook (IMF data portal)", None, label=_weo_label_now())
            return out
        except Exception as e:
            last = e
    raise RuntimeError(f"IMF data portal: {last}")


def weo_all(code, releases):
    """All countries for one WEO subject.unit. Returns ({iso3: series}, release_used).
    Order: IMF DataMapper, then the IMF data portal (both the IMF itself), then the DBnomics mirror,
    which can lag several WEO editions and is flagged as an older copy when used."""
    subj, unit = code.split(".")
    for route, fn, lab in (("datamapper", weo_datamapper, lambda: _DM_LABEL.get("label", "WEO (current edition)")),
                           ("sdmx", weo_sdmx, _weo_label_now)):
        if route in _WEO_FAIL and route not in _WEO_OK:
            continue                       # a route that never worked this run is not retried for every subject
        try:
            out = fn(subj)
            _WEO_OK.add(route)
            return out, lab()
        except Exception as e:
            _WEO_FAIL[route] = f"{type(e).__name__}: {e}"
            log(f"weo.imf_{route}", False, f"{subj}: {_WEO_FAIL[route]}")
    dims = json.dumps({"weo-subject": [subj], "unit": [unit]})
    for rel in releases:
        try:
            url = (f"https://api.db.nomics.world/v22/series/IMF/{rel}?dimensions={requests.utils.quote(dims)}"
                   f"&observations=1&limit=1000&format=json")
            docs = _get(url, timeout=90).json().get("series", {}).get("docs", [])
            out = {}
            for d in docs:
                iso = d.get("series_code", "").split(".")[0]
                iso = ALIAS3.get(iso, iso)
                try:
                    out[iso] = _series([None if v == "NA" else v for v in d["value"]],
                                       [_period_to_ts(p) for p in d["period"]], iso)
                except RuntimeError:
                    pass
            if out:
                if "weo" not in REL:
                    lab = None
                    try:
                        dj = _get(f"https://api.db.nomics.world/v22/datasets/IMF/{rel}?format=json", timeout=60, tries=2).json()
                        doc = (dj.get("datasets", {}).get("docs") or [{}])[0]
                        m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
                                      str(doc.get("name", "")) + " " + str(doc.get("description", "")))
                        lab = f"WEO {m.group(1)} {m.group(2)}" if m else None
                        upd = doc.get("updated_at") or doc.get("provider_updated_at")
                    except Exception:
                        upd = None
                    cur = _weo_label_now()
                    flag = "" if lab == cur else f" (older copy via DBnomics; IMF unreachable; current edition is {cur.replace('WEO ', '')})"
                    set_rel("weo", "IMF World Economic Outlook (via DBnomics)", upd, label=(lab or rel) + flag)
                    REL["weo"]["stale"] = lab != cur
                    log("weo.fallback", lab == cur, f"using DBnomics {lab or rel}" + ("" if lab == cur else f"; current edition is {cur}"))
                return out, rel
        except Exception:
            continue
    raise RuntimeError("WEO unavailable: " + "; ".join(f"{k}: {v}" for k, v in _WEO_FAIL.items()))


# ---------------- BIS (central bank policy rates) ----------------
def bis_batch(codes):
    key = "+".join(sorted(set(codes)))
    for url in (f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{key}/all?detail=dataonly&format=csv",
                f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.{key}?format=csv"):
        try:
            resp = _get(url, timeout=90)
            set_rel("bis", "BIS", resp.headers.get("Last-Modified"))
            df = pd.read_csv(io.StringIO(resp.text), dtype=str)
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
def worldbank_all(indicator: str, since=2003) -> pd.DataFrame:
    """Every country for one indicator (one request). Columns: iso3, year, value."""
    url = (f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
           f"?format=json&per_page=20000&date={since}:{datetime.utcnow().year}")
    j = _get(url, timeout=150).json()
    if not isinstance(j, list) or len(j) < 2 or j[1] is None:
        raise RuntimeError("no data")
    set_rel(f"wb:{indicator}", "World Bank", (j[0] or {}).get("lastupdated"), basis="dataset",
            label="World Development Indicators")
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
            top = " ".join(str(v) for v in raw.iloc[:8].values.ravel() if str(v) != "nan")
            m = re.search(r"[Uu]pdated(?: on)?[:\s]+([A-Za-z]+ \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", top)
            set_rel("pink", "World Bank Pink Sheet", m.group(1) if m else None)
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
    set_rel("ecb", "ECB", out.index[-1], basis="daily")
    return out


# ---------------- US Treasury (daily yield curves, public domain) ----------------
def treasury_curve(kind="daily_treasury_yield_curve", years=None) -> pd.DataFrame:
    years = years or list(range(datetime.utcnow().year - 21, datetime.utcnow().year + 1))
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
    df = df.set_index("Date").sort_index().apply(pd.to_numeric, errors="coerce")
    set_rel("treasury", "US Treasury", df.index[-1], basis="daily")
    return df


def treasury_debt() -> pd.Series:
    url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
           "?fields=record_date,tot_pub_debt_out_amt&sort=-record_date&page[size]=6000")
    d = _get(url, timeout=90).json()["data"]
    set_rel("fiscaldata", "US Treasury Fiscal Data", d[0]["record_date"] if d else None, basis="daily")
    return _series([x["tot_pub_debt_out_amt"] for x in d], [x["record_date"] for x in d], "US debt")


def us_fiscal_years():
    """US federal receipts, outlays and surplus/deficit by fiscal year (Oct-Sep) from the Monthly Treasury Statement,
    Table 1 'Year-to-Date' lines (full year in each September statement; year to date in the latest statement)."""
    base = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_1"
    flds = "record_date,record_fiscal_year,record_calendar_month,classification_desc,print_order_nbr," \
           "current_month_gross_rcpt_amt,current_month_gross_outly_amt,current_month_dfct_sur_amt"
    r = _get(f"{base}?fields={flds}&filter=classification_desc:eq:Year-to-Date&sort=-record_date&page[size]=1000", timeout=90)
    set_rel("mts", "US Treasury, Monthly Treasury Statement", r.headers.get("Last-Modified"))
    df = pd.DataFrame(r.json().get("data", []))
    if df.empty:
        raise RuntimeError("no MTS rows")
    for c in ("current_month_gross_rcpt_amt", "current_month_gross_outly_amt", "print_order_nbr"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["record_date"] = pd.to_datetime(df["record_date"])
    # each statement prints the prior year's block first; the current fiscal year's Year-to-Date line is printed last
    cur = df.sort_values("print_order_nbr").groupby("record_date").tail(1)
    rows = []
    for _, x in cur.sort_values("record_date").iterrows():
        rows.append({"fy": int(x["record_fiscal_year"]), "through": x["record_date"],
                     "receipts": float(x["current_month_gross_rcpt_amt"]), "outlays": float(x["current_month_gross_outly_amt"])})
    return pd.DataFrame(rows)


def nyfed_effr() -> pd.Series:
    end = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        d = _get(f"https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2000-01-01&endDate={end}",
                 timeout=90).json()["refRates"]
    except Exception:
        d = _get("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/500.json").json()["refRates"]
    if d:
        set_rel("nyfed", "Federal Reserve Bank of New York", max(x["effectiveDate"] for x in d), basis="daily")
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


def portwatch_release(service, key):
    try:
        j = _get(f"{ARC}/{service}/FeatureServer/0?f=json", timeout=60, tries=2).json()
        ei = j.get("editingInfo") or {}
        set_rel(key, "IMF PortWatch", ei.get("dataLastEditDate") or ei.get("lastEditDate"), basis="dataset")
    except Exception:
        set_rel(key, "IMF PortWatch", None)


def portwatch_port_daily(pid, start):
    return _dated(_arcgis("Daily_Ports_Data", f"portid = '{pid.upper()}' AND date >= TIMESTAMP '{start} 00:00:00'"))


def portwatch_chokepoint_daily(cid, start):
    return _dated(_arcgis("Daily_Chokepoints_Data", f"portid = '{cid.upper()}' AND date >= TIMESTAMP '{start} 00:00:00'"))


# ---------------- Ember monthly electricity (CC BY 4.0) ----------------
EMBER_URLS = [
    "https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_monthly_global.csv",
    "https://files.ember-energy.org/public-downloads/monthly_full_release_long_format.csv",
    "https://storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/monthly_full_release_long_format.csv",
]


_AREA_FIX = {"Türkiye": "TUR", "Turkey": "TUR", "Russia": "RUS", "South Korea": "KOR", "Korea": "KOR",
             "Taiwan": "TWN", "Vietnam": "VNM", "Iran": "IRN", "Czechia": "CZE", "Bolivia": "BOL",
             "Venezuela": "VEN", "Tanzania": "TZA", "Moldova": "MDA", "Kosovo": "XKX", "United States": "USA",
             "United Kingdom": "GBR", "Laos": "LAO", "Syria": "SYR", "North Macedonia": "MKD"}


def _area_iso3(name):
    name = str(name).strip()
    if name in _AREA_FIX:
        return _AREA_FIX[name]
    try:
        import pycountry
        return pycountry.countries.lookup(name).alpha_3
    except Exception:
        return None


def _col(cols, *keys, exclude=()):
    for k in keys:
        for low, c in cols.items():
            if k in low and not any(x in low for x in exclude):
                return c
    return None


EMBER_CLEAN: dict = {}     # {"df": DataFrame(iso3, year, value)}: low-carbon share of generation, completed years


def _ember_clean(df, cols, date, src, val):
    """Share of electricity generation from low-carbon sources (Ember's 'Clean' aggregate: renewables + nuclear),
    by calendar year, from the same monthly file: clean TWh / total generation TWh, years with all 12 months."""
    gen = _col(cols, "generation (twh)", exclude=("change", "share")) or val
    unit = cols.get("unit")
    x = df
    if unit and gen == val:
        x = x[x[unit].astype(str).str.upper().str.contains("TWH")]
    name = x[src].astype(str).str.strip().str.lower()
    iso = _col(cols, "iso 3", "iso3", "country code", "iso")
    if iso:
        codes = x[iso]
    else:
        area = _col(cols, "area", "country", "entity", exclude=("type", "member"))
        codes = x[area].map(_area_iso3)
    t = pd.DataFrame({"iso3": codes.values, "date": pd.to_datetime(x[date], errors="coerce").values,
                      "v": pd.to_numeric(x[gen], errors="coerce").values, "n": name.values}).dropna()
    t = t[t.iso3.astype(str).str.len() == 3]
    cl = t[t.n == "clean"].groupby(["iso3", t.date.dt.year])["v"].agg(["sum", "count"])
    tot = t[t.n.isin(["total generation", "total"])].groupby(["iso3", t.date.dt.year])["v"].agg(["sum", "count"])
    j = cl.join(tot, lsuffix="_c", rsuffix="_t", how="inner")
    j = j[(j.count_c == 12) & (j.count_t == 12) & (j.sum_t > 0)]
    if len(j) < 50:
        raise RuntimeError(f"only {len(j)} country-years")
    out = (j.sum_c / j.sum_t * 100).rename("value").reset_index()
    out.columns = ["iso3", "year", "value"]
    EMBER_CLEAN["df"] = out
    log("ember.clean_share", True, f"{out.iso3.nunique()} countries")


def ember_monthly() -> pd.DataFrame:
    """Monthly electricity demand (TWh) by ISO3. Columns: iso3, date, value.
    Handles Ember's July-2026 wide format (one row per area/month/source, metrics as columns)
    and the older long format (Variable/Unit/Value rows)."""
    last = None
    for u in EMBER_URLS:
        try:
            resp = _get(u, timeout=180)
            df = pd.read_csv(io.BytesIO(resp.content), low_memory=False)
            set_rel("ember", "Ember", resp.headers.get("Last-Modified"))
            cols = {str(c).lower().strip(): c for c in df.columns}
            date = _col(cols, "date", "month", exclude=("change",))
            src = _col(cols, "electricity source", "variable", "source", exclude=("aggregat",))
            val = (_col(cols, "demand (twh)") or _col(cols, "generation (twh)", exclude=("change", "share"))
                   or _col(cols, "value", exclude=("change",)))
            if not (date and src and val):
                raise RuntimeError(f"columns: {list(df.columns)[:8]}")
            try:
                _ember_clean(df, cols, date, src, val)
            except Exception as e:
                log("ember.clean_share", False, e)
            d = df[df[src].astype(str).str.strip().str.lower() == "demand"]
            unit = cols.get("unit")
            if unit and len(d):
                d = d[d[unit].astype(str).str.upper().str.contains("TWH")]
            iso = _col(cols, "iso 3", "iso3", "country code", "iso")
            if iso:
                codes = d[iso]
            else:
                area = _col(cols, "area", "country", "entity", exclude=("type", "member"))
                codes = d[area].map(_area_iso3)
            out = pd.DataFrame({"iso3": codes, "date": pd.to_datetime(d[date], errors="coerce"),
                                "value": pd.to_numeric(d[val], errors="coerce")}).dropna()
            out = out[out.iso3.astype(str).str.len() == 3]
            if len(out) > 100:
                return out
            last = f"only {len(out)} demand rows ({len(d)} raw)"
        except Exception as e:
            last = (str(e) or type(e).__name__)[:80]
    raise RuntimeError(last or "ember unavailable")


# ---------------- CFTC Commitments of Traders (U.S. government work, public domain) ----------------
def cftc_cot(codes, dataset, since):
    """Weekly futures-only positions for the given contract market codes since a date.
    Columns: code, date, oi, mm_long, mm_short, name (the CFTC's own market and exchange name)."""
    q = ",".join(f"'{c}'" for c in codes)
    url = (f"https://publicreporting.cftc.gov/resource/{dataset}.json?$limit=50000"
           f"&$where=cftc_contract_market_code%20in({requests.utils.quote(q)})%20AND%20report_date_as_yyyy_mm_dd%20>=%20'{since}'"
           f"&$order=report_date_as_yyyy_mm_dd")
    j = _get(url, timeout=120).json()
    if not isinstance(j, list) or not j:
        raise RuntimeError("no rows")
    pick = lambda d, *ks: next((d[k] for k in ks if k in d), None)   # noqa: E731
    rows = [{"code": str(pick(d, "cftc_contract_market_code")), "date": pd.Timestamp(str(pick(d, "report_date_as_yyyy_mm_dd"))[:10]),
             "oi": pick(d, "open_interest_all"), "mm_long": pick(d, "m_money_positions_long_all"),
             "mm_short": pick(d, "m_money_positions_short_all"), "name": pick(d, "market_and_exchange_names")} for d in j]
    df = pd.DataFrame(rows)
    for c in ("oi", "mm_long", "mm_short"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["oi"]).sort_values(["code", "date"])
    if df.code.nunique() < 3:
        raise RuntimeError(f"only {df.code.nunique()} markets")
    last = df.date.max()
    set_rel("cftc", "U.S. Commodity Futures Trading Commission", (last + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
            label="Commitments of Traders")
    return df


# ---------------- Electricity by source, yearly (Ember, CC BY 4.0) ----------------
EMBER_YEARLY_URLS = [
    "https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_yearly_global.csv",
    "https://files.ember-energy.org/public-downloads/yearly_full_release_long_format.csv",
    "https://storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/yearly_full_release_long_format.csv",
]
ELEC_SOURCES = {"coal": "coal", "gas": "gas", "other fossil": "other_fossil", "nuclear": "nuclear", "hydro": "hydro",
                "wind": "wind", "solar": "solar", "bioenergy": "bio", "other renewables": "other_ren"}


def ember_yearly() -> pd.DataFrame:
    """Electricity generation by source and year. Columns: iso3, year, source (ELEC_SOURCES values), twh.
    Handles Ember's 2026 wide format (metrics as columns) and the older long format (Variable/Unit/Value)."""
    last = None
    for u in EMBER_YEARLY_URLS:
        try:
            resp = _get(u, timeout=240)
            df = pd.read_csv(io.BytesIO(resp.content), low_memory=False)
            cols = {str(c).lower().strip(): c for c in df.columns}
            year = cols.get("year") or _col(cols, "date", exclude=("change",))
            src = _col(cols, "electricity source", "variable", exclude=("aggregat",))
            gen = _col(cols, "generation (twh)", exclude=("change", "share"))
            val = gen or _col(cols, "value", exclude=("change",))
            if not (year and src and val):
                raise RuntimeError(f"columns: {list(df.columns)[:8]}")
            x = df
            unit = cols.get("unit")
            if unit and not gen:
                x = x[x[unit].astype(str).str.upper().str.strip() == "TWH"]
            name = x[src].astype(str).str.strip().str.lower()
            x = x[name.isin(ELEC_SOURCES)]
            iso = _col(cols, "iso 3", "iso3", "country code")
            codes = x[iso] if iso else x[_col(cols, "area", "country", exclude=("type", "member"))].map(_area_iso3)
            yr = pd.to_numeric(x[year].astype(str).str[:4], errors="coerce")
            out = pd.DataFrame({"iso3": codes.values, "year": yr.values, "source": x[src].astype(str).str.strip().str.lower().map(ELEC_SOURCES).values,
                                "twh": pd.to_numeric(x[val], errors="coerce").values}).dropna()
            out = out[out.iso3.astype(str).str.len() == 3]
            out["year"] = out["year"].astype(int)
            if out.iso3.nunique() < 50:
                raise RuntimeError(f"only {out.iso3.nunique()} countries")
            set_rel("ember_yearly", "Ember", resp.headers.get("Last-Modified"), label="Yearly Electricity Data")
            return out.groupby(["iso3", "year", "source"], as_index=False)["twh"].sum()
        except Exception as e:
            last = (str(e) or type(e).__name__)[:100]
    raise RuntimeError(last or "ember yearly unavailable")


# ---------------- Energy consumption by fuel (U.S. EIA International Energy Statistics, public domain) ----------------
EIA_INTL_URLS = ["https://api.eia.gov/bulk/INTL.zip", "http://api.eia.gov/bulk/INTL.zip"]
ENERGY_FUELS = ("oil", "gas", "coal", "nuclear", "renewables", "lowcarbon")


def _eia_fuel(name):
    """Fuel group from an EIA series name such as 'Coal consumption, Germany, Annual' or
    'Nuclear, renewables, and other consumption, ...'. Components (wind, solar, ...) and non-primary series are skipped."""
    n = str(name).lower()
    if " consumption" not in n:
        return None
    n = n.split(" consumption")[0].strip()
    if any(w in n for w in ("per capita", "electricity", "intensity", "per gdp", "net generation")):
        return None
    if n.startswith("total") or "primary energy" in n:
        return "total"
    if "nuclear" in n and "renew" in n:
        return "_nre"
    if n.startswith("coal"):
        return "coal"
    if "natural gas" in n:
        return "gas"
    if n.startswith(("petroleum", "crude oil", "oil", "liquids", "other liquids")):
        return "oil"
    if n.startswith("nuclear"):
        return "nuclear"
    if n.startswith("renew"):
        return "renewables"
    if n.startswith("hydro"):
        return "_hydro"
    if n.startswith(("non-hydro", "nonhydro", "other renewables")):
        return "_nonhydro"
    return None


def eia_energy() -> pd.DataFrame:
    """Primary energy consumption by fuel, quadrillion Btu. Columns: iso3, year, fuel, qbtu.
    From the EIA bulk file: series INTL.{product}-{activity}-{ISO3}-{unit}.A, activity 2 = consumption, unit QBTU."""
    import zipfile
    last = None
    for u in EIA_INTL_URLS:
        try:
            resp = _get(u, timeout=300, tries=2)
            z = zipfile.ZipFile(io.BytesIO(resp.content))
            rows = []
            with z.open(z.namelist()[0]) as f:
                for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                    if '"series_id"' not in line or "QBTU" not in line:
                        continue
                    o = json.loads(line)
                    sid = str(o.get("series_id", ""))
                    if not (sid.startswith("INTL.") and sid.endswith(".A")):
                        continue
                    parts = sid[5:-2].split("-")
                    if len(parts) != 4 or parts[1] != "2" or parts[3] != "QBTU" or len(parts[2]) != 3:
                        continue
                    fuel = _eia_fuel(o.get("name", ""))
                    if not fuel:
                        continue
                    for y, v in o.get("data") or []:
                        try:
                            rows.append((parts[2], int(str(y)[:4]), fuel, float(v)))
                        except (TypeError, ValueError):
                            pass
            df = pd.DataFrame(rows, columns=["iso3", "year", "fuel", "qbtu"]).drop_duplicates(["iso3", "year", "fuel"])
            if df.iso3.nunique() < 50:
                raise RuntimeError(f"only {df.iso3.nunique()} countries; fuels seen: {sorted(df.fuel.unique())[:8]}")
            w = df.pivot_table(index=["iso3", "year"], columns="fuel", values="qbtu", aggfunc="first")
            col = lambda c: w[c] if c in w.columns else pd.Series(float("nan"), index=w.index)   # noqa: E731
            fos = col("oil").fillna(0) + col("gas").fillna(0) + col("coal").fillna(0)
            ren = col("renewables")
            parts = col("_hydro").fillna(0) + col("_nonhydro").fillna(0)
            ren = ren.fillna(parts.where(parts > 0))
            nuc = col("nuclear")
            ren = ren.fillna((col("_nre") - nuc.fillna(0)).where(col("_nre").notna() & nuc.notna()))
            # whatever the split, low-carbon = total - fossil, so the fossil share is always right
            low = col("_nre").fillna(nuc.fillna(0) + ren.fillna(0) if (nuc.notna().any() or ren.notna().any()) else float("nan"))
            low = low.fillna(col("total") - fos)
            w2 = pd.DataFrame({"oil": col("oil"), "gas": col("gas"), "coal": col("coal")})
            if nuc.notna().sum() > len(w) * 0.5 and ren.notna().sum() > len(w) * 0.5:
                w2["nuclear"], w2["renewables"] = nuc, ren
            else:
                w2["lowcarbon"] = low.clip(lower=0)
            w2["total"] = col("total")
            out = w2.reset_index().melt(id_vars=["iso3", "year"], var_name="fuel", value_name="qbtu").dropna()
            set_rel("eia_intl", "U.S. Energy Information Administration", resp.headers.get("Last-Modified"),
                    label="International Energy Statistics")
            return out
        except Exception as e:
            last = (str(e) or type(e).__name__)[:100]
    raise RuntimeError(last or "EIA unavailable")


# ---------------- Our World in Data grapher CSVs (OWID's work CC BY 4.0; each indicator keeps its original licence) ----------------
OWID_ALIAS = {"OWID_KOS": "XKX"}


def owid_grapher(slug):
    """One OWID chart's data. Returns DataFrame(iso3, year, value); countries only (OWID_ region codes dropped)."""
    base = f"https://ourworldindata.org/grapher/{slug}"
    hdr = {"User-Agent": "WorldEconomyLive/1.0 (data fetch)"}
    r = _get(f"{base}.csv?v=1&csvType=full&useColumnShortNames=true", timeout=120, tries=3, headers=hdr)
    df = pd.read_csv(io.StringIO(r.text))
    cols = {c.lower(): c for c in df.columns}
    code, year = cols.get("code"), cols.get("year")
    if not code or not year:
        raise RuntimeError(f"columns: {list(df.columns)[:6]}")
    vals = [c for c in df.columns if c not in (cols.get("entity"), code, year) and pd.api.types.is_numeric_dtype(df[c])]
    if not vals:
        raise RuntimeError("no value column")
    out = pd.DataFrame({"iso3": df[code].map(lambda c: OWID_ALIAS.get(str(c), str(c))), "year": pd.to_numeric(df[year], errors="coerce"),
                        "value": pd.to_numeric(df[vals[0]], errors="coerce")}).dropna()
    out = out[out.iso3.str.len() == 3]
    out["year"] = out["year"].astype(int)
    if out.iso3.nunique() < 30:
        raise RuntimeError(f"only {out.iso3.nunique()} countries")
    upd, cite = None, None
    try:
        m = _get(f"{base}.metadata.json?v=1&csvType=full&useColumnShortNames=true", timeout=60, tries=2, headers=hdr).json()
        col = next(iter((m.get("columns") or {}).values()), {})
        upd, cite = col.get("lastUpdated"), col.get("citationShort") or (m.get("chart") or {}).get("citation")
    except Exception:
        pass
    set_rel(f"owid:{slug}", "Our World in Data", upd, basis="dataset", label=cite)
    return out


# ---------------- Freight by mode outside the US (open data) ----------------
def dbnomics_dims(provider, dataset, dims, limit=1000):
    """All series of a DBnomics dataset matching a dimension filter. Returns {series_code: (series, dimensions)}."""
    q = requests.utils.quote(json.dumps(dims))
    out, offset = {}, 0
    while True:
        url = (f"https://api.db.nomics.world/v22/series/{provider}/{dataset}?dimensions={q}"
               f"&observations=1&limit={limit}&offset={offset}&format=json")
        js = _get(url, timeout=120).json().get("series", {})
        docs = js.get("docs", [])
        for d in docs:
            try:
                out[d["series_code"]] = (_series([None if v == "NA" else v for v in d["value"]],
                                                 [_period_to_ts(x) for x in d["period"]], d["series_code"]),
                                         d.get("dimensions", {}))
            except Exception:
                pass
        offset += len(docs)
        if not docs or offset >= js.get("num_found", 0):
            return out


def _geo_iso3(code):
    code = {"EL": "GR", "UK": "GB"}.get(code, code)
    try:
        import pycountry
        c = pycountry.countries.get(alpha_2=code)
        return c.alpha_3 if c else None
    except Exception:
        return None


def eurostat_jsonstat(dataset, dims, since):
    """Eurostat's own dissemination API (JSON-stat 2.0), always current. Returns {iso3: series}."""
    q = "&".join(f"{k}={v[0]}" for k, v in dims.items()) + f"&sinceTimePeriod={since}&lang=EN"
    js = _get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?{q}", timeout=120).json()
    set_rel(f"eurostat:{dataset}", "Eurostat", js.get("updated"), basis="dataset")
    ids, size, vals = js["id"], js["size"], js.get("value", {})
    idx = {d: js["dimension"][d]["category"]["index"] for d in ids}
    pos = {d: {i: c for c, i in idx[d].items()} if isinstance(idx[d], dict) else dict(enumerate(idx[d])) for d in ids}
    gi, ti = ids.index("geo"), ids.index("time")
    out = {}
    for k, v in (vals.items() if isinstance(vals, dict) else enumerate(vals)):
        if v is None:
            continue
        k, coord = int(k), []
        for n in reversed(size):
            coord.append(k % n)
            k //= n
        coord = coord[::-1]
        if any(c != 0 for j, c in enumerate(coord) if j not in (gi, ti)):
            continue
        out.setdefault(pos["geo"][coord[gi]], {})[_period_to_ts(pos["time"][coord[ti]])] = float(v)
    res = {}
    for geo, obs in out.items():
        iso = _geo_iso3(geo)
        if iso:
            res[iso] = pd.Series(obs).sort_index().rename(iso).set_axis(pd.to_datetime(sorted(obs)))
    if not res:
        raise RuntimeError(f"{dataset}: empty")
    return res


def eurostat_by_country(dataset, dims, since="2003-01"):
    """{iso3: series}: Eurostat API first (current), DBnomics mirror as fallback."""
    try:
        return eurostat_jsonstat(dataset, dims, since)
    except Exception:
        pass
    res = {}
    for code, (s, d) in dbnomics_dims("Eurostat", dataset, dims).items():
        iso = _geo_iso3(d.get("geo") or code.split(".")[-1])
        if iso and len(s) and (iso not in res or len(s) > len(res[iso])):
            res[iso] = s
    if not res:
        raise RuntimeError(f"{dataset}: no series")
    return res


def eu_air_freight():
    """Monthly air freight and mail loaded + unloaded, tonnes (Eurostat avia_gooc)."""
    return eurostat_by_country("avia_gooc", {"freq": ["M"], "unit": ["T"], "tra_meas": ["FRM_LD_NLD"],
                                             "schedule": ["TOT"], "tra_cov": ["TOTAL"]})


def eu_rail_freight():
    """Quarterly goods transported by rail, thousand tonnes (Eurostat rail_go_quartal)."""
    return eurostat_by_country("rail_go_quartal", {"freq": ["Q"], "unit": ["THS_T"]}, since="2003-Q1")


def canada_rail():
    """Monthly railway carloadings, total tonnes, Canada (Statistics Canada table 23-10-0216-01, open licence)."""
    try:
        cm = S.post("https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata", json=[{"productId": 23100216}], timeout=60).json()
        obj = (cm[0] if isinstance(cm, list) and cm else {}).get("object", {})
        set_rel("statcan", "Statistics Canada", obj.get("releaseTime"))
    except Exception:
        set_rel("statcan", "Statistics Canada", None)
    meta = _get("https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/23100216/en", timeout=60).json()
    url = meta.get("object") if isinstance(meta, dict) else None
    if not url:
        raise RuntimeError("statcan: no download link")
    z = zipfile.ZipFile(io.BytesIO(_get(url, timeout=180).content))
    name = next(n for n in z.namelist() if n.endswith(".csv") and "MetaData" not in n)
    df = pd.read_csv(z.open(name), low_memory=False)
    df = df[df["GEO"].astype(str).str.strip() == "Canada"]
    if "UOM" in df.columns:
        t = df[df["UOM"].astype(str).str.lower().str.contains("tonne")]
        df = t if len(t) else df
    skip = {"REF_DATE", "GEO", "DGUID", "UOM", "UOM_ID", "SCALAR_FACTOR", "SCALAR_ID", "VECTOR", "COORDINATE",
            "VALUE", "STATUS", "SYMBOL", "TERMINATED", "DECIMALS"}
    dims = [c for c in df.columns if c not in skip and df[c].nunique() > 1]
    for c in dims:                                        # prefer the total of every breakdown
        tot = df[df[c].astype(str).str.contains("Total", case=False)]
        if len(tot):
            df = tot
    df = df.assign(VALUE=pd.to_numeric(df["VALUE"], errors="coerce")).dropna(subset=["VALUE"])
    key = [c for c in dims if df[c].nunique() > 1]
    if key:                                               # still several series: keep the biggest
        big = df.groupby(key)["VALUE"].mean().idxmax()
        big = big if isinstance(big, tuple) else (big,)
        for c, v in zip(key, big):
            df = df[df[c] == v]
    s = df.groupby(pd.to_datetime(df["REF_DATE"].astype(str) + "-01", errors="coerce"))["VALUE"].sum().sort_index()
    s = s[s.index.notna()]
    if len(s) < 24:
        raise RuntimeError(f"statcan: only {len(s)} months")
    return s


# ---------------- US Bureau of Transportation Statistics (public domain) ----------------
def bts_monthly() -> pd.DataFrame:
    try:
        meta = _get("https://data.bts.gov/api/views/crem-w557.json", timeout=60, tries=2).json()
        set_rel("bts", "US Bureau of Transportation Statistics", meta.get("rowsUpdatedAt") or meta.get("dataUpdatedAt"))
    except Exception:
        set_rel("bts", "US Bureau of Transportation Statistics", None)
    url = "https://data.bts.gov/resource/crem-w557.json?$order=date%20DESC&$limit=400"
    rows = _get(url, timeout=90).json()
    df = pd.DataFrame(rows)
    if df.empty or "date" not in df.columns:
        raise RuntimeError("empty")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    return df.apply(pd.to_numeric, errors="coerce")
_PINK_CACHE = None
