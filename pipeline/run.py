"""World Economy Live pipeline: pull every open source, compute, write site/data/heartbeat.json.

A failing source never breaks the run: it is logged in the status block and the site
shows whatever is available.   Run:  python pipeline/run.py
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import registry as R  # noqa: E402
import sources as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "heartbeat.json"
HIST = ROOT / "data" / "score_history.csv"
TODAY = pd.Timestamp.utcnow().tz_localize(None).normalize()
T0 = datetime.now()


def step(msg):
    print(f"[{(datetime.now() - T0).total_seconds():6.0f}s] {msg}", flush=True)


def timed(name, fn):
    t = datetime.now()
    step(f"start {name}")
    try:
        return fn()
    finally:
        step(f"done  {name} ({(datetime.now() - t).total_seconds():.0f}s)")


# ---------------------------------------------------------------- helpers
def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if (math.isnan(x) or math.isinf(x)) else round(float(x), 3)
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.strftime("%Y-%m-%d")
    return x


def yoy(s, periods=12, freq="MS"):
    s = s.resample(freq).mean().dropna()
    return ((s / s.shift(periods) - 1) * 100).dropna()


def spark(s, n=24, freq="MS"):
    if s is None or s.empty:
        return []
    s = s.resample(freq).mean().dropna().iloc[-n:]
    return [[d.strftime("%Y-%m"), round(float(v), 3)] for d, v in s.items()]


def value_ago(s, days):
    p = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
    return float(p.iloc[-1]) if len(p) else None


def pct(a, b):
    return None if (a is None or b in (None, 0)) else (a / b - 1) * 100


def z_last(s, years=10, min_n=24):
    """Robust z-score of the latest value vs this series' own history:
    median/MAD over the last `years`, excluding the pandemic distortion (Mar 2020 - Dec 2021)."""
    if s is None:
        return None
    s = s.dropna()
    if len(s) < min_n:
        return None
    h = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
    h = h[(h.index < "2020-03-01") | (h.index > "2021-12-31")]
    if len(h) < max(8, min_n // 2):
        return None
    med = h.median()
    mad = (h - med).abs().median() * 1.4826
    sd = mad if mad and not np.isnan(mad) else h.std()
    if not sd or np.isnan(sd):
        return None
    return float(np.clip((s.iloc[-1] - med) / sd, -3, 3))


# ---------------------------------------------------------------- macro (monthly, batched)
_WB_ALL: dict = {}


def wb_all(ind):
    if ind not in _WB_ALL:
        _WB_ALL[ind] = S.worldbank_all(ind)
    return _WB_ALL[ind]


def transform(s, tf, attrs):
    if attrs.get("TRANSFORMATION") in ("GY", "G1", "GQ") and tf in ("yoy", "yoyq"):
        return s                                    # already a growth rate
    if tf == "yoy":
        return yoy(s)
    if tf == "yoyq":
        return yoy(s, 4, "QS")
    if tf == "usd_bn":
        mult = attrs.get("UNIT_MULT")
        try:
            return s * (10 ** int(float(mult))) / 1e9 if mult not in (None, "", "nan") else s / 1e9
        except ValueError:
            return s
    return s


def age_months(s):
    return (TODAY - s.index[-1]).days / 30.4


def fallback_series(cand, iso3):
    kind = cand[0]
    if kind == "dbn":
        _, sid, tf = cand
        return transform(S.dbnomics(sid), tf, {}), "Eurostat", False
    if kind == "wb":
        _, ind, tf = cand
        d = wb_all(ind)
        d = d[d.iso3 == iso3].sort_values("year")
        return S._series(d["value"], d["year"].astype(str) + "-07-01", ind), "World Bank (annual)", True
    raise RuntimeError(kind)


def macro_block():
    areas = list(R.ECONOMIES)
    batch = {}
    for ind, spec in R.OECD_SPECS.items():
        try:
            got = S.oecd_batch(spec, areas)
            res = {}
            for iso3, (s, attrs) in got.items():
                s = transform(s, spec["transform"], attrs).dropna()
                b = spec.get("bounds")
                if len(s) and (b is None or abs(s.iloc[-1]) <= b):
                    res[iso3] = s
            batch[ind] = res
            S.log(f"oecd.{ind}", bool(res), f"{len(res)}/{len(areas)} economies")
        except Exception as e:
            batch[ind] = {}
            S.log(f"oecd.{ind}", False, e)
    try:
        bis = S.bis_batch(["XM" if i in R.EURO else R.ECONOMIES[i][1] for i in areas])
        S.log("bis.policy_rates", True, f"{len(bis)} central banks")
    except Exception as e:
        bis = {}
        S.log("bis.policy_rates", False, e)

    out = {}
    for iso3, (name, iso2, geo) in R.ECONOMIES.items():
        e = {"name": name, "iso3": iso3, "g20": iso3 in R.G20, "indicators": {}, "pillars": {}}
        series, fb = {}, R.fallbacks(iso3)
        for ind in ["gdp", "inflation", "unemployment", "industry", "long_rate", "short_rate", "exports_usd", "imports_usd"]:
            best = None   # (series, label, annual)
            s = batch.get(ind, {}).get(iso3)
            if s is not None and age_months(s) <= R.MAX_STALE_MONTHS:
                best = (s, "OECD", False)
            if best is None or age_months(best[0]) > R.FRESH_MONTHS:
                for cand in fb.get(ind, []):
                    try:
                        s2, lab, annual = fallback_series(cand, iso3)
                        lim = 30 if annual else R.MAX_STALE_MONTHS
                        if len(s2) < 3 or age_months(s2) > lim:
                            continue
                        if best is None or (not annual and age_months(s2) < age_months(best[0])):
                            best = (s2, lab, annual)
                        if not annual and age_months(s2) <= R.FRESH_MONTHS:
                            break
                    except Exception:
                        continue
            if best:
                s, lab, annual = best
                series[ind] = None if annual else s
                q = ind == "gdp"
                e["indicators"][ind] = {"latest": float(s.iloc[-1]), "date": s.index[-1], "annual": annual,
                                        "year_ago": value_ago(s, 335), "source": lab,
                                        "spark": [] if annual else spark(s, 20 if q else 24, "QS" if q else "MS")}
        b = bis.get("XM" if iso3 in R.EURO else iso2)
        if b is not None and age_months(b) <= R.MAX_STALE_MONTHS:
            series["policy_rate"] = b
            e["indicators"]["policy_rate"] = {"latest": float(b.iloc[-1]), "date": b.index[-1], "annual": False,
                                              "year_ago": value_ago(b, 335), "source": "BIS", "spark": spark(b, 24)}
        elif "short_rate" in e["indicators"]:
            e["indicators"]["policy_rate"] = dict(e["indicators"]["short_rate"], source="OECD (3-month rate)")
            series["policy_rate"] = series.get("short_rate")
        # monthly merchandise trade in US$ -> balance
        X, Mi = series.get("exports_usd"), series.get("imports_usd")
        if X is not None and Mi is not None:
            bal = (X - Mi).dropna()
            if len(bal):
                e["indicators"]["trade_balance_usd"] = {"latest": float(bal.iloc[-1]), "date": bal.index[-1], "annual": False,
                                                        "year_ago": value_ago(bal, 335), "source": "OECD", "spark": spark(bal, 24)}
                e["trade_m"] = {"exports": float(X.iloc[-1]), "imports": float(Mi.iloc[-1]), "balance": float(bal.iloc[-1]),
                                "exports_yoy": pct(float(X.iloc[-1]), value_ago(X, 335)),
                                "imports_yoy": pct(float(Mi.iloc[-1]), value_ago(Mi, 335)),
                                "exports_12m": float(X.iloc[-12:].sum()) if len(X) >= 12 else None,
                                "imports_12m": float(Mi.iloc[-12:].sum()) if len(Mi) >= 12 else None,
                                "date": X.index[-1]}
        if series.get("industry") is not None:
            e["pillars"]["activity"] = z_last(series["industry"])
        elif series.get("gdp") is not None:
            e["pillars"]["activity"] = z_last(series["gdp"], min_n=12)
        if series.get("unemployment") is not None:
            u = series["unemployment"].resample("MS").mean()
            z = z_last((u - u.shift(12)).dropna())
            e["pillars"]["labor"] = None if z is None else -z
        if series.get("inflation") is not None:
            e["pillars"]["prices"] = z_last(-(series["inflation"] - 2.0).abs())
        e["_series"] = series
        out[iso3] = e
    return out


def history_series(e, months=120):
    """Monthly history (last 10 years) of every scorecard column, for the click-to-chart view."""
    S_ = e.get("_series", {})
    m = lambda k: None if S_.get(k) is None else S_[k].resample("MS").mean()  # noqa: E731
    pi, u, i, lr, X, M = (m(k) for k in ("inflation", "unemployment", "policy_rate", "long_rate", "exports_usd", "imports_usd"))
    g = S_.get("gdp")
    out = {}
    if g is not None:
        out["gdp"] = g
    for k, v in (("inflation", pi), ("unemployment", u), ("policy_rate", i), ("long_rate", lr)):
        if v is not None:
            out[k] = v
    if i is not None and pi is not None:
        i_ff = i.reindex(pi.index).ffill()
        out["real_rate"] = i_ff - pi
    if pi is not None and u is not None:
        out["misery"] = pi + u.reindex(pi.index).ffill()
    if lr is not None and i is not None:
        out["curve"] = lr - i.reindex(lr.index).ffill()
    if u is not None and pi is not None:
        uu = u.dropna()
        ubar = uu.rolling(120, min_periods=36).mean()
        gap = -2.0 * (uu - ubar)
        p_ = pi.reindex(gap.index).ffill()
        taylor = 0.5 + p_ + 0.5 * (p_ - 2.0) + 0.5 * gap
        if i is not None:
            out["taylor_gap"] = (i.reindex(taylor.index).ffill() - taylor)
        a3 = uu.rolling(3).mean()
        out["sahm"] = a3 - a3.rolling(13).min()
    if X is not None and M is not None:
        b = (X - M).dropna()
        out["trade_balance"] = b
        out["trade_balance_12m"] = b.rolling(12).sum()
    res = {}
    for k, v in out.items():
        v = v.dropna()
        v = v[v.index >= v.index.max() - pd.DateOffset(months=months)] if len(v) else v
        if len(v) >= 3:
            res[k] = [[d.strftime("%Y-%m"), round(float(x), 3)] for d, x in v.items()]
    return res


def macro_math(e):
    I, m, series = e["indicators"], {}, e["_series"]
    g = lambda k: I[k]["latest"] if k in I and not I[k].get("annual") else None  # noqa: E731
    pi, u, i, lr = g("inflation"), g("unemployment"), g("policy_rate"), g("long_rate")
    if i is not None and pi is not None:
        m["real_rate"] = i - pi
    if pi is not None and u is not None:
        m["misery"] = pi + u
    if lr is not None and i is not None:
        m["curve"] = lr - i
    us = series.get("unemployment")
    if us is not None and pi is not None and len(us) >= 24:
        us = us.resample("MS").mean().dropna()
        ubar = us[us.index >= us.index[-1] - pd.DateOffset(years=10)].mean()
        gap = -2.0 * (us.iloc[-1] - ubar)
        taylor = 0.5 + pi + 0.5 * (pi - 2.0) + 0.5 * gap
        m["output_gap"], m["taylor"] = gap, taylor
        if i is not None:
            m["taylor_gap"] = i - taylor
        a3 = us.rolling(3).mean().dropna()
        if len(a3) >= 13:
            m["sahm"] = float(a3.iloc[-1] - a3.iloc[-13:].min())
    return m


def real_rate_any(e):
    """Policy rate minus the latest inflation reading; falls back to annual inflation if no monthly CPI."""
    if e["math"].get("real_rate") is not None:
        return e["math"]["real_rate"]
    I = e["indicators"]
    i, pi = I.get("policy_rate", {}).get("latest"), I.get("inflation", {}).get("latest")
    return None if i is None or pi is None else i - pi


# ---------------------------------------------------------------- annual (all countries)
SERIES_OUT: dict = {}    # iso3 -> {column: [[YYYY-MM, value], ...]} written to site/data/series.json
ANNUAL_HIST: dict = {}   # iso3 -> {gdp_growth|inflation_a|unemployment_a: annual series}


def z_annual(s, years=15, min_n=8):
    """Robust z of this year's value vs the country's own past years (2020-21 excluded)."""
    s = s.dropna()
    if len(s) < min_n:
        return None
    h = s[(s.index.year >= s.index[-1].year - years) & ~s.index.year.isin([2020, 2021])]
    if len(h) < min_n - 2:
        return None
    med = h.median()
    sd = (h - med).abs().median() * 1.4826 or h.std()
    if not sd or np.isnan(sd):
        return None
    return float(np.clip((s.iloc[-1] - med) / sd, -3, 3))


def annual_score(iso3, ports, power):
    """Score for countries without monthly data: IMF WEO estimates for the current year vs that country's own
    history, blended with port cargo and electricity where available. Same 50 + 15*z scale."""
    H, p = ANNUAL_HIST.get(iso3, {}), {}
    g = H.get("gdp_growth")
    if g is not None and len(g) and g.index[-1].year >= TODAY.year - 1:
        p["activity"] = z_annual(g)
    pz = power.get(iso3, {}).get("z")
    if pz is not None:
        p["activity"] = pz if p.get("activity") is None else (p["activity"] + pz) / 2
    u = H.get("unemployment_a")
    if u is not None and len(u) > 9 and u.index[-1].year >= TODAY.year - 1:
        z = z_annual(u.diff().dropna())
        p["labor"] = None if z is None else -z
    pi = H.get("inflation_a")
    if pi is not None and len(pi) and pi.index[-1].year >= TODAY.year - 1:
        p["prices"] = z_annual(-(pi - 2.0).abs())
    if ports and iso3 in ports.get("economies", {}):
        p["trade"] = float(np.clip(ports["economies"][iso3] / 10, -3, 3))
    zs = {k: v for k, v in p.items() if v is not None}
    if len(zs) < 2:
        return None, None
    return float(np.clip(50 + 15 * np.mean(list(zs.values())), 0, 100)), {PILLAR_NAMES[k]: round(15 * v / len(zs), 2) for k, v in zs.items()}


def annual_block():
    """IMF WEO + World Bank for every country. Returns ({iso3: {key: record}}, weo_release)."""
    from concurrent.futures import ThreadPoolExecutor
    allc, rel_used = {}, None
    first = next(iter(R.WEO.values()))[0]
    try:                                            # find the live WEO release once
        _, rel_used = S.weo_all(first, R.WEO_RELEASES)
    except Exception:
        pass
    rels = [rel_used] if rel_used else R.WEO_RELEASES
    with ThreadPoolExecutor(4) as ex:
        weo = {k: ex.submit(S.weo_all, v[0], rels) for k, v in R.WEO.items()}
        wbf = {k: ex.submit(wb_all, v[0]) for k, v in R.WB.items()}
    for key, (code, label, unit, scale) in R.WEO.items():
        try:
            data, rel = weo[key].result()
            rel_used = rel
            for iso3, s in data.items():
                s = s[s.index.year <= TODAY.year] * scale
                if key in ("gdp_growth", "inflation_a", "unemployment_a"):
                    ANNUAL_HIST.setdefault(iso3, {})[key] = s.dropna()
                if len(s):
                    allc.setdefault(iso3, {})[key] = {"label": label, "unit": unit, "value": float(s.iloc[-1]),
                                                      "year": int(s.index[-1].year), "source": "IMF WEO",
                                                      "estimate": bool(s.index[-1].year >= TODAY.year - 0)}
            S.log(f"weo.{key}", True, f"{len(data)} countries")
        except Exception as e:
            S.log(f"weo.{key}", False, e)
    for key, (ind, label, unit) in R.WB.items():
        try:
            df = wbf[key].result()
            for iso3, g in df.groupby("iso3"):
                g = g.sort_values("year")
                last = g.iloc[-1]
                ten = g[g["year"] <= last["year"] - 10]
                allc.setdefault(iso3, {})[key] = {"label": label, "unit": unit, "value": float(last["value"]),
                                                  "year": int(last["year"]), "source": "World Bank", "estimate": False,
                                                  "ten_years_ago": float(ten.iloc[-1]["value"]) if len(ten) else None}
            S.log(f"worldbank.{ind}", True, f"{df.iso3.nunique()} countries")
        except Exception as e:
            S.log(f"worldbank.{ind}", False, e)
    # fall back to World Bank debt when WEO has none
    for iso3, d in allc.items():
        if "gov_debt" not in d and "debt_wb" in d:
            d["gov_debt"] = dict(d["debt_wb"], label="Government debt")
    return allc, rel_used


def derive(e, f):
    I, d = e["indicators"], {}
    X, M = f.get("exports_usd_a"), f.get("imports_usd_a")
    if X and M and X["year"] == M["year"]:
        d["trade_balance_usd"] = {"value": X["value"] - M["value"], "year": X["year"]}
    gr = I.get("gdp", {}).get("latest") if not I.get("gdp", {}).get("annual") else f.get("gdp_growth", {}).get("value")
    pi = I.get("inflation", {}).get("latest")
    r = I.get("long_rate", {}).get("latest")
    if gr is not None and pi is not None and r is not None:
        g = gr + pi
        d["nominal_growth"], d["r_minus_g"] = g, r - g
        debt = f.get("gov_debt", {}).get("value")
        if debt is not None:
            d["pb_stabilizing"] = (r - g) / (100 + g) * debt
            pb = f.get("primary_balance", {}).get("value")
            if pb is not None:
                d["fiscal_gap"] = pb - d["pb_stabilizing"]
    if "savings" in f and ("investment_weo" in f or "investment" in f):
        d["s_minus_i"] = f["savings"]["value"] - (f.get("investment_weo") or f["investment"])["value"]
    if "current_account" in f and "gov_balance" in f:
        d["twin"] = f["current_account"]["value"] + f["gov_balance"]["value"]
    return d


# ---------------------------------------------------------------- prices & markets
def prices_block():
    try:
        ps = S.pink_sheet()
        S._PINK_CACHE = ps
        S.log("worldbank.pinksheet", True, f"{ps.index[-1]:%Y-%m}")
    except Exception as e:
        S.log("worldbank.pinksheet", False, e)
        return []
    rows = []
    for prefix, name, ship, unit in R.COMMODITIES:
        col = next((c for c in ps.columns if str(c).lower().startswith(prefix.lower())), None)
        if not col:
            continue
        s = ps[col].dropna()
        if len(s) < 13:
            continue
        rows.append({"name": name, "ship": ship, "level": float(s.iloc[-1]), "date": s.index[-1],
                     "unit": unit, "m1": pct(float(s.iloc[-1]), float(s.iloc[-2])),
                     "yoy": pct(float(s.iloc[-1]), value_ago(s, 360)), "spark": spark(s, 24)})
    return rows


def markets_block():
    out = {"fx": [], "rates": [], "us_fiscal": [], "global_rates": [], "fx_note": "ECB euro foreign exchange reference rates (spot, set daily around 14:15 CET), converted to US-dollar pairs through the euro: USD/XXX = (XXX per EUR) ÷ (USD per EUR)."}
    start = (TODAY - pd.Timedelta(days=430)).strftime("%Y-%m-%d")
    try:
        fx = S.ecb_fx(R.FX, start).ffill()
        S.log("ecb.fx", True)
        usd = fx["USD"]                                     # USD per 1 EUR
        series = {}
        for c in ["EUR"] + [x for x in R.FX if x != "USD"]:
            if c == "EUR":
                s_, pair, meaning = usd, "EUR/USD", "US dollars per 1 euro"
            elif c not in fx:
                continue
            elif c in R.FX_BASE_IS_FOREIGN:
                s_, pair, meaning = usd / fx[c], f"{c}/USD", f"US dollars per 1 {R.FX_UNITS.get(c, c)}"
            else:
                s_, pair, meaning = fx[c] / usd, f"USD/{c}", f"{R.FX_UNITS.get(c, c)} per 1 US dollar"
            s_ = s_.dropna()
            last = float(s_.iloc[-1])
            # sign so that + always means the foreign currency strengthened vs USD
            strong = 1 if c in R.FX_BASE_IS_FOREIGN or c == "EUR" else -1
            m1, y1 = pct(last, value_ago(s_, 30)), pct(last, value_ago(s_, 365))
            out["fx"].append({"name": R.FX_NAMES.get(c, c), "code": c, "pair": pair, "meaning": meaning,
                              "latest": last, "date": s_.index[-1], "m1": m1, "y1": y1,
                              "ccy_y1": None if y1 is None else strong * y1,
                              "spark": spark(s_, 13), "unit": "%"})
    except Exception as e:
        S.log("ecb.fx", False, e)

    def rate_row(name, s):
        s = s.dropna()
        last = float(s.iloc[-1])
        a, b = value_ago(s, 30), value_ago(s, 365)
        out["rates"].append({"name": name, "latest": last, "date": s.index[-1], "unit": "pp",
                             "m1": None if a is None else last - a, "y1": None if b is None else last - b,
                             "spark": spark(s, 13)})
    try:
        effr = S.nyfed_effr()
        S.log("nyfed.effr", True)
        rate_row("Fed funds (effective)", effr)
    except Exception as e:
        S.log("nyfed.effr", False, e)
    try:
        yc = S.treasury_curve()
        S.log("treasury.curve", True)
        for col, nm in (("3 Mo", "3-month T-bill"), ("2 Yr", "2-year Treasury"), ("10 Yr", "10-year Treasury"), ("30 Yr", "30-year Treasury")):
            if col in yc:
                rate_row(nm, yc[col])
        if "10 Yr" in yc and "2 Yr" in yc:
            rate_row("Yield curve (10y − 2y)", yc["10 Yr"] - yc["2 Yr"])
        try:
            ry = S.treasury_curve("daily_treasury_real_yield_curve")
            if "10 YR" in ry or "10 Yr" in ry:
                real10 = ry["10 YR"] if "10 YR" in ry else ry["10 Yr"]
                rate_row("10-year real yield", real10)
                rate_row("Inflation expected, next 10 years", (yc["10 Yr"] - real10).dropna())
        except Exception:
            pass
    except Exception as e:
        S.log("treasury.curve", False, e)
    try:
        debt = S.treasury_debt()
        S.log("treasury.debt", True)
        last = float(debt.iloc[-1])
        out["us_fiscal"].append({"name": "US federal debt (total)", "latest": last, "date": debt.index[-1],
                                 "y1_abs": None if value_ago(debt, 365) is None else last - value_ago(debt, 365),
                                 "y1": pct(last, value_ago(debt, 365))})
    except Exception as e:
        S.log("treasury.debt", False, e)
    return out


# ---------------------------------------------------------------- ports & chokepoints
def ports_block():
    try:
        ports = S.portwatch_ports()
        S.log("portwatch.ports", True, f"{len(ports)} ports")
    except Exception as e:
        S.log("portwatch.ports", False, e)
        return None
    iso_region = {i: r for r, l in R.REGIONS.items() for i in l}
    ports["region"] = ports["ISO3"].map(iso_region)
    ports = ports.sort_values("vessel_count_total", ascending=False)
    picks = pd.concat([ports.dropna(subset=["region"]).groupby("region").head(R.PORTS_PER_REGION),
                       ports[ports["ISO3"].isin(R.ECONOMIES)].groupby("ISO3").head(R.PORTS_PER_ECONOMY)]
                      ).drop_duplicates("portid")
    start = (TODAY - pd.Timedelta(days=430)).strftime("%Y-%m-%d")
    from concurrent.futures import ThreadPoolExecutor

    def _one(pid):
        try:
            return S.portwatch_port_daily(pid, start)
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        frames = [f for f in ex.map(_one, list(picks["portid"])) if f is not None and len(f)]
    S.log("portwatch.daily", bool(frames), f"{len(frames)}/{len(picks)} ports")
    if not frames:
        return None
    pv = pd.concat(frames, ignore_index=True)
    pv = pv.drop(columns=[c for c in ("region",) if c in pv.columns]).merge(picks[["portid", "region"]], on="portid", how="left")
    if "ISO3" not in pv.columns:
        pv = pv.merge(picks[["portid", "ISO3"]], on="portid", how="left")
    P = list(R.PRODUCTS)
    for p in P:
        pv[f"imp_{p}"] = pv.get(f"import_{p}", 0)
        pv[f"exp_{p}"] = pv.get(f"export_{p}", 0)
        pv[p] = pv[f"imp_{p}"].fillna(0) + pv[f"exp_{p}"].fillna(0)
    pv["total"] = pv[P].sum(axis=1)
    pv["imports"] = pv[[f"imp_{p}" for p in P]].fillna(0).sum(axis=1)
    pv["exports"] = pv[[f"exp_{p}" for p in P]].fillna(0).sum(axis=1)
    cols = P + ["total", "imports", "exports", "portcalls"]
    end = pv["date"].max() - pd.Timedelta(days=R.LAG_DAYS)
    a = end - pd.Timedelta(days=R.WINDOW_DAYS - 1)
    pa, pb = a - pd.Timedelta(days=364), end - pd.Timedelta(days=364)

    def win(lo, hi, key):
        return pv[(pv.date >= lo) & (pv.date <= hi)].groupby(key)[cols].sum()

    def ratio(c, p):
        return ((c / p - 1) * 100).replace([np.inf, -np.inf], np.nan)

    cur_r, prv_r = win(a, end, "region"), win(pa, pb, "region")
    reg = ratio(cur_r, prv_r)
    mix = cur_r[P].div(cur_r[P].sum(axis=1), axis=0) * 100
    cs = pv[(pv.date >= a) & (pv.date <= end)][cols].sum()
    ps_ = pv[(pv.date >= pa) & (pv.date <= pb)][cols].sum()
    glob = ratio(cs, ps_)
    eco = ratio(win(a, end, "ISO3"), win(pa, pb, "ISO3"))
    flows = win(a, end, "region")[["imports", "exports"]]

    wk = pv[pv.date <= end].groupby(["region", pd.Grouper(key="date", freq="W")])["total"].sum().unstack("region")
    wky = (wk.pct_change(52, fill_method=None) * 100)
    wky = wky[wky.index <= end].tail(8)

    def _cp(cid):
        try:
            return cid, S.portwatch_chokepoint_daily(cid, start)
        except Exception:
            return cid, None
    with ThreadPoolExecutor(8) as ex:
        cpdata = dict(ex.map(_cp, list(R.CHOKEPOINTS)))
    cps = []
    for cid, (cname, lon, lat) in R.CHOKEPOINTS.items():
        try:
            d = cpdata.get(cid)
            if d is None or not len(d):
                continue
            cur, prv = d[(d.date >= a) & (d.date <= end)], d[(d.date >= pa) & (d.date <= pb)]
            cps.append({"name": cname, "lon": lon, "lat": lat,
                        "transits_yoy": pct(float(cur["n_total"].sum()), float(prv["n_total"].sum())),
                        "tanker_yoy": pct(float(cur["n_tanker"].sum()), float(prv["n_tanker"].sum())) if "n_tanker" in d else None,
                        "capacity_yoy": pct(float(cur["capacity"].sum()), float(prv["capacity"].sum())) if "capacity" in d else None,
                        "daily_transits": float(cur["n_total"].mean()) if len(cur) else None})
        except Exception:
            pass
    S.log("portwatch.chokepoints", bool(cps), f"{len(cps)}/24")

    names = picks.set_index("portid")
    portrows = ratio(win(a, end, "portid"), win(pa, pb, "portid")).join(names[["portname", "ISO3", "region"]])
    return {
        "window": [a, end],
        "regions": [{"region": r, **row[cols].to_dict(),
                     "imports_t": float(flows.loc[r, "imports"]) if r in flows.index else None,
                     "exports_t": float(flows.loc[r, "exports"]) if r in flows.index else None}
                    for r, row in reg.iterrows()],
        "mix": [{"region": r, **row.to_dict()} for r, row in mix.iterrows()],
        "global": glob.to_dict(),
        "economies": {i: float(v) for i, v in eco["total"].items() if pd.notna(v)},
        "weekly": {"weeks": [d.strftime("%m/%d") for d in wky.index], "series": {c: wky[c].tolist() for c in wky.columns}},
        "ports": [{"port": row["portname"], "iso3": row["ISO3"], "region": row["region"], **row[cols].to_dict()}
                  for _, row in portrows.iterrows()],
        "chokepoints": cps,
    }


# ---------------------------------------------------------------- summary
def label(score):
    if score is None:
        return "Pending"
    return "Strong" if score >= 60 else "Steady" if score >= 45 else "Soft" if score >= 35 else "Stressed"


PILLAR_NAMES = {"activity": "Output", "labor": "Jobs", "prices": "Prices", "trade": "Trade"}


def score_economies(econ, ports, power):
    for iso3, e in econ.items():
        if ports and iso3 in ports["economies"]:
            e["trade_yoy"] = ports["economies"][iso3]
            e["pillars"]["trade"] = float(np.clip(e["trade_yoy"] / 10, -3, 3))
        pz = power.get(iso3, {}).get("z")
        if pz is not None:                      # electricity demand joins the output pillar
            a = e["pillars"].get("activity")
            e["pillars"]["activity"] = pz if a is None else (a + pz) / 2
        zs = {k: v for k, v in e["pillars"].items() if v is not None}
        if len(zs) >= 2:
            e["score"] = float(np.clip(50 + 15 * np.mean(list(zs.values())), 0, 100))
            e["contrib"] = {PILLAR_NAMES[k]: 15 * v / len(zs) for k, v in zs.items()}   # points vs 50
        else:
            e["score"] = None
        e["label"] = label(e["score"])
        e["coverage"] = f"{len(zs)}/4"


def electricity_block():
    try:
        df = S.ember_monthly()
        S.log("ember.electricity", True, f"{df.iso3.nunique()} countries")
    except Exception as ex:
        S.log("ember.electricity", False, ex)
        return {}
    out = {}
    for iso3, g in df.groupby("iso3"):
        s = g.set_index("date")["value"].sort_index()
        s = s[~s.index.duplicated()]
        if len(s) < 27 or age_months(s) > 8:
            continue
        s3 = s.rolling(3).sum()
        y = ((s3 / s3.shift(12) - 1) * 100).dropna()     # 3-month demand vs same 3 months a year ago
        if not len(y):
            continue
        out[iso3] = {"twh": float(s.iloc[-1]), "date": s.index[-1], "yoy_3m": float(y.iloc[-1]),
                     "z": z_last(y, min_n=24), "spark": spark(y, 24)}
    return out


def transport_block():
    """US freight by mode (BTS Monthly Transportation Statistics). Columns chosen by keyword."""
    try:
        df = S.bts_monthly()
    except Exception as ex:
        S.log("bts.transport", False, ex)
        return []
    want = [("Rail carloads", ["freight_rail"], ["intermodal", "ton"]),
            ("Rail intermodal (containers, trailers)", ["intermodal"], []),
            ("Air cargo (revenue ton-miles)", ["air", "freight"], ["passenger"]),
            ("Air cargo (revenue ton-miles)", ["air", "ton"], ["passenger"]),
            ("Waterborne freight", ["waterborne"], []),
            ("Pipeline", ["pipeline"], []),
            ("Transborder freight, total", ["transborder", "total"], [])]
    rows, used = [], set()
    for name, inc, exc in want:
        if name in {r["name"] for r in rows}:
            continue
        col = next((c for c in df.columns if all(k in c.lower() for k in inc) and not any(k in c.lower() for k in exc) and c not in used), None)
        if not col:
            continue
        s = df[col].dropna()
        if len(s) < 13 or age_months(s) > 10:
            continue
        used.add(col)
        rows.append({"name": name, "latest": float(s.iloc[-1]), "date": s.index[-1],
                     "yoy": pct(float(s.iloc[-1]), value_ago(s, 360)), "spark": spark(s, 24), "field": col})
    S.log("bts.transport", bool(rows), f"{len(rows)} series")
    return rows


def freight_block():
    """Rail and air freight outside the US: EU air (monthly), EU rail (quarterly), Canada rail (monthly).
    Returns {"rows": [...table rows...], "z": {iso3: z of freight volume growth vs own history}}."""
    rows, zs, skipped = [], {}, []

    def add(iso3, mode, s, unit, quarterly=False):
        s = s.dropna().sort_index()
        s = s[~s.index.duplicated()]
        if len(s) < (12 if quarterly else 27) or age_months(s) > (12 if quarterly else 8):
            skipped.append(f"{iso3} {mode}: {len(s)} obs, latest {str(s.index[-1])[:7] if len(s) else 'none'}")
            return
        if quarterly:
            y = ((s / s.shift(4) - 1) * 100).dropna()
            z = z_last(y, min_n=12)
        else:
            s3 = s.rolling(3).sum()
            y = ((s3 / s3.shift(12) - 1) * 100).dropna()        # last 3 months vs same 3 months a year ago
            z = z_last(y, min_n=24)
        if not len(y):
            return
        import pycountry
        c = pycountry.countries.get(alpha_3=iso3)
        rows.append({"country": c.name if c else iso3, "iso3": iso3, "mode": mode, "latest": float(s.iloc[-1]),
                     "unit": unit, "date": s.index[-1], "yoy": float(y.iloc[-1]), "spark": spark(y, 24 if not quarterly else 12),
                     "period": "quarter" if quarterly else "3 months"})
        if z is not None:
            zs.setdefault(iso3, []).append(z)

    for name, fn, mode, unit, q in (("eurostat.air_freight", S.eu_air_freight, "Air freight", "tonnes", False),
                                    ("eurostat.rail_freight", S.eu_rail_freight, "Rail freight", "thousand tonnes", True)):
        try:
            data = fn()
            n0 = len(rows)
            for iso3, ser in data.items():
                add(iso3, mode, ser, unit, q)
            kept = len(rows) - n0
            note = f"{kept}/{len(data)} countries current"
            if kept < len(data):
                note += " · skipped e.g. " + "; ".join([x for x in skipped if mode in x][:2])
            S.log(name, kept > 0, note)
        except Exception as ex:
            S.log(name, False, ex)
    try:
        add("CAN", "Rail carloadings", S.canada_rail(), "tonnes")
        S.log("statcan.rail", True, "Canada")
    except Exception as ex:
        S.log("statcan.rail", False, ex)
    return {"rows": rows, "z": {k: float(np.mean(v)) for k, v in zs.items()}}


def activity_signals(power, freight):
    """Combine electricity-demand and freight z-scores into one live activity signal per country."""
    out = {}
    for iso3 in set(power) | set((freight or {}).get("z", {})):
        v = [x for x in (power.get(iso3, {}).get("z"), (freight or {}).get("z", {}).get(iso3)) if x is not None]
        if v:
            out[iso3] = {"z": float(np.mean(v))}
    return out


def global_stress(prices, ports):
    """Global supply/energy stress: z-scores of oil and gas price shocks and world port cargo."""
    comps = {}
    try:
        ps = S._PINK_CACHE
        for col_prefix, key in (("Crude oil, Brent", "Oil price shock"), ("Natural gas, Europe", "Gas price shock")):
            col = next((c for c in ps.columns if str(c).startswith(col_prefix)), None)
            if col:
                y = ((ps[col] / ps[col].shift(12) - 1) * 100).dropna()
                z = z_last(y, years=15)
                if z is not None:
                    comps[key] = -z                     # price spikes = stress
    except Exception:
        pass
    if ports and ports["global"].get("total") is not None:
        comps["World port cargo"] = float(np.clip(ports["global"]["total"] / 10, -3, 3))
    return comps



def drivers(econ, prices, ports):
    out = []
    if ports:
        for c in sorted(ports["chokepoints"], key=lambda x: -abs(x["transits_yoy"] or 0))[:2]:
            v = c["transits_yoy"]
            if v is not None and abs(v) >= 15:
                out.append(f"Ship traffic at {c['name']} is {'up' if v > 0 else 'down'} {abs(v):.0f}% on a year ago.")
        for r in sorted(ports["regions"], key=lambda x: -abs(x["total"] or 0))[:2]:
            v = r["total"]
            if v is not None:
                out.append(f"{r['region']} port cargo is {'up' if v > 0 else 'down'} {abs(v):.0f}% on a year ago.")
    for p in sorted([p for p in prices if p["yoy"] is not None], key=lambda x: -abs(x["yoy"]))[:3]:
        out.append(f"{p['name']} is {'up' if p['yoy'] > 0 else 'down'} {abs(p['yoy']):.0f}% on a year ago.")
    sahm = [e["name"] for e in econ.values() if (e.get("math", {}).get("sahm") or 0) >= 0.5]
    if sahm:
        out.append("Sahm rule recession signal (unemployment rising fast): " + ", ".join(sahm) + ".")
    scored = [e for e in econ.values() if e["score"] is not None]
    if len(scored) >= 2:
        b, w = max(scored, key=lambda e: e["score"]), min(scored, key=lambda e: e["score"])
        out.append(f"Strongest: {b['name']} ({b['score']:.0f}). Weakest: {w['name']} ({w['score']:.0f}).")
    return out


def headline(prices, ports):
    vol = ports["global"].get("total") if ports else None
    oil = next((p["yoy"] for p in prices if p["name"] == "Brent crude"), None)
    if vol is not None and oil is not None:
        if vol < -2 and oil > 15:
            return "Supply shock: goods are moving less while prices rise."
        if vol > 2 and oil < 0:
            return "Expansion with easing costs: more trade, cheaper energy."
    if vol is not None:
        return "Global trade is slowing." if vol < -2 else "Global trade is growing." if vol > 2 else "Global trade is flat."
    return "Global economy: mixed signals."


def save_history(econ):
    rows = [{"date": TODAY.strftime("%Y-%m-%d"), "iso3": k, "score": v["score"]} for k, v in econ.items()]
    new = pd.DataFrame(rows)
    if HIST.exists():
        old = pd.read_csv(HIST)
        new = pd.concat([old[old["date"] != rows[0]["date"]], new])
    HIST.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(HIST, index=False)
    return {i: g.sort_values("date")[["date", "score"]].dropna().values.tolist()[-120:] for i, g in new.groupby("iso3")}


def main():
    import pycountry
    # Every block hits different servers, so run them side by side.
    from concurrent.futures import ThreadPoolExecutor
    jobs = {"macro": macro_block, "annual": annual_block, "prices": prices_block, "markets": markets_block,
            "power": electricity_block, "transport": transport_block, "ports": ports_block, "freight": freight_block}
    res = {}
    with ThreadPoolExecutor(len(jobs)) as ex:
        futs = {k: ex.submit(timed, k, f) for k, f in jobs.items()}
        for k, fu in futs.items():
            res[k] = fu.result()
    econ, (annual, weo_rel), prices, markets = res["macro"], res["annual"], res["prices"], res["markets"]
    power, transport, ports, freight = res["power"], res["transport"], res["ports"], res["freight"]
    for r in transport:
        r.setdefault("country", "United States")
    act = activity_signals(power, freight)
    step("scoring")
    score_economies(econ, ports, act)
    for k, e in econ.items():
        f = annual.get(k, {})
        e["vitals"] = {x: f[x] for x in R.VITAL_KEYS if x in f}
        e["fundamentals"] = {x: v for x, v in f.items() if x not in R.VITAL_KEYS}
        e["math"] = macro_math(e)
        e["derived"] = derive(e, e["fundamentals"])
        SERIES_OUT[k] = history_series(e)
        tb = SERIES_OUT[k].get("trade_balance_12m")
        if tb:
            e.setdefault("trade_m", {})["balance_12m"] = tb[-1][1]
        e.pop("_series", None)
    hist = save_history(econ)
    for k in econ:
        econ[k]["history"] = hist.get(k, [])
    for k, e in econ.items():
        if k in power:
            e["power"] = power[k]
    # World score: GDP-weighted country scores (80%) + global energy/supply stress (20%)
    sc = [(e["score"], (annual.get(k, {}).get("gdp_usd") or {}).get("value") or 0) for k, e in econ.items() if e["score"] is not None]
    wsum = sum(w for _, w in sc)
    country_avg = (sum(s_ * w for s_, w in sc) / wsum) if wsum else (float(np.mean([s_ for s_, _ in sc])) if sc else None)
    stress = global_stress(prices, ports)
    stress_score = 50 + 15 * float(np.mean(list(stress.values()))) if stress else None
    world = None
    if country_avg is not None:
        world = float(np.clip(0.8 * country_avg + 0.2 * (stress_score if stress_score is not None else country_avg), 0, 100))
    world_breakdown = {"economies (GDP-weighted)": country_avg, "global stress": stress_score,
                       "stress_components": stress}

    # Global rates table (every tracked economy)
    for e in econ.values():
        I = e["indicators"]
        if "policy_rate" in I or "long_rate" in I:
            markets["global_rates"].append({
                "name": e["name"], "iso3": e["iso3"], "policy": I.get("policy_rate", {}).get("latest"),
                "policy_src": I.get("policy_rate", {}).get("source"), "long": I.get("long_rate", {}).get("latest"),
                "real": real_rate_any(e), "real_est": e["math"].get("real_rate") is None and real_rate_any(e) is not None,
                "curve": e["math"].get("curve"),
                "policy_y1": None if I.get("policy_rate", {}).get("year_ago") is None else I["policy_rate"]["latest"] - I["policy_rate"]["year_ago"],
                "date": I.get("policy_rate", I.get("long_rate", {})).get("date")})

    # Map: every country with any data, keyed by ISO numeric
    map_rows = {}
    for iso3 in set(annual) | set(econ) | set((ports or {}).get("economies", {})) | set(power):
        c = pycountry.countries.get(alpha_3=iso3)
        if not c:
            continue
        f, row = annual.get(iso3, {}), {"iso3": iso3, "name": c.name}
        for k in ("gdp_growth", "inflation_a", "unemployment_a", "gov_debt", "current_account", "gdp_usd", "population", "net_exports"):
            if k in f:
                row[k] = f[k]["value"]
        if iso3 not in econ:
            sc_, contrib_ = annual_score(iso3, ports, act)
            if sc_ is not None:
                row.update(score=sc_, label=label(sc_), basis="annual", contrib=contrib_)
        if iso3 in econ:
            e = econ[iso3]
            row.update(name=e["name"], score=e["score"], label=e["label"], tracked=True)
            for k in ("inflation", "unemployment", "gdp"):
                x = e["indicators"].get(k)
                if x and not x.get("annual"):
                    row[k] = x["latest"]
        if ports and iso3 in ports["economies"]:
            row["trade"] = ports["economies"][iso3]
        if iso3 in power:
            row["power"] = power[iso3]["yoy_3m"]
        row.setdefault("inflation", row.get("inflation_a"))
        row.setdefault("unemployment", row.get("unemployment_a"))
        row.setdefault("gdp", row.get("gdp_growth"))
        map_rows[str(int(c.numeric))] = row

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "weo_release": weo_rel,
        "world": {"score": world, "label": label(world), "headline": headline(prices, ports), "breakdown": world_breakdown,
                  "trade_yoy": ports["global"].get("total") if ports else None,
                  "countries": len(map_rows), "tracked": len(econ),
                  "scored": sum(1 for r in map_rows.values() if r.get("score") is not None)},
        "drivers": drivers(econ, prices, ports),
        "economies": sorted(econ.values(), key=lambda e: (not e["g20"], -(e["score"] or -1))),
        "map": map_rows,
        "prices": prices, "markets": markets, "trade": ports, "products": R.PRODUCTS, "transport": transport,
        "freight": freight.get("rows", []),
        "power": {k: v for k, v in power.items()},
        "status": S.STATUS,
    }
    step("writing output")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(clean(data), separators=(",", ":")))
    for k, e in econ.items():                       # score history joins the chart series
        if e.get("history"):
            SERIES_OUT.setdefault(k, {})["score"] = [[d, round(v, 1)] for d, v in e["history"] if v is not None]
    (OUT.parent / "series.json").write_text(json.dumps(clean(SERIES_OUT), separators=(",", ":")))
    ok = sum(v["ok"] for v in S.STATUS.values())
    print(f"Wrote {OUT} | sources ok {ok}/{len(S.STATUS)} | world score {world} | map countries {len(map_rows)}")
    for k, v in S.STATUS.items():
        if not v["ok"]:
            print(f"  MISSING {k}: {v['note']}")


if __name__ == "__main__":
    main()
