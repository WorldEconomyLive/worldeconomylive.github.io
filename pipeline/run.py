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
    if s is None:
        return None
    s = s.dropna()
    if len(s) < min_n:
        return None
    h = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
    sd = h.std()
    if not sd or np.isnan(sd):
        return None
    return float(np.clip((s.iloc[-1] - h.mean()) / sd, -3, 3))


# ---------------------------------------------------------------- macro (monthly)
_WB_CACHE = {}


def fetch_candidate(cand, iso3):
    kind = cand[0]
    if kind == "oecd_key":
        _, flow, key, tf = cand
        df = S.oecd_frame(flow, key)
        s = S._series(df["OBS_VALUE"], df["TIME_PERIOD"].map(S._period_to_ts), key)
        label, attrs = "OECD", {}
    elif kind == "oecd":
        _, flow, filters, prefer, tf = cand
        s, attrs = S.oecd_pick(flow, filters, prefer)
        label = "OECD"
    elif kind == "dbn":
        _, sid, tf = cand
        s, label, attrs = S.dbnomics(sid), "Eurostat" if sid.startswith("Eurostat") else "DBnomics", {}
    elif kind == "bis":
        _, cc, tf = cand
        s, label, attrs = S.bis_policy_rate(cc), "BIS", {}
    elif kind == "wb":
        _, ind, tf = cand
        if ind not in _WB_CACHE:
            _WB_CACHE[ind] = S.worldbank(ind, list(R.ECONOMIES))
        d = _WB_CACHE[ind]
        d = d[d.iso3 == iso3].sort_values("year")
        s = S._series(d["value"], d["year"].astype(str) + "-07-01", ind)
        label, attrs = "World Bank (annual)", {}
    else:
        raise RuntimeError(f"unknown kind {kind}")
    if tf == "yoy":
        s = yoy(s)
    elif tf == "yoyq":
        s = yoy(s, 4, "QS")
    elif tf == "usd_bn":
        mult = attrs.get("UNIT_MULT")
        try:
            s = s * (10 ** int(float(mult))) / 1e9 if mult not in (None, "", "nan") else s
        except ValueError:
            pass
    return s.dropna(), label, kind == "wb"


def first_fresh(cands, iso3, key):
    errs = []
    for cand in cands:
        try:
            s, label, annual = fetch_candidate(cand, iso3)
            age = (TODAY - s.index[-1]).days / 30.4
            if len(s) >= 6 and age <= (30 if annual else R.MAX_STALE_MONTHS):
                S.log(key, True, label)
                return s, label, annual
            errs.append(f"{cand[0]}: stale")
        except Exception as e:
            errs.append(f"{cand[0]}: {str(e)[:40]}")
    S.log(key, False, " | ".join(errs[-3:]))
    return None, None, False


def macro_block():
    out = {}
    for iso3, (name, iso2, geo, num) in R.ECONOMIES.items():
        e = {"name": name, "iso3": iso3, "num": num, "indicators": {}, "pillars": {}}
        series = {}
        for ind, cands in R.monthly_candidates(iso3).items():
            s, label, annual = first_fresh(cands, iso3, f"{iso3}.{ind}")
            series[ind] = None if annual else s
            if s is not None:
                e["indicators"][ind] = {"latest": float(s.iloc[-1]), "date": s.index[-1], "annual": annual,
                                        "year_ago": value_ago(s, 335), "source": label,
                                        "spark": spark(s, 24, "QS" if ind == "gdp" else "MS") if not annual else []}
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


def macro_math(e):
    I, m, series = e["indicators"], {}, e["_series"]
    g = lambda k: I[k]["latest"] if k in I else None  # noqa: E731
    pi, u, i, lr, gy = g("inflation"), g("unemployment"), g("policy_rate"), g("long_rate"), g("gdp")
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


# ---------------------------------------------------------------- annual blocks
def vitals_block():
    out = {k: {} for k in R.ECONOMIES}
    for key, (ind, label, unit) in R.VITALS.items():
        try:
            df = S.worldbank(ind, list(R.ECONOMIES))
            S.log(f"worldbank.{ind}", True)
            for iso3, g in df.groupby("iso3"):
                g = g.sort_values("year")
                last = g.iloc[-1]
                ten = g[g["year"] <= last["year"] - 10]
                out.setdefault(iso3, {})[key] = {"label": label, "unit": unit, "value": float(last["value"]),
                                                 "year": int(last["year"]),
                                                 "ten_years_ago": float(ten.iloc[-1]["value"]) if len(ten) else None}
        except Exception as e:
            S.log(f"worldbank.{ind}", False, e)
    return out


def fundamentals_block():
    out = {i: {} for i in R.ECONOMIES}
    wb = {}
    weo_ok = None  # remember which WEO release works
    for key, (label, unit, cands) in R.FUNDAMENTALS.items():
        for iso3 in R.ECONOMIES:
            got = None
            for kind, code, scale in cands:
                try:
                    if kind == "weo":
                        rels = [weo_ok] if weo_ok else R.WEO_RELEASES
                        for rel in rels:
                            try:
                                s = S.dbnomics(f"IMF/{rel}/{iso3}.{code}") * scale
                                weo_ok = rel
                                break
                            except Exception:
                                s = None
                        if s is None:
                            continue
                        s = s[s.index.year <= TODAY.year]
                        if len(s):
                            got = (float(s.iloc[-1]), int(s.index[-1].year), "IMF WEO", bool(s.index[-1].year >= TODAY.year))
                    else:
                        if code not in wb:
                            wb[code] = S.worldbank(code, list(R.ECONOMIES))
                        d = wb[code][wb[code].iso3 == iso3].sort_values("year")
                        if len(d):
                            got = (float(d.iloc[-1]["value"]) * scale, int(d.iloc[-1]["year"]), "World Bank", False)
                except Exception:
                    continue
                if got:
                    break
            if got:
                out[iso3][key] = {"label": label, "unit": unit, "value": got[0], "year": got[1],
                                  "source": got[2], "estimate": got[3]}
        S.log(f"fund.{key}", any(key in out[i] for i in out))
    return out


def derive(e, f):
    I, d = e["indicators"], {}
    if "exports_usd" in f and "imports_usd" in f and f["exports_usd"]["year"] == f["imports_usd"]["year"]:
        d["trade_balance_usd"] = {"value": f["exports_usd"]["value"] - f["imports_usd"]["value"], "year": f["exports_usd"]["year"]}
    gr = I.get("gdp", {}).get("latest") if not I.get("gdp", {}).get("annual") else None
    pi = I.get("inflation", {}).get("latest")
    r = I.get("long_rate", {}).get("latest")
    if gr is not None and pi is not None and r is not None:
        g = gr + pi                                   # nominal growth (approx.)
        d["nominal_growth"], d["r_minus_g"] = g, r - g
        debt = f.get("gov_debt", {}).get("value")
        if debt is not None:
            d["pb_stabilizing"] = (r - g) / (100 + g) * debt
            pb = f.get("primary_balance", {}).get("value")
            if pb is not None:
                d["fiscal_gap"] = pb - d["pb_stabilizing"]
    if "savings" in f and "investment" in f:
        d["s_minus_i"] = f["savings"]["value"] - f["investment"]["value"]
    if "current_account" in f and "gov_balance" in f:
        d["twin"] = f["current_account"]["value"] + f["gov_balance"]["value"]
    return d


# ---------------------------------------------------------------- prices & markets
def prices_block():
    try:
        ps = S.pink_sheet()
        S.log("worldbank.pinksheet", True, f"{ps.index[-1]:%Y-%m}")
    except Exception as e:
        S.log("worldbank.pinksheet", False, e)
        return []
    rows = []
    for prefix, name, ship in R.COMMODITIES:
        col = next((c for c in ps.columns if str(c).lower().startswith(prefix.lower())), None)
        if not col:
            continue
        s = ps[col].dropna()
        if len(s) < 13:
            continue
        rows.append({"name": name, "ship": ship, "level": float(s.iloc[-1]), "date": s.index[-1],
                     "unit": "", "m1": pct(float(s.iloc[-1]), float(s.iloc[-2])),
                     "yoy": pct(float(s.iloc[-1]), value_ago(s, 360)), "spark": spark(s, 24)})
    return rows


def markets_block():
    out = {"fx": [], "rates": [], "us_fiscal": []}
    start = (TODAY - pd.Timedelta(days=430)).strftime("%Y-%m-%d")
    try:
        fx = S.ecb_fx(R.FX, start).ffill()
        S.log("ecb.fx", True)
        usd = fx["USD"]
        series = {"EUR": usd}                               # USD per EUR
        if "GBP" in fx:
            series["GBP"] = usd / fx["GBP"]                 # USD per GBP
        for c in R.FX:
            if c not in ("USD", "GBP") and c in fx:
                series[c] = fx[c] / usd                     # units per USD
        for c, s in series.items():
            s = s.dropna()
            last = float(s.iloc[-1])
            out["fx"].append({"name": R.FX_NAMES.get(c, c), "code": c, "latest": last, "date": s.index[-1],
                              "m1": pct(last, value_ago(s, 30)), "y1": pct(last, value_ago(s, 365)),
                              "spark": spark(s, 13), "unit": "%"})
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
    frames = []
    for pid in picks["portid"]:
        try:
            frames.append(S.portwatch_port_daily(pid, start))
        except Exception:
            pass
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

    cps = []
    for cid, (cname, lon, lat) in R.CHOKEPOINTS.items():
        try:
            d = S.portwatch_chokepoint_daily(cid, start)
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


def score_economies(econ, ports):
    for iso3, e in econ.items():
        if ports and iso3 in ports["economies"]:
            e["trade_yoy"] = ports["economies"][iso3]
            e["pillars"]["trade"] = float(np.clip(e["trade_yoy"] / 10, -3, 3))
        zs = [v for v in e["pillars"].values() if v is not None]
        e["score"] = float(np.clip(50 + 15 * np.mean(zs), 0, 100)) if len(zs) >= 2 else None
        e["label"] = label(e["score"])
        e["coverage"] = f"{len(zs)}/4"


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
    econ = macro_block()
    vitals = vitals_block()
    fund = fundamentals_block()
    prices = prices_block()
    markets = markets_block()
    ports = ports_block()
    score_economies(econ, ports)
    for k, e in econ.items():
        e["vitals"], e["fundamentals"] = vitals.get(k, {}), fund.get(k, {})
        e["math"] = macro_math(e)
        e["derived"] = derive(e, e["fundamentals"])
        e.pop("_series", None)
    hist = save_history(econ)
    for k in econ:
        econ[k]["history"] = hist.get(k, [])
    scores = [e["score"] for e in econ.values() if e["score"] is not None]
    world = float(np.mean(scores)) if scores else None
    map_rows = {}
    for iso3, num in R.ISO_NUM.items():
        row = {"iso3": iso3}
        if iso3 in econ:
            e = econ[iso3]
            row.update(name=e["name"], score=e["score"], label=e["label"],
                       inflation=e["indicators"].get("inflation", {}).get("latest"),
                       unemployment=e["indicators"].get("unemployment", {}).get("latest"))
        if ports and iso3 in ports["economies"]:
            row["trade"] = ports["economies"][iso3]
        if len(row) > 1:
            map_rows[str(num)] = row
    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "world": {"score": world, "label": label(world), "headline": headline(prices, ports),
                  "trade_yoy": ports["global"].get("total") if ports else None},
        "drivers": drivers(econ, prices, ports),
        "economies": list(econ.values()),
        "map": map_rows,
        "prices": prices, "markets": markets, "trade": ports, "products": R.PRODUCTS,
        "status": S.STATUS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(clean(data), separators=(",", ":")))
    ok = sum(v["ok"] for v in S.STATUS.values())
    print(f"Wrote {OUT} | sources ok {ok}/{len(S.STATUS)} | world score {world}")
    for k, v in S.STATUS.items():
        if not v["ok"]:
            print(f"  MISSING {k}: {v['note']}")


if __name__ == "__main__":
    main()
