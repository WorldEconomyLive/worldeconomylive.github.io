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
import sources as S
import changes as C  # noqa: E402
import history as HB  # noqa: E402
import packs as PK  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "heartbeat.json"
HIST = ROOT / "data" / "score_history.csv"
ARCH = ROOT / "site" / "data" / "archive"
INPUTS = ROOT / "data" / "archive" / "inputs"
PACKS = ROOT / "site" / "data" / "packs"
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
        return transform(S.dbnomics(sid), tf, {}), "Eurostat", False, "dbn:" + "/".join(sid.split("/")[:2])
    if kind == "wb":
        _, ind, tf = cand
        d = wb_all(ind)
        d = d[d.iso3 == iso3].sort_values("year")
        return S._series(d["value"], d["year"].astype(str) + "-07-01", ind), "World Bank (annual)", True, f"wb:{ind}"
    raise RuntimeError(kind)


def macro_block():
    areas = list(R.ECONOMIES)
    batch = {}
    for flow in {sp["flow"] for sp in R.OECD_SPECS.values()}:
        S.oecd_release(flow, "oecd:" + flow.split(",")[1])
    raw_batch = {}
    for ind, spec in R.OECD_SPECS.items():
        try:
            got = S.oecd_batch(spec, areas)
            res, raw = {}, {}
            for iso3, (s, attrs) in got.items():
                s = transform(s, spec["transform"], attrs).dropna()
                b = spec.get("bounds")
                if len(s):
                    raw[iso3] = s
                if len(s) and (b is None or abs(s.iloc[-1]) <= b):
                    res[iso3] = s
            batch[ind], raw_batch[ind] = res, raw
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
        rawe = RAW["macro"][iso3] = {"name": name, "g20": iso3 in R.G20, "ind": {}, "bis": None}
        for ind in ["gdp", "inflation", "unemployment", "industry", "long_rate", "short_rate", "exports_usd", "imports_usd"]:
            best = None   # (series, label, annual, release key)
            cands, tried = [], set()
            s0 = raw_batch.get(ind, {}).get(iso3)
            if s0 is not None:
                cands.append({"s": s0, "lab": "OECD", "annual": False, "rk": "oecd:" + R.OECD_SPECS[ind]["flow"].split(",")[1],
                              "b": R.OECD_SPECS[ind].get("bounds"), "o": 0})
            s = batch.get(ind, {}).get(iso3)
            if s is not None and age_months(s) <= R.MAX_STALE_MONTHS:
                best = (s, "OECD", False, "oecd:" + R.OECD_SPECS[ind]["flow"].split(",")[1])
            if best is None or age_months(best[0]) > R.FRESH_MONTHS:
                for ci, cand in enumerate(fb.get(ind, [])):
                    try:
                        tried.add(ci)
                        s2, lab, annual, rk = fallback_series(cand, iso3)
                        cands.append({"s": s2, "lab": lab, "annual": annual, "rk": rk, "b": None, "o": ci + 1})
                        lim = 30 if annual else R.MAX_STALE_MONTHS
                        if len(s2) < 3 or age_months(s2) > lim:
                            continue
                        if best is None or (not annual and age_months(s2) < age_months(best[0])):
                            best = (s2, lab, annual, rk)
                        if not annual and age_months(s2) <= R.FRESH_MONTHS:
                            break
                    except Exception:
                        continue
            for ci, cand in enumerate(fb.get(ind, [])):       # World Bank annual fallbacks are cheap: keep them for past dates
                if ci not in tried and cand[0] == "wb":
                    try:
                        s2, lab, annual, rk = fallback_series(cand, iso3)
                        cands.append({"s": s2, "lab": lab, "annual": annual, "rk": rk, "b": None, "o": ci + 1})
                    except Exception:
                        pass
            if cands:
                rawe["ind"][ind] = sorted(cands, key=lambda c: c["o"])
            if best:
                s, lab, annual, rk = best
                series[ind] = None if annual else s
                q = ind == "gdp"
                e["indicators"][ind] = {"latest": float(s.iloc[-1]), "date": s.index[-1], "annual": annual,
                                        "year_ago": value_ago(s, 335), "source": lab, "rel": rk,
                                        "chg": chg(s, IND_KIND[ind], "A" if annual else None),
                                        "spark": [] if annual else spark(s, 20 if q else 24, "QS" if q else "MS")}
        b = bis.get("XM" if iso3 in R.EURO else iso2)
        rawe["bis"] = b
        if b is not None and age_months(b) <= R.MAX_STALE_MONTHS:
            series["policy_rate"] = b
            e["indicators"]["policy_rate"] = {"latest": float(b.iloc[-1]), "date": b.index[-1], "annual": False,
                                              "year_ago": value_ago(b, 335), "source": "BIS", "rel": "bis",
                                              "chg": chg(b, "bp"), "spark": spark(b, 24)}
        elif "short_rate" in e["indicators"]:
            e["indicators"]["policy_rate"] = dict(e["indicators"]["short_rate"], source="OECD (3-month rate)")
            series["policy_rate"] = series.get("short_rate")
        # monthly merchandise trade in US$ -> balance
        X, Mi = series.get("exports_usd"), series.get("imports_usd")
        if X is not None and Mi is not None:
            bal = (X - Mi).dropna()
            if len(bal):
                rk = e["indicators"]["exports_usd"].get("rel")
                e["indicators"]["trade_balance_usd"] = {"latest": float(bal.iloc[-1]), "date": bal.index[-1], "annual": False,
                                                        "year_ago": value_ago(bal, 335), "source": "OECD", "rel": rk,
                                                        "chg": chg(bal, "abs"), "spark": spark(bal, 24)}
                Xm, Mm = X.resample("MS").sum(min_count=1).dropna(), Mi.resample("MS").sum(min_count=1).dropna()
                X12, M12 = Xm.rolling(12).sum().dropna(), Mm.rolling(12).sum().dropna()
                B12 = (X12 - M12).dropna()
                e["trade_m"] = {"exports": float(X.iloc[-1]), "imports": float(Mi.iloc[-1]), "balance": float(bal.iloc[-1]),
                                "rel": rk, "c": {"exports": chg(X, "pct"), "imports": chg(Mi, "pct"), "balance": chg(bal, "abs"),
                                                 "exports_12m": chg(X12, "pct"), "imports_12m": chg(M12, "pct"),
                                                 "balance_12m": chg(B12, "abs")},
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


def history_series(e, months=120, full=False):
    """Monthly history of every scorecard column (last 10 years for the chart; full=True for change calculations)."""
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
        out["taylor"], out["output_gap"] = taylor, gap
        if i is not None:
            out["taylor_gap"] = (i.reindex(taylor.index).ffill() - taylor)
        a3 = uu.rolling(3).mean()
        out["sahm"] = a3 - a3.shift(1).rolling(12).min()
    if X is not None and M is not None:
        b = (X - M).dropna()
        out["trade_balance"] = b
        out["trade_balance_12m"] = b.rolling(12).sum()
    if full:
        return {k: v.dropna() for k, v in out.items()}
    res = {}
    for k, v in out.items():
        if k in ("taylor", "output_gap"):
            continue
        v = v.dropna()
        v = v[v.index >= v.index.max() - pd.DateOffset(months=months)] if len(v) else v
        if len(v) >= 3:
            res[k] = [[d.strftime("%Y-%m"), round(float(x), 3)] for d, x in v.items()]
    return res


def derived_series(e):
    """History of the debt-math and balance figures, so they carry changes like everything else."""
    S_, H = e.get("_series", {}), ANNUAL_HIST.get(e["iso3"], {})
    out = {}
    pi = None if S_.get("inflation") is None else S_["inflation"].resample("MS").mean()
    lr = None if S_.get("long_rate") is None else S_["long_rate"].resample("MS").mean()
    g = S_.get("gdp")
    if g is not None and pi is not None:
        gm = g.resample("MS").mean().reindex(pi.index).ffill(limit=5)
        out["nominal_growth"] = (gm + pi).dropna()
        if lr is not None:
            out["r_minus_g"] = (lr - out["nominal_growth"]).dropna()

            def by_year(a):
                return pd.Series([a.get(pd.Timestamp(f"{d.year}-07-01")) for d in out["r_minus_g"].index],
                                 index=out["r_minus_g"].index, dtype=float)
            if "gov_debt" in H:
                d_m = by_year(H["gov_debt"])
                out["pb_stabilizing"] = (out["r_minus_g"] / (100 + out["nominal_growth"].reindex(d_m.index)) * d_m).dropna()
                if "primary_balance" in H:
                    out["fiscal_gap"] = (by_year(H["primary_balance"]) - out["pb_stabilizing"]).dropna()
    if "savings" in H and ("investment_weo" in H or "investment" in H):
        out["s_minus_i"] = (H["savings"] - H.get("investment_weo", H.get("investment"))).dropna()
    if "current_account" in H and "gov_balance" in H:
        out["twin"] = (H["current_account"] + H["gov_balance"]).dropna()
    if "exports_usd_a" in H and "imports_usd_a" in H:
        out["trade_balance_usd"] = (H["exports_usd_a"] - H["imports_usd_a"]).dropna()
    return out


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
            m["sahm"] = float(a3.iloc[-1] - a3.iloc[-13:-1].min())   # vs the lowest of the prior 12 months
    return m


def real_rate_any(e):
    """Policy rate minus the latest inflation reading; falls back to annual inflation if no monthly CPI."""
    if e["math"].get("real_rate") is not None:
        return e["math"]["real_rate"]
    I = e["indicators"]
    i, pi = I.get("policy_rate", {}).get("latest"), I.get("inflation", {}).get("latest")
    return None if i is None or pi is None else i - pi


# ---------------------------------------------------------------- annual (all countries)
SERIES_OUT: dict = {}
RAW: dict = {"macro": {}}   # every raw input series, for the daily input archive and for rebuilding past dates
TRADE_SER: dict = {}     # iso3 -> (monthly exports, monthly imports) for the all-economies total row    # iso3 -> {column: [[YYYY-MM, value], ...]} written to site/data/series.json
ANNUAL_HIST: dict = {}
IND_KIND = {"gdp": "pp", "inflation": "pp", "unemployment": "pp", "industry": "pp", "long_rate": "bp", "short_rate": "bp",
            "policy_rate": "bp", "exports_usd": "pct", "imports_usd": "pct", "trade_balance_usd": "abs"}
ANNUAL_KIND = {"gdp_growth": "pp", "inflation_a": "pp", "unemployment_a": "pp", "gdp_usd": "pct", "gov_debt": "pp",
               "gov_balance": "pp", "primary_balance": "pp", "revenue": "pp", "spending": "pp", "current_account": "pp",
               "savings": "pp", "investment_weo": "pp", "population": "pct", "pop_growth": "pp", "age65": "pp",
               "fertility": "pct", "life_exp": "pct", "health_spend": "pp", "net_migration": "abs", "gdp_pc": "pct",
               "gini": "pts", "urban": "pp", "exports_usd_a": "pct", "imports_usd_a": "pct", "net_exports": "pp",
               "consumption": "pp", "investment": "pp", "gov_consumption": "pp", "reserves_usd": "pct",
               "reserves_months": "pct", "private_credit": "pp", "debt_wb": "pp",
               "gdp_growth_wb": "pp", "inflation_wb": "pp", "unemployment_wb": "pp", "gdp_usd_wb": "pct"}
MATH_KIND = {"real_rate": "bp", "misery": "pp", "curve": "bp", "taylor_gap": "bp", "taylor": "bp", "sahm": "pp",
             "output_gap": "pp", "nominal_growth": "pp", "r_minus_g": "pp", "pb_stabilizing": "pp", "fiscal_gap": "pp",
             "s_minus_i": "pp", "twin": "pp", "trade_balance_usd": "abs"}


def chg(s, kind, freq=None):
    o = C.change(s, kind, freq)
    o["a"] = "".join(str(x) for x in o["a"])
    return o


def schg(s, window):
    """Seasonal (not seasonally adjusted) series: same window vs the same window N years earlier; 1Y+ only."""
    o = C.seasonal_change(s, window)
    o["a"] = "".join(str(x) for x in o["a"])
    return o   # iso3 -> {gdp_growth|inflation_a|unemployment_a: annual series}


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


def done_years(s):
    """Completed calendar years only: the current year's WEO figure is a forecast and is never scored."""
    if s is None:
        return None
    s = s.dropna()
    s = s[s.index.year < TODAY.year]
    return s if len(s) and s.index[-1].year >= TODAY.year - R.ANNUAL_MAX_AGE else None


def annual_score(iso3, ports, power):
    """Score for countries without monthly data: completed years of IMF WEO (World Bank where WEO has none)
    vs that country's own history, blended with port cargo and electricity where available. Same 50 + 15*z scale."""
    H, p = ANNUAL_HIST.get(iso3, {}), {}
    g = done_years(H.get("gdp_growth"))
    if g is not None:
        p["activity"] = z_annual(g)
    pz = power.get(iso3, {}).get("z")
    if pz is not None:
        p["activity"] = pz if p.get("activity") is None else (p["activity"] + pz) / 2
    u = done_years(H.get("unemployment_a"))
    if u is not None and len(u) > 9:
        z = z_annual(u.diff().dropna())
        p["labor"] = None if z is None else -z
    pi = done_years(H.get("inflation_a"))
    if pi is not None:
        p["prices"] = z_annual(-(pi - 2.0).abs())
    if ports and iso3 in ports.get("economies", {}):
        p["trade"] = float(np.clip(ports["economies"][iso3] / 10, -3, 3))
    zs = {k: v for k, v in p.items() if v is not None}
    if len(zs) < 2:
        return None, None
    return float(np.clip(50 + 15 * np.mean(list(zs.values())), 0, 100)), {PILLAR_NAMES[k]: round(15 * v / len(zs), 2) for k, v in zs.items()}


def stale_pillars(iso3):
    """Pillars with annual data whose latest completed year is too old to score: {pillar word: latest year}."""
    H, out = ANNUAL_HIST.get(iso3, {}), {}
    for k, word in (("gdp_growth", "output"), ("unemployment_a", "jobs"), ("inflation_a", "prices")):
        s = H.get(k)
        if s is None:
            continue
        s = s.dropna()
        s = s[s.index.year < TODAY.year]
        if len(s) and done_years(H.get(k)) is None:
            out[word] = int(s.index[-1].year)
    return out


def unscored_reason(iso3, ports, power):
    """Why a country on the map has no score: which of the four pillars have data."""
    H, have = ANNUAL_HIST.get(iso3, {}), []
    if done_years(H.get("gdp_growth")) is not None or power.get(iso3, {}).get("z") is not None:
        have.append("output")
    u = done_years(H.get("unemployment_a"))
    if u is not None and len(u) > 9:
        have.append("jobs")
    if done_years(H.get("inflation_a")) is not None:
        have.append("prices")
    if ports and iso3 in ports.get("economies", {}):
        have.append("trade")
    return have


def unit_check(allc, key="gdp_usd", ref="gdp_usd_wb"):
    """Guard against a source changing units (e.g. billions vs full dollars): compare WEO GDP in US$ with the
    World Bank's for the same countries and years; if the median ratio is off by a power of 1,000, rescale and log."""
    ratios = []
    for iso3, H in ANNUAL_HIST.items():
        a, b = H.get(key), H.get(ref)
        if a is None or b is None or a is b:
            continue
        j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
        j = j[(j.a > 0) & (j.b > 0)]
        ratios += list((j.a / j.b).values[-5:])
    if len(ratios) < 20:
        return
    med = float(np.median(ratios))
    k = int(round(np.log10(med) / 3)) * 3
    if k == 0:
        S.log(f"weo.{key}.units", True, f"matches World Bank (median ratio {med:.3f})")
        return
    f = 10.0 ** -k
    for iso3, H in ANNUAL_HIST.items():
        if H.get(key) is not None and H.get(key) is not H.get(ref):
            H[key] = H[key] * f
            if key in allc.get(iso3, {}):
                r = allc[iso3][key]
                r["value"] = r["value"] * f
                r["chg"] = chg(H[key], ANNUAL_KIND.get(key, "pct"), "A")
    S.log(f"weo.{key}.units", False, f"rescaled by 1e{-k}: median ratio to World Bank was {med:.3g}")


def annual_block():
    """IMF WEO + World Bank for every country. Returns ({iso3: {key: record}}, weo_release)."""
    from concurrent.futures import ThreadPoolExecutor
    allc, rel_used = {}, None
    first = next(iter(R.WEO.values()))[0]
    try:                                            # find the live WEO release once
        _, rel_used = S.weo_all(first, R.WEO_RELEASES)
    except Exception:
        pass
    rels = [rel_used] if rel_used and str(rel_used).startswith("WEO:") else R.WEO_RELEASES   # DBnomics ids, for the fallback
    with ThreadPoolExecutor(4) as ex:
        weo = {k: ex.submit(S.weo_all, v[0], rels) for k, v in R.WEO.items()}
        wbf = {k: ex.submit(wb_all, v[0]) for k, v in R.WB.items()}
    for key, (code, label, unit, scale) in R.WEO.items():
        try:
            data, rel = weo[key].result()
            rel_used = rel
            for iso3, s in data.items():
                s = (s[s.index.year <= TODAY.year] * scale).dropna()
                ANNUAL_HIST.setdefault(iso3, {})[key] = s
                if len(s):
                    allc.setdefault(iso3, {})[key] = {"label": label, "unit": unit, "value": float(s.iloc[-1]),
                                                      "year": int(s.index[-1].year), "source": "IMF WEO", "rel": "weo",
                                                      "chg": chg(s, ANNUAL_KIND.get(key, "pp"), "A"),
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
                ser = C.annual_series(zip(g["year"], g["value"]))
                ANNUAL_HIST.setdefault(iso3, {})[key] = ser
                allc.setdefault(iso3, {})[key] = {"label": label, "unit": unit, "value": float(last["value"]),
                                                  "year": int(last["year"]), "source": "World Bank", "estimate": False,
                                                  "rel": f"wb:{ind}", "chg": chg(ser, ANNUAL_KIND.get(key, "pct"), "A"),
                                                  "ten_years_ago": float(ten.iloc[-1]["value"]) if len(ten) else None}
            S.log(f"worldbank.{ind}", True, f"{df.iso3.nunique()} countries")
        except Exception as e:
            S.log(f"worldbank.{ind}", False, e)
    unit_check(allc)
    # fall back to the World Bank when WEO has no series for a country (same object, so packs can tell)
    for iso3, d in allc.items():
        for key, wbk in R.WB_FALLBACK.items():
            if key not in d and wbk in d:
                lab = R.WEO[key][1] if key in R.WEO else d[wbk]["label"]
                d[key] = dict(d[wbk], label=lab if key != "gov_debt" else "Government debt")
                if wbk in ANNUAL_HIST.get(iso3, {}):
                    ANNUAL_HIST[iso3][key] = ANNUAL_HIST[iso3][wbk]
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
        RAW["pink"] = {}
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
        RAW["pink"][name] = s
        if len(s) < 13:
            continue
        rows.append({"name": name, "ship": ship, "level": float(s.iloc[-1]), "date": s.index[-1],
                     "unit": unit, "m1": pct(float(s.iloc[-1]), float(s.iloc[-2])), "chg": chg(s, "pct"), "rel": "pink",
                     "yoy": pct(float(s.iloc[-1]), value_ago(s, 360)), "spark": spark(s, 24)})
    return rows


def markets_block():
    out = {"fx": [], "rates": [], "us_fiscal": [], "global_rates": [], "fx_note": "ECB euro foreign exchange reference rates (spot, set daily around 14:15 CET), converted to US-dollar pairs through the euro: USD/XXX = (XXX per EUR) ÷ (USD per EUR)."}
    start = (TODAY - pd.DateOffset(years=22)).strftime("%Y-%m-%d")
    try:
        fx = S.ecb_fx(R.FX, start)
        RAW["fx"] = fx
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
            value_usd = s_ if (c in R.FX_BASE_IS_FOREIGN or c == "EUR") else 1 / s_     # US$ per 1 unit of the currency
            # sign so that + always means the foreign currency strengthened vs USD
            strong = 1 if c in R.FX_BASE_IS_FOREIGN or c == "EUR" else -1
            m1, y1 = pct(last, value_ago(s_, 30)), pct(last, value_ago(s_, 365))
            out["fx"].append({"name": R.FX_NAMES.get(c, c), "code": c, "pair": pair, "meaning": meaning,
                              "latest": last, "date": s_.index[-1], "m1": m1, "y1": y1,
                              "ccy_y1": None if y1 is None else strong * y1, "rel": "ecb",
                              "chg": chg(s_, "pct"), "ccy_chg": chg(value_usd, "pct"),
                              "spark": spark(s_, 13), "unit": "%"})
    except Exception as e:
        S.log("ecb.fx", False, e)

    def rate_row(name, s, rel):
        s = s.dropna()
        last = float(s.iloc[-1])
        a, b = value_ago(s, 30), value_ago(s, 365)
        out["rates"].append({"name": name, "latest": last, "date": s.index[-1], "unit": "pp", "rel": rel, "chg": chg(s, "bp"),
                             "m1": None if a is None else last - a, "y1": None if b is None else last - b,
                             "spark": spark(s, 13)})
    try:
        effr = S.nyfed_effr()
        RAW["effr"] = effr
        S.log("nyfed.effr", True)
        rate_row("Fed funds (effective)", effr, "nyfed")
    except Exception as e:
        S.log("nyfed.effr", False, e)
    try:
        yc = S.treasury_curve()
        RAW["yc"] = yc
        S.log("treasury.curve", True)
        for col, nm in (("3 Mo", "3-month T-bill"), ("2 Yr", "2-year Treasury"), ("10 Yr", "10-year Treasury"), ("30 Yr", "30-year Treasury")):
            if col in yc:
                rate_row(nm, yc[col], "treasury")
        mats = [c for c in ("1 Mo", "2 Mo", "3 Mo", "4 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr") if c in yc]
        ycd = yc[mats].dropna(how="all")
        last_d = ycd.index[-1]
        curve = {"maturities": mats, "today": {"date": last_d, "y": [None if pd.isna(v) else float(v) for v in ycd.iloc[-1]]}, "past": {}}
        for per, m in C.PERIODS:
            tgt = last_d - pd.DateOffset(months=m)
            win = ycd[(ycd.index <= tgt) & (ycd.index >= tgt - pd.Timedelta(days=7))]
            if len(win):
                row = win.iloc[-1]
                curve["past"][per] = {"date": win.index[-1], "y": [None if pd.isna(v) else float(v) for v in row]}
            else:
                curve["past"][per] = {"date": None, "y": None, "why": "s" if tgt < ycd.index[0] else "g", "start": ycd.index[0]}
        out["curve"] = curve
        if "10 Yr" in yc and "2 Yr" in yc:
            rate_row("Yield curve (10y − 2y)", yc["10 Yr"] - yc["2 Yr"], "treasury")
        try:
            ry = S.treasury_curve("daily_treasury_real_yield_curve")
            if "10 YR" in ry or "10 Yr" in ry:
                real10 = ry["10 YR"] if "10 YR" in ry else ry["10 Yr"]
                RAW["ry"] = real10
                rate_row("10-year real yield", real10, "treasury")
                rate_row("Inflation expected, next 10 years", (yc["10 Yr"] - real10).dropna(), "treasury")
        except Exception:
            pass
    except Exception as e:
        S.log("treasury.curve", False, e)
    try:
        debt = S.treasury_debt()
        RAW["debt"] = debt
        S.log("treasury.debt", True)
        last = float(debt.iloc[-1])
        try:
            fy = S.us_fiscal_years()
            RAW["fy"] = fy
            S.log("treasury.mts", True, f"{fy.fy.nunique()} fiscal years")
            fyrows = []
            for f_, g in fy.groupby("fy"):
                x = g.sort_values("through").iloc[-1]
                full = x["through"].month == 9
                end = pd.Timestamp(f"{f_}-09-30")
                de = debt[debt.index <= end]
                ds = debt[debt.index <= pd.Timestamp(f"{f_ - 1}-09-30")]
                fyrows.append({"fy": int(f_), "complete": bool(full), "through": x["through"],
                               "receipts": x["receipts"], "outlays": x["outlays"], "balance": x["receipts"] - x["outlays"],
                               "debt_end": float(de.iloc[-1]) if full and len(de) and de.index[-1] >= end - pd.Timedelta(days=7) else None,
                               "debt_start": float(ds.iloc[-1]) if len(ds) and ds.index[-1] >= pd.Timestamp(f"{f_ - 1}-09-23") else None})
            for r_ in fyrows:
                if r_["debt_end"] is not None and r_["debt_start"] is not None:
                    r_["debt_change"] = r_["debt_end"] - r_["debt_start"]
            out["us_fy"] = sorted(fyrows, key=lambda r_: -r_["fy"])[:25]
        except Exception as e:
            S.log("treasury.mts", False, e)
        out["us_fiscal"].append({"name": "US federal debt (total)", "latest": last, "date": debt.index[-1],
                                 "y1_abs": None if value_ago(debt, 365) is None else last - value_ago(debt, 365),
                                 "y1": pct(last, value_ago(debt, 365)), "rel": "fiscaldata", "chg": chg(debt, "pct")})
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
    start = "2019-01-01"
    S.portwatch_release("Daily_Ports_Data", "portwatch")
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
            dd = d.groupby("date")[["n_total"] + [c for c in ("n_tanker", "capacity") if c in d]].sum().asfreq("D")
            dd = dd[dd.index <= end]
            cw = C.window_change(dd, end, R.WINDOW_DAYS, start=dd.index.min())
            for o in cw.values():
                o["a"] = "".join(str(x) for x in o["a"])
            cps.append({"name": cname, "lon": lon, "lat": lat, "chg": cw.get("n_total"), "rel": "portwatch",
                        "transits_yoy": pct(float(cur["n_total"].sum()), float(prv["n_total"].sum())),
                        "tanker_yoy": pct(float(cur["n_tanker"].sum()), float(prv["n_tanker"].sum())) if "n_tanker" in d else None,
                        "capacity_yoy": pct(float(cur["capacity"].sum()), float(prv["capacity"].sum())) if "capacity" in d else None,
                        "daily_transits": float(cur["n_total"].mean()) if len(cur) else None})
        except Exception:
            pass
    S.log("portwatch.chokepoints", bool(cps), f"{len(cps)}/24")

    names = picks.set_index("portid")
    portrows = ratio(win(a, end, "portid"), win(pa, pb, "portid")).join(names[["portname", "ISO3", "region"]])

    # Change over every period: 28-day window vs the same window `period` earlier (5Y+: 365-day averages)
    first = pv["date"].min()

    def daily(key=None, cols_=cols):
        g = pv[pv.date <= end]
        if key is None:
            d = g.groupby("date")[cols_].sum()
        else:
            d = g.groupby(["date", key])[cols_].sum().unstack(key)
        return d.asfreq("D")
    pc = {"global": C.window_change(daily(), end, R.WINDOW_DAYS, start=first)}
    reg_d = daily("region")
    pc["regions"] = {r: C.window_change(reg_d.xs(r, axis=1, level=1), end, R.WINDOW_DAYS, start=first)
                     for r in reg_d.columns.get_level_values(1).unique()}
    eco_d = daily("ISO3", ["total"])
    pc["economies"] = {i: C.window_change(eco_d.xs(i, axis=1, level=1), end, R.WINDOW_DAYS, start=first)["total"]
                       for i in eco_d.columns.get_level_values(1).unique()}
    port_d = daily("portid")
    pc["ports"] = {p: C.window_change(port_d.xs(p, axis=1, level=1), end, R.WINDOW_DAYS, start=first)
                   for p in port_d.columns.get_level_values(1).unique()}
    RAW["ports"] = {"glob": daily(), "reg": {r: reg_d.xs(r, axis=1, level=1) for r in reg_d.columns.get_level_values(1).unique()},
                    "eco": {i: eco_d.xs(i, axis=1, level=1)["total"] for i in eco_d.columns.get_level_values(1).unique()},
                    "cp": {cid: d.groupby("date")[["n_total"] + [c for c in ("n_tanker", "capacity") if c in d]].sum().asfreq("D")
                           for cid, d in cpdata.items() if d is not None and len(d)},
                    "end": end, "first": first}
    for blk in (pc["global"], *pc["regions"].values(), *pc["economies"].values(), *pc["ports"].values()):
        for o in (blk.values() if "v" not in blk else [blk]):
            o["a"] = "".join(str(x) for x in o["a"])
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
        "ports": [{"port": row["portname"], "iso3": row["ISO3"], "region": row["region"], **row[cols].to_dict(),
                   "c": pc["ports"].get(pid)} for pid, row in portrows.iterrows()],
        "pc": {"global": pc["global"], "regions": pc["regions"], "economies": pc["economies"]},
        "rel": "portwatch",
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
    RAW["ember"] = {}
    for iso3, g in df.groupby("iso3"):
        s = g.set_index("date")["value"].sort_index()
        s = s[~s.index.duplicated()]
        RAW["ember"][iso3] = s
        if len(s) < 27 or age_months(s) > 8:
            continue
        s3 = s.rolling(3).sum()
        y = ((s3 / s3.shift(12) - 1) * 100).dropna()     # 3-month demand vs same 3 months a year ago
        if not len(y):
            continue
        out[iso3] = {"twh": float(s.iloc[-1]), "date": s.index[-1], "yoy_3m": float(y.iloc[-1]), "rel": "ember",
                     "chg": schg(s, 3), "z": z_last(y, min_n=24), "spark": spark(y, 24)}
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
        RAW.setdefault("bts", []).append((name, col, s))
        rows.append({"name": name, "latest": float(s.iloc[-1]), "date": s.index[-1], "rel": "bts", "chg": schg(s, 1),
                     "yoy": pct(float(s.iloc[-1]), value_ago(s, 360)), "spark": spark(s, 24), "field": col})
    S.log("bts.transport", bool(rows), f"{len(rows)} series")
    return rows


def freight_block():
    """Rail and air freight outside the US: EU air (monthly), EU rail (quarterly), Canada rail (monthly).
    Returns {"rows": [...table rows...], "z": {iso3: z of freight volume growth vs own history}}."""
    rows, zs, skipped = [], {}, []

    def add(iso3, mode, s, unit, quarterly=False, rel=None):
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
                     "period": "quarter" if quarterly else "3 months", "rel": rel, "chg": schg(s, 1 if quarterly else 3)})
        if z is not None:
            zs.setdefault(iso3, []).append(z)

    for name, fn, mode, unit, q, rk in (("eurostat.air_freight", S.eu_air_freight, "Air freight", "tonnes", False, "eurostat:avia_gooc"),
                                        ("eurostat.rail_freight", S.eu_rail_freight, "Rail freight", "thousand tonnes", True, "eurostat:rail_go_quartal")):
        try:
            data = fn()
            RAW.setdefault("freight", {})["air" if q is False else "rail"] = data
            n0 = len(rows)
            for iso3, ser in data.items():
                add(iso3, mode, ser, unit, q, rk)
            kept = len(rows) - n0
            note = f"{kept}/{len(data)} countries current"
            if kept < len(data):
                note += " · skipped e.g. " + "; ".join([x for x in skipped if mode in x][:2])
            S.log(name, kept > 0, note)
        except Exception as ex:
            S.log(name, False, ex)
    try:
        cr = S.canada_rail()
        RAW.setdefault("freight", {})["can"] = cr
        add("CAN", "Rail carloadings", cr, "tonnes", rel="statcan")
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
                RAW.setdefault("pink_stress", {})[key] = ps[col]
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


def drivers_by_period(econ, prices, ports):
    """'What changed' for every period on the toggle, from the same change objects the tables use."""
    words = ["past month", "past 3 months", "past 6 months", "past year", "past 3 years", "past 5 years",
             "past 10 years", "past 15 years", "past 20 years"]
    out = {}
    for i, per in enumerate(C.NAMES):
        yr = i >= 4

        def say(subject, v, lead="is"):
            return (f"{subject} {lead} {'up' if v > 0 else 'down'} {abs(v):.0f}%"
                    + (f" a year over the {words[i]} (compound)." if yr else f" over the {words[i]}."))
        lines = []
        if ports:
            cps = [(c["name"], (c.get("chg") or {}).get("v", [None] * 9)[i]) for c in ports["chokepoints"]]
            for n, v in sorted([x for x in cps if x[1] is not None], key=lambda x: -abs(x[1]))[:2]:
                if abs(v) >= (5 if yr else 15):
                    lines.append(say(f"Ship traffic at {n}", v))
            regs = [(r, o.get("total", {}).get("v", [None] * 9)[i]) for r, o in ports.get("pc", {}).get("regions", {}).items()]
            for n, v in sorted([x for x in regs if x[1] is not None], key=lambda x: -abs(x[1]))[:2]:
                lines.append(say(f"{n} port cargo", v))
        pr = [(p["name"], p["chg"]["v"][i]) for p in prices if p.get("chg") and p["chg"]["v"][i] is not None]
        for n, v in sorted(pr, key=lambda x: -abs(x[1]))[:3]:
            lines.append(say(n, v))
        out[per] = lines
    return out


def coverage_report(data):
    """n/a matrix for every change object on the site, grouped by source: {group: {period: {code: count}}}."""
    rep = {}

    def walk(x, rel=None, where=""):
        if isinstance(x, dict):
            if "v" in x and "r" in x and "k" in x and isinstance(x.get("r"), str):
                g = rep.setdefault(f"{rel or where}", {p: {} for p in C.NAMES})
                for p, code in zip(C.NAMES, x["r"]):
                    g[p][code] = g[p].get(code, 0) + 1
                return
            r = x.get("rel") if isinstance(x.get("rel"), str) else rel
            for k, v in x.items():
                if k not in ("coverage", "rel", "status"):
                    walk(v, r, where if r else k)
        elif isinstance(x, list):
            for v in x:
                walk(v, rel, where)
    walk({k: v for k, v in data.items() if k not in ("rel", "status")})
    return rep


YEAR_KEYS = {  # key: (label, unit, release key)
    "gdp_growth": ("GDP growth", "%", "weo"), "inflation_a": ("Inflation", "%", "weo"), "unemployment_a": ("Unemployment", "%", "weo"),
    "gdp_usd": ("GDP", "US$", "weo"), "gov_debt": ("Government debt", "% of GDP", "weo"), "gov_balance": ("Budget balance", "% of GDP", "weo"),
    "primary_balance": ("Primary balance", "% of GDP", "weo"), "current_account": ("Current account", "% of GDP", "weo"),
    "revenue": ("Government revenue", "% of GDP", "weo"), "spending": ("Government spending", "% of GDP", "weo"),
    "net_exports": ("Trade balance (net exports)", "% of GDP", "wb:NE.RSB.GNFS.ZS"), "exports_usd_a": ("Exports", "US$", "wb:NE.EXP.GNFS.CD"),
    "imports_usd_a": ("Imports", "US$", "wb:NE.IMP.GNFS.CD"), "population": ("Population", "people", "wb:SP.POP.TOTL"),
    "gdp_pc": ("GDP per person", "US$", "wb:NY.GDP.PCAP.CD"), "life_exp": ("Life expectancy", "years", "wb:SP.DYN.LE00.IN"),
    # also used by the map readout for countries without a score
    "pop_growth": ("Population growth", "%", "wb:SP.POP.GROW"), "age65": ("Aged 65+", "% of pop.", "wb:SP.POP.65UP.TO.ZS"),
    "fertility": ("Births per woman", "", "wb:SP.DYN.TFRT.IN"), "health_spend": ("Health spending", "% of GDP", "wb:SH.XPD.CHEX.GD.ZS"),
    "net_migration": ("Net migration", "people", "wb:SM.POP.NETM"), "urban": ("Urban population", "% of pop.", "wb:SP.URB.TOTL.IN.ZS"),
    "gini": ("Inequality (Gini)", "0-100", "wb:SI.POV.GINI"), "reserves_usd": ("FX reserves", "US$", "wb:FI.RES.TOTL.CD"),
    # World Bank stand-ins, used by the readouts only where the IMF WEO has no series for the country
    "gdp_growth_wb": ("GDP growth", "%", "wb:NY.GDP.MKTP.KD.ZG"), "inflation_wb": ("Inflation", "%", "wb:FP.CPI.TOTL.ZG"),
    "unemployment_wb": ("Unemployment", "%", "wb:SL.UEM.TOTL.ZS"), "gdp_usd_wb": ("GDP", "US$", "wb:NY.GDP.MKTP.CD"),
}


def annual_export(map_rows):
    """Calendar-year values for every country, for the year-by-year lookup: {iso3: {key: [first_year, [values]]}}."""
    names = {r["iso3"]: r["name"] for r in map_rows.values()}
    g20 = set(R.G20)
    data, years = {}, set()
    for iso3, H in ANNUAL_HIST.items():
        if iso3 not in names:
            continue
        rec = {}
        for k in YEAR_KEYS:
            s_ = H.get(k)
            if s_ is None or not len(s_) or (k in R.WB_FALLBACK and s_ is H.get(R.WB_FALLBACK[k])):
                continue                     # year table rows carry one source each; stand-ins show in the readout
            s_ = s_[s_.index.year >= 1980]
            if not len(s_):
                continue
            y0, y1 = int(s_.index.year.min()), int(s_.index.year.max())
            by = {int(d.year): float(v) for d, v in s_.items()}
            rec[k] = [y0, [by.get(y) for y in range(y0, y1 + 1)]]
            years.update(range(y0, y1 + 1))
        if rec:
            data[iso3] = rec
    return {"data": data, "keys": {k: {"label": v[0], "unit": v[1], "rel": v[2], "kind": ANNUAL_KIND.get(k, "pp")} for k, v in YEAR_KEYS.items()},
            "names": {i: names[i] for i in data}, "g20": sorted(g20 & set(data)),
            "years": [min(years), max(years)] if years else None, "estimate_from": int(TODAY.year),
            "rel": {k: v for k, v in S.REL.items() if k == "weo" or k.startswith("wb:")}}


BAND_WORDS = {"Strong": "strong", "Steady": "steady", "Soft": "soft", "Stressed": "under stress"}
PILLAR_WORD = {"activity": "output", "labor": "jobs", "prices": "prices", "trade": "trade"}


# Codes outside ISO 3166 that the IMF and World Bank publish: map key (matched by name on the map) and display name
EXTRA_ISO = {"XKX": ("XKX", "Kosovo")}


def cty(iso3):
    """(map key, name) for an ISO3 code: ISO numeric for standard countries, the code itself for Kosovo."""
    if iso3 in EXTRA_ISO:
        return EXTRA_ISO[iso3]
    import pycountry
    c = pycountry.countries.get(alpha_3=iso3)
    return (int(c.numeric), c.name) if c else None


def headline(world, econ, prices, ports):
    """Leads with the score band, so the words always match the number; then the main driver:
    the pillar furthest from normal on average across scored economies, or the trade/energy shock when it fires."""
    if world is None:
        return "Global economy: score pending."
    lab = label(world)
    out = f"Global economy {BAND_WORDS.get(lab, lab.lower())} ({world:.0f})."
    vol = ports["global"].get("total") if ports else None
    oil = next((p["yoy"] for p in prices if p["name"] == "Brent crude"), None)
    if vol is not None and oil is not None and vol < -2 and oil > 15:
        return out + " Main driver: a supply shock, with goods moving less while oil prices rise."
    zs = {}
    for e in econ.values():
        if e.get("score") is None:
            continue
        for k, v in (e.get("pillars") or {}).items():
            if v is not None:
                zs.setdefault(k, []).append(v)
    if zs:
        k, m = max(((k, float(np.mean(v))) for k, v in zs.items()), key=lambda x: abs(x[1]))
        if abs(m) >= 0.1:
            return out + f" Main {'drag' if m < 0 else 'support'}: {PILLAR_WORD.get(k, k)}."
    return out


def save_history(scores):
    """Append today's scores ({iso3|WLD: score}) to data/score_history.csv (the archive of scores as shown each day);
    return {iso3: daily score series}."""
    rows = [{"date": TODAY.strftime("%Y-%m-%d"), "iso3": k, "score": v} for k, v in scores.items() if v is not None]
    new = pd.DataFrame(rows, columns=["date", "iso3", "score"])
    if HIST.exists():
        old = pd.read_csv(HIST)
        new = pd.concat([old[old["date"] != TODAY.strftime("%Y-%m-%d")], new])
    HIST.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(HIST, index=False)
    new["date"] = pd.to_datetime(new["date"])
    return {i: g.set_index("date")["score"].sort_index().astype(float) for i, g in new.groupby("iso3")}


def write_packs(rb, hist, days, data):
    """Inputs and rebuilt scores the browser needs to show the site as of any past date."""
    N = len(days)

    def daily(k):
        s_ = hist.get(k)
        return s_.reindex(days).values if s_ is not None else np.full(N, np.nan)
    scores = {"day0": PK.dayn(days[0]), "n": N, "c": {}, "w": {}}
    if rb is not None:
        for iso3, p in rb["pillars"].items():
            scores["c"][iso3] = {"s": HB.rle(daily(iso3), 3), "p": {k: HB.rle(v, 3) for k, v in p.items()}}
        scores["w"] = {"s": HB.rle(daily("WLD"), 3), "avg": HB.rle(rb["avg"], 2), "stress": HB.rle(rb["stress"], 2),
                       "comps": {k: HB.rle(v, 3) for k, v in rb["comps"].items()}, "glob": HB.rle(rb["glob"], 2)}
    meta = {"today": PK.dayn(TODAY), "asof": clean(data["asof"]), "rel": S.REL, "iso": RAW.get("iso", {}),
            "max_stale": R.MAX_STALE_MONTHS, "fresh": R.FRESH_MONTHS, "window": R.WINDOW_DAYS, "lag_days": R.LAG_DAYS,
            "econ": {k: v[0] for k, v in R.ECONOMIES.items()}, "g20": R.G20, "euro": sorted(R.EURO),
            "fx": R.FX, "fx_names": R.FX_NAMES, "fx_units": R.FX_UNITS, "fx_base_foreign": sorted(R.FX_BASE_IS_FOREIGN),
            "fx_note": data["markets"].get("fx_note"), "commodities": R.COMMODITIES,
            "chokepoints": R.CHOKEPOINTS, "regions": R.REGIONS, "products": R.PRODUCTS, "vital_keys": R.VITAL_KEYS,
            "weo": {k: [v[1], v[2]] for k, v in R.WEO.items()}, "wb": {k: [v[0], v[1], v[2]] for k, v in R.WB.items()}, "wb_fallback": R.WB_FALLBACK,
            "annual_kind": ANNUAL_KIND, "ind_kind": IND_KIND, "math_kind": MATH_KIND,
            "year_keys": {k: list(v) for k, v in YEAR_KEYS.items()}, "status": S.STATUS}
    PK.write_packs(RAW, meta, scores, PACKS)


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
        e["fundamentals"] = {x: v for x, v in f.items() if x not in R.VITAL_KEYS and not (x.endswith("_wb") and x != "debt_wb")}
        e["math"] = macro_math(e)
        e["derived"] = derive(e, e["fundamentals"])
        SERIES_OUT[k] = history_series(e)
        tb = SERIES_OUT[k].get("trade_balance_12m")
        if tb:
            e.setdefault("trade_m", {})["balance_12m"] = tb[-1][1]
        full = history_series(e, full=True)
        e["mchg"] = {mk: chg(full[mk], MATH_KIND[mk], "M") for mk in MATH_KIND if mk in full and len(full[mk])}
        e["dchg"] = {dk: chg(v, MATH_KIND[dk], "A" if dk in ("s_minus_i", "twin", "trade_balance_usd") else "M")
                     for dk, v in derived_series(e).items() if len(v)}
        X_, M_ = e["_series"].get("exports_usd"), e["_series"].get("imports_usd")
        if X_ is not None and M_ is not None:
            TRADE_SER[k] = (X_.resample("MS").sum(min_count=1), M_.resample("MS").sum(min_count=1))
        e.pop("_series", None)
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
                "curve": e["math"].get("curve"), "rel": I.get("policy_rate", {}).get("rel"), "rel_long": I.get("long_rate", {}).get("rel"),
                "c": {"policy": I.get("policy_rate", {}).get("chg"), "long": I.get("long_rate", {}).get("chg"),
                      "real": e["mchg"].get("real_rate"), "curve": e["mchg"].get("curve")},
                "policy_y1": None if I.get("policy_rate", {}).get("year_ago") is None else I["policy_rate"]["latest"] - I["policy_rate"]["year_ago"],
                "date": I.get("policy_rate", I.get("long_rate", {})).get("date")})

    # Map: every country with any data, keyed by ISO numeric
    map_rows = {}
    RAW["iso"] = {}
    for iso3 in set(annual) | set(econ) | set((ports or {}).get("economies", {})) | set(power) | set(RAW.get("ember", {})) \
            | set((RAW.get("ports") or {}).get("eco", {})):
        c = cty(iso3)
        if c:
            RAW["iso"][iso3] = list(c)
    for iso3 in set(annual) | set(econ) | set((ports or {}).get("economies", {})) | set(power):
        c = cty(iso3)
        if not c:
            continue
        f, row = annual.get(iso3, {}), {"iso3": iso3, "name": c[1]}
        for k in ("gdp_growth", "inflation_a", "unemployment_a", "gov_debt", "current_account", "gdp_usd", "population", "net_exports"):
            if k in f:
                row[k] = f[k]["value"]
        if iso3 not in econ:
            sc_, contrib_ = annual_score(iso3, ports, act)
            if sc_ is not None:
                row.update(score=sc_, label=label(sc_), basis="annual", contrib=contrib_)
            else:
                row["why"] = unscored_reason(iso3, ports, act)
                old = stale_pillars(iso3)
                if old:
                    row["why_old"] = old
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
        cc = {}
        for disp, mon, ann in (("gdp", "gdp", "gdp_growth"), ("inflation", "inflation", "inflation_a"), ("unemployment", "unemployment", "unemployment_a")):
            x = econ.get(iso3, {}).get("indicators", {}).get(mon)
            if x and not x.get("annual") and row.get(disp) == x["latest"]:
                cc[disp] = x["chg"]
            elif ann in f:
                cc[disp] = f[ann]["chg"]
        for k in ("gov_debt", "current_account", "net_exports", "gdp_usd"):
            if k in f:
                cc[k] = f[k]["chg"]
        if iso3 in power:
            cc["power"] = power[iso3]["chg"]
        if ports and iso3 in ports.get("pc", {}).get("economies", {}):
            cc["trade"] = ports["pc"]["economies"][iso3]
        row["c"] = cc
        map_rows[str(c[0])] = row

    # Development & environment (slow annual indicators for every country)
    try:
        import dev as DV
        dev_out = DV.build({r["iso3"]: r["name"] for r in map_rows.values()})
    except Exception as ex:
        S.log("dev", False, ex)
        dev_out = None

    # Score history (all scored countries + world): rebuilt with today's method for every past day, then the
    # archive of what the site showed (from the first archived day on), then today -> score changes
    allscores = {k: e["score"] for k, e in econ.items()}
    allscores.update({r["iso3"]: r["score"] for r in map_rows.values() if r.get("basis") == "annual"})
    allscores["WLD"] = world
    archived = save_history(allscores)
    idx_p = ARCH / "index.json"
    a0 = min(json.loads(idx_p.read_text())["dates"]) if idx_p.exists() else None
    a0 = pd.Timestamp(a0) if a0 else TODAY
    step("rebuilding score history")
    RAW["annual"] = ANNUAL_HIST
    try:
        rb = HB.Rebuild(RAW, TODAY).run([r["iso3"] for r in map_rows.values()])
    except Exception as ex:                              # never lose the day's run over the history
        import traceback; traceback.print_exc()
        S.log("site.score_history", False, ex)
        rb = None
    hist, days = {}, pd.date_range(R.HISTORY_START, TODAY, freq="D")
    for k in set(allscores) | set((rb or {}).get("scores", {})):
        reb = (rb["world"] if k == "WLD" else rb["scores"].get(k)) if rb else None
        if reb is None:
            reb = np.full(len(days), np.nan)
        arc = archived.get(k, pd.Series(dtype=float, index=pd.DatetimeIndex([])))
        sp = HB.splice(days, reb, arc[arc.index >= a0])
        sp.loc[TODAY] = allscores[k] if allscores.get(k) is not None else np.nan
        hist[k] = sp.dropna()
    if rb is not None:
        S.log("site.score_history", True, f"rebuilt from {R.HISTORY_START} for {len(rb['scores'])} countries")
    for k in econ:
        h_ = hist.get(k, pd.Series(dtype=float)).dropna()
        h_ = h_[h_.index >= TODAY - pd.DateOffset(years=10)]
        h_ = h_.iloc[::-7][::-1]                       # weekly points for the 10-year chart, ending today
        econ[k]["history"] = [[d.strftime("%Y-%m-%d"), float(v)] for d, v in h_.items()]
        econ[k]["score_chg"] = chg(hist.get(k), "pts", "D")
    for r in map_rows.values():
        if r.get("score") is not None:
            r["c"]["score"] = chg(hist.get(r["iso3"]), "pts", "D")
    world_chg = chg(hist.get("WLD"), "pts", "D")

    # All-economies total row for the trade table: sum over months every included economy reports
    trade_totals = None
    if TRADE_SER:
        Xs = pd.concat({k: v[0] for k, v in TRADE_SER.items()}, axis=1)
        Ms = pd.concat({k: v[1] for k, v in TRADE_SER.items()}, axis=1)
        common = Xs.dropna().index.intersection(Ms.dropna().index)
        if len(common) >= 2:
            Xt, Mt = Xs.loc[common].sum(axis=1), Ms.loc[common].sum(axis=1)
            X12, M12 = Xt.rolling(12).sum().dropna(), Mt.rolling(12).sum().dropna()
            trade_totals = {"date": common[-1], "n": Xs.shape[1], "exports": float(Xt.iloc[-1]), "imports": float(Mt.iloc[-1]),
                            "balance": float(Xt.iloc[-1] - Mt.iloc[-1]),
                            "exports_12m": float(X12.iloc[-1]) if len(X12) else None,
                            "imports_12m": float(M12.iloc[-1]) if len(M12) else None,
                            "c": {"exports": chg(Xt, "pct", "M"), "imports": chg(Mt, "pct", "M"), "balance": chg(Xt - Mt, "abs", "M"),
                                  "exports_12m": chg(X12, "pct", "M"), "imports_12m": chg(M12, "pct", "M"),
                                  "balance_12m": chg((X12 - M12).dropna(), "abs", "M")}}

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "weo_release": weo_rel,
        "world": {"score": world, "label": label(world), "headline": headline(world, econ, prices, ports), "breakdown": world_breakdown,
                  "trade_yoy": ports["global"].get("total") if ports else None,
                  "countries": len(map_rows), "tracked": len(econ),
                  "scored": sum(1 for r in map_rows.values() if r.get("score") is not None), "chg": world_chg},
        "drivers": drivers(econ, prices, ports),
        "economies": sorted(econ.values(), key=lambda e: (not e["g20"], -(e["score"] or -1))),
        "map": map_rows,
        "prices": prices, "markets": markets, "trade": ports, "products": R.PRODUCTS, "transport": transport,
        "freight": freight.get("rows", []), "trade_totals": trade_totals, "periods": C.NAMES, "rel": S.REL,
        "power": {k: v for k, v in power.items()},
        "status": S.STATUS,
    }
    data["coverage"] = coverage_report(data)
    firsts = [s_.index[0] for s_ in hist.values() if len(s_)]
    data["asof"] = {"today": TODAY, "earliest": min(firsts) if firsts else TODAY, "archive_start": a0,
                    "lags": R.LAGS, "default_lag": R.DEFAULT_LAG, "weo_md": R.WEO_RELEASE_MD, "wb_md": R.WB_RELEASE_MD,
                    "port_lag": R.LAGS["portwatch"] + R.LAG_DAYS}
    step("writing output")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    hb_text = json.dumps(clean(data), separators=(",", ":"))
    OUT.write_text(hb_text)
    for k, e in econ.items():                       # score history joins the chart series
        if e.get("history"):
            SERIES_OUT.setdefault(k, {})["score"] = [[d, round(v, 1)] for d, v in e["history"] if v is not None]
    series_text = json.dumps(clean(SERIES_OUT), separators=(",", ":"))
    annual_text = json.dumps(clean(annual_export(map_rows)), separators=(",", ":"))
    (OUT.parent / "series.json").write_text(series_text)
    (OUT.parent / "annual.json").write_text(annual_text)
    if dev_out:
        (OUT.parent / "dev.json").write_text(json.dumps(clean(dev_out), separators=(",", ":")))
    day = TODAY.strftime("%Y-%m-%d")
    try:
        # the score line in series.json changes every day and is already in the heartbeat: keep it out of the
        # archived copy so that copy is only stored again when a monthly series changes
        arch_series = json.dumps(clean({k: {c: v for c, v in s_.items() if c != "score"} for k, s_ in SERIES_OUT.items()}), separators=(",", ":"))
        fixed = PK.repair_gdp_units(ARCH, INPUTS)
        if fixed:
            S.log("site.archive_repair", True, f"{fixed} archived GDP values rescaled (US$ vs billions, {', '.join(PK.BAD_GDP_DAYS)})")
        PK.archive_site(day, hb_text, arch_series, annual_text, ARCH)
        n_in = PK.archive_inputs(day, RAW, INPUTS)
        S.log("site.archive", True, f"snapshot {day}; {n_in} new or revised input observations")
    except Exception as ex:
        S.log("site.archive", False, ex)
    try:
        write_packs(rb, hist, days, data)
        S.log("site.packs", True, "past-date data written")
    except Exception as ex:
        S.log("site.packs", False, ex)
    ok = sum(v["ok"] for v in S.STATUS.values())
    print(f"Wrote {OUT} | sources ok {ok}/{len(S.STATUS)} | world score {world} | map countries {len(map_rows)}")
    for k, v in S.STATUS.items():
        if not v["ok"]:
            print(f"  MISSING {k}: {v['note']}")


if __name__ == "__main__":
    main()
