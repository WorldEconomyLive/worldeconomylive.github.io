"""Daily archive: unchanged inputs add nothing; a revised figure is stored once; replaying the files restores it."""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import mock_run  # noqa: E402,F401
import run  # noqa: E402
import packs as PK  # noqa: E402

folder = run.INPUTS
first = sorted(folder.glob("*.json.gz"))
assert len(first) == 1 and json.loads(gzip.open(first[0], "rt").read())["baseline"]
n0 = PK.archive_inputs("2099-01-01", run.RAW, folder)
assert n0 == 0, n0
s = run.RAW["pink"]["Gold"]
s.iloc[-1] = s.iloc[-1] + 1.0                                  # a revision
n1 = PK.archive_inputs("2099-01-02", run.RAW, folder)
assert n1 == 1, n1
state = {}
for p in sorted(folder.glob("*.json.gz")):
    for k, obs in json.loads(gzip.open(p, "rt").read())["diff"].items():
        state.setdefault(k, {}).update(obs)
last_day = s.index[-1].strftime("%Y-%m-%d")
assert abs(state["pink/Gold"][last_day] - PK.rv(s.iloc[-1])) < 1e-9
idx = json.loads((run.ARCH / "index.json").read_text())
print("archive ok:", len(idx["dates"]), "snapshot(s);", sum(1 for _ in folder.glob("*.json.gz")), "input files; unchanged day adds", n0, "; one revision adds", n1)
for p in folder.glob("2099-*"):
    p.unlink()
