"""Check the score rebuild against the live computation: with every release delay set to zero, the rebuilt score
for today must equal today's live score for every economy, every annual-basis country and the world."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import mock_run  # noqa: E402,F401  (runs the mocked pipeline)
import run  # noqa: E402
import registry as R  # noqa: E402
import history as HB  # noqa: E402

d = json.loads(run.OUT.read_text())
R.LAGS = {k: 0 for k in R.LAGS}
R.DEFAULT_LAG = 0
R.WEO_RELEASE_MD = R.WB_RELEASE_MD = (1, 1)
_rd = HB.release_dates
HB.release_dates = lambda s, key: (_rd(s, key) if key and key.startswith("wb:") else _rd(s, key)) if key not in ("weo",) and not (key or "").startswith("wb:") else \
    __import__("pandas").DatetimeIndex([__import__("pandas").Timestamp(year=x.year, month=1, day=1) for x in s.index]) if key == "weo" else \
    __import__("pandas").DatetimeIndex([__import__("pandas").Timestamp(year=x.year + 1, month=1, day=1) for x in s.index])
rb = HB.Rebuild(run.RAW, run.TODAY).run([r["iso3"] for r in d["map"].values()])
bad = 0
for e in d["economies"]:
    a, b = e["score"], rb["scores"][e["iso3"]][-1]
    if (a is None) != np.isnan(b) or (a is not None and abs(a - b) > 0.01):
        bad += 1
        print("ECON MISMATCH", e["iso3"], a, b, {k: round(float(v[-1]), 3) for k, v in rb["pillars"][e["iso3"]].items()}, e["pillars"])
for r in d["map"].values():
    if r.get("basis") == "annual":
        a, b = r["score"], rb["scores"][r["iso3"]][-1]
        if abs(a - b) > 0.01:
            bad += 1
            print("ANNUAL MISMATCH", r["iso3"], a, b)
w = d["world"]["score"]
print("world live", w, "rebuilt", rb["world"][-1], "| stress live", d["world"]["breakdown"]["global stress"], "rebuilt", rb["stress"][-1])
if abs(w - rb["world"][-1]) > 0.01:
    bad += 1
first = min(int(np.argmax(~np.isnan(v))) for v in rb["scores"].values() if (~np.isnan(v)).any())
print("earliest score day", str(run.pd.date_range(R.HISTORY_START, periods=first + 1)[-1].date()), "| mismatches", bad)
sys.exit(1 if bad else 0)
