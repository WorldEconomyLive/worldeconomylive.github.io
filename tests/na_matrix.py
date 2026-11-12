"""n/a matrix for every series family, using the history each source returns to the pipeline (start, frequency, latest)."""
import sys
sys.path.insert(0, "pipeline")
import numpy as np, pandas as pd
from changes import change, window_change, seasonal_change, NAMES

def ser(start, end, freq):
    idx = {"M": pd.date_range(start, end, freq="MS"), "Q": pd.date_range(start, end, freq="QS"),
           "A": pd.DatetimeIndex([pd.Timestamp(f"{y}-07-01") for y in range(int(start[:4]), int(end[:4]) + 1)]),
           "D": pd.bdate_range(start, end)}[freq]
    return pd.Series(np.linspace(1, 2, len(idx)), index=idx)

FAM = [  # name, start, latest, freq, kind
    ("OECD monthly: inflation, unemployment, 10y yield, trade", "2003-01-01", "2026-10-01", "M", "pp"),
    ("OECD factory output (growth, monthly)", "2004-01-01", "2026-09-01", "M", "pp"),
    ("OECD trade, 12-month sums", "2003-12-01", "2026-10-01", "M", "pct"),
    ("BIS policy rates (monthly)", "1990-01-01", "2026-10-01", "M", "bp"),
    ("World Bank Pink Sheet commodities (monthly)", "1960-01-01", "2026-10-01", "M", "pct"),
    ("OECD GDP growth (quarterly)", "2004-01-01", "2026-07-01", "Q", "pp"),
    ("IMF WEO annual (growth, debt, balances...)", "1980-01-01", "2026-01-01", "A", "pp"),
    ("World Bank annual (people, C/I/G/NX, reserves...)", "2003-01-01", "2025-01-01", "A", "pct"),
    ("Debt section, monthly inputs (10y yield, r-g): shown 1Y+ only", "2003-01-01", "2026-10-01", "A*", "pp"),
    ("Inflation where only annual data exists (JP, MX, ZA, SA, CR, NZ, CL)", "2003-01-01", "2025-01-01", "A", "pp"),
    ("ECB exchange rates (daily)", "2004-11-12", "2026-11-11", "D", "pct"),
    ("US Treasury yields (daily)", "2005-01-03", "2026-11-11", "D", "bp"),
    ("US federal debt (daily)", "2003-01-02", "2026-11-10", "D", "pct"),
    ("Fed funds, NY Fed (daily)", "2016-03-01", "2026-11-11", "D", "bp"),
    ("Scores, economies (daily history)", "2026-11-11", "2026-11-13", "D", "pts"),
]
rows = []
for name, st, en, f, k in FAM:
    if f == "A*":
        o = change(ser(st, en, "M"), k); o["v"][:3] = [None] * 3; o["r"] = "fff" + o["r"][3:]
    else:
        o = change(ser(st, en, f), k)
    rows.append((name, o))
SEAS = [("Ember electricity, seasonal (most countries)", "2015-01-01", "2026-09-01", "M", 3),
        ("Ember electricity, seasonal (long-history countries)", "2000-01-01", "2026-09-01", "M", 3),
        ("US BTS rail/air/water freight, seasonal", "2000-01-01", "2026-08-01", "M", 1),
        ("Eurostat air freight, seasonal", "2004-01-01", "2026-08-01", "M", 3),
        ("Statistics Canada rail carloadings, seasonal", "1999-01-01", "2026-08-01", "M", 3),
        ("Eurostat rail freight, seasonal (quarterly)", "2004-01-01", "2026-04-01", "Q", 1)]
for name, st, en, f, w in SEAS:
    rows.append((name, seasonal_change(ser(st, en, f), w)))
dd = pd.date_range("2019-01-01", "2026-11-02", freq="D")
rows.append(("IMF PortWatch ports, chokepoints, ship types (seasonal)", window_change(pd.DataFrame({"t": 1.0}, index=dd), dd[-1], 28)["t"]))
w = max(len(r[0]) for r in rows)
print(f"{'series':{w}s}  " + "  ".join(f"{n:>4s}" for n in NAMES))
for name, o in rows:
    cells = []
    for v, r, a in zip(o["v"], o["r"], o["a"]):
        cells.append(("ok~" if a in (1, "1") else "ok") if r == "." else {"f": "n/a(freq)", "s": "n/a(start)", "g": "n/a(gap)", "x": "n/a(x)", "z": "n/a(seas)"}[r])
    print(f"{name:{w}s}  " + "  ".join(f"{c:>4s}" for c in cells) + f"   starts {o['s']}")
