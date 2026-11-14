"""Write the input series the browser needs to rebuild the site for any past date (site/data/packs/*.json),
and keep the daily archive: the site as shown each day (site/data/archive/) and every input as fetched
(data/archive/inputs/, one file of new or revised observations per day)."""
import gzip
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

try:
    import registry as R
except ImportError:          # imported as pipeline.packs
    from pipeline import registry as R

EPOCH = pd.Timestamp("1970-01-01")


def dayn(ts):
    return int((pd.Timestamp(ts).normalize() - EPOCH).days)


def rv(x):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    a = abs(x)
    if a >= 1e7:
        return int(round(x))
    if a == 0:
        return 0
    return round(x, max(0, min(8, 7 - int(math.floor(math.log10(a))) - 1)))     # 7 significant digits


def enc(s):
    """Series -> {"t": [first day, deltas...], "v": [...]} (days since 1970-01-01)."""
    if s is None:
        return None
    s = pd.to_numeric(pd.Series(s), errors="coerce").dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if not len(s):
        return None
    d = [dayn(x) for x in s.index]
    return {"t": [d[0]] + [b - a for a, b in zip(d, d[1:])], "v": [rv(v) for v in s.values]}


def enc_frame(df, cols=None):
    """Daily/irregular frame with a shared index, NaN kept as null: {"t": [...], "c": {col: [...]}}."""
    if df is None or not len(df):
        return None
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    d = [dayn(x) for x in df.index]
    cols = cols or list(df.columns)
    return {"t": [d[0]] + [b - a for a, b in zip(d, d[1:])], "c": {str(c): [rv(v) for v in df[c].values] for c in cols if c in df}}


def _dump(path, obj):
    path.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False))


def write_packs(raw, meta, scores, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / ".gitignore").write_text("*\n")          # rebuilt every run and deployed; not kept in the repo history
    macro = {}
    for iso3, e in raw.get("macro", {}).items():
        macro[iso3] = {"name": e["name"], "g20": e["g20"], "bis": enc(e.get("bis")),
                       "ind": {k: [{"s": enc(c["s"]), "lab": c["lab"], "annual": bool(c["annual"]), "rk": c["rk"],
                                    "b": c.get("b"), "o": c.get("o", 0)} for c in v] for k, v in e.get("ind", {}).items()}}
    _dump(out / "macro.json", macro)
    ann = {}
    for iso3, H in raw.get("annual", {}).items():
        rec = {}
        for k, s in H.items():
            if k in R.WB_FALLBACK and s is H.get(R.WB_FALLBACK[k]):
                continue                                 # World Bank fallback: the browser applies it itself
            s = s.dropna() if s is not None else None
            if s is None or not len(s):
                continue
            y0, y1 = int(s.index.year.min()), int(s.index.year.max())
            by = {int(d.year): rv(v) for d, v in s.items()}
            rec[k] = [y0, [by.get(y) for y in range(y0, y1 + 1)]]
        if rec:
            ann[iso3] = rec
    _dump(out / "annual.json", ann)
    mk = {"fx": enc_frame(raw.get("fx")), "yc": enc_frame(raw.get("yc")), "ry": enc(raw.get("ry")),
          "effr": enc(raw.get("effr")), "debt": enc(raw.get("debt"))}
    fy = raw.get("fy")
    if fy is not None and len(fy):
        mk["fy"] = [[int(r.fy), dayn(r.through), rv(r.receipts), rv(r.outlays)] for r in fy.itertuples()]
    _dump(out / "markets.json", mk)
    P = raw.get("ports")
    if P:
        _dump(out / "ports.json", {"first": dayn(P["first"]), "end": dayn(P["end"]),
                                   "glob": enc_frame(P["glob"]),
                                   "reg": {r: enc_frame(df) for r, df in P["reg"].items()},
                                   "eco": {i: enc_frame(s.to_frame("total")) for i, s in P["eco"].items()},
                                   "cp": {c: enc_frame(df) for c, df in P["cp"].items()}})
    fr = raw.get("freight", {})
    other = {"pink": {k: enc(s) for k, s in (raw.get("pink") or {}).items()},
             "pink_stress": {k: enc(s) for k, s in (raw.get("pink_stress") or {}).items()},
             "ember": {k: enc(s) for k, s in (raw.get("ember") or {}).items()},
             "bts": [[n, c, enc(s)] for n, c, s in (raw.get("bts") or [])],
             "freight": {"air": {k: enc(s) for k, s in (fr.get("air") or {}).items()},
                         "rail": {k: enc(s) for k, s in (fr.get("rail") or {}).items()},
                         "can": enc(fr.get("can"))}}
    _dump(out / "other.json", other)
    _dump(out / "scores.json", scores)
    _dump(out / "meta.json", meta)


# ---------------------------------------------------------------- terms that travel with the public data files
# Every folder of data the site publishes carries this note, so anyone who opens or copies the files sees the
# sources' terms (the IMF asks distributors of its data to make reasonable efforts to pass its terms on).
TERMS = """WORLD ECONOMY LIVE: TERMS FOR THE DATA IN THIS FOLDER

These files are the data the website loads to draw its pages: published figures from the sources
below, plus the site's own calculations (changes, windows, ratios, scores), which the site labels as
such. No source endorses this site or is responsible for these calculations. Each source's terms
continue to apply to its data. If you reuse any of it, credit the source and follow its terms.
Provided as is, without warranty. Nothing here is investment advice.

INTERNATIONAL MONETARY FUND: World Economic Outlook database; PortWatch
  Source: International Monetary Fund, World Economic Outlook database, https://www.imf.org/en/Publications/WEO
  Source: International Monetary Fund, PortWatch, https://portwatch.imf.org
  Reproduced under the IMF Copyright and Usage terms for statistical data:
  https://www.imf.org/en/about/copyright-and-terms
  Your reuse is subject to those terms. Commercial reuse of IMF data requires permission from copyright@imf.org.

BANK FOR INTERNATIONAL SETTLEMENTS: central bank policy rates
  Source: Bank for International Settlements, https://data.bis.org
  Terms: https://www.bis.org/terms_statistics.htm
  The BIS does not warrant or guarantee the accuracy, completeness or fitness for any contemplated purpose
  of these statistics, and nothing in them is investment advice. Use in a commercial product must not
  result in any additional charge to its users.

OECD: inflation, unemployment, industrial production, GDP, bond yields, share prices, merchandise trade
  Source: OECD Data Explorer, https://data-explorer.oecd.org
  Terms: https://www.oecd.org/en/about/terms-conditions.html

WORLD BANK: World Development Indicators; Commodity Price Data (The Pink Sheet). CC BY 4.0.
  Source: World Bank. No endorsement by the World Bank is implied.
  The R&D spending series (UNESCO Institute for Statistics, via the World Bank) is CC BY-SA 3.0 IGO:
  adaptations of it must be shared under the same licence.

EMBER: monthly and yearly electricity data. CC BY 4.0. Source: Ember, https://ember-energy.org

OUR WORLD IN DATA: processing CC BY 4.0; each series keeps its original licence: Maddison Project
  Database 2023 (CC BY 4.0), Penn World Table 11.0 (CC BY 4.0), UNDP Human Development Report
  (CC BY 3.0 IGO), Global Carbon Budget (CC BY 4.0), Jones et al., National contributions to climate change.

EUROSTAT: euro-area fallbacks, air and rail freight. Source: Eurostat.
  Eurostat bears no responsibility for this reuse.

EUROPEAN CENTRAL BANK: euro reference exchange rates. Source: ECB statistics.

FEDERAL RESERVE BANK OF NEW YORK: effective federal funds rate. The Effective Federal Funds Rate is
  subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for
  publication of the Effective Federal Funds Rate by World Economy Live, does not sanction or endorse
  any particular republication, and has no liability for your use.

U.S. GOVERNMENT WORKS (public domain): Department of the Treasury (yield curves, Fiscal Data),
  Bureau of Transportation Statistics, Commodity Futures Trading Commission (Commitments of Traders),
  Energy Information Administration (International Energy Statistics).

STATISTICS CANADA: adapted from Statistics Canada, Table 23-10-0216-01, Railway carloadings, under the
  Statistics Canada Open Licence. This does not constitute an endorsement by Statistics Canada of this product.
"""


def write_terms(*folders: Path):
    for f in folders:
        f.mkdir(parents=True, exist_ok=True)
        (f / "TERMS.txt").write_text(TERMS)


# ---------------------------------------------------------------- daily archive
def _gz(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(text.encode())


def archive_site(day: str, hb: str, series: str, annual: str, arch: Path):
    """The site exactly as shown today: heartbeat every day; series/annual only when they change."""
    idx_p = arch / "index.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else {"dates": {}}
    rec = {"h": f"h/{day}.json.gz"}
    _gz(arch / rec["h"], hb)
    for k, txt in (("s", series), ("a", annual)):
        h = hashlib.sha1(txt.encode()).hexdigest()[:12]
        p = arch / k / f"{h}.json.gz"
        if not p.exists():
            _gz(p, txt)
        rec[k] = f"{k}/{h}.json.gz"
    idx["dates"][day] = rec
    idx["dates"] = dict(sorted(idx["dates"].items()))
    idx_p.write_text(json.dumps(idx, separators=(",", ":")))
    return idx


def flatten(raw):
    """Every raw series as {key: {YYYY-MM-DD: value}}."""
    out = {}

    def put(key, s):
        if s is None:
            return
        s = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        if len(s):
            out[key] = {pd.Timestamp(d).strftime("%Y-%m-%d"): rv(v) for d, v in s.items()}

    def frame(prefix, df):
        if df is not None:
            for c in df.columns:
                put(f"{prefix}/{c}", df[c])
    for iso3, e in raw.get("macro", {}).items():
        put(f"macro/{iso3}/bis", e.get("bis"))
        for ind, cs in e.get("ind", {}).items():
            for c in cs:
                put(f"macro/{iso3}/{ind}/{c['rk']}", c["s"])
    for iso3, H in raw.get("annual", {}).items():
        for k, s in H.items():
            put(f"annual/{iso3}/{k}", s)
    for k, s in (raw.get("pink") or {}).items():
        put(f"pink/{k}", s)
    for k, df in (raw.get("cftc") or {}).items():
        frame(f"cftc/{k}", df)
    frame("fx", raw.get("fx"))
    frame("yc", raw.get("yc"))
    for k in ("ry", "effr", "debt"):
        put(k, raw.get(k))
    fy = raw.get("fy")
    if fy is not None and len(fy):
        put("mts/receipts", fy.set_index("through")["receipts"])
        put("mts/outlays", fy.set_index("through")["outlays"])
    P = raw.get("ports")
    if P:
        frame("ports/global", P["glob"])
        for r, df in P["reg"].items():
            frame(f"ports/region/{r}", df)
        for i, s in P["eco"].items():
            put(f"ports/economy/{i}", s)
        for c, df in P["cp"].items():
            frame(f"ports/chokepoint/{c}", df)
    for k, s in (raw.get("ember") or {}).items():
        put(f"ember/{k}", s)
    for n, c, s in raw.get("bts") or []:
        put(f"bts/{c}", s)
    fr = raw.get("freight") or {}
    for mode in ("air", "rail"):
        for k, s in (fr.get(mode) or {}).items():
            put(f"freight/{mode}/{k}", s)
    put("freight/can", fr.get("can"))
    return out


def archive_inputs(day: str, raw, folder: Path):
    """Write only what is new or revised since the last archived state (the first file is the full baseline).
    Applying the files in date order rebuilds every input exactly as fetched on any archived day."""
    folder.mkdir(parents=True, exist_ok=True)
    state = {}
    for p in sorted(folder.glob("*.json.gz")):
        if p.name.startswith(day):
            continue
        with gzip.open(p, "rt") as f:
            diff = json.load(f).get("diff", {})
        for k, obs in diff.items():
            cur = state.setdefault(k, {})
            for d, v in obs.items():
                if v is None:
                    cur.pop(d, None)
                else:
                    cur[d] = v
    now = flatten(raw)
    diff = {}
    for k, obs in now.items():
        old = state.get(k, {})
        ch = {d: v for d, v in obs.items() if old.get(d) != v}
        ch.update({d: None for d in old if d not in obs})
        if ch:
            diff[k] = ch
    _gz(folder / f"{day}.json.gz", json.dumps({"day": day, "baseline": not state, "diff": diff}, separators=(",", ":")))
    return sum(len(v) for v in diff.values())


# ---- one-time repair: on these days the IMF data-portal route sent GDP in US$ while the site assumed billions,
# so archived GDP figures came out 1e9 too large. Idempotent: only values above 1e15 (no GDP is $1,000tn) change.
BAD_GDP_DAYS = ("2026-11-13",)
_GDP_CAP = 1e15


def _fix_num(v):
    return v / 1e9 if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) > _GDP_CAP else v


def _fix_gdp(x):
    """Walk a site JSON object; scale every 'gdp_usd' number (plain, {'value'}, or [y0, [values]]) that is too large."""
    n = 0
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "gdp_usd":
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    nv = _fix_num(v); n += nv != v; x[k] = nv
                elif isinstance(v, dict) and "value" in v:
                    for kk in ("value", "ten_years_ago", "year_ago"):
                        if kk in v:
                            nv = _fix_num(v[kk]); n += nv != v[kk]; v[kk] = nv
                elif isinstance(v, list) and len(v) == 2 and isinstance(v[1], list):
                    new = [_fix_num(a) for a in v[1]]; n += sum(a != b for a, b in zip(new, v[1])); v[1] = new
            else:
                n += _fix_gdp(v)
    elif isinstance(x, list):
        for v in x:
            n += _fix_gdp(v)
    return n


def repair_gdp_units(arch: Path, inputs: Path):
    """Fix the archived site snapshots and input files of BAD_GDP_DAYS. Returns the number of values changed."""
    n = 0
    idx_p = arch / "index.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else {"dates": {}}
    files = set()
    for day in BAD_GDP_DAYS:
        rec = idx["dates"].get(day) or {}
        files |= {arch / rec[k] for k in ("h", "a") if rec.get(k)}
    for p in sorted(files):
        if not p.exists():
            continue
        with gzip.open(p, "rt") as f:
            obj = json.load(f)
        c = _fix_gdp(obj)
        if c:
            _gz(p, json.dumps(obj, separators=(",", ":")))
            n += c
    for day in BAD_GDP_DAYS:
        p = inputs / f"{day}.json.gz"
        if not p.exists():
            continue
        with gzip.open(p, "rt") as f:
            obj = json.load(f)
        c = 0
        for k, obs in obj.get("diff", {}).items():
            if k.endswith("/gdp_usd"):
                for d, v in obs.items():
                    nv = _fix_num(v); c += nv != v; obs[d] = nv
        if c:
            _gz(p, json.dumps(obj, separators=(",", ":")))
            n += c
    return n
