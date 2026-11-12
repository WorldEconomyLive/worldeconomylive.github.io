"""Known-answer tests for the change engine across all 9 periods."""
import sys, math
sys.path.insert(0, "pipeline")
import numpy as np, pandas as pd
from changes import change, window_change, NAMES

def show(name, o):
    cells = []
    for n, v, r, a in zip(NAMES, o["v"], o["r"], o["a"]):
        cells.append(f"{n}:" + ("n/a(" + r + ")" if v is None else f"{v:+.3f}" + ("~" if a else "")))
    print(f"{name:34s} f={o['f']} start={o['s']}  " + "  ".join(cells))

# 1) monthly linear series 2004-01..2026-09: value = month index -> pp changes equal months
m = pd.date_range("2004-01-01", "2026-09-01", freq="MS")
lin = pd.Series(np.arange(len(m), dtype=float), index=m)
o = change(lin, "pp"); show("monthly linear (pp)", o)
exp_short = [1, 3, 6, 12, 36]
assert [round(x, 6) for x in o["v"][:5]] == exp_short
assert o["v"][5] == 60 and o["a"][5] == 1          # 12m-avg vs 12m-avg shifted 60 months = 60 on a line
assert o["v"][6] == 120 and o["v"][7] == 180 and o["v"][8] == 240
# 2) monthly that starts 2012-03 -> 15Y, 20Y before start; 10Y needs window from 2015-10.. ok
lin2 = lin[lin.index >= "2012-03-01"]
o = change(lin2, "pp"); show("monthly from 03/2012 (pp)", o)
assert o["r"][7] == "s" and o["r"][8] == "s" and o["v"][6] == 120 and o["s"] == "03/2012"
# 3) pct with CAGR: monthly growing 1%/month compounding
g = pd.Series(100 * 1.01 ** np.arange(len(m)), index=m)
o = change(g, "pct"); show("monthly +1%/mo (pct)", o)
assert abs(o["v"][0] - 1.0) < 1e-9 and abs(o["v"][3] - (1.01 ** 12 - 1) * 100) < 1e-9
assert abs(o["v"][4] - (1.01 ** 12 - 1) * 100) < 1e-9          # 3Y shown per year = 12.68%/yr
assert abs(o["v"][6] - (1.01 ** 12 - 1) * 100) < 1e-6          # 10Y avg-based per year same growth
# 4) quarterly GDP growth 2010Q1..2026Q3 : 1M n/a(f), 3M q/q
q = pd.date_range("2010-01-01", "2026-07-01", freq="QS")
qs = pd.Series(np.arange(len(q), dtype=float), index=q)
o = change(qs, "pp"); show("quarterly from 01/2010 (pp)", o)
assert o["r"][0] == "f" and o["v"][1] == 1 and o["v"][2] == 2 and o["v"][3] == 4 and o["v"][5] == 20 and o["a"][5] == 0
assert o["v"][7] == 60 and o["r"][8] == "s"
# 5) annual 2000..2026 dated 1 July
a = pd.Series({pd.Timestamp(f"{y}-07-01"): float(y) for y in range(2000, 2027)})
o = change(a, "pp"); show("annual 2000-2026 (pp)", o)
assert o["r"][:3] == "fff" and o["v"][3] == 1 and o["v"][4] == 3 and o["v"][8] == 20 and o["a"][8] == 0
# 6) daily rates (bp) business days
d = pd.bdate_range("2016-03-01", "2026-11-11")
ds = pd.Series(np.linspace(0.5, 4.0, len(d)), index=d)
o = change(ds, "bp"); show("daily from 03/2016 (bp)", o)
assert o["r"][7] == "s" and o["r"][8] == "s" and o["v"][0] > 0 and o["a"][5] == 0   # daily: point vs point
# 7) gap inside monthly history -> g
gap = lin.drop(lin.index[-13])
o = change(gap, "pp"); show("monthly w/ missing month (pp)", o)
assert o["r"][3] == "g"
# 8) pct with negative values -> x
neg = pd.Series(np.linspace(-5, 5, len(m)), index=m)
o = change(neg, "pct"); assert "x" in o["r"]
# 9) window_change on ports-like daily totals from 2019
dd = pd.date_range("2019-01-01", "2026-11-01", freq="D")
df = pd.DataFrame({"total": 100.0}, index=dd)
wc = window_change(df, dd[-1], 28)["total"]; show("ports daily flat (pct, seasonal)", wc)
assert wc["r"][:3] == "zzz" and all(abs(v) < 1e-9 for v in wc["v"][3:6]) and wc["r"][6:] == "sss"
# 10) seasonal monthly (electricity-like): strong seasonality, +2%/yr trend -> same-window compare removes seasonality
from changes import seasonal_change
mm = pd.date_range("2005-01-01", "2026-09-01", freq="MS")
seas = pd.Series([100 * (1.02 ** (i / 12)) * (1 + 0.3 * np.cos(2 * np.pi * d.month / 12)) for i, d in enumerate(mm)], index=mm)
sc = seasonal_change(seas, 3); show("seasonal monthly 3-mo window (pct)", sc)
assert sc["r"][:3] == "zzz" and abs(sc["v"][3] - 2.0) < 1e-6 and abs(sc["v"][5] - 2.0) < 1e-6 and abs(sc["v"][8] - 2.0) < 1e-6
# 11) seasonal quarterly (rail freight): quarter vs same quarter
qq = pd.date_range("2004-01-01", "2026-04-01", freq="QS")
sq = pd.Series([50 * 1.01 ** (i / 4) * (1.2 if d.month == 7 else 1) for i, d in enumerate(qq)], index=qq)
so = seasonal_change(sq, 1); show("seasonal quarterly (pct)", so)
assert so["r"][:3] == "zzz" and abs(so["v"][3] - 1.0) < 1e-6 and abs(so["v"][7] - 1.0) < 1e-6
print("ALL CHANGE TESTS PASSED")
