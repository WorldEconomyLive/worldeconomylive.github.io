"""World Economy Live pipeline: pull every source, score every economy, write site/data/heartbeat.json.

Never crashes on a single bad source: failures are logged to the status block and
the site shows what's available.  Run:  python pipeline/run.py
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


def clean(x):
    """Make values JSON-safe."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if (x is None or math.isnan(x) or math.isinf(x)) else round(float(x), 2)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.strftime("%Y-%m-%d")
    return x


def yoy(s: pd.Series) -> pd.Series:
    s = s.resample("MS").mean().dropna()
    return (s / s.shift(12) - 1) * 100


def yoyq(s: pd.Series) -> pd.Series:
    s = s.resample("QS").mean().dropna()
    return (s / s.shift(4) - 1) * 100


def fetch_kind(kind, code):
    s = S.fred(code) if kind.startswith("fred") else S.dbnomics(code)
    if kind.endswith("_yoyq"):
        s = yoyq(s)
    elif kind.endswith("_yoy"):
        s = yoy(s)
    return s.dropna()


def first_fresh(cands, key):
    for kind, code in cands:
        try:
            s = fetch_kind(kind, code)
            age = (TODAY - s.index[-1]).days / 30.4
            if age <= R.MAX_STALE_MONTHS and len(s) >= 6:
                S.log(key, True, f"{kind}:{code}")
                return s, f"{code}"
        except Exception as e:  # try next candidate
            last = str(e)[:80]
    S.log(key, False, "no fresh source")
    return None, None


def _year_ago(s):
    prior = s[s.index <= s.index[-1] - pd.DateOffset(months=11)]
    return float(prior.iloc[-1]) if len(prior) else None


def markets_block():
    out = {}
    for group, items in R.MARKETS.items():
        rows = []
        for name, sid in items.items():
            try:
                s = S.fred(sid)
                last, d = float(s.iloc[-1]), s.index[-1]
                def chg(days):
                    p = s[s.index <= d - pd.Timedelta(days=days)]
                    if not len(p):
                        return None
                    p = float(p.iloc[-1])
                    if group == "US rates":  # rates: change in percentage points
                        return last - p
                    return (last / p - 1) * 100 if p else None
                licensed = group == "Equity indices"  # show % changes only, not index levels
                rows.append({"name": name, "latest": None if licensed else last, "date": d, "m1": chg(30), "y1": chg(365),
                             "unit": "pp" if group == "US rates" else "%", "spark": spark(s.resample("MS").mean(), 24)})
                S.log(f"mkt.{sid}", True)
            except Exception as e:
                S.log(f"mkt.{sid}", False, str(e)[:80])
        out[group] = rows
    return out


def z_last(s, years=10):
    if s is None or len(s.dropna()) < 24:
        return None
    s = s.dropna()
    h = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
    sd = h.std()
    if not sd or np.isnan(sd):
        return None
    return float(np.clip((s.iloc[-1] - h.mean()) / sd, -3, 3))


def spark(s, n=24):
    if s is None:
        return []
    s = s.dropna().iloc[-n:]
    return [[d.strftime("%Y-%m"), round(float(v), 2)] for d, v in s.items()]


# ======================================================================
def macro_block():
    out = {}
    for iso3, (name, iso2, geo) in R.ECONOMIES.items():
        cands = R.monthly_candidates(iso3)
        e = {"name": name, "iso3": iso3, "indicators": {}, "pillars": {}}
        series = {}
        for ind, cl in cands.items():
            s, code = first_fresh(cl, f"{iso3}.{ind}")
            series[ind] = s
            if s is not None:
                e["indicators"][ind] = {"latest": float(s.iloc[-1]), "date": s.index[-1],
                                        "year_ago": _year_ago(s),
                                        "source": code, "spark": spark(s)}
        # Pillar z-scores, signed so that + = healthier
        if series["industry"] is not None:
            e["pillars"]["activity"] = z_last(series["industry"])
        if series["unemployment"] is not None:
            u = series["unemployment"].resample("MS").mean()
            e["pillars"]["labor"] = None if z_last(u - u.shift(12)) is None else -z_last(u - u.shift(12))
        if series["inflation"] is not None:
            dev = -(series["inflation"] - 2.0).abs()
            e["pillars"]["prices"] = z_last(dev)
        out[iso3] = e
    return out


def vitals_block():
    iso3s = list(R.ECONOMIES)
    out = {k: {} for k in iso3s}
    for key, (ind, label, unit) in R.VITALS.items():
        try:
            df = S.worldbank(ind, iso3s)
            S.log(f"worldbank.{ind}", True)
            for iso3, g in df.groupby("iso3"):
                g = g.sort_values("year")
                last = g.iloc[-1]
                ten = g[g["year"] <= last["year"] - 10]
                out.setdefault(iso3, {})[key] = {
                    "label": label, "unit": unit, "value": float(last["value"]),
                    "year": int(last["year"]),
                    "ten_years_ago": float(ten.iloc[-1]["value"]) if len(ten) else None}
        except Exception as e:
            S.log(f"worldbank.{ind}", False, str(e)[:80])
    return out


def prices_block():
    rows, series = [], {}
    for name, (sid, ship) in R.PRICES.items():
        try:
            s = S.fred(sid).resample("MS").mean().dropna()
            y = (s / s.shift(12) - 1) * 100
            series[name] = y
            rows.append({"name": name, "ship": ship, "yoy": float(y.iloc[-1]),
                         "date": y.index[-1], "level": float(s.iloc[-1]), "spark": spark(y, 18)})
            S.log(f"price.{sid}", True)
        except Exception as e:
            S.log(f"price.{sid}", False, str(e)[:80])
    return rows


def us_fast_block():
    rows = []
    for name, sid in R.US_FAST.items():
        try:
            s = S.fred(sid)
            if "weekly" in name:
                cur, prev = s.iloc[-4:].mean(), s[s.index <= s.index[-1] - pd.Timedelta(days=364)].iloc[-4:].mean()
                y = (cur / prev - 1) * 100
            else:
                y = float(yoy(s).iloc[-1])
            rows.append({"name": name, "yoy": float(y), "date": s.index[-1], "latest": float(s.iloc[-1])})
            S.log(f"us.{sid}", True)
        except Exception as e:
            S.log(f"us.{sid}", False, str(e)[:80])
    return rows


def ports_block():
    """Region x product, per-economy trade, chokepoints. Returns dict or None."""
    try:
        ports = S.portwatch_ports()
        S.log("portwatch.ports", True, f"{len(ports)} ports")
    except Exception as e:
        S.log("portwatch.ports", False, str(e)[:80])
        return None
    iso_region = {i: r for r, l in R.REGIONS.items() for i in l}
    ports["region"] = ports["ISO3"].map(iso_region)
    ports = ports.sort_values("vessel_count_total", ascending=False)
    picks = pd.concat([
        ports.dropna(subset=["region"]).groupby("region").head(R.PORTS_PER_REGION),
        ports[ports["ISO3"].isin(R.ECONOMIES)].groupby("ISO3").head(R.PORTS_PER_ECONOMY),
    ]).drop_duplicates("portid")

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
    pv = pv.merge(picks[["portid", "region"]], on="portid", how="left")
    for p in R.PRODUCTS:
        pv[p] = pv.get(f"import_{p}", 0).fillna(0) + pv.get(f"export_{p}", 0).fillna(0)
    pv["total"] = pv[list(R.PRODUCTS)].sum(axis=1)
    cols = list(R.PRODUCTS) + ["total", "portcalls"]

    end = pv["date"].max() - pd.Timedelta(days=R.LAG_DAYS)
    a = end - pd.Timedelta(days=R.WINDOW_DAYS - 1)
    pa, pb = a - pd.Timedelta(days=364), end - pd.Timedelta(days=364)

    def win(df, lo, hi, key):
        return df[(df["date"] >= lo) & (df["date"] <= hi)].groupby(key)[cols].sum()

    def pct(c, p):
        if np.isscalar(c):
            return float((c / p - 1) * 100) if p else None
        return ((c / p - 1) * 100).replace([np.inf, -np.inf], np.nan)

    reg = pct(win(pv, a, end, "region"), win(pv, pa, pb, "region"))
    mix = win(pv, a, end, "region")[list(R.PRODUCTS)]
    mix = mix.div(mix.sum(axis=1), axis=0) * 100
    glob = pct(pv[(pv.date >= a) & (pv.date <= end)][cols].sum(), pv[(pv.date >= pa) & (pv.date <= pb)][cols].sum())
    eco = pct(win(pv, a, end, "ISO3"), win(pv, pa, pb, "ISO3"))
    portyoy = pct(win(pv, a, end, "portid"), win(pv, pa, pb, "portid"))
    portyoy = portyoy.join(picks.set_index("portid")[["portname", "ISO3", "region"]])

    wk = pv[pv.date <= end].groupby(["region", pd.Grouper(key="date", freq="W")])["total"].sum().unstack("region")
    wky = (wk.pct_change(52, fill_method=None) * 100)
    wky = wky[wky.index <= end].tail(8)

    # chokepoints
    cps = []
    for cid, cname in R.CHOKEPOINTS.items():
        try:
            d = S.portwatch_chokepoint_daily(cid, start)
            cur = d[(d.date >= a) & (d.date <= end)]
            prv = d[(d.date >= pa) & (d.date <= pb)]
            cps.append({"name": cname,
                        "transits_yoy": pct(cur["n_total"].sum(), prv["n_total"].sum()),
                        "tanker_yoy": pct(cur["n_tanker"].sum(), prv["n_tanker"].sum()),
                        "capacity_yoy": pct(cur["capacity"].sum(), prv["capacity"].sum()),
                        "daily_transits": cur["n_total"].mean()})
        except Exception:
            pass
    S.log("portwatch.chokepoints", bool(cps), f"{len(cps)}/24")

    return {
        "window": [a, end],
        "regions": [{"region": r, **{k: row[k] for k in cols}} for r, row in reg.iterrows()],
        "mix": [{"region": r, **row.to_dict()} for r, row in mix.iterrows()],
        "global": glob.to_dict(),
        "economies": {i: row["total"] for i, row in eco.iterrows()},
        "weekly": {"weeks": [d.strftime("%m/%d") for d in wky.index],
                   "series": {c: wky[c].tolist() for c in wky.columns}},
        "ports": [{"port": row["portname"], "iso3": row["ISO3"], "region": row["region"],
                   **{k: row[k] for k in cols}} for _, row in portyoy.iterrows()],
        "chokepoints": cps,
    }


# ======================================================================
def label(score):
    if score is None:
        return "Pending"
    return "Strong" if score >= 60 else "Steady" if score >= 45 else "Soft" if score >= 35 else "Stressed"


def finalize(econ, ports):
    for iso3, e in econ.items():
        if ports and iso3 in ports["economies"] and ports["economies"][iso3] is not None:
            e["pillars"]["trade"] = float(np.clip(ports["economies"][iso3] / 10, -3, 3))
            e["trade_yoy"] = ports["economies"][iso3]
        zs = [v for v in e["pillars"].values() if v is not None]
        e["score"] = None if not zs else float(np.clip(50 + 15 * np.mean(zs), 0, 100))
        e["label"] = label(e["score"])
        e["coverage"] = f"{len(zs)}/4 pillars"
    return econ


def drivers(econ, prices, ports, us):
    out = []
    if ports:
        for r in sorted(ports["regions"], key=lambda x: -abs(x["total"] or 0))[:3]:
            v = r["total"]
            out.append(f"{r['region']} port cargo is {'up' if v > 0 else 'down'} {abs(v):.0f}% from a year ago.")
        for c in sorted(ports["chokepoints"], key=lambda x: -abs(x["transits_yoy"] or 0))[:2]:
            v = c["transits_yoy"]
            if v is not None and abs(v) >= 15:
                out.append(f"Ships through the {c['name']} are {'up' if v > 0 else 'down'} {abs(v):.0f}% year over year.")
    for p in sorted(prices, key=lambda x: -abs(x["yoy"] or 0))[:3]:
        v = p["yoy"]
        out.append(f"{p['name']} is {'up' if v > 0 else 'down'} {abs(v):.0f}% from a year ago.")
    scored = [e for e in econ.values() if e["score"] is not None]
    if scored:
        best = max(scored, key=lambda e: e["score"])
        worst = min(scored, key=lambda e: e["score"])
        out.append(f"Strongest: {best['name']} ({best['score']:.0f}). Weakest: {worst['name']} ({worst['score']:.0f}).")
    return out


def headline(prices, ports):
    vol = ports["global"].get("total") if ports else None
    energy = next((p["yoy"] for p in prices if p["name"] == "Brent crude"), None)
    if vol is not None and energy is not None:
        if vol < -2 and energy > 15:
            return "Supply shock: goods are moving less while prices rise."
        if vol > 2 and energy < 0:
            return "Expansion with easing costs: more trade, cheaper energy."
        if vol < -2:
            return "Global trade is slowing."
        if vol > 2:
            return "Global trade is growing."
    return "Global economy: mixed signals."


def save_history(econ):
    rows = [{"date": TODAY.strftime("%Y-%m-%d"), "iso3": k, "score": v["score"]} for k, v in econ.items()]
    new = pd.DataFrame(rows)
    if HIST.exists():
        old = pd.read_csv(HIST)
        old = old[old["date"] != rows[0]["date"]]
        new = pd.concat([old, new])
    HIST.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(HIST, index=False)
    return {iso: g.sort_values("date")[["date", "score"]].values.tolist()[-90:] for iso, g in new.groupby("iso3")}


def main():
    econ = macro_block()
    vitals = vitals_block()
    prices = prices_block()
    us = us_fast_block()
    markets = markets_block()
    ports = ports_block()
    econ = finalize(econ, ports)
    for k in econ:
        econ[k]["vitals"] = vitals.get(k, {})
    hist = save_history(econ)
    for k in econ:
        econ[k]["history"] = hist.get(k, [])
    scores = [e["score"] for e in econ.values() if e["score"] is not None]
    world = float(np.mean(scores)) if scores else None
    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "seed": False,
        "world": {"score": world, "label": label(world), "headline": headline(prices, ports)},
        "drivers": drivers(econ, prices, ports, us),
        "economies": list(econ.values()),
        "prices": prices, "us_fast": us, "trade": ports, "markets": markets,
        "products": R.PRODUCTS,
        "status": S.STATUS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(clean(data), indent=1))
    ok = sum(v["ok"] for v in S.STATUS.values())
    print(f"Wrote {OUT} | sources ok {ok}/{len(S.STATUS)} | world score {world}")
    for k, v in S.STATUS.items():
        if not v["ok"]:
            print(f"  MISSING {k}: {v['note']}")


if __name__ == "__main__":
    main()
