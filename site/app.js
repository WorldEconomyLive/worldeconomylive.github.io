(async function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ok = (v) => v !== null && v !== undefined && !Number.isNaN(v);
  const num = (v, d = 1) => (ok(v) ? Number(v).toFixed(d) : '—');
  const sg = (v, d = 1, suf = '%') => { if (!ok(v)) return '—'; const a = Math.abs(v).toFixed(d), z = +a === 0; return (z ? '' : v > 0 ? '+' : '−') + a + suf; };
  const cls = (v, goodUp = true) => (!ok(v) || v === 0 ? '' : (v > 0) === goodUp ? 'pos' : 'neg');
  const big = (v) => !ok(v) ? '—' : Math.abs(v) >= 1e12 ? (v / 1e12).toFixed(2) + 'tn' : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(1) + 'bn' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'm' : Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : num(v);
  const usd = (v) => !ok(v) ? '—' : (v < 0 ? '−$' : '$') + big(Math.abs(v));
  const bn = (v) => !ok(v) ? '—' : (v < 0 ? '−$' : '$') + Math.abs(v).toFixed(1) + 'bn';
  const sd = (v) => ok(v) ? `<span class="sd">${v >= 0 ? 'surplus' : 'deficit'}</span>` : '';
  const POS = [62, 230, 196], NEG = [255, 77, 109], MID = [28, 31, 36];
  function div(v, cap) {
    if (!ok(v)) return '#111317';
    const t = Math.max(-1, Math.min(1, v / cap)), e = t < 0 ? NEG : POS, a = Math.abs(t);
    return `rgb(${MID.map((m, i) => Math.round(m + (e[i] - m) * a))})`;
  }
  function seq(v, lo, hi, col = POS) {
    if (!ok(v)) return '#111317';
    const a = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    return `rgb(${MID.map((m, i) => Math.round(m + (col[i] - m) * a))})`;
  }
  function spark(pts, w = 120, h = 26, color = '#a7abb3') {
    if (!pts || pts.length < 3) return '';
    const v = pts.map((p) => p[1]), mn = Math.min(...v), mx = Math.max(...v);
    const xy = v.map((y, i) => `${((i / (v.length - 1)) * w).toFixed(1)},${(h - ((y - mn) / (mx - mn || 1)) * (h - 4) - 2).toFixed(1)}`).join(' ');
    return `<svg class="spk" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${color}" stroke-width="1.3" points="${xy}"/></svg>`;
  }
  function bar(v, color, cap = 60, label) {
    if (!ok(v)) return `<div class="trk"><div class="ax"></div><span class="val na" style="left:52%">n/a</span></div>`;
    const w = (Math.min(Math.abs(v), cap) / cap) * 50, l = v < 0 ? 50 - w : 50, pos = v < 0 ? `right:${50 + w + 1}%` : `left:${50 + w + 1}%`;
    return `<div class="trk"><div class="ax"></div><div class="bar-f" style="left:${l}%;width:${w}%;background:${color}"></div><span class="val" style="${pos}">${label ?? sg(v, 0)}${Math.abs(v) > cap ? '›' : ''}</span></div>`;
  }
  const table = (head, rows) => `<table><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;

  // ---------------- comparison period ----------------
  const PERS = ['1M', '3M', '6M', '1Y', '3Y', '5Y', '10Y', '15Y', '20Y'];
  const PWORD = ['1 month', '3 months', '6 months', '1 year', '3 years', '5 years', '10 years', '15 years', '20 years'];
  let PI = 3;
  try { const s = localStorage.getItem('wel-period'); if (PERS.includes(s)) PI = PERS.indexOf(s); } catch (_) { /* storage unavailable */ }
  const FREQ = { D: 'daily', W: 'weekly', M: 'monthly', Q: 'quarterly', A: 'annual' };
  // change text for the selected period. o = change object from the pipeline.
  function ctext(o, abs) {
    const v = o?.v?.[PI];
    if (!ok(v)) return null;
    switch (o.k) {
      case 'pts': return sg(v, Math.abs(v) < 10 ? 1 : 0, ' pts');
      case 'bp': return sg(v, 0, ' bp');
      case 'pp': return sg(v, Math.abs(v) < 1 ? 2 : 1, ' pp');
      case 'pct': return sg(v, 1, '%') + (PI >= 4 ? ' per year' : '');
      default: return abs ? abs(v) : sg(v, 1, '');
    }
  }
  function ctitle(o) {
    const t = [];
    if (o?.a?.[PI] === '1') t.push(`Latest 12-month average vs the 12-month average ${PWORD[PI]} earlier`);
    else t.push(`Change over ${PWORD[PI]}`);
    if (o?.k === 'pct' && PI >= 4) t.push('compound annual rate');
    return t.join(' · ');
  }
  // good: 1 = rise is good, -1 = rise is bad, 0 = neutral
  function chg(o, good = 0, abs) {
    if (!o) return '';
    const t = ctext(o, abs);
    if (t === null) return '<span class="chg na">n/a</span>';
    const v = o.v[PI];
    return `<span class="chg ${good ? cls(v, good > 0) : ''}" title="${esc(ctitle(o))}">${t}</span>`;
  }
  // annual sections: 1Y and longer only, whatever the underlying frequency
  const A1 = (o) => (!o ? o : { ...o, v: o.v.map((x, i) => (i < 3 ? null : x)), r: o.r.split('').map((c, i) => (i < 3 ? 'f' : c)).join(''), f: 'A' });
  const absBn = (v) => (v < 0 ? '−' : '+') + '$' + Math.abs(v).toFixed(1) + 'bn';
  const absUsd = (v) => (v < 0 ? '−' : '+') + '$' + big(Math.abs(v));
  const absPeople = (v) => (v < 0 ? '−' : '+') + big(Math.abs(v));

  // ---------------- footnotes: latest period, publication date, source, n/a reasons ----------------
  const MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const mdy = (s) => { const d = String(s || '').slice(0, 10).split('-'); return d.length === 3 ? `${d[1]}/${d[2]}/${d[0]}` : String(s || ''); };
  function plab(s, f) {
    const d = String(s || '').slice(0, 10).split('-').map(Number);
    if (d.length < 2 || !d[0]) return String(s || '');
    if (f === 'A') return String(d[0]);
    if (f === 'Q') return `Q${Math.floor((d[1] - 1) / 3) + 1} ${d[0]}`;
    if (f === 'D' || f === 'W') return mdy(s);
    return `${MON[d[1] - 1]} ${d[0]}`;
  }
  function foot(word = 'Latest') {
    const rel = new Map(), items = [];
    return {
      rel(key, date, f, what, fallback) {
        if (!date) return;
        const k = key || fallback || 'other';
        if (!rel.has(k)) rel.set(k, { dates: [], f, what: new Set(), fallback });
        const r = rel.get(k); r.dates.push(String(date).slice(0, 10)); if (what) r.what.add(what); if (!r.f) r.f = f;
      },
      add(name, o) { if (o) items.push([name, o]); },
      html() {
        const lines = [], merged = new Map();
        for (const [k, r] of rel) {
          if (k === 'site') { lines.push(`${esc([...r.what].join(', '))} — last computed ${mdy(r.dates.sort().pop())} by this site from the sources listed in this note and in Method.`); continue; }
          const R = (D.rel || {})[k] || {}, ds = r.dates.sort(), lo = plab(ds[0], r.f), hi = plab(ds[ds.length - 1], r.f);
          const when = R.released ? `released ${mdy(R.released)}${R.basis === 'daily' ? ' (published daily)' : ''}` : 'release date not published by source';
          const src = (R.source || r.fallback || k) + (R.label ? `, ${R.label}` : '');
          const key = [lo, hi, when, src].join('|');
          if (!merged.has(key)) merged.set(key, { what: new Set(), lo, hi, when, src });
          r.what.forEach((w) => merged.get(key).what.add(w));
        }
        for (const m of merged.values()) lines.push(`${m.what.size ? esc([...m.what].join(', ')) + ' — ' : ''}${word}: ${esc(m.lo === m.hi ? m.hi : m.lo + ' to ' + m.hi)} · ${esc(m.when)} · source: ${esc(m.src)}`);
        const by = { s: new Map(), f: [], g: [], x: [], z: [] };
        let avg = false, perYear = false;
        for (const [n, o] of items) {
          const r = o.r?.[PI];
          if (o.a?.[PI] === '1') avg = true;
          if (o.k === 'pct' && PI >= 4 && ok(o.v?.[PI])) perYear = true;
          if (r === 's') { const k = o.s || 'n/a'; if (!by.s.has(k)) by.s.set(k, []); by.s.get(k).push(n); }
          else if (r === 'f') by.f.push(n + (o.f ? ` (${FREQ[o.f]})` : ''));
          else if (r === 'g') by.g.push(n); else if (r === 'x') by.x.push(n); else if (r === 'z') by.z.push(n);
        }
        const names = (a) => { const u = [...new Set(a)]; return esc(u.slice(0, 4).join(', ')) + (u.length > 4 ? ` and ${u.length - 4} more` : ''); };
        const na = [];
        for (const [start, ns] of [...by.s].sort()) na.push(start === 'n/a' ? `no history yet: ${names(ns)}` : `history begins ${esc(start)}: ${names(ns)}`);
        if (by.f.length) na.push(`too infrequent for ${PERS[PI]}: ${names(by.f)}`);
        if (by.g.length) na.push(`comparison point missing at source: ${names(by.g)}`);
        if (by.x.length) na.push(`percent change not meaningful (value at or below zero): ${names(by.x)}`);
        if (by.z.length) na.push(`seasonal series (not seasonally adjusted) only compare the same window 1 year or more earlier: ${names(by.z)}`);
        const notes = [];
        if (na.length) notes.push(`n/a for ${PERS[PI]} — ${na.join('; ')}.`);
        if (avg) notes.push(`${PERS[PI]} compares the latest 12-month average with the 12-month average ${PWORD[PI]} earlier.`);
        if (perYear) notes.push('Percent changes over 3 years or more are compound annual rates ("per year").');
        return `<div class="foot">${lines.map((l) => `<p>${l}</p>`).join('')}${notes.map((l) => `<p class="fn">${l}</p>`).join('')}</div>`;
      },
    };
  }

  let D;
  try { D = await (await fetch('data/heartbeat.json', { cache: 'no-store' })).json(); }
  catch (e) { $('headline').textContent = 'Data not available yet. The first daily run will create it.'; return; }
  const E = D.economies || [], T = D.trade, M = D.markets || {};
  $('upd').textContent = 'UPDATED ' + (D.generated_at || '');
  $('gen').textContent = 'LAST UPDATE ' + (D.generated_at || '');
  const mapName = (iso) => Object.values(D.map || {}).find((r) => r.iso3 === iso)?.name || iso;

  // ---------------- map ----------------
  const LAYERS = {
    score: { get: (r) => r.score, c: 'score', color: (v) => div(ok(v) ? v - 50 : null, 25), legend: ['Stressed', 'Normal', 'Strong'], ramp: [div(-25, 25), div(0, 25), div(25, 25)] },
    gdp: { get: (r) => r.gdp, c: 'gdp', color: (v) => div(v, 6), legend: ['−6%', '0', '+6%'], ramp: [div(-6, 6), div(0, 6), div(6, 6)] },
    inflation: { get: (r) => r.inflation, c: 'inflation', color: (v) => seq(v, 0, 8, NEG), legend: ['0%', '', '8%+'], ramp: [seq(0, 0, 8, NEG), seq(8, 0, 8, NEG)] },
    unemployment: { get: (r) => r.unemployment, c: 'unemployment', color: (v) => seq(v, 2, 10, NEG), legend: ['2%', '', '10%+'], ramp: [seq(2, 2, 10, NEG), seq(10, 2, 10, NEG)] },
    debt: { get: (r) => r.gov_debt, c: 'gov_debt', color: (v) => seq(v, 0, 150, NEG), legend: ['0%', '', '150%+ of GDP'], ramp: [seq(0, 0, 150, NEG), seq(150, 0, 150, NEG)] },
    ca: { get: (r) => r.current_account, c: 'current_account', color: (v) => div(v, 8), legend: ['Deficit', '0', 'Surplus'], ramp: [div(-8, 8), div(0, 8), div(8, 8)] },
    tb: { get: (r) => r.net_exports, c: 'net_exports', color: (v) => div(v, 10), legend: ['Deficit', '0', 'Surplus'], ramp: [div(-10, 10), div(0, 10), div(10, 10)] },
    // these two layers are themselves changes, so they follow the period toggle
    power: { get: (r) => r.power, c: 'power', color: (v) => div(v, 8), legend: ['−8%', '0', '+8% power use'], ramp: [div(-8, 8), div(0, 8), div(8, 8)] },
    trade: { get: (r) => r.trade, c: 'trade', color: (v) => div(v, 30), legend: ['−30%', '0', '+30%'], ramp: [div(-30, 30), div(0, 30), div(30, 30)] },
  };
  const LAYER_SRC = { score: 'Score', gdp: 'GDP growth', inflation: 'Inflation', unemployment: 'Unemployment', debt: 'Government debt', ca: 'Current account', tb: 'Trade balance', power: 'Electricity demand', trade: 'Port cargo' };
  let layer = 'score', paths, cpG, proj;
  const tip = $('tip');
  function showTip(ev, html) { const r = $('map').getBoundingClientRect(); tip.innerHTML = html; tip.style.opacity = 1; tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 260) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px'; }
  const hideTip = () => { tip.style.opacity = 0; };
  function mapFoot() {
    const L = LAYERS[layer], F = foot();
    for (const r of Object.values(D.map || {})) {
      const o = r.c?.[L.c]; if (!o) continue;
      F.add(r.name, o);
      if (layer === 'score') continue;
      const e = E.find((x) => x.iso3 === r.iso3);
      if (layer === 'power') F.rel('ember', D.power?.[r.iso3]?.date, 'M', '', 'Ember');
      else if (layer === 'trade') F.rel('portwatch', T?.window?.[1], 'D', '', 'IMF PortWatch');
      else if (o.f === 'A') F.rel(L.c === 'net_exports' ? 'wb:NE.RSB.GNFS.ZS' : 'weo', null, 'A');
      else if (e) { const x = e.indicators?.[L.c]; if (x) F.rel(x.rel, x.date, o.f, '', x.source); }
    }
    if (layer !== 'score' && layer !== 'power' && layer !== 'trade') {
      const yrs = Object.values(D.map || {}).map((r) => r.c?.[L.c]).filter((o) => o?.f === 'A').length;
      if (yrs) { const anyK = layer === 'tb' ? 'wb:NE.RSB.GNFS.ZS' : 'weo'; F.rel(anyK, `${new Date().getUTCFullYear()}-07-01`, 'A', 'Annual estimates', layer === 'tb' ? 'World Bank' : 'IMF WEO'); }
    }
    if (layer === 'score') F.rel('site', D.generated_at, 'D', 'Scores (computed by this site from the series below)', 'World Economy Live');
    $('f-map').innerHTML = `<p class="fl">MAP COLORS · ${esc(LAYER_SRC[layer].toUpperCase())} (CURRENT VALUES) · TOOLTIP CHANGES OVER ${PERS[PI]}</p>` + F.html();
  }
  function paint() {
    const L = LAYERS[layer], lg = typeof L.legend === 'function' ? L.legend() : L.legend;
    if (paths) paths.attr('fill', (d) => { const r = D.map?.[String(+d.id)]; return r ? L.color(L.get(r)) : '#0d0f12'; });
    $('legend').innerHTML = `<span>${lg[0]}</span><span class="ramp" style="background:linear-gradient(90deg,${L.ramp.join(',')})"></span><span>${lg[2]}</span>${layer === 'power' || layer === 'trade' ? '<span class="na">· vs a year ago</span>' : ''}`;
    document.querySelectorAll('#layers button').forEach((b) => b.classList.toggle('on', b.dataset.l === layer));
    mapFoot();
  }
  document.querySelectorAll('#layers button').forEach((b) => b.addEventListener('click', () => { layer = b.dataset.l; paint(); }));
  const tipLine = (lab, val, o, good, abs) => `<br>${lab} ${val}${o ? ' <span class="tc">' + (ctext(o, abs) ?? 'n/a') + '</span>' : ''}`;
  try {
    const world = await (await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json')).json();
    const feats = topojson.feature(world, world.objects.countries).features.filter((f) => f.properties.name !== 'Antarctica');
    const el = $('globe'), W = el.clientWidth, H = el.clientHeight;
    proj = d3.geoNaturalEarth1().fitExtent([[10, 50], [W - 10, H - 30]], { type: 'FeatureCollection', features: feats });
    const path = d3.geoPath(proj);
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    svg.append('path').datum(d3.geoGraticule10()).attr('class', 'graticule').attr('d', path);
    const hl = svg.append('path').attr('class', 'hl');
    paths = svg.insert('g', '.hl').selectAll('path').data(feats).join('path').attr('class', 'country').attr('d', path)
      .on('mouseenter', (ev, d) => hl.attr('d', path(d)).style('opacity', 1))
      .on('mousemove', (ev, d) => {
        const r = D.map?.[String(+d.id)], c = r?.c || {};
        let h = `<b>${esc(r?.name || d.properties.name)}</b>${r ? `<span class="tc"> · change over ${PERS[PI]}</span>` : ''}`;
        if (r) {
          if (ok(r.score)) h += tipLine('Score', `${num(r.score, 0)} · ${esc(r.label)}`, c.score);
          if (ok(r.gdp)) h += tipLine('GDP growth', sg(r.gdp), c.gdp);
          if (ok(r.inflation)) h += tipLine('Inflation', num(r.inflation) + '%', c.inflation);
          if (ok(r.unemployment)) h += tipLine('Unemployment', num(r.unemployment) + '%', c.unemployment);
          if (ok(r.gov_debt)) h += tipLine('Gov. debt', num(r.gov_debt, 0) + '% of GDP', c.gov_debt);
          if (ok(r.current_account)) h += tipLine('Current account', sg(r.current_account) + ' of GDP', c.current_account);
          if (ok(r.net_exports)) h += tipLine(`Trade ${r.net_exports >= 0 ? 'surplus' : 'deficit'}`, num(Math.abs(r.net_exports), 1) + '% of GDP', c.net_exports);
          if (ok(r.gdp_usd)) h += tipLine('GDP', usd(r.gdp_usd), c.gdp_usd);
          if (c.trade) h += `<br>Port cargo <span class="tc">${ctext(c.trade) ?? 'n/a'}</span>`;
          if (c.power) h += `<br>Power use <span class="tc">${ctext(c.power) ?? 'n/a'}</span>`;
          if (!r.tracked) h += `<br><span style="color:#5f646d">${r.basis === 'annual' ? 'score from IMF annual estimates' + (c.trade || c.power ? ' + live port/power data' : '') : 'annual data (IMF/World Bank)'}</span>`;
        } else h += '<br><span style="color:#5f646d">not tracked yet</span>';
        showTip(ev, h);
      })
      .on('mouseleave', () => { hideTip(); hl.style('opacity', 0); })
      .on('click', (ev, d) => { const r = D.map?.[String(+d.id)]; const i = E.findIndex((e) => e.iso3 === r?.iso3); if (i >= 0) { filt = 'all'; renderGrid(); openDetail(i); } });
    const cps = (T?.chokepoints || []).filter((c) => ok(c.lon));
    cpG = svg.append('g');
    cps.forEach((c) => {
      const [x, y] = proj([c.lon, c.lat]), r = 2.5 + Math.min(6, Math.sqrt(c.daily_transits || 1) / 2);
      const col = div(c.transits_yoy, 40);
      cpG.append('circle').attr('class', 'cpring').attr('cx', x).attr('cy', y).attr('r', 3).attr('stroke', col);
      cpG.append('circle').attr('class', 'cp').attr('cx', x).attr('cy', y).attr('r', r).attr('fill', col)
        .on('mousemove', (ev) => showTip(ev, `<b>${esc(c.name)}</b><br>${num(c.daily_transits, 0)} ships/day<br>${sg(c.transits_yoy, 0)} vs a year ago${PI !== 3 ? `<br><span class="tc">${ctext(c.chg) ?? 'n/a'} over ${PERS[PI]}</span>` : ''}`)).on('mouseleave', hideTip);
    });
  } catch (e) { $('globe').innerHTML = '<p class="sub" style="padding:120px 30px;text-align:right">Map unavailable.</p>'; }

  // ---------------- economies (grid + detail) ----------------
  const PIL = { activity: 'ACT', labor: 'JOBS', prices: 'PRICE', trade: 'TRADE' };
  let filt = 'g20', q = '', openIdx = null;
  function card(e, i) {
    return `<button class="eco" data-i="${i}"><div class="n">${esc(e.name)}</div>
    <div class="s">${ok(e.score) ? Math.round(e.score) : '—'}</div><div class="cc">${chg(e.score_chg, 1) || '<span class="chg na">n/a</span>'}</div><span class="pill ${esc(e.label)}">${esc(e.label)}</span>
    <div class="chips">${Object.entries(PIL).map(([k, l]) => { const z = e.pillars?.[k]; const c = !ok(z) ? 'var(--mute)' : z > 0.5 ? 'var(--pos)' : z < -0.5 ? 'var(--neg)' : 'var(--ink2)'; return `<span class="chip" style="color:${c}">${l} ${!ok(z) ? '·' : z > 0.5 ? '▲' : z < -0.5 ? '▼' : '●'}</span>`; }).join('')}</div></button>`;
  }
  function renderGrid() {
    const list = E.map((e, i) => [e, i]).filter(([e]) => (filt === 'all' || e.g20 || q) && (!q || e.name.toLowerCase().includes(q)));
    $('econ').innerHTML = list.map(([e, i]) => card(e, i)).join('') || '<p class="sub" style="padding:16px;background:#000">No match.</p>';
    document.querySelectorAll('.eco').forEach((b) => { b.classList.toggle('on', +b.dataset.i === openIdx); b.addEventListener('click', () => openDetail(+b.dataset.i)); });
    document.querySelectorAll('#economies .filters button').forEach((b) => b.classList.toggle('on', b.dataset.f === filt));
    const F = foot();
    list.forEach(([e]) => F.add(e.name, e.score_chg));
    F.rel('site', D.generated_at, 'D', 'Scores (computed by this site daily)', 'World Economy Live');
    $('f-econ').innerHTML = F.html();
  }
  document.querySelectorAll('#economies .filters button').forEach((b) => b.addEventListener('click', () => { filt = b.dataset.f; renderGrid(); }));
  $('q').addEventListener('input', (ev) => { q = ev.target.value.trim().toLowerCase(); renderGrid(); });
  const IND = {
    gdp: ['GDP growth', (x) => sg(x.latest), 1], inflation: ['Inflation', (x) => num(x.latest) + '%', -1],
    unemployment: ['Unemployment', (x) => num(x.latest) + '%', -1], industry: ['Factory output', (x) => sg(x.latest), 1],
    policy_rate: ['Central bank rate', (x) => num(x.latest, 2) + '%', 0], long_rate: ['10-year bond yield', (x) => num(x.latest, 2) + '%', 0],
    exports_usd: ['Goods exports (month)', (x) => usd(x.latest * 1e9), 1], imports_usd: ['Goods imports (month)', (x) => usd(x.latest * 1e9), 0],
    trade_balance_usd: ['Goods trade balance (month)', (x) => usd(Math.abs(x.latest) * 1e9) + (x.latest >= 0 ? ' surplus' : ' deficit'), 1],
  };
  function plain(e) {
    const I = e.indicators || {}, s = [];
    if (I.gdp) s.push(`The economy is ${I.gdp.latest >= 0 ? 'growing' : 'shrinking'} ${Math.abs(I.gdp.latest).toFixed(1)}% a year.`);
    if (I.inflation) s.push(`Prices are rising ${num(I.inflation.latest)}% a year${ok(I.inflation.year_ago) ? (I.inflation.latest > I.inflation.year_ago ? ', faster than a year ago' : ', slower than a year ago') : ''}.`);
    if (I.unemployment) s.push(`${num(I.unemployment.latest)}% of people who want work can't find it.`);
    if (I.industry) s.push(`Factories are making ${Math.abs(I.industry.latest).toFixed(1)}% ${I.industry.latest >= 0 ? 'more' : 'less'} than a year ago.`);
    if (ok(e.trade_yoy)) s.push(`Cargo through its main ports is ${e.trade_yoy >= 0 ? 'up' : 'down'} ${Math.abs(e.trade_yoy).toFixed(0)}% on last year.`);
    if (ok(e.math?.sahm) && e.math.sahm >= 0.5) s.push('Unemployment is rising fast enough to flash a recession signal.');
    return s.join(' ');
  }
  const fact = (k, val, m, extra = '') => `<li><div class="k">${esc(k)}</div><b>${val}</b>${extra}<div class="m">${m}</div></li>`;
  function openDetail(i) {
    showDetail(i);
    const cardEl = document.querySelector(`.eco[data-i="${i}"]`);
    const back = () => (cardEl || $('economies')).scrollIntoView({ behavior: 'smooth', block: 'center' });
    $('dback')?.addEventListener('click', back);
    $('dclose')?.addEventListener('click', () => { openIdx = null; $('detail').innerHTML = ''; document.querySelectorAll('.eco').forEach((b) => b.classList.remove('on')); back(); });
    requestAnimationFrame(() => $('detail').scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }
  function showDetail(i) {
    openIdx = i;
    document.querySelectorAll('.eco').forEach((b) => b.classList.toggle('on', +b.dataset.i === i));
    const e = E[i], I = e.indicators || {}, Fd = e.fundamentals || {}, V = e.vitals || {}, d = e.derived || {}, m = e.math || {}, F = foot();
    const live = Object.entries(IND).filter(([k]) => I[k]).map(([k, [lab, f, good]]) => {
      F.rel(I[k].rel, I[k].date, I[k].chg?.f, lab, I[k].source);
      return fact(lab, f(I[k]), `${I[k].annual ? String(I[k].date).slice(0, 4) + ' · ANNUAL' : esc(I[k].date)} · ${esc(I[k].source)}${ok(I[k].year_ago) && !I[k].annual ? ' · YEAR AGO ' + num(I[k].year_ago) : ''}`, spark(I[k].spark));
    }).join('') + (e.power ? (F.rel('ember', e.power.date, 'M', 'Electricity demand', 'Ember'),
      fact('Electricity demand', sg(e.power.yoy_3m), `3 MONTHS Y/Y · ${esc(String(e.power.date).slice(0, 7))} · EMBER`, spark(e.power.spark))) : '');
    const gov = [['gov_debt', 'Government debt', -1], ['gov_balance', 'Budget balance', 1], ['primary_balance', 'Primary balance', 1], ['current_account', 'Current account', 0], ['revenue', 'Revenue', 0], ['spending', 'Spending', 0]]
      .filter(([k]) => Fd[k]).map(([k, l]) => { F.rel(Fd[k].rel, `${Fd[k].year}-07-01`, 'A', l, Fd[k].source);
        return fact(l, sg(Fd[k].value, 1, '%').replace(/^\+/, k === 'gov_debt' || k === 'revenue' || k === 'spending' ? '' : '+'), `OF GDP · ${Fd[k].year}${Fd[k].estimate ? ' EST' : ''} · ${esc(Fd[k].source)}`); }).join('')
      + (d.trade_balance_usd ? fact('Trade balance (X − M)', usd(Math.abs(d.trade_balance_usd.value)) + (d.trade_balance_usd.value >= 0 ? ' surplus' : ' deficit'), `${d.trade_balance_usd.year} · WORLD BANK`) : '')
      + (Fd.gdp_usd ? fact('GDP', usd(Fd.gdp_usd.value), `${Fd.gdp_usd.year} · ${esc(Fd.gdp_usd.source)}`) : '')
      + (ok(d.r_minus_g) ? fact('r − g', sg(d.r_minus_g, 1, ' pp'), d.r_minus_g > 0 ? 'DEBT GROWS FASTER THAN GDP' : 'GROWTH ERODES DEBT') : '');
    const mth = [['real_rate', 'Real interest rate', (v) => sg(v, 2, '%')], ['misery', 'Misery index', (v) => num(v)], ['taylor', 'Taylor rule rate', (v) => num(v, 2) + '%'], ['taylor_gap', 'Taylor gap', (v) => sg(v, 2, ' pp')], ['sahm', 'Sahm rule', (v) => num(v, 2)], ['curve', 'Yield curve (10y − policy)', (v) => sg(v, 2, ' pp')], ['output_gap', 'Output gap (Okun)', (v) => sg(v, 1)]]
      .filter(([k]) => ok(m[k])).map(([k, l, f]) => fact(l, f(m[k]), k === 'sahm' ? (m[k] >= 0.5 ? 'RECESSION SIGNAL' : 'NO SIGNAL (NEEDS 0.5)') : '')).join('');
    const vit = [['population', 0], ['life_exp', 1], ['age65', 0], ['fertility', 0], ['health_spend', 0], ['net_migration', 0], ['urban', 0], ['gdp_pc', 1], ['gini', -1]].filter(([k]) => V[k])
      .map(([k]) => { F.rel(V[k].rel, `${V[k].year}-07-01`, 'A', V[k].label, 'World Bank');
        return fact(V[k].label, big(V[k].value) + (V[k].unit.startsWith('%') ? '%' : ''), `${esc(V[k].unit).toUpperCase()} · ${V[k].year}${ok(V[k].ten_years_ago) ? ' · 10Y AGO ' + big(V[k].ten_years_ago) : ''}`); }).join('');
    F.add('Score', e.score_chg);
    $('detail').innerHTML = `<div class="detail"><div class="dtop"><button class="back" id="dback">← All economies</button><button class="back" id="dclose" aria-label="Close">✕</button></div><h3>${esc(e.name)}</h3><div class="score" style="font-size:56px">${ok(e.score) ? Math.round(e.score) : '—'}<small>/100</small></div>
      <div class="cc big">${chg(e.score_chg, 1) || ''} <span class="na mono small">over ${PERS[PI]}</span></div>
      <span class="pill ${esc(e.label)}">${esc(e.label)}</span><span class="mono small" style="margin-left:10px">${esc(e.coverage || '')} PILLARS</span>
      <p class="plain">${esc(plain(e)) || 'Detailed data fills in after the first automated run.'}</p>
      ${e.contrib ? `<h3>What moved the score (points vs 50)</h3><div class="bars contrib">${Object.entries(e.contrib).map(([k, v]) => `<div class="row"><div>${esc(k)}</div>${bar(v, v < 0 ? 'var(--neg)' : 'var(--pos)', 25, sg(v, 0, ''))}</div>`).join('')}</div>` : ''}
      ${live ? `<h3>Live indicators</h3><ul class="facts">${live}</ul>` : ''}${mth ? `<h3>Formulas</h3><ul class="facts">${mth}</ul>` : ''}
      ${gov ? `<h3>Government and trade</h3><ul class="facts">${gov}</ul>` : ''}${vit ? `<h3>People and health</h3><ul class="facts">${vit}</ul>` : ''}${F.html()}
      <div class="dyr"><h3>Year by year</h3><select id="dysel" aria-label="Calendar year"></select></div><ul class="facts" id="dyfacts"></ul><div id="dyfoot"></div></div>`;
    detailYear(e.iso3);
  }
  async function detailYear(iso) {
    await loadAnnual();
    if (!AN.years || !$('dysel')) return;
    if (YEAR === null) YEAR = AN.estimate_from - 1;
    const sel = $('dysel');
    for (let y = AN.years[1]; y >= AN.years[0]; y--) sel.insertAdjacentHTML('beforeend', `<option value="${y}">${y}${y >= AN.estimate_from ? ' (est.)' : ''}</option>`);
    sel.value = String(YEAR);
    sel.addEventListener('change', () => { YEAR = +sel.value; detailYear(iso); renderYears(); });
    const star = YEAR >= AN.estimate_from ? '*' : '';
    const items = YCOLS.map(([k, l, f]) => { const v = anVal(iso, k, YEAR); return ok(v) ? fact(l, f(v) + (AN.keys[k]?.rel === 'weo' ? star : ''), `${YEAR} · ${AN.keys[k]?.rel === 'weo' ? 'IMF WEO' : 'WORLD BANK'}`) : ''; }).join('');
    $('dyfacts').innerHTML = items || `<li><div class="m">No annual data published for ${YEAR}.</div></li>`;
    $('dyfoot').innerHTML = yearFoot(YEAR, [iso]);
  }

  // ---------------- scorecard history chart (unchanged by the toggle) ----------------
  const I_ = (e, k) => e.indicators?.[k]?.latest;
  const IC = (e, k) => e.indicators?.[k]?.chg;
  const COLS = [['score', 'Score', ''], ['gdp', 'GDP growth', '%'], ['inflation', 'Inflation', '%'], ['unemployment', 'Jobless', '%'], ['policy_rate', 'Policy rate', '%'],
    ['real_rate', 'Real rate', '%'], ['misery', 'Misery', ''], ['taylor_gap', 'Taylor gap', 'pp'], ['sahm', 'Sahm', 'pp'], ['curve', '10y − policy', 'pp'], ['trade_balance_12m', 'Trade bal. 12m', '$bn']];
  let SER = null, scIso = null, scCol = 'gdp';
  async function showHist(iso) {
    scIso = iso;
    document.querySelectorAll('#scoretbl tbody tr').forEach((r) => r.classList.toggle('sel', r.dataset.iso === iso));
    if (!SER) { try { SER = await (await fetch('data/series.json', { cache: 'no-store' })).json(); } catch (_) { SER = {}; } }
    const e = E.find((x) => x.iso3 === iso), H = SER[iso] || {};
    const avail = COLS.filter(([k]) => (H[k] || []).length >= 3);
    if (!avail.find(([k]) => k === scCol) && avail.length) scCol = avail[0][0];
    const box = $('schart');
    box.innerHTML = `<div class="hchart"><h3>${esc(e?.name || iso)}</h3><div class="toggles">${avail.map(([k, n]) => `<button data-c="${k}" class="${k === scCol ? 'on' : ''}">${n}</button>`).join('') || '<span class="sub">No history yet for this economy.</span>'}</div><div id="hplot"></div><p class="sub small" id="hnote"></p></div>`;
    box.querySelectorAll('.toggles button').forEach((b) => b.addEventListener('click', () => { scCol = b.dataset.c; showHist(scIso); }));
    const pts = (H[scCol] || []).map(([dd, v]) => [new Date(dd.length === 7 ? dd + '-01' : dd), v]);
    if (!pts.length) return;
    const W = Math.min($('hplot').clientWidth || 800, 1100), Hh = 240, mg = { l: 48, r: 14, t: 10, b: 24 };
    const x = d3.scaleTime().domain(d3.extent(pts, (p) => p[0])).range([mg.l, W - mg.r]);
    const ext = d3.extent(pts, (p) => p[1]), lo = Math.min(ext[0], 0), hi = Math.max(ext[1], 0), pad = (hi - lo) * 0.08 || 1;
    const y = d3.scaleLinear().domain([lo - pad, hi + pad]).nice().range([Hh - mg.b, mg.t]);
    const svg = d3.select('#hplot').append('svg').attr('width', W).attr('height', Hh);
    svg.append('g').attr('transform', `translate(0,${Hh - mg.b})`).call(d3.axisBottom(x).ticks(6).tickSize(0)).call((g) => g.select('.domain').attr('stroke', '#2a2e35'));
    svg.append('g').attr('transform', `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(W - mg.l - mg.r))).call((g) => { g.select('.domain').remove(); g.selectAll('line').attr('stroke', '#16191e'); });
    svg.append('line').attr('x1', mg.l).attr('x2', W - mg.r).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', '#3a3f47');
    svg.append('path').datum(pts).attr('fill', 'none').attr('stroke', 'var(--pos)').attr('stroke-width', 1.6).attr('d', d3.line().x((p) => x(p[0])).y((p) => y(p[1])));
    const last = pts[pts.length - 1], col = COLS.find(([k]) => k === scCol);
    svg.append('circle').attr('cx', x(last[0])).attr('cy', y(last[1])).attr('r', 3).attr('fill', 'var(--pos)');
    const unit = col[2] === '%' ? '%' : col[2] === '$bn' ? ' bn US$' : col[2] === 'pp' ? ' pp' : '';
    $('hnote').textContent = `${col[1]}: latest ${num(last[1], 2)}${unit} (${pts[pts.length - 1][0].toISOString().slice(0, 7)}). `
      + (scCol === 'trade_balance_12m' ? 'Goods exports minus imports over the past 12 months; above zero is a surplus, below is a deficit. ' : '')
      + (scCol === 'score' ? 'Score history builds up one point per day from launch. ' : '') + 'Sources and release dates: see the note under the table.';
  }

  // ---------------- everything that follows the period toggle ----------------
  const v1 = (val, o, good = 0, abs) => `${val}${chg(o, good, abs)}`;
  function renderAll() {
    $('perlabel').textContent = `Changes shown over ${PWORD[PI]}`;
    document.querySelectorAll('#period button').forEach((b) => b.classList.toggle('on', +b.dataset.p === PI));

    // hero
    const w = D.world || {};
    $('wscore').textContent = ok(w.score) ? Math.round(w.score) : '—';

    $('wlabel').textContent = w.label || 'Pending'; $('wlabel').className = 'pill ' + (w.label || '');
    $('headline').textContent = w.headline || '';
    const bd = w.breakdown || {};
    if (ok(bd['economies (GDP-weighted)'])) $('breakdown').textContent = `ECONOMIES ${Math.round(bd['economies (GDP-weighted)'])} · GLOBAL STRESS ${ok(bd['global stress']) ? Math.round(bd['global stress']) : '—'}`;
    if (w.tracked) $('coverage').textContent = `${w.scored || w.tracked} COUNTRIES SCORED · ${w.tracked} IN DEPTH · ${w.countries} ON THE MAP`;
    paint();

    // ticker (not period-driven)
    const tk = [];
    (D.prices || []).filter((p) => ['Brent crude', 'Gold', 'Copper', 'Wheat', 'Asia LNG'].includes(p.name)).forEach((p) => tk.push(`<span>${esc(p.name.toUpperCase())}<b>${num(p.level, 2)}</b><em class="${cls(p.yoy)}">${sg(p.yoy, 0)} y/y</em></span>`));
    (M.fx || []).filter((f) => ['EUR', 'JPY', 'CNY', 'GBP'].includes(f.code)).forEach((f) => tk.push(`<span>${esc(f.pair)}<b>${num(f.latest, f.latest < 10 ? 4 : 2)}</b><em class="${cls(f.y1)}">${sg(f.y1, 1)} y/y</em></span>`));
    (M.rates || []).filter((r) => /10-year Treasury|Fed funds/.test(r.name)).forEach((r) => tk.push(`<span>${esc(r.name.toUpperCase())}<b>${num(r.latest, 2)}%</b></span>`));
    if (ok(w.trade_yoy)) tk.push(`<span>GLOBAL PORT CARGO<b>${sg(w.trade_yoy, 1)}</b>y/y</span>`);
    $('ticker').innerHTML = tk.length ? tk.join('') + tk.join('') : '<span>Markets fill in on the first automated run.</span>';

    // what changed (not period-driven: a summary of recent changes)
    {
      $('drivers').innerHTML = (D.drivers || []).map((x) => `<li>${esc(x)}</li>`).join('') || '<li>Waiting for the first data run.</li>';
      const F = foot();
      (D.prices || []).forEach((p) => F.rel(p.rel, p.date, 'M', 'Commodity prices', 'World Bank Pink Sheet'));
      if (T?.window) F.rel('portwatch', T.window[1], 'D', 'Ships and port cargo', 'IMF PortWatch');
      E.forEach((e) => { const x = e.indicators?.unemployment; if (x) F.rel(x.rel, x.date, x.chg?.f, 'Unemployment (Sahm rule)', x.source); });
      F.rel('site', D.generated_at, 'D', 'Scores', 'World Economy Live');
      $('f-changes').innerHTML = F.html();
    }

    renderGrid();
    if (openIdx !== null) showDetail(openIdx);

    // scorecard
    {
      const F = foot();
      $('scoretbl').innerHTML = table(['Economy', 'Score', 'GDP', 'Inflation', 'Jobless', 'Policy rate', 'Real rate', 'Misery', 'Taylor gap', 'Sahm', '10y − policy', 'Trade bal. 12m'],
        E.map((e) => {
          const mc = e.mchg || {};
          [['Score', e.score_chg], ['GDP', IC(e, 'gdp')], ['Inflation', IC(e, 'inflation')], ['Jobless', IC(e, 'unemployment')], ['Policy rate', IC(e, 'policy_rate')], ['Real rate', mc.real_rate],
            ['Misery', mc.misery], ['Taylor gap', mc.taylor_gap], ['Sahm', mc.sahm], ['10y − policy', mc.curve], ['Trade balance', e.trade_m?.c?.balance_12m]].forEach(([n, o]) => F.add(`${e.name} ${n.toLowerCase()}`, o));
          ['gdp', 'inflation', 'unemployment', 'policy_rate', 'long_rate', 'exports_usd'].forEach((k) => { const x = e.indicators?.[k]; if (x) F.rel(x.rel, x.date, x.chg?.f, { gdp: 'GDP', inflation: 'Inflation', unemployment: 'Jobless', policy_rate: 'Policy rates', long_rate: '10-year yields', exports_usd: 'Trade' }[k], x.source); });
          return `<tr data-iso="${esc(e.iso3)}"><td>${esc(e.name)}</td><td>${v1(ok(e.score) ? Math.round(e.score) : '—', e.score_chg, 1)}</td><td class="${cls(I_(e, 'gdp'))}">${v1(sg(I_(e, 'gdp')), IC(e, 'gdp'), 1)}</td>
          <td>${v1(num(I_(e, 'inflation')) + '%', IC(e, 'inflation'), -1)}</td><td>${v1(num(I_(e, 'unemployment')) + '%', IC(e, 'unemployment'), -1)}</td>
          <td>${v1(num(I_(e, 'policy_rate'), 2), IC(e, 'policy_rate'))}</td><td>${v1(sg(e.math?.real_rate, 2, ''), mc.real_rate)}</td><td>${v1(num(e.math?.misery), mc.misery, -1)}</td><td>${v1(sg(e.math?.taylor_gap, 2, ''), mc.taylor_gap)}</td>
          <td class="${ok(e.math?.sahm) && e.math.sahm >= 0.5 ? 'neg' : ''}">${v1(num(e.math?.sahm, 2), mc.sahm, -1)}</td><td class="${cls(e.math?.curve)}">${v1(sg(e.math?.curve, 2, ''), mc.curve)}</td>
          <td class="${cls(e.trade_m?.balance_12m)}">${ok(e.trade_m?.balance_12m) ? v1(bn(Math.abs(e.trade_m.balance_12m)) + sd(e.trade_m.balance_12m), e.trade_m?.c?.balance_12m, 1, absBn) : '—'}</td></tr>`;
        }));
      F.rel('site', D.generated_at, 'D', 'Scores and formulas (computed by this site)', 'World Economy Live');
      $('f-scorecard').innerHTML = F.html();
      document.querySelectorAll('#scoretbl tbody tr').forEach((r) => { r.classList.toggle('sel', r.dataset.iso === scIso); r.addEventListener('click', () => { showHist(r.dataset.iso); $('schart').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }); });
    }

    // fundamentals, composition, debt math
    {
      const F_ = (e, k) => e.fundamentals?.[k];
      const F = foot();
      const fv = (e, k, signed, good = 0) => { const x = F_(e, k); if (!x) return '—'; F.add(`${e.name} ${x.label.toLowerCase()}`, A1(x.chg)); F.rel(x.rel, `${x.year}-07-01`, 'A', x.label + (x.estimate ? ' (estimate *)' : ''), x.source); return v1(`${signed ? sg(x.value, 1, '') : num(x.value, 0)}${x.estimate ? '*' : ''}`, A1(x.chg), good); };
      const fu = (e, k, good = 0) => { const x = F_(e, k); if (!x) return '—'; F.add(`${e.name} ${x.label.toLowerCase()}`, A1(x.chg)); F.rel(x.rel, `${x.year}-07-01`, 'A', x.label + (x.estimate ? ' (estimate *)' : ''), x.source); return v1(usd(x.value), A1(x.chg), good); };
      $('fund').innerHTML = table(['Economy', 'GDP', 'Debt % GDP', 'Budget bal.', 'Primary bal.', 'Current acct', 'Exports', 'Imports', 'Trade bal.', 'Twin bal.', 'FX reserves'],
        E.map((e) => { const tb = e.derived?.trade_balance_usd?.value; F.add(`${e.name} trade balance`, A1(e.dchg?.trade_balance_usd)); F.add(`${e.name} twin balance`, A1(e.dchg?.twin));
          return `<tr><td>${esc(e.name)}</td><td>${fu(e, 'gdp_usd', 1)}</td><td>${fv(e, 'gov_debt', 0, -1)}</td><td class="${cls(F_(e, 'gov_balance')?.value)}">${fv(e, 'gov_balance', 1, 1)}</td>
          <td class="${cls(F_(e, 'primary_balance')?.value)}">${fv(e, 'primary_balance', 1, 1)}</td><td class="${cls(F_(e, 'current_account')?.value)}">${fv(e, 'current_account', 1)}</td>
          <td>${fu(e, 'exports_usd_a', 1)}</td><td>${fu(e, 'imports_usd_a')}</td><td class="${cls(tb)}">${ok(tb) ? v1(usd(Math.abs(tb)) + sd(tb), A1(e.dchg?.trade_balance_usd), 1, absUsd) : '—'}</td>
          <td class="${cls(e.derived?.twin)}">${v1(sg(e.derived?.twin, 1, ''), A1(e.dchg?.twin), 1)}</td><td>${fu(e, 'reserves_usd')}</td></tr>`; }));
      $('f-fund').innerHTML = F.html();

      const G = foot();
      const comp = E.filter((e) => F_(e, 'consumption') && F_(e, 'investment') && F_(e, 'gov_consumption'));
      $('comp').innerHTML = comp.length ? `<div class="bars">${comp.map((e) => {
        const c = F_(e, 'consumption').value, i = F_(e, 'investment').value, g = F_(e, 'gov_consumption').value, nx = F_(e, 'net_exports')?.value ?? 100 - c - i - g;
        ['consumption', 'investment', 'gov_consumption', 'net_exports'].forEach((k) => { const x = F_(e, k); if (x) { G.add(`${e.name} ${x.label}`, A1(x.chg)); G.rel(x.rel, `${x.year}-07-01`, 'A', x.label, 'World Bank'); } });
        const ch = (k, l) => `${l} ${ctext(A1(F_(e, k)?.chg)) ?? 'n/a'}`;
        const parts = [[c, 'var(--c1)', 'C'], [i, 'var(--c2)', 'I'], [g, 'var(--c3)', 'G'], [Math.max(nx, 0), 'var(--c4)', 'NX']], tot = parts.reduce((a, p) => a + p[0], 0);
        return `<div class="row"><div>${esc(e.name)}<div class="m">${F_(e, 'consumption').year} · NX ${sg(nx, 1)}</div><div class="m">${[ch('consumption', 'C'), ch('investment', 'I'), ch('gov_consumption', 'G'), ch('net_exports', 'NX')].join(' · ')}</div></div><div class="stack">${parts.filter((p) => p[0] > 0).map(([v, col, l]) => `<span style="width:${(v / tot) * 100}%;background:${col}" title="${l} ${num(v)}%">${v / tot > 0.09 ? l + ' ' + Math.round(v) : ''}</span>`).join('')}</div></div>`;
      }).join('')}</div>` : '<p class="sub">Fills in on the first automated run.</p>';
      $('f-comp').innerHTML = G.html();

      const H = foot();
      const dm = E.filter((e) => ok(e.derived?.r_minus_g));
      $('debtmath').innerHTML = dm.length ? table(['Economy', '10y yield (r)', 'Nominal growth (g)', 'r − g', 'Debt % GDP', 'Primary bal. needed', 'Actual primary bal.', 'Debt ratio'],
        dm.map((e) => { const d = e.derived, pb0 = F_(e, 'primary_balance'), pb = pb0 && { ...pb0, chg: A1(pb0.chg) }, dc = Object.fromEntries(Object.entries(e.dchg || {}).map(([k, o]) => [k, A1(o)])), lr0 = e.indicators?.long_rate, lr = lr0 && { ...lr0, chg: A1(lr0.chg) };
          [['10y yield', lr?.chg], ['nominal growth', dc.nominal_growth], ['r − g', dc.r_minus_g], ['debt', A1(F_(e, 'gov_debt')?.chg)], ['primary balance needed', dc.pb_stabilizing], ['primary balance', pb?.chg]].forEach(([n, o]) => H.add(`${e.name} ${n}`, o));
          if (lr) H.rel(lr.rel, lr.date, lr.chg?.f, '10-year yields', lr.source);
          if (F_(e, 'gov_debt')) H.rel(F_(e, 'gov_debt').rel, `${F_(e, 'gov_debt').year}-07-01`, 'A', 'Debt and primary balance', F_(e, 'gov_debt').source);
          return `<tr><td>${esc(e.name)}</td><td>${v1(num(I_(e, 'long_rate'), 2) + '%', lr?.chg)}</td><td>${v1(num(d.nominal_growth) + '%', dc.nominal_growth)}</td><td class="${cls(d.r_minus_g, false)}">${v1(sg(d.r_minus_g, 1, ' pp'), dc.r_minus_g, -1)}</td><td>${v1(num(F_(e, 'gov_debt')?.value, 0) + '%', A1(F_(e, 'gov_debt')?.chg), -1)}</td>
            <td>${v1(sg(d.pb_stabilizing, 1), dc.pb_stabilizing)}</td><td>${v1(sg(pb?.value, 1), pb?.chg, 1)}</td><td>${!ok(d.fiscal_gap) ? '—' : d.fiscal_gap >= 0 ? '<span class="pill Strong">Falling</span>' : '<span class="pill Stressed">Rising</span>'}</td></tr>`; }))
        : '<p class="sub" style="padding:14px">Needs bond yields, growth and inflation. Fills in on the first automated run.</p>';
      $('f-debtmath').innerHTML = H.html();
    }

    // trade: ports heat map, import/export bars, chokepoints
    if (T?.regions) {
      $('tradesub').textContent = `Cargo (metric tons) through each region's busiest ports: the 28 days to ${T.window[1]} vs the same 28 days ${PI < 3 ? 'a year or more earlier (seasonal data: choose 1Y or longer)' : PWORD[PI] + ' earlier' + (PI >= 4 ? ', shown per year' : '')}.`;
      const P = Object.keys(D.products || {}), Hd = { tanker: 'Oil & gas', container: 'Goods', dry_bulk: 'Ores & grain', general_cargo: 'Steel', roro: 'Vehicles', total: 'Total' };
      const pcR = T.pc?.regions || {}, F = foot();
      const val = (r, k) => (r === 'ALL TRACKED PORTS' ? T.pc?.global?.[k] : pcR[r]?.[k])?.v?.[PI];
      const rows = T.regions.map((r) => r.region).sort((a, b) => (val(a, 'total') ?? 0) - (val(b, 'total') ?? 0));
      rows.push('ALL TRACKED PORTS');
      rows.forEach((r) => [...P, 'total'].forEach((k) => F.add(`${r} ${Hd[k].toLowerCase()}`, r === 'ALL TRACKED PORTS' ? T.pc?.global?.[k] : pcR[r]?.[k])));
      F.rel(T.rel || 'portwatch', T.window[1], 'D', '', 'IMF PortWatch');
      $('heat').innerHTML = `<table class="hm"><thead><tr><th>Region</th>${[...P, 'total'].map((k) => `<th style="text-align:center">${Hd[k]}</th>`).join('')}</tr></thead><tbody>` +
        rows.map((r) => `<tr><td>${esc(r)}</td>${[...P, 'total'].map((k) => { const v = val(r, k); return `<td class="c" style="background:${div(v, PI >= 4 ? 12 : 40)};color:${ok(v) && Math.abs(v) > (PI >= 4 ? 7 : 22) ? '#000' : ok(v) ? 'var(--ink)' : 'var(--mute)'}">${ok(v) ? sg(v, 0, '') : 'n/a'}</td>`; }).join('')}</tr>`).join('') + '</tbody></table>';
      $('f-heat').innerHTML = F.html();
      const G = foot();
      $('impexp').innerHTML = [...T.regions].sort((a, b) => (a.region > b.region ? 1 : -1)).map((r) => { G.add(`${r.region} imports`, pcR[r.region]?.imports); G.add(`${r.region} exports`, pcR[r.region]?.exports);
        return `<div class="row"><div>${esc(r.region)}<div class="m">IMPORTS / EXPORTS · SAME 28 DAYS ${PI < 3 ? '—' : PERS[PI] + ' EARLIER'}</div></div><div>${bar(pcR[r.region]?.imports?.v?.[PI], 'var(--c1)', PI >= 4 ? 15 : 60)}${bar(pcR[r.region]?.exports?.v?.[PI], 'var(--c4)', PI >= 4 ? 15 : 60)}</div></div>`; }).join('')
        + '<div class="legend-row mono" style="margin-top:10px"><i style="background:var(--c1)"></i>Imports <i style="background:var(--c4)"></i>Exports</div>';
      G.rel('portwatch', T.window[1], 'D', '', 'IMF PortWatch');
      $('f-impexp').innerHTML = G.html();
      const Hf = foot();
      $('choke').innerHTML = [...(T.chokepoints || [])].sort((a, b) => (a.chg?.v?.[PI] ?? 0) - (b.chg?.v?.[PI] ?? 0)).map((c) => { Hf.add(c.name, c.chg);
        const v = c.chg?.v?.[PI];
        return `<div class="row"><div>${esc(c.name)}<div class="m">${num(c.daily_transits, 0)} SHIPS/DAY</div></div>${bar(v, (v ?? 0) < 0 ? 'var(--neg)' : 'var(--pos)', PI >= 4 ? 15 : 60, ok(v) ? ctext(c.chg) : undefined)}</div>`; }).join('');
      Hf.rel('portwatch', T.window[1], 'D', '', 'IMF PortWatch');
      $('f-choke').innerHTML = Hf.html();
    } else { $('heat').innerHTML = '<p class="sub" style="padding:14px">Port data pending.</p>'; }

    // merchandise trade in US$
    {
      const TU = E.filter((e) => e.trade_m).sort((a, b) => (b.trade_m.exports_12m ?? 0) - (a.trade_m.exports_12m ?? 0));
      const F = foot();
      if (TU.length) {
        const cell = (e, v, k, fmt, good) => { const o = e.trade_m.c?.[k]; F.add(`${e.name} ${k.replace('_', ' ')}`, o); return v1(fmt(v), o, good, k.startsWith('balance') ? absBn : undefined); };
        const tn = (v) => ok(v) ? '$' + (v / 1000).toFixed(2) + 'tn' : '—';
        const bal = (v) => ok(v) ? bn(Math.abs(v)) + sd(v) : '—';
        const rows = TU.map((e) => { const t = e.trade_m; F.rel(t.rel, t.date, 'M', '', 'OECD');
          const b12 = ok(t.exports_12m) && ok(t.imports_12m) ? t.exports_12m - t.imports_12m : null;
          return `<tr><td>${esc(e.name)}</td><td>${cell(e, t.exports, 'exports', bn, 1)}</td><td>${cell(e, t.imports, 'imports', bn)}</td><td class="${cls(t.balance)}">${cell(e, t.balance, 'balance', bal, 1)}</td><td>${cell(e, t.exports_12m, 'exports_12m', tn, 1)}</td><td>${cell(e, t.imports_12m, 'imports_12m', tn)}</td><td class="${cls(b12)}">${cell(e, b12, 'balance_12m', bal, 1)}</td><td class="na">${esc(String(t.date).slice(0, 7))}</td></tr>`; });
        const tt = D.trade_totals;
        if (tt) {
          const tc = (k, v, fmt, good) => { F.add(`All shown ${k.replace('_', ' ')}`, tt.c?.[k]); return `<b>${fmt(v)}</b>${chg(tt.c?.[k], good, k.startsWith('balance') ? absBn : undefined)}`; };
          const b12 = ok(tt.exports_12m) && ok(tt.imports_12m) ? tt.exports_12m - tt.imports_12m : null;
          rows.push(`<tr><td><b>All shown</b><div class="m na">${tt.n} economies, months all report</div></td><td>${tc('exports', tt.exports, bn, 1)}</td><td>${tc('imports', tt.imports, bn)}</td><td>${tc('balance', tt.balance, bal, 1)}</td><td>${tc('exports_12m', tt.exports_12m, tn, 1)}</td><td>${tc('imports_12m', tt.imports_12m, tn)}</td><td>${tc('balance_12m', b12, bal, 1)}</td><td class="na">${esc(String(tt.date).slice(0, 7))}</td></tr>`);
        }
        $('tradeusd').innerHTML = table(['Economy', 'Exports (month)', 'Imports (month)', 'Balance (month)', 'Exports, 12m', 'Imports, 12m', 'Balance, 12m', 'Month'], rows);
        $('tusdsub').textContent = `Monthly goods exports and imports in US$ (OECD international merchandise trade), with the change over ${PWORD[PI]}. Balances are shown as a dollar change because they can switch between surplus and deficit.`;
      } else { $('tradeusd').innerHTML = '<p class="sub" style="padding:14px">Fills in on the next automated run.</p>'; }
      $('f-tradeusd').innerHTML = F.html();
    }

    // energy & transport
    {
      const F = foot();
      const PW = Object.entries(D.power || {}).map(([iso, v]) => ({ iso, name: mapName(iso), ...v })).sort((a, b) => (b.twh ?? 0) - (a.twh ?? 0));
      $('power').innerHTML = PW.length ? table(['Country', 'Demand, latest month', 'Trend (3-month y/y)', 'Month'],
        PW.slice(0, 40).map((r) => { F.add(r.name, r.chg); F.rel(r.rel || 'ember', r.date, 'M', '', 'Ember');
          return `<tr><td>${esc(r.name)}</td><td>${v1(num(r.twh, 1) + ' TWh', r.chg)}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(String(r.date).slice(0, 7))}</td></tr>`; }))
        : '<p class="sub" style="padding:14px">Fills in on the next automated run.</p>';
      $('f-power').innerHTML = F.html() + `<div class="foot"><p class="fn">Change compares demand in the latest 3 months with the same 3 months ${PI < 3 ? '1 year or more' : PWORD[PI]} earlier (not seasonally adjusted, so shorter periods are not shown).</p></div>`;
      const G = foot();
      const TR = [...(D.transport || []).map((r) => ({ country: r.country || 'United States', mode: r.name, latest: r.latest, unit: '', chg: r.chg, spark: r.spark, date: r.date, rel: r.rel || 'bts' })),
        ...(D.freight || []).sort((a, b) => a.mode.localeCompare(b.mode) || (b.latest ?? 0) - (a.latest ?? 0))];
      $('transport').innerHTML = TR.length ? table(['Country', 'Mode', 'Latest', 'Trend', 'Period'],
        TR.map((r) => { G.add(`${r.country} ${r.mode.toLowerCase()}`, r.chg); G.rel(r.rel, r.date, r.chg?.f, '', r.rel === 'bts' ? 'US Bureau of Transportation Statistics' : r.rel === 'statcan' ? 'Statistics Canada' : 'Eurostat');
          return `<tr><td>${esc(r.country)}</td><td>${esc(r.mode)}</td><td>${v1(big(r.latest) + (r.unit ? ' <span class="na">' + esc(r.unit) + '</span>' : ''), r.chg)}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(r.chg?.f === 'Q' ? plab(r.date, 'Q') : String(r.date).slice(0, 7))}</td></tr>`; }))
        : '<p class="sub" style="padding:14px">Fills in on the next automated run.</p>';
      $('f-transport').innerHTML = G.html() + '<div class="foot"><p class="fn">Like-for-like windows, not seasonally adjusted: US series compare the latest month with the same month in the earlier year; European air freight and Canadian rail compare the latest 3 months; European rail compares the latest quarter.</p></div>';
    }

    // commodities + ship types
    {
      const F = foot();
      $('prices').innerHTML = (D.prices || []).length ? table(['Commodity', 'Price', 'Unit', 'Trend', 'Month'],
        D.prices.map((p) => { F.add(p.name, p.chg); F.rel(p.rel || 'pink', p.date, 'M', '', 'World Bank Pink Sheet');
          return `<tr><td>${esc(p.name)}</td><td>${v1(num(p.level, p.level < 10 ? 2 : 1), p.chg)}</td><td class="na">${esc(p.unit || '')}</td><td>${p.spark ? spark(p.spark, 90, 22) : ''}</td><td class="na">${esc(String(p.date).slice(0, 7))}</td></tr>`; }))
        : '<p class="sub" style="padding:14px">Fills in on the first automated run.</p>';
      $('f-prices').innerHTML = F.html();
      const SHIP = [['tanker', 'Tankers — crude, fuel, gas, chemicals'], ['dry_bulk', 'Dry bulk — ores, coal, grain, fertilizer'],
        ['container', 'Containers — manufactured goods, coffee, cotton'], ['general_cargo', 'General cargo — steel, machinery'], ['roro', 'Ro-ro — cars and trucks'], ['total', 'All cargo']];
      const G = T?.pc?.global || {}, H = foot();
      $('shiptypes').innerHTML = SHIP.filter(([k]) => G[k]).map(([k, n]) => { H.add(n.split(' — ')[0], G[k]); const v = G[k].v?.[PI];
        return `<div class="row"><div>${n}<div class="m">${ctext(G[k]) ?? 'n/a'} over ${PERS[PI]}</div></div><div>${bar(v, 'var(--pos)', PI >= 4 ? 10 : 30, ok(v) ? sg(v, 0) : undefined)}</div></div>`; }).join('')
        || '<p class="sub">Fills in on the next automated run.</p>';
      if (T?.window) H.rel('portwatch', T.window[1], 'D', '', 'IMF PortWatch');
      $('f-ship').innerHTML = H.html();
    }

    // markets
    {
      const F = foot();
      $('fxnote').textContent = (M.fx_note || '') + ` "Currency vs USD" shows whether that currency gained (+) or lost (−) value against the dollar over ${PWORD[PI]}.`;
      $('fx').innerHTML = (M.fx || []).length ? table(['Pair', 'Means', 'Spot', 'Currency vs USD', '12 months', 'Date'], M.fx.map((r) => { F.add(r.pair, r.chg); F.add(`${r.code} vs USD`, r.ccy_chg); F.rel(r.rel || 'ecb', r.date, 'D', '', 'ECB');
        return `<tr><td class="mono">${esc(r.pair || r.name)}</td><td class="def">${esc(r.meaning || r.name)}</td><td>${v1(num(r.latest, r.latest < 10 ? 4 : 2), r.chg)}</td><td>${chg(r.ccy_chg, 1) || '—'}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(r.date)}</td></tr>`; })) : '<p class="sub" style="padding:14px">Fills in on the first automated run.</p>';
      $('f-fx').innerHTML = F.html();
      const G = foot(), GR = M.global_rates || [];
      $('grates').innerHTML = GR.length ? table(['Economy', 'Policy rate', '10-year yield', 'Real policy rate', 'Curve (10y − policy)', 'Source', 'Date'],
        GR.map((r) => { const c = r.c || {}; G.add(`${r.name} policy rate`, c.policy); G.add(`${r.name} 10-year`, c.long); G.add(`${r.name} real rate`, r.real_est ? null : c.real); G.add(`${r.name} curve`, c.curve);
          G.rel(r.rel, r.date, 'M', 'Policy rates', r.policy_src); if (r.rel_long) G.rel(r.rel_long, r.date, 'M', '10-year yields', 'OECD');
          return `<tr><td>${esc(r.name)}</td><td>${ok(r.policy) ? v1(num(r.policy, 2) + '%', c.policy) : '—'}</td><td>${ok(r.long) ? v1(num(r.long, 2) + '%', c.long) : '—'}</td><td class="${cls(r.real)}">${v1(sg(r.real, 2, '%') + (r.real_est ? '*' : ''), r.real_est ? { v: Array(9).fill(null), r: 'xxxxxxxxx' } : c.real)}</td><td class="${cls(r.curve)}">${v1(sg(r.curve, 2, ' pp'), c.curve)}</td><td class="na">${esc(r.policy_src || 'OECD')}</td><td class="na">${esc(String(r.date || '').slice(0, 7))}</td></tr>`; }))
        : '<p class="sub" style="padding:14px">Fills in on the next automated run.</p>';
      $('f-grates').innerHTML = G.html() + (GR.some((r) => r.real_est) ? '<div class="foot"><p class="fn">* Real rate uses latest annual inflation; no change is shown for these rows because annual inflation has no matching monthly history.</p></div>' : '');
      // Treasury curve: today vs the start of the selected period
      const YC = M.curve;
      if (YC?.today?.y) {
        const yrs = { '1 Mo': 1 / 12, '2 Mo': 2 / 12, '3 Mo': 0.25, '4 Mo': 4 / 12, '6 Mo': 0.5, '1 Yr': 1, '2 Yr': 2, '3 Yr': 3, '5 Yr': 5, '7 Yr': 7, '10 Yr': 10, '20 Yr': 20, '30 Yr': 30 };
        const past = YC.past?.[PERS[PI]], now = YC.maturities.map((m, i) => [m, YC.today.y[i]]).filter((p) => ok(p[1]));
        const then = past?.y ? YC.maturities.map((m, i) => [m, past.y[i]]).filter((p) => ok(p[1])) : [];
        const box = $('ycurve'); box.innerHTML = '';
        const W = Math.min(box.clientWidth || 800, 1100) - 36, Hh = 230, mg = { l: 40, r: 14, t: 14, b: 26 };
        const x = d3.scaleLog().domain([1 / 12, 30]).range([mg.l, W - mg.r]);
        const all = [...now, ...then].map((p) => p[1]), y = d3.scaleLinear().domain([Math.min(0, d3.min(all)), d3.max(all) * 1.08]).nice().range([Hh - mg.b, mg.t]);
        const svg = d3.select(box).append('svg').attr('width', W).attr('height', Hh);
        svg.append('g').attr('transform', `translate(0,${Hh - mg.b})`).call(d3.axisBottom(x).tickValues([0.25, 1, 2, 5, 10, 30]).tickFormat((v) => (v < 1 ? v * 12 + 'm' : v + 'y')).tickSize(0)).call((g) => g.select('.domain').attr('stroke', '#2a2e35'));
        svg.append('g').attr('transform', `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat((v) => v + '%').tickSize(-(W - mg.l - mg.r))).call((g) => { g.select('.domain').remove(); g.selectAll('line').attr('stroke', '#16191e'); });
        const line = d3.line().x((p) => x(yrs[p[0]])).y((p) => y(p[1]));
        if (then.length) svg.append('path').datum(then).attr('fill', 'none').attr('stroke', '#7d828b').attr('stroke-dasharray', '4 3').attr('stroke-width', 1.5).attr('d', line);
        svg.append('path').datum(now).attr('fill', 'none').attr('stroke', 'var(--pos)').attr('stroke-width', 1.8).attr('d', line);
        svg.selectAll('circle.n').data(now).join('circle').attr('cx', (p) => x(yrs[p[0]])).attr('cy', (p) => y(p[1])).attr('r', 2.5).attr('fill', 'var(--pos)');
        const why = past && !past.y ? (past.why === 's' ? `n/a — history begins ${mdy(past.start).slice(0, 3) + mdy(past.start).slice(6)}` : 'n/a — no published curve within a week of that date') : '';
        box.insertAdjacentHTML('beforeend', `<div class="legend-row mono"><i style="background:var(--pos)"></i>Today (${esc(mdy(YC.today.date))}) <i style="background:#7d828b"></i>${PERS[PI]} earlier ${past?.date ? '(' + esc(mdy(past.date)) + ')' : '<span class="na">' + esc(why) + '</span>'}</div>`);
        $('ycsub').textContent = `Today's US Treasury yield curve (green) with the curve ${PWORD[PI]} earlier (dashed grey). Point-in-time curves, not averages.`;
      }
      const H = foot();
      $('rates').innerHTML = (M.rates || []).length ? table(['Rate', 'Latest %', '12 months', 'Date'], M.rates.map((r) => { H.add(r.name, r.chg); H.rel(r.rel, r.date, 'D', '', r.rel === 'nyfed' ? 'Federal Reserve Bank of New York' : 'US Treasury');
        return `<tr><td>${esc(r.name)}</td><td>${v1(num(r.latest, 2), r.chg)}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(r.date)}</td></tr>`; })) : '<p class="sub" style="padding:14px">Fills in on the first automated run.</p>';
      $('f-rates').innerHTML = H.html();
      const J = foot();
      $('usfiscal').innerHTML = (M.us_fiscal || []).map((r) => { J.add(r.name, r.chg); J.rel(r.rel || 'fiscaldata', r.date, 'D', '', 'US Treasury Fiscal Data');
        return `<h3>${esc(r.name)}</h3><div class="score" style="font-size:44px">${usd(r.latest)}</div><div class="cc big">${chg(r.chg, -1)} <span class="na mono small">over ${PERS[PI]}</span></div><p class="mono small">${esc(r.date)}</p>`; }).join('') + J.html();
      const FY = M.us_fy || [], K = foot();
      const mon = (d) => { const p = String(d).slice(0, 10).split('-'); return `${MON[+p[1] - 1]} ${p[0]}`; };
      $('usfy').innerHTML = FY.length ? table(['Fiscal year', 'Receipts', 'Outlays', 'Surplus / deficit', 'Debt at year end', 'Debt added in year'], FY.map((r) => {
        K.rel('mts', r.through, 'M', 'Receipts, outlays, surplus/deficit', 'US Treasury, Monthly Treasury Statement');
        if (r.debt_end) K.rel('fiscaldata', `${r.fy}-09-30`, 'D', 'Debt at fiscal year end', 'US Treasury Fiscal Data');
        return `<tr><td>FY${r.fy}${r.complete ? '' : `<div class="m na">to date, through ${esc(mon(r.through))}</div>`}</td><td>${usd(r.receipts)}</td><td>${usd(r.outlays)}</td><td class="${cls(r.balance)}">${usd(Math.abs(r.balance))}${sd(r.balance)}</td><td>${r.debt_end ? usd(r.debt_end) : '<span class="na">—</span>'}</td><td>${ok(r.debt_change) ? usd(r.debt_change) : '<span class="na">—</span>'}</td></tr>`; }))
        : '<p class="sub" style="padding:14px">Fills in on the next automated run.</p>';
      $('f-usfy').innerHTML = K.html() + '<div class="foot"><p class="fn">Fiscal years are not affected by the change-period toggle. Debt columns start where the daily debt series the site loads begins.</p></div>';
    }

    // people
    {
      const F = foot();
      const VK = [['population', 'Population'], ['pop_growth', 'Growth %'], ['life_exp', 'Life exp.'], ['age65', '65+ %'], ['fertility', 'Births/woman'], ['health_spend', 'Health % GDP'], ['net_migration', 'Net migration'], ['urban', 'Urban %'], ['gdp_pc', 'GDP/person $']];
      $('vitals').innerHTML = E.some((e) => Object.keys(e.vitals || {}).length) ? table(['Economy', ...VK.map((v) => v[1])], E.map((e) => `<tr><td>${esc(e.name)}</td>${VK.map(([k, l]) => { const x = e.vitals?.[k]; if (!x) return '<td>—</td>';
        F.add(`${e.name} ${l.toLowerCase()}`, x.chg); F.rel(x.rel, `${x.year}-07-01`, 'A', x.label, 'World Bank');
        return `<td>${v1(big(x.value), x.chg, 0, k === 'net_migration' ? absPeople : undefined)}</td>`; }).join('')}</tr>`)) : '<p class="sub" style="padding:14px">Fills in on the first automated run.</p>';
      $('f-vitals').innerHTML = F.html();
    }
  }

  // ---------------- year by year (calendar years; not period-dependent) ----------------
  let AN = null, YEAR = null, yfilt = 'g20', yq = '';
  const anVal = (iso, k, y) => { const r = AN?.data?.[iso]?.[k]; if (!r) return null; const v = r[1][y - r[0]]; return ok(v) ? v : null; };
  const YCOLS = [['gdp_growth', 'GDP growth', (v) => sg(v), 1], ['inflation_a', 'Inflation', (v) => num(v) + '%', -1], ['unemployment_a', 'Unemployment', (v) => num(v) + '%', -1],
    ['gdp_usd', 'GDP', (v) => usd(v), 0], ['gov_debt', 'Gov. debt % GDP', (v) => num(v, 0), 0], ['gov_balance', 'Budget bal. % GDP', (v) => sg(v, 1, ''), 1],
    ['current_account', 'Current acct % GDP', (v) => sg(v, 1, ''), 1], ['net_exports', 'Trade bal. % GDP', (v) => sg(v, 1, '') + sd(v), 1],
    ['population', 'Population', (v) => big(v), 0], ['gdp_pc', 'GDP/person', (v) => usd(v), 0], ['life_exp', 'Life exp.', (v) => num(v, 1), 0]];
  async function loadAnnual() {
    if (AN) return AN;
    try { AN = await (await fetch('data/annual.json', { cache: 'no-store' })).json(); } catch (_) { AN = { data: {} }; }
    return AN;
  }
  function yearFoot(y, isos) {
    const F = foot('Year shown'), est = AN.estimate_from;
    for (const [k, l] of YCOLS) {
      const meta = AN.keys?.[k]; if (!meta) continue;
      if (isos.some((i) => ok(anVal(i, k, y)))) F.rel(meta.rel, `${y}-07-01`, 'A', l, meta.rel === 'weo' ? 'IMF World Economic Outlook' : 'World Bank');
    }
    const relSrc = D.rel; D.rel = { ...(AN.rel || {}), ...(relSrc || {}) };  // release dates from the same pipeline run
    const h = F.html(); D.rel = relSrc;
    const notes = [`Calendar year ${y} (January–December), as currently published by each source.`];
    if (y >= est) notes.push(`IMF figures for ${est} are current-year estimates (*); recent years can still be revised by the source.`);
    else if (y >= est - 2) notes.push('IMF figures for the most recent years can still be estimates for some countries and may be revised.');
    return h + `<div class="foot">${notes.map((t) => `<p class="fn">${esc(t)}</p>`).join('')}</div>`;
  }
  async function renderYears() {
    await loadAnnual();
    if (!AN.years) { $('ytbl').innerHTML = '<p class="sub" style="padding:14px">Fills in on the next automated run.</p>'; return; }
    if (YEAR === null) YEAR = AN.estimate_from - 1;
    const sel = $('ysel');
    if (!sel.options.length) { for (let y = AN.years[1]; y >= AN.years[0]; y--) sel.insertAdjacentHTML('beforeend', `<option value="${y}">${y}${y >= AN.estimate_from ? ' (est.)' : ''}</option>`); sel.addEventListener('change', () => { YEAR = +sel.value; renderYears(); if (openIdx !== null) showDetail(openIdx); }); }
    sel.value = String(YEAR);
    document.querySelectorAll('.yfil button').forEach((b) => b.classList.toggle('on', b.dataset.y === yfilt));
    const g20 = new Set(AN.g20 || []);
    const isos = Object.keys(AN.data).filter((i) => (yfilt === 'all' || g20.has(i) || yq) && (!yq || (AN.names[i] || '').toLowerCase().includes(yq)))
      .sort((a, b) => (anVal(b, 'gdp_usd', YEAR) ?? -1) - (anVal(a, 'gdp_usd', YEAR) ?? -1));
    const star = YEAR >= AN.estimate_from ? '*' : '';
    $('ytbl').innerHTML = isos.length ? table(['Country', ...YCOLS.map((c) => c[1])], isos.map((i) => `<tr><td>${esc(AN.names[i])}</td>${YCOLS.map(([k, , f, good]) => { const v = anVal(i, k, YEAR);
      return `<td class="${good ? cls(v, good > 0) : ''}">${ok(v) ? f(v) + (AN.keys[k]?.rel === 'weo' ? star : '') : '<span class="na">—</span>'}</td>`; }).join('')}</tr>`))
      : '<p class="sub" style="padding:14px">No match.</p>';
    $('f-years').innerHTML = yearFoot(YEAR, isos);
  }
  document.querySelectorAll('.yfil button').forEach((b) => b.addEventListener('click', () => { yfilt = b.dataset.y; renderYears(); }));
  $('yq').addEventListener('input', (ev) => { yq = ev.target.value.trim().toLowerCase(); renderYears(); });
  renderYears();

  // period toggle
  $('period').innerHTML = PERS.map((p, i) => `<button data-p="${i}" title="Change over ${PWORD[i]}">${p}</button>`).join('');
  document.querySelectorAll('#period button').forEach((b) => b.addEventListener('click', () => {
    PI = +b.dataset.p;
    try { localStorage.setItem('wel-period', PERS[PI]); } catch (_) { /* storage unavailable */ }
    renderAll();
  }));
  renderAll();

  // ---------------- formulas & status (not period-dependent) ----------------
  const FX = [
    ['GDP (spending side)', 'Y = C + I + G + (X - M)', 'Output equals household spending, plus investment, plus government, plus exports minus imports.'],
    ['Trade balance', 'TB = X - M', 'Exports minus imports. Negative is a trade deficit.'],
    ['Savings and the current account', 'CA = S - I', 'A country that saves more than it invests lends to the world and runs a surplus.'],
    ['Twin balances', '\\text{Twin} = CA + \\text{budget balance}', 'Both negative means borrowing from abroad to fund government spending.'],
    ['Real interest rate (Fisher)', 'r = i - \\pi', 'Policy rate minus inflation. Positive means money is tight.'],
    ['Misery index', '\\text{Misery} = \\pi + u', 'Inflation plus unemployment.'],
    ["Okun's law (output gap)", '\\text{gap} \\approx -2\\,(u - \\bar{u})', 'Each point of unemployment above its 10-year average ≈ 2% of output lost.'],
    ['Taylor rule', 'i^{*} = r^{*} + \\pi + 0.5(\\pi - 2) + 0.5\\,\\text{gap}', 'Where the policy rate "should" be given inflation and slack (r* = 0.5%).'],
    ['Sahm rule', '\\bar{u}_{3m,t} - \\min_{12m}\\bar{u}_{3m} \\geq 0.5', 'A recession signal when 3-month average unemployment rises 0.5 points above its 12-month low.'],
    ['Debt dynamics', '\\Delta d = \\frac{r - g}{1 + g}\\,d - pb', 'r = interest rate, g = nominal growth, d = debt/GDP, pb = primary balance.'],
    ['Debt-stabilizing primary balance', 'pb^{*} = \\frac{r - g}{1 + g}\\,d', 'The budget balance before interest that holds debt/GDP flat.'],
    ['Breakeven inflation', '\\pi^{e}_{10y} = y_{10y}^{\\text{nominal}} - y_{10y}^{\\text{real}}', 'What bond markets expect inflation to average over 10 years.'],
    ['Economy score', '\\text{Score} = 50 + 15\\,\\bar{z},\\quad z_k = \\frac{x_k - \\mu_k}{\\sigma_k}', 'Each pillar compared with its own last 10 years.'],
    ['Change, percent series (pp) and rates (bp)', '\\Delta = x_t - x_{t-k}\\quad(\\text{bp} = 100\\,\\Delta)', 'Straight change over the selected period k.'],
    ['Change, levels, 3 years or more', 'g = \\left(\\frac{x_t}{x_{t-k}}\\right)^{12/k} - 1', 'Compound annual rate, k in months.'],
    ['Long periods (5 years or more)', '\\bar{x}_{t} = \\tfrac{1}{12}\\sum_{j=0}^{11} x_{t-j}', 'Monthly, weekly and daily series compare 12-month averages, so one unusual month cannot distort the result.'],
  ];
  $('formulas').innerHTML = FX.map(([t, tex, txt]) => `<div class="fx-row"><div class="mono small">${esc(t).toUpperCase()}</div><div class="tex" data-tex="${esc(tex)}"></div><div class="small">${esc(txt)}</div></div>`).join('');
  document.querySelectorAll('.tex').forEach((el) => { try { katex.render(el.dataset.tex, el, { displayMode: true, throwOnError: false }); } catch (e) { el.textContent = el.dataset.tex; } });
  const st = Object.entries(D.status || {});
  $('status').innerHTML = st.length ? `<p class="mono small">${st.filter(([, v]) => v.ok).length} OF ${st.length} SOURCES LOADED</p>` + st.map(([k, v]) => `<span class="${v.ok ? 'ok' : 'no'}" title="${esc(v.note)}">${esc(k)}</span>`).join('') : '';
})();

// Header: highlight the section on screen
(() => {
  const links = [...document.querySelectorAll('nav a')];
  const byId = Object.fromEntries(links.map((a) => [a.getAttribute('href').slice(1), a]));
  const secs = Object.keys(byId).map((id) => document.getElementById(id)).filter(Boolean);
  const set = (id) => { links.forEach((a) => a.classList.toggle('on', a === byId[id]));
    const a = byId[id], n = a && a.parentNode;
    if (n && n.scrollWidth > n.clientWidth) n.scrollTo({ left: a.offsetLeft - n.offsetLeft - n.clientWidth / 2 + a.offsetWidth / 2, behavior: 'smooth' }); };
  let ticking = false;
  const pick = () => { ticking = false; let cur = secs[0]?.id;
    for (const sec of secs) if (sec.getBoundingClientRect().top <= 110) cur = sec.id;
    if (cur) set(cur); };
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(pick); } }, { passive: true });
  pick();
})();

// Every table: click a column header to sort (click again to reverse). Sorts on the value, not the change line.
(() => {
  const val = (td) => {
    const t = (td?.childNodes?.length ? [...td.childNodes].filter((n) => !(n.classList && n.classList.contains('chg'))).map((n) => n.textContent).join(' ') : td?.innerText || '').trim().toLowerCase();
    if (!t || t === '—') return null;
    if (/^\d{4}-\d{2}/.test(t)) return Number(t.slice(0, 7).replace('-', ''));
    const m = t.replace(/−/g, '-').replace(/,/g, '').match(/-?\d+(\.\d+)?/);
    if (!m) return t;
    let v = parseFloat(m[0]);
    if (/\dtn/.test(t)) v *= 1e12; else if (/\dbn/.test(t)) v *= 1e9; else if (/\dm\b/.test(t)) v *= 1e6;
    if (t.includes('deficit') && v > 0) v = -v;
    return v;
  };
  document.addEventListener('click', (ev) => {
    const th = ev.target.closest('th'); if (!th) return;
    const tbl = th.closest('table'), body = tbl?.tBodies[0]; if (!body) return;
    const col = [...th.parentNode.children].indexOf(th);
    const dir = th.dataset.dir ? (th.dataset.dir === 'desc' ? 'asc' : 'desc') : (col === 0 ? 'asc' : 'desc');
    tbl.querySelectorAll('th').forEach((h) => { delete h.dataset.dir; h.classList.remove('sorted'); });
    th.dataset.dir = dir; th.classList.add('sorted');
    const rows = [...body.rows], pinned = rows.filter((r) => /^all shown/i.test(r.cells[0]?.innerText || ''));
    const sortable = rows.filter((r) => !pinned.includes(r));
    sortable.sort((a, b) => {
      const x = val(a.cells[col]), y = val(b.cells[col]);
      if (x === null && y === null) return 0; if (x === null) return 1; if (y === null) return -1;
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
      return dir === 'asc' ? c : -c;
    });
    [...sortable, ...pinned].forEach((r) => body.appendChild(r));
  });
})();
