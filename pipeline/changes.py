"""Change-over-period engine for World Economy Live.

Every value shown on the site carries a change object computed here:
    {"v": [9 values], "r": "9 reason codes", "k": kind, "f": freq, "s": "MM/YYYY", "a": [9 flags]}
Periods (same order everywhere): 1M 3M 6M 1Y 3Y 5Y 10Y 15Y 20Y.

Kinds
    pts  straight change in points            (scores, indices)
    bp   straight change x 100, basis points  (interest rates, bond yields, rate spreads)
    pp   straight change, percentage points   (inflation, unemployment, growth rates, % of GDP)
    pct  percent change; for 3Y+ the compound annual rate ("per year")   (prices, FX, trade, cargo, power)
    abs  straight change in the series' own unit (balances that cross zero, e.g. trade balance in US$)

Rules
    * A period shorter than the series' own spacing is n/a (reason "f"): 1M on quarterly, 1M-6M on annual.
    * 5Y+ on daily/weekly/monthly series compares the latest 12-month average with the 12-month average
      the same number of years earlier ("a" flag = 1). Quarterly and annual series compare point with point.
    * If the comparison reaches back before the series begins: n/a, reason "s" (start date reported).
    * If the comparison point is missing inside the history: n/a, reason "g". Nothing is ever estimated.
    * pct needs both values > 0; otherwise n/a, reason "x".
Reason codes: "." ok, "f" too infrequent, "s" before history starts, "g" gap, "x" not meaningful,
    "z" seasonal series below 1Y (they compare like-for-like windows only).

Seasonal series that are not seasonally adjusted (port cargo, chokepoints, electricity, freight) use
seasonal_change / window_change: the same window (e.g. the latest 3 months, or 28 days) compared with the same window
1, 3, 5, 10, 15 or 20 years earlier. 1M-6M are n/a ("z"). No 12-month averaging; 3Y+ percent changes are per year.
"""
import math

import numpy as np
import pandas as pd

PERIODS = [("1M", 1), ("3M", 3), ("6M", 6), ("1Y", 12), ("3Y", 36), ("5Y", 60), ("10Y", 120), ("15Y", 180), ("20Y", 240)]
NAMES = [p for p, _ in PERIODS]
SPACING_MONTHS = {"D": 0, "W": 0, "M": 1, "Q": 3, "A": 12}
POINT_TOL = {"D": pd.Timedelta(days=7), "W": pd.Timedelta(days=10), "M": pd.Timedelta(days=16),
             "Q": pd.Timedelta(days=46), "A": pd.Timedelta(days=200)}


def freq_of(s: pd.Series) -> str:
    """Native frequency from the median spacing between observations."""
    if len(s) < 2:
        return "A"
    d = np.median(np.diff(s.index.values).astype("timedelta64[D]").astype(float))
    if d <= 4:
        return "D"
    if d <= 10:
        return "W"
    if d <= 45:
        return "M"
    if d <= 135:
        return "Q"
    return "A"


def _compare(a, b, kind, months):
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)) or (isinstance(b, float) and math.isnan(b)):
        return None, "g"
    if kind == "pct":
        if a <= 0 or b <= 0:
            return None, "x"
        if months >= 36:
            return ((a / b) ** (12.0 / months) - 1) * 100, "."
        return (a / b - 1) * 100, "."
    if kind == "bp":
        return (a - b) * 100, "."
    return a - b, "."            # pts, pp, abs


def change(s, kind, freq=None, avg_long=True):
    """Change object for one series. s: pd.Series indexed by date (any frequency)."""
    out = {"v": [None] * 9, "r": ["s"] * 9, "k": kind, "f": None, "s": None, "a": [0] * 9}
    if s is None:
        out["r"] = "".join(out["r"])
        return out
    s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if len(s) < 2:
        out["r"] = "".join(out["r"])
        if len(s):
            out["s"] = s.index[0].strftime("%m/%Y")
        return out
    f = freq or freq_of(s)
    out["f"], out["s"] = f, (str(s.index[0].year) if f == "A" else s.index[0].strftime("%m/%Y"))
    first, last_d = s.index[0], s.index[-1]
    a_now = float(s.iloc[-1])
    tol = POINT_TOL[f]
    for i, (_, m) in enumerate(PERIODS):
        if m < SPACING_MONTHS[f]:
            out["r"][i] = "f"
            continue
        target = last_d - pd.DateOffset(months=m)
        if avg_long and m >= 60 and f in ("W", "M"):
            cur = s[s.index > last_d - pd.DateOffset(months=12)]
            lo, hi = target - pd.DateOffset(months=12), target
            if lo < first - tol:
                out["r"][i] = "s"
                continue
            prev = s[(s.index > lo) & (s.index <= hi)]
            if len(prev) < 0.8 * len(cur) or not len(prev):
                out["r"][i] = "g"
                continue
            v, r = _compare(float(cur.mean()), float(prev.mean()), kind, m)
            out["v"][i], out["r"][i], out["a"][i] = v, r, 1
            continue
        if target < first - tol:
            out["r"][i] = "s"
            continue
        if f in ("D", "W"):
            cand = s[(s.index <= target) & (s.index >= target - tol)]
            b = float(cand.iloc[-1]) if len(cand) else None
        else:
            near = s[(s.index >= target - tol) & (s.index <= target + tol)]
            b = float(near.iloc[(abs(near.index - target)).argmin()]) if len(near) else None
        v, r = _compare(a_now, b, kind, m)
        out["v"][i], out["r"][i] = v, r
    out["r"] = "".join(out["r"])
    return out


def seasonal_change(s, window, kind="pct"):
    """Seasonal monthly/quarterly series: sum of the latest `window` observations vs the same observations exactly
    1/3/5/10/15/20 years earlier. Periods under 1Y are n/a ("z")."""
    out = {"v": [None] * 9, "r": ["z"] * 9, "k": kind, "f": None, "s": None, "a": [0] * 9}
    if s is None:
        out["r"] = "".join(out["r"])
        return out
    s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if len(s) < window:
        out["r"] = "".join("z" if m < 12 else "s" for _, m in PERIODS)
        return out
    f = freq_of(s)
    step = 3 if f == "Q" else 1
    out["f"], out["s"] = f, s.index[0].strftime("%m/%Y")
    ends = [s.index[-1] - pd.DateOffset(months=step * j) for j in range(window)]

    def total(shift):
        dates = [d - pd.DateOffset(months=shift) for d in ends]
        if min(dates) < s.index[0]:
            return None, "s"
        vals = [s.get(d) for d in dates]
        if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
            return None, "g"
        return float(sum(vals)), "."
    cur, rc = total(0)
    for i, (_, m) in enumerate(PERIODS):
        if m < 12:
            continue
        if rc != ".":
            out["r"][i] = rc
            continue
        prev, rp = total(m)
        if rp != ".":
            out["r"][i] = rp
            continue
        v, r = _compare(cur, prev, kind, m)
        out["v"][i], out["r"][i] = v, r
    out["r"] = "".join(out["r"])
    return out


def window_change(daily: pd.DataFrame, end, window_days, kind="pct", start=None):
    """Seasonal flow data kept as daily totals (ports, chokepoints): the sum over `window_days` ending `end`
    compared with the same window 1/3/5/10/15/20 years earlier. Under 1Y is n/a ("z"). Returns {column: change}."""
    daily = daily.sort_index()
    first = start if start is not None else daily.index.min()
    res = {}
    for col in daily.columns:
        o = {"v": [None] * 9, "r": ["s"] * 9, "k": kind, "f": "D", "s": first.strftime("%m/%Y"), "a": [0] * 9}
        x = daily[col]

        def tot(hi, days):
            lo = hi - pd.Timedelta(days=days - 1)
            if lo < first:
                return None, "s"
            w = x[(x.index >= lo) & (x.index <= hi)]
            if w.count() < 0.8 * days:
                return None, "g"
            return float(w.mean()) * days, "."
        cur, rc = tot(end, window_days)
        for i, (_, m) in enumerate(PERIODS):
            if m < 12:
                o["r"][i] = "z"
                continue
            if rc != ".":
                o["r"][i] = rc
                continue
            prev, rp = tot(end - pd.DateOffset(months=m), window_days)
            if rp != ".":
                o["r"][i] = rp
                continue
            v, r = _compare(cur, prev, kind, m)
            o["v"][i], o["r"][i] = v, r
        o["r"] = "".join(o["r"])
        res[col] = o
    return res


def annual_series(rows):
    """[(year, value), ...] -> annual series dated 1 July."""
    s = pd.Series({pd.Timestamp(f"{int(y)}-07-01"): v for y, v in rows if v is not None})
    return s.sort_index()
