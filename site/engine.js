/* World Economy Live — rebuild the whole site for a past date, in the browser.
   Every input series is cut back to the observations that count as released on or before the chosen date
   (each source's standard publication delay), then the same calculations the daily run makes are applied.
   This file mirrors pipeline/run.py and pipeline/changes.py; scores come pre-rebuilt from pipeline/history.py. */
(function () {
  'use strict';
  // ---------------------------------------------------------------- dates (days since 1970-01-01, UTC)
  const DAY = 86400000;
  const dn = (y, m, d) => Math.round(Date.UTC(y, m - 1, d) / DAY);
  const ymd = (n) => { const t = new Date(n * DAY); return [t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate()]; };
  const iso = (n) => new Date(n * DAY).toISOString().slice(0, 10);
  const parse = (s) => { const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return dn(y, m, d || 1); };
  const dim = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
  function addMonths(n, k) { // pandas DateOffset(months=k): same day, clamped to the month's end
    let [y, m, d] = ymd(n); let mm = m - 1 + k; y += Math.floor(mm / 12); mm = ((mm % 12) + 12) % 12;
    return dn(y, mm + 1, Math.min(d, dim(y, mm + 1)));
  }
  const addYears = (n, k) => addMonths(n, 12 * k);
  const monthStart = (n) => { const [y, m] = ymd(n); return dn(y, m, 1); };
  const ym = (n) => iso(n).slice(0, 7);
  const ok = (v) => v !== null && v !== undefined && !Number.isNaN(v);

  // ---------------------------------------------------------------- series {t:[days], v:[values]} (finite values only)
  function dec(o) {
    if (!o) return null;
    const t = new Array(o.t.length); let c = 0;
    for (let i = 0; i < o.t.length; i++) { c += o.t[i]; t[i] = c; }
    const T = [], V = [];
    for (let i = 0; i < t.length; i++) if (ok(o.v[i])) { T.push(t[i]); V.push(o.v[i]); }
    return T.length ? { t: T, v: V } : null;
  }
  function decFrame(o) {
    if (!o) return null;
    const t = new Array(o.t.length); let c = 0;
    for (let i = 0; i < o.t.length; i++) { c += o.t[i]; t[i] = c; }
    const cols = {};
    for (const [k, v] of Object.entries(o.c)) cols[k] = v.map((x) => (ok(x) ? x : NaN));
    return { t, c: cols };
  }
  const col = (F, k) => { if (!F || !F.c[k]) return null; const T = [], V = []; F.c[k].forEach((x, i) => { if (ok(x)) { T.push(F.t[i]); V.push(x); } }); return T.length ? { t: T, v: V } : null; };
  const len = (s) => (s ? s.t.length : 0);
  const last = (s) => s.v[s.v.length - 1];
  const lastT = (s) => s.t[s.t.length - 1];
  function ub(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] <= x) lo = m + 1; else hi = m; } return lo; } // first index with a[i] > x
  function lb(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; } return lo; } // first index with a[i] >= x
  const head = (s, k) => (k <= 0 ? null : k >= s.t.length ? s : { t: s.t.slice(0, k), v: s.v.slice(0, k) });
  const upto = (s, n) => (s ? head(s, ub(s.t, n)) : null);
  const map = (s, f) => (s ? { t: s.t, v: s.v.map(f) } : null);
  function dropna(t, v) { const T = [], V = []; for (let i = 0; i < t.length; i++) if (ok(v[i]) && Number.isFinite(v[i])) { T.push(t[i]); V.push(v[i]); } return T.length ? { t: T, v: V } : null; }

  function freqOf(s) {
    if (!s || s.t.length < 2) return 'A';
    const d = []; for (let i = 1; i < s.t.length; i++) d.push(s.t[i] - s.t[i - 1]);
    d.sort((a, b) => a - b); const n = d.length, med = n % 2 ? d[(n - 1) / 2] : (d[n / 2 - 1] + d[n / 2]) / 2;
    return med <= 4 ? 'D' : med <= 10 ? 'W' : med <= 45 ? 'M' : med <= 135 ? 'Q' : 'A';
  }

  // ---------------------------------------------------------------- release timing
  let META = null;
  function lagOf(key) {
    const L = META.asof.lags;
    if (key in L) return L[key];
    for (const k of Object.keys(L)) if (key && key.startsWith(k)) return L[k];
    return META.asof.default_lag;
  }
  function periodEnd(t, f) {
    const [y, m] = ymd(t);
    if (f === 'M') return dn(y, m, dim(y, m));
    if (f === 'Q') { const qm = Math.ceil(m / 3) * 3; return dn(y, qm, dim(y, qm)); }
    if (f === 'W') return t + 6;
    if (f === 'A') return dn(y, 12, 31);
    return t;
  }
  function releaseOf(s, key) {
    if (s._rel && s._relk === key) return s._rel;
    let r;
    if (key === 'weo') { const [m, d] = META.asof.weo_md; r = s.t.map((t) => dn(ymd(t)[0], m, d)); }
    else if (key && key.startsWith('wb:')) { const [m, d] = META.asof.wb_md; r = s.t.map((t) => dn(ymd(t)[0] + 1, m, d)); }
    else { const f = freqOf(s), L = lagOf(key); r = s.t.map((t) => periodEnd(t, f) + L); }
    for (let i = 1; i < r.length; i++) if (r[i] < r[i - 1]) r[i] = r[i - 1];
    s._rel = r; s._relk = key; return r;
  }
  // the series as known on day d: observations that count as released on or before d
  const cut = (s, key, d) => (s ? head(s, ub(releaseOf(s, key), d)) : null);

  // ---------------------------------------------------------------- change engine (pipeline/changes.py)
  const PER = [['1M', 1], ['3M', 3], ['6M', 6], ['1Y', 12], ['3Y', 36], ['5Y', 60], ['10Y', 120], ['15Y', 180], ['20Y', 240]];
  const SPACING = { D: 0, W: 0, M: 1, Q: 3, A: 12 }, TOL = { D: 7, W: 10, M: 16, Q: 46, A: 200 };
  const mmyyyy = (n) => { const [y, m] = ymd(n); return String(m).padStart(2, '0') + '/' + y; };
  function cmp(a, b, kind, months) {
    if (!ok(a) || !ok(b)) return [null, 'g'];
    if (kind === 'pct') { if (a <= 0 || b <= 0) return [null, 'x']; return [months >= 36 ? (Math.pow(a / b, 12 / months) - 1) * 100 : (a / b - 1) * 100, '.']; }
    if (kind === 'bp') return [(a - b) * 100, '.'];
    return [a - b, '.'];
  }
  function clean(s) { // sorted, unique dates (keep last), finite
    if (!s || !s.t.length) return null;
    const T = [], V = [];
    for (let i = 0; i < s.t.length; i++) { if (!ok(s.v[i]) || !Number.isFinite(s.v[i])) continue; if (T.length && T[T.length - 1] === s.t[i]) V[V.length - 1] = s.v[i]; else { T.push(s.t[i]); V.push(s.v[i]); } }
    return T.length ? { t: T, v: V } : null;
  }
  function change(s0, kind, freq, avgLong = true) {
    const out = { v: Array(9).fill(null), r: Array(9).fill('s'), k: kind, f: null, s: null, a: Array(9).fill(0) };
    const s = clean(s0);
    if (!s || s.t.length < 2) { if (s && s.t.length) out.s = mmyyyy(s.t[0]); out.r = out.r.join(''); out.a = out.a.join(''); return out; }
    const f = freq || freqOf(s);
    out.f = f; out.s = f === 'A' ? String(ymd(s.t[0])[0]) : mmyyyy(s.t[0]);
    const first = s.t[0], L = lastT(s), aNow = last(s), tol = TOL[f];
    PER.forEach(([, m], i) => {
      if (m < SPACING[f]) { out.r[i] = 'f'; return; }
      const target = addMonths(L, -m);
      if (avgLong && m >= 60 && (f === 'W' || f === 'M')) {
        const c0 = ub(s.t, addMonths(L, -12)), cur = s.v.slice(c0);
        const lo = addMonths(target, -12), hi = target;
        if (lo < first - tol) { out.r[i] = 's'; return; }
        const p0 = ub(s.t, lo), p1 = ub(s.t, hi), prev = s.v.slice(p0, p1);
        if (prev.length < 0.8 * cur.length || !prev.length) { out.r[i] = 'g'; return; }
        const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
        const [v, r] = cmp(mean(cur), mean(prev), kind, m);
        out.v[i] = v; out.r[i] = r; out.a[i] = 1; return;
      }
      if (target < first - tol) { out.r[i] = 's'; return; }
      let b = null;
      if (f === 'D' || f === 'W') { const j = ub(s.t, target) - 1; if (j >= 0 && s.t[j] >= target - tol) b = s.v[j]; }
      else {
        const j0 = lb(s.t, target - tol), j1 = ub(s.t, target + tol);
        let best = -1, bd = Infinity; for (let j = j0; j < j1; j++) { const dd = Math.abs(s.t[j] - target); if (dd < bd) { bd = dd; best = j; } }
        if (best >= 0) b = s.v[best];
      }
      const [v, r] = cmp(aNow, b, kind, m); out.v[i] = v; out.r[i] = r;
    });
    out.r = out.r.join(''); out.a = out.a.join('');
    return out;
  }
  function seasonalChange(s0, window, kind = 'pct') {
    const out = { v: Array(9).fill(null), r: Array(9).fill('z'), k: kind, f: null, s: null, a: Array(9).fill(0) };
    const s = clean(s0);
    if (!s || s.t.length < window) { out.r = PER.map(([, m]) => (m < 12 ? 'z' : 's')).join(''); out.a = out.a.join(''); return out; }
    const f = freqOf(s), step = f === 'Q' ? 3 : 1; out.f = f; out.s = mmyyyy(s.t[0]);
    const L = lastT(s), ends = []; for (let j = 0; j < window; j++) ends.push(addMonths(L, -step * j));
    const at = new Map(s.t.map((t, i) => [t, s.v[i]]));
    const total = (shift) => { const ds = ends.map((d) => addMonths(d, -shift)); if (Math.min(...ds) < s.t[0]) return [null, 's']; const vs = ds.map((d) => at.get(d)); if (vs.some((v) => !ok(v))) return [null, 'g']; return [vs.reduce((a, b) => a + b, 0), '.']; };
    const [cur, rc] = total(0);
    PER.forEach(([, m], i) => {
      if (m < 12) return;
      if (rc !== '.') { out.r[i] = rc; return; }
      const [prev, rp] = total(m); if (rp !== '.') { out.r[i] = rp; return; }
      const [v, r] = cmp(cur, prev, kind, m); out.v[i] = v; out.r[i] = r;
    });
    out.r = out.r.join(''); out.a = out.a.join('');
    return out;
  }
  // daily: {t0, v[] with NaN}, regular calendar days
  function windowChange(daily, end, days, first, kind = 'pct') {
    const o = { v: Array(9).fill(null), r: Array(9).fill('s'), k: kind, f: 'D', s: mmyyyy(first), a: '000000000' };
    const tot = (hi) => {
      const lo = hi - (days - 1); if (lo < first) return [null, 's'];
      let n = 0, sum = 0; for (let t = lo; t <= hi; t++) { const x = daily.get(t); if (ok(x)) { n++; sum += x; } }
      if (n < 0.8 * days) return [null, 'g'];
      return [(sum / n) * days, '.'];
    };
    const [cur, rc] = tot(end);
    PER.forEach(([, m], i) => {
      if (m < 12) { o.r[i] = 'z'; return; }
      if (rc !== '.') { o.r[i] = rc; return; }
      const [prev, rp] = tot(addMonths(end, -m)); if (rp !== '.') { o.r[i] = rp; return; }
      const [v, r] = cmp(cur, prev, kind, m); o.v[i] = v; o.r[i] = r;
    });
    o.r = o.r.join('');
    return o;
  }

  // ---------------------------------------------------------------- pandas-like helpers
  // resample to a regular month-start (or quarter-start) grid with the mean of each bucket; NaN where empty
  function resample(s, q = false) {
    if (!s) return null;
    const key = (t) => { const [y, m] = ymd(t); return q ? dn(y, Math.floor((m - 1) / 3) * 3 + 1, 1) : dn(y, m, 1); };
    const acc = new Map(); s.t.forEach((t, i) => { const k = key(t); const a = acc.get(k) || [0, 0]; a[0] += s.v[i]; a[1]++; acc.set(k, a); });
    const k0 = key(s.t[0]), k1 = key(lastT(s)), T = [], V = [];
    for (let k = k0; k <= k1; k = addMonths(k, q ? 3 : 1)) { T.push(k); const a = acc.get(k); V.push(a ? a[0] / a[1] : NaN); }
    return { t: T, v: V };
  }
  const resampleSum = (s) => { // resample("MS").sum(min_count=1)
    if (!s) return null; const acc = new Map(); s.t.forEach((t, i) => { const k = monthStart(t); acc.set(k, (acc.get(k) || 0) + s.v[i]); });
    const T = [], V = []; for (let k = monthStart(s.t[0]); k <= monthStart(lastT(s)); k = addMonths(k, 1)) { T.push(k); V.push(acc.has(k) ? acc.get(k) : NaN); } return { t: T, v: V };
  };
  const drop = (s) => (s ? dropna(s.t, s.v) : null);
  function rolling(v, w, mp, fn) { const out = new Array(v.length).fill(NaN); for (let i = 0; i < v.length; i++) { const win = []; for (let j = Math.max(0, i - w + 1); j <= i; j++) if (ok(v[j]) && Number.isFinite(v[j])) win.push(v[j]); if (win.length >= (mp ?? w) && win.length) out[i] = fn(win); } return out; }
  const rmean = (a) => a.reduce((x, y) => x + y, 0) / a.length, rsum = (a) => a.reduce((x, y) => x + y, 0), rmin = (a) => Math.min(...a);
  const shift = (v, k) => v.map((_, i) => (i - k >= 0 && i - k < v.length ? v[i - k] : NaN));
  function reindexFfill(s, T, limit = Infinity) { // s.reindex(T).ffill(limit)
    const at = new Map(s.t.map((t, i) => [t, s.v[i]])); const V = []; let lastV = NaN, gap = 0;
    for (const t of T) { const x = at.get(t); if (ok(x) && !Number.isNaN(x)) { lastV = x; gap = 0; V.push(x); } else { gap++; V.push(gap <= limit ? lastV : NaN); } }
    return { t: T, v: V };
  }
  function align(a, b, op) { // pandas a op b on the union index, NaN where either is missing
    if (!a || !b) return null; const B = new Map(b.t.map((t, i) => [t, b.v[i]])); const T = [], V = [];
    a.t.forEach((t, i) => { if (B.has(t)) { T.push(t); V.push(op(a.v[i], B.get(t))); } });
    return { t: T, v: V };
  }
  function valueAgo(s, days) { const j = ub(s.t, lastT(s) - days) - 1; return j >= 0 ? s.v[j] : null; }
  const pct = (a, b) => (!ok(a) || !ok(b) || b === 0 ? null : (a / b - 1) * 100);
  function spark(s, n = 24, q = false) { if (!s) return []; const r = drop(resample(s, q)); if (!r) return []; const k = Math.max(0, r.t.length - n); return r.t.slice(k).map((t, i) => [ym(t), r.v[k + i]]); }
  const yoyPos = (s, p) => { const v = s.v.map((x, i) => (i >= p ? (x / s.v[i - p] - 1) * 100 : NaN)); return dropna(s.t, v); };
  const ageMonths = (s, d) => (d - lastT(s)) / 30.4;

  // ---------------------------------------------------------------- blocks
  function annualAt(P, d) {
    const out = {}, H = {};
    const weoK = META.weo, wbK = META.wb, AK = META.annual_kind;
    for (const [iso3, rec] of Object.entries(P.annual)) {
      const h = (H[iso3] = {}), o = {};
      for (const [k, [y0, vals]] of Object.entries(rec)) {
        const T = [], V = [];
        vals.forEach((x, i) => { if (ok(x)) { T.push(dn(y0 + i, 7, 1)); V.push(x); } });
        if (!T.length) continue;
        const isW = k in weoK, rk = isW ? 'weo' : 'wb:' + (wbK[k] ? wbK[k][0] : k);
        const s = cut({ t: T, v: V }, rk, d); if (!s) continue;
        h[k] = s;
        const yr = ymd(lastT(s))[0];
        if (isW) o[k] = { label: weoK[k][0], unit: weoK[k][1], value: last(s), year: yr, source: 'IMF WEO', rel: 'weo', chg: change(s, AK[k] || 'pp', 'A'), estimate: yr >= ymd(d)[0] };
        else if (wbK[k]) { const j = ub(s.t, dn(yr - 10, 12, 31)) - 1; o[k] = { label: wbK[k][1], unit: wbK[k][2], value: last(s), year: yr, source: 'World Bank', estimate: false, rel: rk, chg: change(s, AK[k] || 'pct', 'A'), ten_years_ago: j >= 0 ? s.v[j] : null }; }
      }
      // World Bank stand-ins where WEO has no series for the country (as the daily run does)
      for (const [k, wk] of Object.entries(META.wb_fallback || { gov_debt: 'debt_wb' })) if (!o[k] && o[wk]) { o[k] = { ...o[wk], label: k === 'gov_debt' ? 'Government debt' : weoK[k] ? weoK[k][0] : o[wk].label }; h[k] = h[wk]; }
      if (Object.keys(o).length) out[iso3] = o;
    }
    return { allc: out, H };
  }

  function macroAt(P, d) {
    const out = {}, maxStale = META.max_stale, fresh = META.fresh;
    for (const [iso3, E] of Object.entries(P.macro)) {
      const e = { name: E.name, iso3, g20: E.g20, indicators: {}, pillars: {} }, series = {};
      for (const ind of ['gdp', 'inflation', 'unemployment', 'industry', 'long_rate', 'short_rate', 'exports_usd', 'imports_usd', 'share_prices']) {
        const cands = (E.ind[ind] || []).map((c) => ({ ...c, cs: cut(c.S, c.rk, d) }));
        let best = null;
        const p = cands.find((c) => c.o === 0);
        if (p && p.cs && ageMonths(p.cs, d) <= maxStale && (p.b == null || Math.abs(last(p.cs)) <= p.b)) best = p;
        if (!best || ageMonths(best.cs, d) > fresh) {
          for (const c of cands.filter((x) => x.o > 0)) {
            const s2 = c.cs; if (!s2) continue;
            const lim = c.annual ? 30 : maxStale;
            if (len(s2) < 3 || ageMonths(s2, d) > lim) continue;
            if (!best || (!c.annual && ageMonths(s2, d) < ageMonths(best.cs, d))) best = c;
            if (!c.annual && ageMonths(s2, d) <= fresh) break;
          }
        }
        if (best) {
          const s = best.cs, q = ind === 'gdp';
          series[ind] = best.annual ? null : s;
          e.indicators[ind] = { latest: last(s), date: iso(lastT(s)), annual: best.annual, year_ago: valueAgo(s, 335), source: best.lab, rel: best.rk,
            chg: change(s, META.ind_kind[ind], best.annual ? 'A' : null), spark: best.annual ? [] : spark(s, q ? 20 : 24, q) };
          if (ind === 'share_prices' && !best.annual) e.indicators[ind].pct10 = priceStats(s.v).pct10;
        }
      }
      const b = cut(E.BIS, 'bis', d);
      if (b && ageMonths(b, d) <= maxStale) {
        series.policy_rate = b;
        e.indicators.policy_rate = { latest: last(b), date: iso(lastT(b)), annual: false, year_ago: valueAgo(b, 335), source: 'BIS', rel: 'bis', chg: change(b, 'bp'), spark: spark(b, 24) };
      } else if (e.indicators.short_rate) { e.indicators.policy_rate = { ...e.indicators.short_rate, source: 'OECD (3-month rate)' }; series.policy_rate = series.short_rate; }
      const X = series.exports_usd, Mi = series.imports_usd;
      if (X && Mi) {
        const bal = drop(align(X, Mi, (a, c) => a - c));
        if (bal) {
          const rk = e.indicators.exports_usd.rel;
          e.indicators.trade_balance_usd = { latest: last(bal), date: iso(lastT(bal)), annual: false, year_ago: valueAgo(bal, 335), source: 'OECD', rel: rk, chg: change(bal, 'abs'), spark: spark(bal, 24) };
          const Xm = drop(resampleSum(X)), Mm = drop(resampleSum(Mi));
          const X12 = drop({ t: Xm.t, v: rolling(Xm.v, 12, 12, rsum) }), M12 = drop({ t: Mm.t, v: rolling(Mm.v, 12, 12, rsum) });
          const B12 = drop(align(X12, M12, (a, c) => a - c));
          const s12 = (s) => (s.v.length >= 12 ? s.v.slice(-12).reduce((a, c) => a + c, 0) : null);
          e.trade_m = { exports: last(X), imports: last(Mi), balance: last(bal), rel: rk,
            c: { exports: change(X, 'pct'), imports: change(Mi, 'pct'), balance: change(bal, 'abs'), exports_12m: change(X12, 'pct'), imports_12m: change(M12, 'pct'), balance_12m: change(B12, 'abs') },
            exports_yoy: pct(last(X), valueAgo(X, 335)), imports_yoy: pct(last(Mi), valueAgo(Mi, 335)), exports_12m: s12(X), imports_12m: s12(Mi), date: iso(lastT(X)) };
        }
      }
      e._series = series;
      out[iso3] = e;
    }
    return out;
  }

  function historySeries(e, full) {
    const S = e._series || {}, m = (k) => (S[k] ? resample(S[k]) : null);
    const pi = m('inflation'), u = m('unemployment'), i = m('policy_rate'), lr = m('long_rate'), X = m('exports_usd'), M = m('imports_usd'), g = S.gdp;
    const out = {};
    if (g) out.gdp = g;
    [['inflation', pi], ['unemployment', u], ['policy_rate', i], ['long_rate', lr]].forEach(([k, v]) => { if (v) out[k] = v; });
    if (i && pi) { const iff = reindexFfill(i, pi.t); out.real_rate = { t: pi.t, v: pi.v.map((x, j) => iff.v[j] - x) }; }
    if (pi && u) { const uf = reindexFfill(u, pi.t); out.misery = { t: pi.t, v: pi.v.map((x, j) => x + uf.v[j]) }; }
    if (lr && i) { const iff = reindexFfill(i, lr.t); out.curve = { t: lr.t, v: lr.v.map((x, j) => x - iff.v[j]) }; }
    if (u && pi) {
      const uu = drop(u);
      if (uu) {
        const ubar = rolling(uu.v, 120, 36, rmean), gap = uu.v.map((x, j) => -2 * (x - ubar[j]));
        const p_ = reindexFfill(pi, uu.t).v, taylor = gap.map((gp, j) => 0.5 + p_[j] + 0.5 * (p_[j] - 2) + 0.5 * gp);
        out.taylor = { t: uu.t, v: taylor }; out.output_gap = { t: uu.t, v: gap };
        if (i) { const iff = reindexFfill(i, uu.t).v; out.taylor_gap = { t: uu.t, v: taylor.map((x, j) => iff[j] - x) }; }
        const a3 = rolling(uu.v, 3, 3, rmean), mn = rolling(shift(a3, 1), 12, 12, rmin);
        out.sahm = { t: uu.t, v: a3.map((x, j) => x - mn[j]) };
      }
    }
    if (X && M) { const b = drop(align(X, M, (a, c) => a - c)); if (b) { out.trade_balance = b; out.trade_balance_12m = { t: b.t, v: rolling(b.v, 12, 12, rsum) }; } }
    const res = {};
    for (const [k, v] of Object.entries(out)) { const s = drop(v); if (s) res[k] = s; }
    if (full) return res;
    const ch = {};
    for (const [k, v] of Object.entries(res)) {
      if (k === 'taylor' || k === 'output_gap') continue;
      const k0 = lb(v.t, addMonths(lastT(v), -120)), t = v.t.slice(k0), vv = v.v.slice(k0);
      if (t.length >= 3) ch[k] = t.map((x, j) => [ym(x), vv[j]]);
    }
    return ch;
  }

  function derivedSeries(e, H) {
    const S = e._series || {}, out = {};
    const pi = S.inflation ? resample(S.inflation) : null, lr = S.long_rate ? resample(S.long_rate) : null, g = S.gdp;
    if (g && pi) {
      const gm = reindexFfill(resample(g), pi.t, 5);
      out.nominal_growth = drop({ t: pi.t, v: pi.v.map((x, j) => gm.v[j] + x) });
      if (lr && out.nominal_growth) {
        out.r_minus_g = drop(align(lr, out.nominal_growth, (a, b) => a - b));
        const byYear = (a) => { const at = new Map(a.t.map((t, j) => [ymd(t)[0], a.v[j]])); return { t: out.r_minus_g.t, v: out.r_minus_g.t.map((t) => (at.has(ymd(t)[0]) ? at.get(ymd(t)[0]) : NaN)) }; };
        if (out.r_minus_g && H.gov_debt) {
          const dm = byYear(H.gov_debt), ng = new Map(out.nominal_growth.t.map((t, j) => [t, out.nominal_growth.v[j]]));
          out.pb_stabilizing = drop({ t: dm.t, v: dm.t.map((t, j) => (out.r_minus_g.v[j] / (100 + (ng.has(t) ? ng.get(t) : NaN))) * dm.v[j]) });
          if (H.primary_balance && out.pb_stabilizing) out.fiscal_gap = drop(align(byYear(H.primary_balance), out.pb_stabilizing, (a, b) => a - b));
        }
      }
    }
    const inv = H.investment_weo || H.investment;
    if (H.savings && inv) out.s_minus_i = drop(align(H.savings, inv, (a, b) => a - b));
    if (H.current_account && H.gov_balance) out.twin = drop(align(H.current_account, H.gov_balance, (a, b) => a + b));
    if (H.exports_usd_a && H.imports_usd_a) out.trade_balance_usd = drop(align(H.exports_usd_a, H.imports_usd_a, (a, b) => a - b));
    for (const k of Object.keys(out)) if (!out[k]) delete out[k];
    return out;
  }

  function macroMath(e) {
    const I = e.indicators, m = {}, S = e._series;
    const g = (k) => (I[k] && !I[k].annual ? I[k].latest : null);
    const pi = g('inflation'), u = g('unemployment'), i = g('policy_rate'), lr = g('long_rate');
    if (ok(i) && ok(pi)) m.real_rate = i - pi;
    if (ok(pi) && ok(u)) m.misery = pi + u;
    if (ok(lr) && ok(i)) m.curve = lr - i;
    let us = S.unemployment;
    if (us && ok(pi) && len(us) >= 24) {
      us = drop(resample(us));
      const k0 = lb(us.t, addYears(lastT(us), -10)), ubar = rmean(us.v.slice(k0));
      const gap = -2 * (last(us) - ubar), taylor = 0.5 + pi + 0.5 * (pi - 2) + 0.5 * gap;
      m.output_gap = gap; m.taylor = taylor; if (ok(i)) m.taylor_gap = i - taylor;
      const a3 = drop({ t: us.t, v: rolling(us.v, 3, 3, rmean) });
      if (a3 && a3.v.length >= 13) m.sahm = last(a3) - Math.min(...a3.v.slice(-13, -1));
    }
    return m;
  }

  function derive(e, f) {
    const I = e.indicators, d = {};
    const X = f.exports_usd_a, M = f.imports_usd_a;
    if (X && M && X.year === M.year) d.trade_balance_usd = { value: X.value - M.value, year: X.year };
    const gr = !I.gdp?.annual ? I.gdp?.latest : f.gdp_growth?.value;
    const pi = I.inflation?.latest, r = I.long_rate?.latest;
    if (ok(gr) && ok(pi) && ok(r)) {
      const g = gr + pi; d.nominal_growth = g; d.r_minus_g = r - g;
      const debt = f.gov_debt?.value;
      if (ok(debt)) { d.pb_stabilizing = ((r - g) / (100 + g)) * debt; const pb = f.primary_balance?.value; if (ok(pb)) d.fiscal_gap = pb - d.pb_stabilizing; }
    }
    if (f.savings && (f.investment_weo || f.investment)) d.s_minus_i = f.savings.value - (f.investment_weo || f.investment).value;
    if (f.current_account && f.gov_balance) d.twin = f.current_account.value + f.gov_balance.value;
    return d;
  }

  // 12-month low/high of monthly averages and the latest price's percentile over the last 120 months (as run.py price_stats)
  function priceStats(v) {
    const w12 = v.slice(-12), w120 = v.slice(-120), x = v[v.length - 1];
    let lo = 0, eq = 0; for (const y of w120) { if (y < x) lo++; else if (y === x) eq++; }
    const pc = w120.length >= 24 ? Math.round(((lo + 0.5 * (eq - 1)) / (w120.length - 1)) * 1000) / 10 : null;
    return { lo12: Math.min(...w12), hi12: Math.max(...w12), pct10: pc };
  }
  function pricesAt(P, d) {
    const rows = [];
    for (const [, name, ship, unit] of META.commodities) {
      const s = cut(P.pink[name], 'pink', d); if (!s || len(s) < 13) continue;
      const B = (META.commodity_basis || {})[name] || ['', 'cash'];
      rows.push({ name, ship, level: last(s), date: iso(lastT(s)), unit, m1: pct(last(s), s.v[s.v.length - 2]), chg: change(s, 'pct'), rel: 'pink', yoy: pct(last(s), valueAgo(s, 360)), spark: spark(s, 24), ...priceStats(s.v), basis: B[0], kind: B[1] });
    }
    return rows;
  }

  function marketsAt(P, d) {
    const out = { fx: [], rates: [], us_fiscal: [], global_rates: [], fx_note: META.fx_note };
    const fx = P.fx;
    if (fx) {
      const usd = cut(col(fx, 'USD'), 'ecb', d);
      if (usd) {
        const ratio = (a, b, f) => drop(align(a, b, f));
        for (const c of ['EUR', ...META.fx.filter((x) => x !== 'USD')]) {
          let s_, pair, meaning; const base = META.fx_base_foreign.includes(c);
          if (c === 'EUR') { s_ = usd; pair = 'EUR/USD'; meaning = 'US dollars per 1 euro'; }
          else { const x = cut(col(fx, c), 'ecb', d); if (!x) continue; if (base) { s_ = ratio(usd, x, (a, b) => a / b); pair = `${c}/USD`; meaning = `US dollars per 1 ${META.fx_units[c] || c}`; } else { s_ = ratio(x, usd, (a, b) => a / b); pair = `USD/${c}`; meaning = `${META.fx_units[c] || c} per 1 US dollar`; } }
          if (!s_) continue;
          const lastV = last(s_), valueUsd = base || c === 'EUR' ? s_ : map(s_, (v) => 1 / v), strong = base || c === 'EUR' ? 1 : -1;
          const y1 = pct(lastV, valueAgo(s_, 365));
          out.fx.push({ name: META.fx_names[c] || c, code: c, pair, meaning, latest: lastV, date: iso(lastT(s_)), m1: pct(lastV, valueAgo(s_, 30)), y1, ccy_y1: ok(y1) ? strong * y1 : null, rel: 'ecb', chg: change(s_, 'pct'), ccy_chg: change(valueUsd, 'pct'), spark: spark(s_, 13), unit: '%' });
        }
      }
    }
    const rateRow = (name, s, rel) => { if (!s) return; const lv = last(s), a = valueAgo(s, 30), b = valueAgo(s, 365); out.rates.push({ name, latest: lv, date: iso(lastT(s)), unit: 'pp', rel, chg: change(s, 'bp'), m1: ok(a) ? lv - a : null, y1: ok(b) ? lv - b : null, spark: spark(s, 13) }); };
    rateRow('Fed funds (effective)', cut(P.effr, 'nyfed', d), 'nyfed');
    const yc = P.yc;
    if (yc) {
      const C = (k) => cut(col(yc, k), 'treasury', d);
      [['3 Mo', '3-month T-bill'], ['2 Yr', '2-year Treasury'], ['10 Yr', '10-year Treasury'], ['30 Yr', '30-year Treasury']].forEach(([c, n]) => { if (yc.c[c]) rateRow(n, C(c), 'treasury'); });
      const mats = ['1 Mo', '2 Mo', '3 Mo', '4 Mo', '6 Mo', '1 Yr', '2 Yr', '3 Yr', '5 Yr', '7 Yr', '10 Yr', '20 Yr', '30 Yr'].filter((c) => yc.c[c]);
      const rowsT = yc.t.map((t, j) => [t, mats.map((c) => yc.c[c][j])]).filter(([t, ys]) => t <= d - lagOf('treasury') && ys.some(ok));
      if (rowsT.length) {
        const [lastD, ys] = rowsT[rowsT.length - 1], nul = (a) => a.map((v) => (ok(v) ? v : null));
        const curve = { maturities: mats, today: { date: iso(lastD), y: nul(ys) }, past: {} };
        const ts = rowsT.map((r) => r[0]);
        for (const [per, m] of PER) {
          const tgt = addMonths(lastD, -m), j = ub(ts, tgt) - 1;
          if (j >= 0 && ts[j] >= tgt - 7) curve.past[per] = { date: iso(ts[j]), y: nul(rowsT[j][1]) };
          else curve.past[per] = { date: null, y: null, why: tgt < ts[0] ? 's' : 'g', start: iso(ts[0]) };
        }
        out.curve = curve;
      }
      if (yc.c['10 Yr'] && yc.c['2 Yr']) rateRow('Yield curve (10y − 2y)', drop(align(C('10 Yr'), C('2 Yr'), (a, b) => a - b)), 'treasury');
      const ry = cut(P.ry, 'treasury', d);
      if (ry) { rateRow('10-year real yield', ry, 'treasury'); rateRow('Inflation expected, next 10 years', drop(align(C('10 Yr'), ry, (a, b) => a - b)), 'treasury'); }
    }
    const debt = cut(P.debt, 'fiscaldata', d);
    if (debt) {
      const lv = last(debt);
      if (P.fy) {
        const rows = P.fy.filter(([, th]) => th + lagOf('mts') <= d), by = new Map();
        rows.forEach(([fy, th, rc, ou]) => { if (!by.has(fy) || by.get(fy)[1] < th) by.set(fy, [fy, th, rc, ou]); });
        const at = (n) => { const j = ub(debt.t, n) - 1; return j >= 0 ? [debt.t[j], debt.v[j]] : null; };
        const fyrows = [...by.values()].map(([f_, th, rc, ou]) => {
          const full = ymd(th)[1] === 9, end = dn(f_, 9, 30), de = at(end), ds = at(dn(f_ - 1, 9, 30));
          const r = { fy: f_, complete: full, through: iso(th), receipts: rc, outlays: ou, balance: rc - ou,
            debt_end: full && de && de[0] >= end - 7 ? de[1] : null, debt_start: ds && ds[0] >= dn(f_ - 1, 9, 23) ? ds[1] : null };
          if (ok(r.debt_end) && ok(r.debt_start)) r.debt_change = r.debt_end - r.debt_start;
          return r;
        });
        out.us_fy = fyrows.sort((a, b) => b.fy - a.fy).slice(0, 25);
      }
      const y = valueAgo(debt, 365);
      out.us_fiscal.push({ name: 'US federal debt (total)', latest: lv, date: iso(lastT(debt)), y1_abs: ok(y) ? lv - y : null, y1: pct(lv, y), rel: 'fiscaldata', chg: change(debt, 'pct') });
    }
    return out;
  }

  function portsAt(P, d) {
    if (!P) return null;
    const W = META.window, end = Math.min(d - META.asof.port_lag, P.end), a = end - (W - 1), pa = a - 364, pb = end - 364;
    if (end < P.first) return null;
    const asMap = (F, c) => { const m = new Map(); if (F && F.c[c]) F.t.forEach((t, i) => { if (t <= end && ok(F.c[c][i]) && !Number.isNaN(F.c[c][i])) m.set(t, F.c[c][i]); }); return m; };
    const wsum = (m, lo, hi) => { let s = 0, n = 0; for (let t = lo; t <= hi; t++) { const x = m.get(t); if (x !== undefined) { s += x; n++; } } return n ? s : null; };
    const ratio = (c, p) => (ok(c) && ok(p) && p !== 0 ? (c / p - 1) * 100 : null);
    const P_ = Object.keys(META.products), cols = [...P_, 'total', 'imports', 'exports', 'portcalls'];
    const regions = [], mix = [], pcR = {};
    for (const [r, F] of Object.entries(P.reg)) {
      const row = { region: r }, cur = {}, prv = {};
      cols.forEach((c) => { const m = asMap(F, c); cur[c] = wsum(m, a, end); prv[c] = wsum(m, pa, pb); row[c] = ratio(cur[c], prv[c]); });
      if (cols.every((c) => cur[c] === null)) continue;
      row.imports_t = cur.imports; row.exports_t = cur.exports; regions.push(row);
      const tp = P_.reduce((s, c) => s + (cur[c] || 0), 0); mix.push({ region: r, ...Object.fromEntries(P_.map((c) => [c, tp ? ((cur[c] || 0) / tp) * 100 : null])) });
      pcR[r] = Object.fromEntries(cols.map((c) => [c, windowChange(asMap(F, c), end, W, P.first)]));
    }
    const glob = {}, pcG = {};
    cols.forEach((c) => { const m = asMap(P.glob, c); glob[c] = ratio(wsum(m, a, end), wsum(m, pa, pb)); pcG[c] = windowChange(m, end, W, P.first); });
    const economies = {}, pcE = {};
    for (const [i, F] of Object.entries(P.eco)) { const m = asMap(F, 'total'); const v = ratio(wsum(m, a, end), wsum(m, pa, pb)); if (ok(v)) economies[i] = v; pcE[i] = windowChange(m, end, W, P.first); }
    const cps = [];
    for (const [cid, [cname, lon, lat]] of Object.entries(META.chokepoints)) {
      const F = P.cp[cid]; if (!F) continue;
      const m = asMap(F, 'n_total'); if (!m.size) continue;
      const cur = wsum(m, a, end), prv = wsum(m, pa, pb), mt = asMap(F, 'n_tanker'), mc = asMap(F, 'capacity');
      let n = 0, s = 0; for (let t = a; t <= end; t++) if (m.has(t)) { n++; s += m.get(t); }
      cps.push({ name: cname, lon, lat, chg: windowChange(m, end, W, F.t[0]), rel: 'portwatch', transits_yoy: ratio(cur, prv),
        tanker_yoy: F.c.n_tanker ? ratio(wsum(mt, a, end), wsum(mt, pa, pb)) : null, capacity_yoy: F.c.capacity ? ratio(wsum(mc, a, end), wsum(mc, pa, pb)) : null, daily_transits: n ? s / n : null });
    }
    return { window: [iso(a), iso(end)], regions, mix, global: glob, economies, weekly: { weeks: [], series: {} }, ports: [], pc: { global: pcG, regions: pcR, economies: pcE }, rel: 'portwatch', chokepoints: cps };
  }

  function powerAt(P, d) {
    const out = {};
    for (const [i3, S0] of Object.entries(P.ember)) {
      const s = cut(S0, 'ember', d); if (!s || len(s) < 27 || ageMonths(s, d) > 8) continue;
      const s3 = rolling(s.v, 3, 3, rsum), y = dropna(s.t, s3.map((x, j) => (j >= 12 ? (x / s3[j - 12] - 1) * 100 : NaN)));
      if (!y) continue;
      out[i3] = { twh: last(s), date: iso(lastT(s)), yoy_3m: last(y), rel: 'ember', chg: seasonalChange(s, 3), spark: spark(y, 24) };
    }
    return out;
  }

  function transportAt(P, d) {
    const rows = [], seen = new Set();
    for (const [name, field, S0] of P.bts) {
      if (seen.has(name)) continue;
      const s = cut(S0, 'bts', d); if (!s || len(s) < 13 || ageMonths(s, d) > 10) continue;
      seen.add(name);
      rows.push({ name, latest: last(s), date: iso(lastT(s)), rel: 'bts', chg: seasonalChange(s, 1), yoy: pct(last(s), valueAgo(s, 360)), spark: spark(s, 24), field, country: 'United States' });
    }
    return rows;
  }

  function freightAt(P, d) {
    const rows = [], add = (iso3, mode, S0, unit, q, rel) => {
      const s = cut(S0, rel, d); if (!s || len(s) < (q ? 12 : 27) || ageMonths(s, d) > (q ? 12 : 8)) return;
      let y;
      if (q) y = yoyPos(s, 4); else { const s3 = rolling(s.v, 3, 3, rsum); y = dropna(s.t, s3.map((x, j) => (j >= 12 ? (x / s3[j - 12] - 1) * 100 : NaN))); }
      if (!y) return;
      rows.push({ country: META.iso[iso3]?.[1] || iso3, iso3, mode, latest: last(s), unit, date: iso(lastT(s)), yoy: last(y), spark: spark(y, q ? 12 : 24), period: q ? 'quarter' : '3 months', rel, chg: seasonalChange(s, q ? 1 : 3) });
    };
    for (const [i3, s] of Object.entries(P.freight.air || {})) add(i3, 'Air freight', s, 'tonnes', false, 'eurostat:avia_gooc');
    for (const [i3, s] of Object.entries(P.freight.rail || {})) add(i3, 'Rail freight', s, 'thousand tonnes', true, 'eurostat:rail_go_quartal');
    if (P.freight.can) add('CAN', 'Rail carloadings', P.freight.can, 'tonnes', false, 'statcan');
    return rows;
  }

  // ---------------------------------------------------------------- rebuilt scores (pipeline/history.py)
  function rleAt(r, i) { if (!r || !r.length) return null; let lo = 0, hi = r.length; while (lo < hi) { const m = (lo + hi) >> 1; if (r[m][0] <= i) lo = m + 1; else hi = m; } return lo ? r[lo - 1][1] : null; }
  function rleSeries(r, day0, upTo) { // daily series of non-null values up to day index upTo
    const T = [], V = [];
    for (let j = 0; j < r.length; j++) {
      const [i0, v] = r[j], i1 = Math.min(j + 1 < r.length ? r[j + 1][0] - 1 : upTo, upTo);
      if (v === null || i0 > upTo) continue;
      for (let i = i0; i <= i1; i++) { T.push(day0 + i); V.push(v); }
    }
    return T.length ? { t: T, v: V } : null;
  }
  const label = (s) => (!ok(s) ? 'Pending' : s >= 60 ? 'Strong' : s >= 45 ? 'Steady' : s >= 35 ? 'Soft' : 'Stressed');
  const PNAME = { activity: 'Output', labor: 'Jobs', prices: 'Prices', trade: 'Trade' };

  const BANDW = { Strong: 'strong', Steady: 'steady', Soft: 'soft', Stressed: 'under stress' };
  const PWORD = { activity: 'output', labor: 'jobs', prices: 'prices', trade: 'trade' };
  function headline(world, econ, prices, ports) {
    if (!ok(world)) return 'Global economy: score pending.';
    const lab = label(world), out = `Global economy ${BANDW[lab] || lab.toLowerCase()} (${world.toFixed(0)}).`;
    const vol = ports?.global?.total, oil = prices.find((p) => p.name === 'Brent crude')?.yoy;
    if (ok(vol) && ok(oil) && vol < -2 && oil > 15) return out + ' Main driver: a supply shock, with goods moving less while oil prices rise.';
    const zs = {};
    for (const e of Object.values(econ)) { if (!ok(e.score)) continue; for (const [k, v] of Object.entries(e.pillars || {})) if (ok(v)) (zs[k] = zs[k] || []).push(v); }
    let bk = null, bm = 0;
    for (const [k, v] of Object.entries(zs)) { const m = v.reduce((a, b) => a + b, 0) / v.length; if (bk === null || Math.abs(m) > Math.abs(bm)) { bk = k; bm = m; } }
    if (bk !== null && Math.abs(bm) >= 0.1) return out + ` Main ${bm < 0 ? 'drag' : 'support'}: ${PWORD[bk] || bk}.`;
    return out;
  }
  function drivers(econ, prices, ports) {
    const out = [], dir = (v) => (v > 0 ? 'up' : 'down');
    if (ports) {
      [...ports.chokepoints].sort((a, b) => Math.abs(b.transits_yoy || 0) - Math.abs(a.transits_yoy || 0)).slice(0, 2).forEach((c) => { const v = c.transits_yoy; if (ok(v) && Math.abs(v) >= 15) out.push(`Ship traffic at ${c.name} is ${dir(v)} ${Math.abs(v).toFixed(0)}% on a year ago.`); });
      [...ports.regions].sort((a, b) => Math.abs(b.total || 0) - Math.abs(a.total || 0)).slice(0, 2).forEach((r) => { if (ok(r.total)) out.push(`${r.region} port cargo is ${dir(r.total)} ${Math.abs(r.total).toFixed(0)}% on a year ago.`); });
    }
    prices.filter((p) => ok(p.yoy)).sort((a, b) => Math.abs(b.yoy) - Math.abs(a.yoy)).slice(0, 3).forEach((p) => out.push(`${p.name} is ${dir(p.yoy)} ${Math.abs(p.yoy).toFixed(0)}% on a year ago.`));
    const sahm = Object.values(econ).filter((e) => (e.math?.sahm || 0) >= 0.5).map((e) => e.name);
    if (sahm.length) out.push('Sahm rule recession signal (unemployment rising fast): ' + sahm.join(', ') + '.');
    const sc = Object.values(econ).filter((e) => ok(e.score));
    if (sc.length >= 2) { const b = sc.reduce((x, y) => (y.score > x.score ? y : x)), w = sc.reduce((x, y) => (y.score < x.score ? y : x)); out.push(`Strongest: ${b.name} (${b.score.toFixed(0)}). Weakest: ${w.name} (${w.score.toFixed(0)}).`); }
    return out;
  }

  // ---------------------------------------------------------------- the whole site for day d
  function build(P, dStr, live) {
    META = P.meta;
    const d = parse(dStr), SC = P.scores, di = d - SC.day0;
    const { allc: annual, H: AH } = annualAt(P, d);
    const econ = macroAt(P, d), prices = pricesAt(P, d), markets = marketsAt(P, d), power = powerAt(P, d);
    const transport = transportAt(P, d), freight = freightAt(P, d), ports = portsAt(P.ports, d);
    const SER = {}, TRADE = {};
    const scoreS = (k) => (SC.c[k] ? rleSeries(SC.c[k].s, SC.day0, di) : null);
    for (const [k, e] of Object.entries(econ)) {
      const f = annual[k] || {};
      const p = SC.c[k]?.p || {};
      for (const pk of ['activity', 'labor', 'prices', 'trade']) { const v = rleAt(p[pk], di); e.pillars[pk] = ok(v) ? v : null; }
      if (ports && ok(ports.economies[k])) e.trade_yoy = ports.economies[k];
      const zs = Object.entries(e.pillars).filter(([, v]) => ok(v));
      const sv = rleAt(SC.c[k]?.s, di);
      e.score = ok(sv) && zs.length >= 2 ? sv : null;
      if (zs.length >= 2) e.contrib = Object.fromEntries(zs.map(([pk, v]) => [PNAME[pk], (15 * v) / zs.length]));
      e.label = label(e.score); e.coverage = `${zs.length}/4`;
      e.vitals = Object.fromEntries(META.vital_keys.filter((x) => f[x]).map((x) => [x, f[x]]));
      e.fundamentals = Object.fromEntries(Object.entries(f).filter(([x]) => !META.vital_keys.includes(x) && !(x.endsWith('_wb') && x !== 'debt_wb')));
      e.math = macroMath(e); e.derived = derive(e, e.fundamentals);
      SER[k] = historySeries(e, false);
      const tb = SER[k].trade_balance_12m; if (tb) (e.trade_m = e.trade_m || {}).balance_12m = tb[tb.length - 1][1];
      const full = historySeries(e, true);
      e.mchg = Object.fromEntries(Object.keys(META.math_kind).filter((mk) => full[mk]).map((mk) => [mk, change(full[mk], META.math_kind[mk], 'M')]));
      e.dchg = Object.fromEntries(Object.entries(derivedSeries(e, AH[k] || {})).map(([dk, v]) => [dk, change(v, META.math_kind[dk], ['s_minus_i', 'twin', 'trade_balance_usd'].includes(dk) ? 'A' : 'M')]));
      const X = e._series.exports_usd, M = e._series.imports_usd;
      if (X && M) TRADE[k] = [resampleSum(X), resampleSum(M)];
      delete e._series;
      if (power[k]) e.power = power[k];
      const hs = scoreS(k);
      e.score_chg = change(hs, 'pts', 'D');
      if (hs) { const k0 = lb(hs.t, addYears(d, -10)), pts = []; for (let j = hs.t.length - 1; j >= k0; j -= 7) pts.push([iso(hs.t[j]), hs.v[j]]); e.history = pts.reverse(); SER[k].score = e.history.map(([x, v]) => [x, Math.round(v * 10) / 10]); }
      else e.history = [];
    }
    // world
    const ws = rleAt(SC.w.s, di), avg = rleAt(SC.w.avg, di), stress = rleAt(SC.w.stress, di);
    const comps = Object.fromEntries(Object.entries(SC.w.comps || {}).map(([k, r]) => [k, rleAt(r, di)]).filter(([, v]) => ok(v)));
    for (const e of Object.values(econ)) {
      const I = e.indicators;
      if (I.policy_rate || I.long_rate || I.share_prices) {
        const sp = I.share_prices;
        markets.global_rates.push({ stocks: !sp || sp.annual ? null : { chg: sp.chg, spark: sp.spark, pct10: sp.pct10 ?? null, date: sp.date, rel: sp.rel }, name: e.name, iso3: e.iso3, policy: I.policy_rate?.latest ?? null, policy_src: I.policy_rate?.source, long: I.long_rate?.latest ?? null,
          real: ok(e.math.real_rate) ? e.math.real_rate : (ok(I.policy_rate?.latest) && ok(I.inflation?.latest) ? I.policy_rate.latest - I.inflation.latest : null),
          real_est: !ok(e.math.real_rate) && ok(I.policy_rate?.latest) && ok(I.inflation?.latest), curve: e.math.curve ?? null, rel: I.policy_rate?.rel, rel_long: I.long_rate?.rel,
          c: { policy: I.policy_rate?.chg, long: I.long_rate?.chg, real: e.mchg.real_rate, curve: e.mchg.curve },
          policy_y1: ok(I.policy_rate?.year_ago) ? I.policy_rate.latest - I.policy_rate.year_ago : null, date: (I.policy_rate || I.long_rate || {}).date });
      }
    }
    // map
    const mapRows = {};
    const isos = new Set([...Object.keys(annual), ...Object.keys(econ), ...Object.keys(ports?.economies || {}), ...Object.keys(power)]);
    for (const i3 of isos) {
      const c = META.iso[i3]; if (!c) continue;
      const f = annual[i3] || {}, row = { iso3: i3, name: c[1] };
      for (const k of ['gdp_growth', 'inflation_a', 'unemployment_a', 'gov_debt', 'current_account', 'gdp_usd', 'population', 'net_exports']) if (f[k]) row[k] = f[k].value;
      const e = econ[i3];
      if (!e) {
        const p = SC.c[i3]?.p || {}, zs = ['activity', 'labor', 'prices', 'trade'].map((k) => [k, rleAt(p[k], di)]).filter(([, v]) => ok(v));
        const sv = rleAt(SC.c[i3]?.s, di);
        if (zs.length >= 2 && ok(sv)) Object.assign(row, { score: sv, label: label(sv), basis: 'annual', contrib: Object.fromEntries(zs.map(([k, v]) => [PNAME[k], Math.round((1500 * v) / zs.length) / 100])) });
        else row.why = zs.map(([k]) => ({ activity: 'output', labor: 'jobs', prices: 'prices', trade: 'trade' }[k]));
      } else {
        Object.assign(row, { name: e.name, score: e.score, label: e.label, tracked: true });
        for (const k of ['inflation', 'unemployment', 'gdp']) { const x = e.indicators[k]; if (x && !x.annual) row[k] = x.latest; }
      }
      if (ports && ok(ports.economies[i3])) row.trade = ports.economies[i3];
      if (power[i3]) row.power = power[i3].yoy_3m;
      if (!('inflation' in row) && 'inflation_a' in row) row.inflation = row.inflation_a;
      if (!('unemployment' in row) && 'unemployment_a' in row) row.unemployment = row.unemployment_a;
      if (!('gdp' in row) && 'gdp_growth' in row) row.gdp = row.gdp_growth;
      const cc = {};
      for (const [disp, mon, ann] of [['gdp', 'gdp', 'gdp_growth'], ['inflation', 'inflation', 'inflation_a'], ['unemployment', 'unemployment', 'unemployment_a']]) {
        const x = e?.indicators?.[mon];
        if (x && !x.annual && row[disp] === x.latest) cc[disp] = x.chg; else if (f[ann]) cc[disp] = f[ann].chg;
      }
      for (const k of ['gov_debt', 'current_account', 'net_exports', 'gdp_usd']) if (f[k]) cc[k] = f[k].chg;
      if (power[i3]) cc.power = power[i3].chg;
      if (ports?.pc?.economies?.[i3]) cc.trade = ports.pc.economies[i3];
      if (ok(row.score)) cc.score = change(scoreS(i3), 'pts', 'D');
      row.c = cc;
      mapRows[String(c[0])] = row;
    }
    // trade totals
    let tradeTotals = null;
    const keys = Object.keys(TRADE);
    if (keys.length) {
      const sets = keys.map((k) => [new Map(TRADE[k][0].t.map((t, j) => [t, TRADE[k][0].v[j]])), new Map(TRADE[k][1].t.map((t, j) => [t, TRADE[k][1].v[j]]))]);
      const all = [...new Set(keys.flatMap((k) => TRADE[k][0].t))].sort((a, b) => a - b);
      const common = all.filter((t) => sets.every(([x, m]) => ok(x.get(t)) && !Number.isNaN(x.get(t)) && ok(m.get(t)) && !Number.isNaN(m.get(t))));
      if (common.length >= 2) {
        const Xt = { t: common, v: common.map((t) => sets.reduce((s, [x]) => s + x.get(t), 0)) }, Mt = { t: common, v: common.map((t) => sets.reduce((s, [, m]) => s + m.get(t), 0)) };
        const X12 = drop({ t: common, v: rolling(Xt.v, 12, 12, rsum) }), M12 = drop({ t: common, v: rolling(Mt.v, 12, 12, rsum) });
        const B = { t: common, v: Xt.v.map((x, j) => x - Mt.v[j]) };
        tradeTotals = { date: iso(common[common.length - 1]), n: keys.length, exports: last(Xt), imports: last(Mt), balance: last(Xt) - last(Mt),
          exports_12m: X12 ? last(X12) : null, imports_12m: M12 ? last(M12) : null,
          c: { exports: change(Xt, 'pct', 'M'), imports: change(Mt, 'pct', 'M'), balance: change(B, 'abs', 'M'), exports_12m: change(X12, 'pct', 'M'), imports_12m: change(M12, 'pct', 'M'), balance_12m: change(drop(align(X12, M12, (a, b) => a - b)), 'abs', 'M') } };
      }
    }
    // release metadata: every figure counts as released after its source's standard delay
    const rel = {};
    for (const [k, r] of Object.entries(META.rel || {})) rel[k] = { source: r.source, label: r.label, released: null, basis: k === 'weo' ? 'weo' : k.startsWith('wb:') ? 'wb' : 'lag', lag: lagOf(k) };
    const ecoList = Object.values(econ).sort((a, b) => (a.g20 === b.g20 ? (b.score ?? -1) - (a.score ?? -1) : a.g20 ? -1 : 1));
    const wscore = rleSeries(SC.w.s, SC.day0, di);
    const D = {
      generated_at: live?.generated_at, weo_release: live?.weo_release, asof_view: dStr, rebuilt: true,
      world: { score: ok(ws) ? ws : null, label: label(ws), headline: headline(ws, econ, prices, ports),
        breakdown: { 'economies (GDP-weighted)': avg, 'global stress': stress, stress_components: comps },
        trade_yoy: ports?.global?.total ?? null, countries: Object.keys(mapRows).length, tracked: ecoList.length,
        scored: Object.values(mapRows).filter((r) => ok(r.score)).length, chg: change(wscore, 'pts', 'D') },
      drivers: drivers(econ, prices, ports), economies: ecoList, map: mapRows, prices, markets, trade: ports,
      products: META.products, transport, freight, trade_totals: tradeTotals, periods: PER.map((p) => p[0]), rel,
      power, status: live?.status || META.status, asof: live?.asof || META.asof,
    };
    // year-by-year table data for the same day
    const names = Object.fromEntries(Object.values(mapRows).map((r) => [r.iso3, r.name]));
    const anData = {}; let y0 = Infinity, y1 = -Infinity;
    for (const [i3, H] of Object.entries(AH)) {
      if (!names[i3]) continue; const rec = {};
      for (const k of Object.keys(META.year_keys)) {
        const s = H[k]; if (!s) continue; const T = s.t.filter((t) => ymd(t)[0] >= 1980); if (!T.length) continue;
        const a0 = ymd(T[0])[0], a1 = ymd(T[T.length - 1])[0], by = new Map(s.t.map((t, j) => [ymd(t)[0], s.v[j]]));
        rec[k] = [a0, Array.from({ length: a1 - a0 + 1 }, (_, j) => (by.has(a0 + j) ? by.get(a0 + j) : null))];
        y0 = Math.min(y0, a0); y1 = Math.max(y1, a1);
      }
      if (Object.keys(rec).length) anData[i3] = rec;
    }
    const AN = { data: anData, keys: Object.fromEntries(Object.entries(META.year_keys).map(([k, v]) => [k, { label: v[0], unit: v[1], rel: v[2], kind: META.annual_kind[k] || 'pp' }])),
      names: Object.fromEntries(Object.keys(anData).map((i) => [i, names[i]])), g20: META.g20.filter((i) => anData[i]),
      years: y0 <= y1 ? [y0, y1] : null, estimate_from: ymd(d)[0], rel };
    return { D, SER, AN };
  }

  // annual values for any country (readouts for countries without a score)
  function countryAt(P, dStr, iso3) { META = P.meta; const { allc } = annualAt({ annual: { [iso3]: P.annual[iso3] || {} } }, parse(dStr)); return allc[iso3] || {}; }

  async function loadPacks(base = 'data/packs/') {
    const names = ['meta', 'macro', 'annual', 'markets', 'ports', 'other', 'scores'];
    const got = await Promise.all(names.map((n) => fetch(base + n + '.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).catch(() => null)));
    const [meta, macro, annual, mk, ports, other, scores] = got;
    if (!meta || !macro || !annual || !scores) throw new Error('past-date data not available');
    for (const e of Object.values(macro)) { e.BIS = dec(e.bis); for (const cs of Object.values(e.ind)) cs.forEach((c) => { c.S = dec(c.s); }); }
    const P = { meta, macro, annual, scores,
      fx: decFrame(mk?.fx), yc: decFrame(mk?.yc), ry: dec(mk?.ry), effr: dec(mk?.effr), debt: dec(mk?.debt), fy: mk?.fy || null,
      ports: ports ? { first: ports.first, end: ports.end, glob: decFrame(ports.glob), reg: Object.fromEntries(Object.entries(ports.reg).map(([k, v]) => [k, decFrame(v)])),
        eco: Object.fromEntries(Object.entries(ports.eco).map(([k, v]) => [k, decFrame(v)])), cp: Object.fromEntries(Object.entries(ports.cp).map(([k, v]) => [k, decFrame(v)])) } : null,
      pink: Object.fromEntries(Object.entries(other?.pink || {}).map(([k, v]) => [k, dec(v)])),
      ember: Object.fromEntries(Object.entries(other?.ember || {}).map(([k, v]) => [k, dec(v)])),
      bts: (other?.bts || []).map(([n, c, s]) => [n, c, dec(s)]),
      freight: { air: Object.fromEntries(Object.entries(other?.freight?.air || {}).map(([k, v]) => [k, dec(v)])), rail: Object.fromEntries(Object.entries(other?.freight?.rail || {}).map(([k, v]) => [k, dec(v)])), can: dec(other?.freight?.can) } };
    return P;
  }

  window.WELEngine = { build, loadPacks, countryAt, change, seasonalChange, windowChange, addMonths, dn, iso, parse, ymd, periodEnd, lagOf: (k) => lagOf(k), setMeta: (m) => { META = m; } };
})();
