"""Score history for every day, rebuilt with today's method.

For each past day d, every input series is cut back to the observations that count as released on or before d
(each source's standard publication delay, registry.LAGS; annual sources by WEO/WDI rules), and the economy
scores, annual-basis scores and the world score are computed exactly as the daily run computes them today.
The result covers days before the daily archive began; from then on the archived scores (as shown on the
day) are used.
"""
import math

import numpy as np
import pandas as pd

import registry as R
import changes as C

PANDEMIC = (pd.Timestamp("2020-03-01"), pd.Timestamp("2021-12-31"))


# ---------------------------------------------------------------- release timing
def lag_of(key):
    if key in R.LAGS:
        return R.LAGS[key]
    for k, v in R.LAGS.items():
        if key and key.startswith(k):
            return v
    return R.DEFAULT_LAG


def period_end(idx, f):
    idx = pd.DatetimeIndex(idx)
    if f == "M":
        return idx + pd.offsets.MonthEnd(0)
    if f == "Q":
        return idx + pd.offsets.QuarterEnd(0)
    if f == "W":
        return idx + pd.Timedelta(days=6)
    if f == "A":
        return pd.DatetimeIndex([pd.Timestamp(f"{d.year}-12-31") for d in idx])
    return idx


def release_dates(s, key):
    """Date each observation of s counts as released."""
    if s is None or not len(s):
        return pd.DatetimeIndex([])
    idx = pd.DatetimeIndex(s.index)
    if key == "weo":
        m, d = R.WEO_RELEASE_MD
        return pd.DatetimeIndex([pd.Timestamp(year=x.year, month=m, day=d) for x in idx])
    if key and key.startswith("wb:"):
        m, d = R.WB_RELEASE_MD
        return pd.DatetimeIndex([pd.Timestamp(year=x.year + 1, month=m, day=d) for x in idx])
    f = C.freq_of(s)
    return period_end(idx, f) + pd.Timedelta(days=lag_of(key))


def avail_count(s, key, days):
    """For each day, how many observations of s (sorted) count as released."""
    rel = release_dates(s, key).values.astype("datetime64[D]")
    rel = np.maximum.accumulate(rel) if len(rel) else rel
    return np.searchsorted(rel, days.values.astype("datetime64[D]"), side="right")


# ---------------------------------------------------------------- z-scores of every prefix
def _robust(h):
    med = np.median(h)
    mad = np.median(np.abs(h - med)) * 1.4826
    sd = mad if mad and not np.isnan(mad) else (np.std(h, ddof=1) if len(h) > 1 else np.nan)
    if not sd or np.isnan(sd):
        return None
    return med, sd


def z_prefix(s, years=10, min_n=24):
    """out[k] = z_last(s.iloc[:k]) for k = 0..len(s) (nan where z_last returns None)."""
    s = s.dropna()
    n = len(s)
    out = np.full(n + 1, np.nan)
    if n < min_n:
        return out
    idx, vals = s.index, s.values.astype(float)
    lo = (idx - pd.DateOffset(years=years)).values
    pand = np.asarray((idx >= PANDEMIC[0]) & (idx <= PANDEMIC[1]))
    iv = idx.values
    for k in range(min_n, n + 1):
        j0 = np.searchsorted(iv, lo[k - 1], side="left")
        h = vals[j0:k][~pand[j0:k]]
        if len(h) < max(8, min_n // 2):
            continue
        r = _robust(h)
        if r is None:
            continue
        out[k] = float(np.clip((vals[k - 1] - r[0]) / r[1], -3, 3))
    return out


def z_annual_prefix(s, years=15, min_n=8):
    """out[k] = z_annual(s.iloc[:k])."""
    s = s.dropna()
    n = len(s)
    out = np.full(n + 1, np.nan)
    yrs, vals = s.index.year.values, s.values.astype(float)
    for k in range(min_n, n + 1):
        y = yrs[k - 1]
        m = (yrs[:k] >= y - years) & ~np.isin(yrs[:k], [2020, 2021])
        h = vals[:k][m]
        if len(h) < min_n - 2:
            continue
        med = np.median(h)
        sd = np.median(np.abs(h - med)) * 1.4826 or (np.std(h, ddof=1) if len(h) > 1 else np.nan)
        if not sd or np.isnan(sd):
            continue
        out[k] = float(np.clip((vals[k - 1] - med) / sd, -3, 3))
    return out


def map_prefix(base, derived):
    """For each prefix length k of `base`, the number of observations of `derived` dated on or before base[k-1]."""
    bi = base.index.values
    di = derived.dropna().index.values
    out = np.zeros(len(bi) + 1, dtype=int)
    if len(bi):
        out[1:] = np.searchsorted(di, bi, side="right")
    return out


# ---------------------------------------------------------------- the rebuild
class Rebuild:
    def __init__(self, raw, today, live_port_end=None):
        self.raw, self.today = raw, pd.Timestamp(today).normalize()
        self.days = pd.date_range(R.HISTORY_START, self.today, freq="D")
        self.N = len(self.days)
        self.dv = self.days.values.astype("datetime64[D]")
        self.live_port_end = live_port_end

    # age in months of the latest available observation, per day
    def _age(self, s, k):
        iv = s.index.values.astype("datetime64[D]")
        last = np.where(k > 0, iv[np.maximum(k - 1, 0)] if len(iv) else self.dv, self.dv)
        return (self.dv - last).astype(float) / 30.4

    # ---- monthly economy inputs: which source counts on each day (same rules as the daily run)
    def selection(self, cands):
        """cands: list of {"s","annual","rk","b"} in priority order. Returns (choice index per day, k per candidate)."""
        N = self.N
        info = []
        for c in cands:
            s = c["s"].dropna().sort_index()
            s = s[~s.index.duplicated(keep="last")]
            k = avail_count(s, c["rk"], self.days)
            age = self._age(s, k)
            ok_b = np.ones(N, bool)
            if c.get("b") is not None and len(s):
                last_v = s.values[np.maximum(k - 1, 0)]
                ok_b = np.abs(last_v) <= c["b"]
            info.append({"s": s, "k": k, "age": age, "annual": c["annual"], "okb": ok_b, "o": c.get("o", 0)})
        best = np.full(N, -1)
        best_age = np.full(N, np.inf)
        if info and info[0]["o"] == 0:
            p = info[0]
            m = (p["k"] >= 1) & (p["age"] <= R.MAX_STALE_MONTHS) & p["okb"]
            best[m], best_age[m] = 0, p["age"][m]
            rest = range(1, len(info))
        else:
            rest = range(len(info))
        need = (best < 0) | (best_age > R.FRESH_MONTHS)
        done = ~need
        best_annual = np.zeros(N, bool)
        for j in rest:
            c = info[j]
            lim = 30 if c["annual"] else R.MAX_STALE_MONTHS
            usable = (~done) & (c["k"] >= 3) & (c["age"] <= lim)
            take = usable & ((best < 0) | ((not c["annual"]) & (c["age"] < best_age)))
            best[take], best_age[take], best_annual[take] = j, c["age"][take], c["annual"]
            if not c["annual"]:
                done = done | (usable & (c["age"] <= R.FRESH_MONTHS))
        return best, info

    def econ_pillars(self, iso3, act_z, trade_p):
        e = self.raw["macro"].get(iso3, {})
        N = self.N
        out = {k: np.full(N, np.nan) for k in ("activity", "labor", "prices", "trade")}
        sel = {}
        for ind in ("industry", "gdp", "unemployment", "inflation"):
            cands = e.get("ind", {}).get(ind, [])
            if cands:
                sel[ind] = self.selection(cands)

        def series_z(ind, fn):
            """Per day: z from the chosen non-annual candidate (nan if annual or none); also a mask 'monthly chosen'."""
            res, has = np.full(N, np.nan), np.zeros(N, bool)
            if ind not in sel:
                return res, has
            best, info = sel[ind]
            for j, c in enumerate(info):
                m = (best == j)
                if not m.any() or c["annual"]:
                    continue
                arr = fn(c["s"])
                res[m] = arr[c["k"][m]]
                has |= m
            return res, has
        zi, hi = series_z("industry", lambda s: z_prefix(s))
        zg, hg = series_z("gdp", lambda s: z_prefix(s, min_n=12))
        out["activity"] = np.where(hi, zi, np.where(hg, zg, np.nan))

        def labor_fn(s):
            u = s.resample("MS").mean()
            d = (u - u.shift(12)).dropna()
            zd = z_prefix(d)
            return -zd[map_prefix(s, d)]
        out["labor"], _ = series_z("unemployment", labor_fn)

        def prices_fn(s):
            return z_prefix(-(s - 2.0).abs())
        out["prices"], _ = series_z("inflation", prices_fn)
        out["trade"] = trade_p
        a = out["activity"]
        out["activity"] = np.where(np.isnan(act_z), a, np.where(np.isnan(a), act_z, (a + act_z) / 2))
        return out

    def annual_pillars(self, iso3, act_z, trade_p):
        H = self.raw["annual"].get(iso3, {})
        N = self.N
        out = {k: np.full(N, np.nan) for k in ("activity", "labor", "prices", "trade")}
        yr = self.days.year.values

        def rk(key):
            """Release rule: WEO, or the World Bank's when the series is the World Bank stand-in."""
            fb = R.WB_FALLBACK.get(key)
            return ("wb:" + R.WB[fb][0]) if fb and H.get(key) is not None and H.get(key) is H.get(fb) else "weo"

        def ann(s, fn, key, extra=None):
            s = s.dropna().sort_index()
            if not len(s):
                return np.full(N, np.nan)
            k = avail_count(s, rk(key), self.days)
            years = s.index.year.values
            k = np.minimum(k, np.searchsorted(years, yr, side="left"))     # completed years only, never the forecast year
            lasty = np.where(k > 0, years[np.maximum(k - 1, 0)], -9999)
            arr = fn(s)
            v = arr[k]
            ok = (k > 0) & (lasty >= yr - R.ANNUAL_MAX_AGE)
            if extra is not None:
                ok &= extra(k)
            return np.where(ok, v, np.nan)
        g = H.get("gdp_growth")
        if g is not None:
            out["activity"] = ann(g, z_annual_prefix, "gdp_growth")
        a = out["activity"]
        out["activity"] = np.where(np.isnan(act_z), a, np.where(np.isnan(a), act_z, (a + act_z) / 2))
        u = H.get("unemployment_a")
        if u is not None and len(u.dropna()):
            uu = u.dropna().sort_index()

            def lab(s):
                d = s.diff().dropna()
                zd = z_annual_prefix(d)
                return -zd[map_prefix(s, d)]
            out["labor"] = ann(uu, lab, "unemployment_a", extra=lambda k: k > 9)
        pi = H.get("inflation_a")
        if pi is not None:
            out["prices"] = ann(pi, lambda s: z_annual_prefix(-(s - 2.0).abs()), "inflation_a")
        out["trade"] = trade_p
        return out

    # ---- live activity signals: electricity demand and freight (z of volume growth vs own history)
    def monthly_signal_z(self, s, key, min_len, max_age, quarterly=False):
        s = s.dropna().sort_index()
        s = s[~s.index.duplicated()]
        if not len(s):
            return np.full(self.N, np.nan)
        if quarterly:
            y = ((s / s.shift(4) - 1) * 100).dropna()
            zy = z_prefix(y, min_n=12)
        else:
            s3 = s.rolling(3).sum()
            y = ((s3 / s3.shift(12) - 1) * 100).dropna()
            zy = z_prefix(y, min_n=24)
        k = avail_count(s, key, self.days)
        age = self._age(s, k)
        zz = zy[map_prefix(s, y)][k]
        ok = (k >= min_len) & (age <= max_age)
        return np.where(ok, zz, np.nan)

    def act_signals(self):
        out = {}
        for iso3, s in (self.raw.get("ember") or {}).items():
            out.setdefault(iso3, {})["power"] = self.monthly_signal_z(s, "ember", 27, 8)
        fr = self.raw.get("freight") or {}
        for iso3, s in (fr.get("air") or {}).items():
            out.setdefault(iso3, {}).setdefault("freight", []).append(self.monthly_signal_z(s, "eurostat:avia_gooc", 27, 8))
        for iso3, s in (fr.get("rail") or {}).items():
            out.setdefault(iso3, {}).setdefault("freight", []).append(self.monthly_signal_z(s, "eurostat:rail_go_quartal", 12, 12, True))
        if fr.get("can") is not None:
            out.setdefault("CAN", {}).setdefault("freight", []).append(self.monthly_signal_z(fr["can"], "statcan", 27, 8))
        res = {}
        for iso3, d in out.items():
            parts = []
            if "power" in d:
                parts.append(d["power"])
            if d.get("freight"):
                fz = np.vstack(d["freight"])
                with np.errstate(all="ignore"):
                    parts.append(np.where(np.isnan(fz).all(0), np.nan, np.nanmean(np.where(np.isnan(fz), np.nan, fz), 0)))
            st = np.vstack(parts)
            with np.errstate(all="ignore"):
                res[iso3] = np.where(np.isnan(st).all(0), np.nan, np.nanmean(st, 0))
        return res

    # ---- ports: 28-day cargo vs the same 28 days a year earlier, window ending 'end(d)'
    def port_end(self):
        P = self.raw.get("ports")
        if not P:
            return None
        lag = lag_of("portwatch") + R.LAG_DAYS
        end = self.days - pd.Timedelta(days=lag)
        cap = P["end"]
        end = end.where(end <= cap, cap)
        return end

    def window_ratio(self, x):
        """x: daily series (NaN where no data). Returns per-day ratio % (nan if unavailable)."""
        P = self.raw["ports"]
        ends = self.port_end()
        x = x.reindex(pd.date_range(P["first"], P["end"], freq="D"))
        r28 = x.rolling(R.WINDOW_DAYS, min_periods=1).sum()
        cur = r28.reindex(ends).values
        prv = r28.reindex(ends - pd.Timedelta(days=364)).values
        with np.errstate(all="ignore"):
            v = (cur / prv - 1) * 100
        v[~np.isfinite(v)] = np.nan
        return v

    def trade_pillars(self):
        P = self.raw.get("ports")
        if not P:
            return {}, np.full(self.N, np.nan)
        out = {i: np.clip(self.window_ratio(s) / 10, -3, 3) for i, s in P["eco"].items()}
        glob = self.window_ratio(P["glob"]["total"]) if "total" in P["glob"] else np.full(self.N, np.nan)
        return out, glob

    def stress(self, glob):
        comps = {}
        for key, s in (self.raw.get("pink_stress") or {}).items():
            s = s.dropna().sort_index()
            y = ((s / s.shift(12) - 1) * 100).dropna()
            zy = z_prefix(y, years=15)
            k = avail_count(s, "pink", self.days)
            comps[key] = -zy[map_prefix(s, y)][k]
        comps["World port cargo"] = np.clip(glob / 10, -3, 3)
        st = np.vstack(list(comps.values()))
        with np.errstate(all="ignore"):
            score = np.where(np.isnan(st).all(0), np.nan, 50 + 15 * np.nanmean(st, 0))
        return score, comps

    def gdp_weight(self, iso3):
        s = self.raw["annual"].get(iso3, {}).get("gdp_usd")
        if s is None or not len(s.dropna()):
            return np.zeros(self.N)
        s = s.dropna().sort_index()
        k = avail_count(s, "weo", self.days)
        v = np.where(k > 0, s.values[np.maximum(k - 1, 0)], 0.0)
        return np.nan_to_num(v)

    def run(self, map_isos):
        act = self.act_signals()
        tp, glob = self.trade_pillars()
        nan = np.full(self.N, np.nan)
        pillars, scores = {}, {}
        for iso3 in self.raw["macro"]:
            pillars[iso3] = self.econ_pillars(iso3, act.get(iso3, nan), tp.get(iso3, nan))
        for iso3 in map_isos:
            if iso3 not in self.raw["macro"]:
                pillars[iso3] = self.annual_pillars(iso3, act.get(iso3, nan), tp.get(iso3, nan))
        for iso3, p in pillars.items():
            st = np.vstack([p[k] for k in ("activity", "labor", "prices", "trade")])
            n = (~np.isnan(st)).sum(0)
            with np.errstate(all="ignore"):
                sc = np.clip(50 + 15 * np.nanmean(st, 0), 0, 100)
            scores[iso3] = np.where(n >= 2, sc, np.nan)
        ss, comps = self.stress(glob)
        num, den, plain, cnt = np.zeros(self.N), np.zeros(self.N), np.zeros(self.N), np.zeros(self.N)
        for iso3 in self.raw["macro"]:
            sc = scores[iso3]
            w = self.gdp_weight(iso3)
            m = ~np.isnan(sc)
            num += np.where(m, sc * w, 0)
            den += np.where(m, w, 0)
            plain += np.where(m, sc, 0)
            cnt += m
        with np.errstate(all="ignore"):
            avg = np.where(den > 0, num / den, np.where(cnt > 0, plain / cnt, np.nan))
        world = np.clip(0.8 * avg + 0.2 * np.where(np.isnan(ss), avg, ss), 0, 100)
        return {"pillars": pillars, "scores": scores, "world": world, "avg": avg, "stress": ss, "comps": comps,
                "glob": glob}


# ---------------------------------------------------------------- splice with the archive, encode
def splice(days, rebuilt, archived, today_value=None):
    """Daily series: rebuilt values before the archive starts, archived values from then on, today's live value last."""
    s = pd.Series(rebuilt, index=days)
    if archived is not None and len(archived):
        a0 = archived.index.min()
        s = s[s.index < a0]
        s = pd.concat([s, archived.reindex(pd.date_range(a0, days[-1], freq="D"))])
    if today_value is not None:
        s.loc[days[-1]] = today_value
    return s.astype(float)


def rle(values, nd=2):
    """[[day_index, value], ...] at each change (None = no value)."""
    out, prev = [], object()
    for i, v in enumerate(values):
        v = None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)
        if v != prev:
            out.append([i, v])
            prev = v
    return out
