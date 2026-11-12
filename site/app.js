(async function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ok = (v) => v !== null && v !== undefined && !Number.isNaN(v);
  const num = (v, d = 1) => (ok(v) ? Number(v).toFixed(d) : '—');
  const sg = (v, d = 1, suf = '%') => (ok(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d) + suf : '—');
  const cls = (v, goodUp = true) => (!ok(v) || v === 0 ? '' : (v > 0) === goodUp ? 'pos' : 'neg');
  const big = (v) => !ok(v) ? '—' : Math.abs(v) >= 1e12 ? (v / 1e12).toFixed(2) + 'tn' : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(1) + 'bn' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'm' : Math.abs(v) >= 1e4 ? Math.round(v).toLocaleString() : num(v);
  const usd = (v) => !ok(v) ? '—' : (v < 0 ? '−$' : '$') + big(Math.abs(v));
  const POS = [62, 230, 196], NEG = [255, 77, 109], MID = [28, 31, 36];
  function div(v, cap) { // diverging color on black
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
  function bar(v, color, cap = 60) {
    if (!ok(v)) return `<div class="trk"><div class="ax"></div><span class="val" style="left:52%">n/a</span></div>`;
    const w = (Math.min(Math.abs(v), cap) / cap) * 50, l = v < 0 ? 50 - w : 50, pos = v < 0 ? `right:${50 + w + 1}%` : `left:${50 + w + 1}%`;
    return `<div class="trk"><div class="ax"></div><div class="bar-f" style="left:${l}%;width:${w}%;background:${color}"></div><span class="val" style="${pos}">${sg(v, 0)}${Math.abs(v) > cap ? '›' : ''}</span></div>`;
  }
  const table = (head, rows) => `<table><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;

  let D;
  try { D = await (await fetch('data/heartbeat.json', { cache: 'no-store' })).json(); }
  catch (e) { $('headline').textContent = 'Data not available yet. The first daily run will create it.'; return; }
  const E = D.economies || [], T = D.trade, M = D.markets || {};
  $('upd').textContent = 'UPDATED ' + (D.generated_at || '');
  $('gen').textContent = 'LAST UPDATE ' + (D.generated_at || '');

  // ---------------- hero ----------------
  const w = D.world || {};
  $('wscore').textContent = ok(w.score) ? Math.round(w.score) : '—';
  $('wlabel').textContent = w.label || 'Pending'; $('wlabel').className = 'pill ' + (w.label || '');
  $('headline').textContent = w.headline || '';

  // ---------------- map ----------------
  const LAYERS = {
    score: { get: (r) => r.score, color: (v) => div(ok(v) ? v - 50 : null, 25), legend: ['Stressed', 'Normal', 'Strong'], ramp: [div(-25, 25), div(0, 25), div(25, 25)], fmt: (v) => num(v, 0) + ' / 100' },
    inflation: { get: (r) => r.inflation, color: (v) => seq(v, 0, 8, NEG), legend: ['0%', '', '8%+'], ramp: [seq(0, 0, 8, NEG), seq(8, 0, 8, NEG)], fmt: (v) => num(v) + '% a year' },
    unemployment: { get: (r) => r.unemployment, color: (v) => seq(v, 2, 10, NEG), legend: ['2%', '', '10%+'], ramp: [seq(2, 2, 10, NEG), seq(10, 2, 10, NEG)], fmt: (v) => num(v) + '% jobless' },
    trade: { get: (r) => r.trade, color: (v) => div(v, 30), legend: ['−30%', '0', '+30%'], ramp: [div(-30, 30), div(0, 30), div(30, 30)], fmt: (v) => sg(v, 0) + ' port cargo y/y' },
  };
  let layer = 'score', paths, cpG;
  const tip = $('tip');
  function showTip(ev, html) { const r = $('map').getBoundingClientRect(); tip.innerHTML = html; tip.style.opacity = 1; tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 250) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px'; }
  const hideTip = () => { tip.style.opacity = 0; };
  function paint() {
    const L = LAYERS[layer];
    if (paths) paths.attr('fill', (d) => { const r = D.map?.[String(+d.id)]; return r ? L.color(L.get(r)) : '#0d0f12'; });
    $('legend').innerHTML = `<span>${L.legend[0]}</span><span class="ramp" style="background:linear-gradient(90deg,${L.ramp.join(',')})"></span><span>${L.legend[2]}</span>`;
    document.querySelectorAll('#layers button').forEach((b) => b.classList.toggle('on', b.dataset.l === layer));
  }
  document.querySelectorAll('#layers button').forEach((b) => b.addEventListener('click', () => { layer = b.dataset.l; paint(); }));
  try {
    const world = await (await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json')).json();
    const feats = topojson.feature(world, world.objects.countries).features.filter((f) => f.properties.name !== 'Antarctica');
    const el = $('globe'), W = el.clientWidth, H = el.clientHeight;
    const proj = d3.geoNaturalEarth1().fitExtent([[10, 50], [W - 10, H - 30]], { type: 'FeatureCollection', features: feats });
    const path = d3.geoPath(proj);
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('preserveAspectRatio', 'xMidYMid meet');
    svg.append('path').datum(d3.geoGraticule10()).attr('class', 'graticule').attr('d', path);
    paths = svg.append('g').selectAll('path').data(feats).join('path').attr('class', 'country').attr('d', path)
      .on('mousemove', (ev, d) => {
        const r = D.map?.[String(+d.id)], L = LAYERS[layer];
        let h = `<b>${esc(r?.name || d.properties.name)}</b>`;
        if (r) { if (ok(r.score)) h += `<br>Score ${num(r.score, 0)} · ${esc(r.label)}`; if (ok(r.inflation)) h += `<br>Inflation ${num(r.inflation)}%`; if (ok(r.unemployment)) h += `<br>Unemployment ${num(r.unemployment)}%`; if (ok(r.trade)) h += `<br>Port cargo ${sg(r.trade, 0)} y/y`; }
        else h += '<br><span style="color:#5f646d">not tracked yet</span>';
        showTip(ev, h);
      })
      .on('mouseleave', hideTip)
      .on('click', (ev, d) => { const r = D.map?.[String(+d.id)]; const i = E.findIndex((e) => e.iso3 === r?.iso3); if (i >= 0) { showDetail(i); $('economies').scrollIntoView(); } });
    const cps = (T?.chokepoints || []).filter((c) => ok(c.lon));
    cpG = svg.append('g');
    cps.forEach((c) => {
      const [x, y] = proj([c.lon, c.lat]); const col = div(c.transits_yoy, 40), r = 2.5 + Math.min(6, Math.sqrt(c.daily_transits || 1) / 2);
      cpG.append('circle').attr('class', 'cpring').attr('cx', x).attr('cy', y).attr('r', 3).attr('stroke', col);
      cpG.append('circle').attr('class', 'cp').attr('cx', x).attr('cy', y).attr('r', r).attr('fill', col)
        .on('mousemove', (ev) => showTip(ev, `<b>${esc(c.name)}</b><br>${num(c.daily_transits, 0)} ships/day<br>${sg(c.transits_yoy, 0)} vs a year ago`)).on('mouseleave', hideTip);
    });
    paint();
  } catch (e) { $('globe').innerHTML = '<p class="sub" style="padding:120px 30px;text-align:right">Map unavailable.</p>'; }

  // ---------------- ticker ----------------
  const tk = [];
  (D.prices || []).filter((p) => ['Brent crude', 'Gold', 'Copper', 'Wheat', 'Asia LNG'].includes(p.name)).forEach((p) => tk.push(`<span>${esc(p.name.toUpperCase())}<b>${num(p.level, 2)}</b><em class="${cls(p.yoy)}">${sg(p.yoy, 0)} y/y</em></span>`));
  (M.fx || []).filter((f) => ['EUR', 'JPY', 'CNY', 'GBP'].includes(f.code)).forEach((f) => tk.push(`<span>${esc(f.code === 'EUR' ? 'EUR/USD' : f.code === 'GBP' ? 'GBP/USD' : 'USD/' + f.code)}<b>${num(f.latest, f.latest < 10 ? 4 : 2)}</b><em class="${cls(f.y1)}">${sg(f.y1, 1)} y/y</em></span>`));
  (M.rates || []).filter((r) => /10-year Treasury|Fed funds/.test(r.name)).forEach((r) => tk.push(`<span>${esc(r.name.toUpperCase())}<b>${num(r.latest, 2)}%</b></span>`));
  if (ok(w.trade_yoy)) tk.push(`<span>GLOBAL PORT CARGO<b>${sg(w.trade_yoy, 1)}</b>y/y</span>`);
  $('ticker').innerHTML = tk.join('') || '<span>Markets fill in on the first automated run.</span>';

  $('drivers').innerHTML = (D.drivers || []).map((d) => `<li>${esc(d)}</li>`).join('') || '<li>Waiting for the first data run.</li>';

  // ---------------- economies ----------------
  const PIL = { activity: 'ACT', labor: 'JOBS', prices: 'PRICE', trade: 'TRADE' };
  $('econ').innerHTML = E.map((e, i) => `<button class="eco" data-i="${i}"><div class="n">${esc(e.name)}</div>
    <div class="s">${ok(e.score) ? Math.round(e.score) : '—'}</div><span class="pill ${esc(e.label)}">${esc(e.label)}</span>
    <div class="chips">${Object.entries(PIL).map(([k, l]) => { const z = e.pillars?.[k]; const c = !ok(z) ? 'var(--mute)' : z > 0.5 ? 'var(--pos)' : z < -0.5 ? 'var(--neg)' : 'var(--ink2)'; return `<span class="chip" style="color:${c}">${l} ${!ok(z) ? '·' : z > 0.5 ? '▲' : z < -0.5 ? '▼' : '●'}</span>`; }).join('')}</div></button>`).join('');
  const IND = {
    gdp: ['GDP growth', (x) => sg(x.latest), 'vs a year ago'], inflation: ['Inflation', (x) => num(x.latest) + '%', 'a year'],
    unemployment: ['Unemployment', (x) => num(x.latest) + '%', 'of workers'], industry: ['Factory output', (x) => sg(x.latest), 'vs a year ago'],
    policy_rate: ['Central bank rate', (x) => num(x.latest, 2) + '%', ''], long_rate: ['10-year bond yield', (x) => num(x.latest, 2) + '%', ''],
    exports: ['Goods exports', (x) => sg(x.latest), 'vs a year ago'], imports: ['Goods imports', (x) => sg(x.latest), 'vs a year ago'],
    trade_balance: ['Trade balance (month)', (x) => usd(x.latest * 1e9), ''],
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
  const fact = (k, val, m, extra = '') => `<li><div class="k">${esc(k)}</div><b>${val}</b><div class="m">${m}</div>${extra}</li>`;
  function showDetail(i) {
    document.querySelectorAll('.eco').forEach((b) => b.classList.toggle('on', +b.dataset.i === i));
    const e = E[i], I = e.indicators || {}, F = e.fundamentals || {}, V = e.vitals || {}, d = e.derived || {}, m = e.math || {};
    const live = Object.entries(IND).filter(([k]) => I[k]).map(([k, [lab, f, sub]]) => fact(lab, f(I[k]), `${I[k].annual ? String(I[k].date).slice(0, 4) + ' · ANNUAL' : esc(I[k].date)} · ${esc(I[k].source)}${ok(I[k].year_ago) && !I[k].annual ? ' · YEAR AGO ' + num(I[k].year_ago) : ''}`, spark(I[k].spark))).join('');
    const gov = [['gov_debt', 'Government debt'], ['gov_balance', 'Budget balance'], ['primary_balance', 'Primary balance'], ['current_account', 'Current account'], ['revenue', 'Revenue'], ['spending', 'Spending']]
      .filter(([k]) => F[k]).map(([k, l]) => fact(l, sg(F[k].value, 1, '%').replace(/^\+/, k === 'gov_debt' || k === 'revenue' || k === 'spending' ? '' : '+'), `OF GDP · ${F[k].year}${F[k].estimate ? ' EST' : ''} · ${esc(F[k].source)}`)).join('')
      + (d.trade_balance_usd ? fact('Trade balance (X − M)', usd(d.trade_balance_usd.value), `${d.trade_balance_usd.year} · ${d.trade_balance_usd.value >= 0 ? 'SURPLUS' : 'DEFICIT'}`) : '')
      + (F.gdp_usd ? fact('GDP', usd(F.gdp_usd.value), `${F.gdp_usd.year} · ${esc(F.gdp_usd.source)}`) : '')
      + (ok(d.r_minus_g) ? fact('r − g', sg(d.r_minus_g, 1, ' pp'), d.r_minus_g > 0 ? 'DEBT GROWS FASTER THAN GDP' : 'GROWTH ERODES DEBT') : '');
    const mth = [['real_rate', 'Real interest rate', (v) => sg(v, 2, '%')], ['misery', 'Misery index', (v) => num(v)], ['taylor', 'Taylor rule rate', (v) => num(v, 2) + '%'], ['taylor_gap', 'Taylor gap', (v) => sg(v, 2, ' pp')], ['sahm', 'Sahm rule', (v) => num(v, 2)], ['curve', 'Yield curve (10y − policy)', (v) => sg(v, 2, ' pp')], ['output_gap', 'Output gap (Okun)', (v) => sg(v, 1)]]
      .filter(([k]) => ok(m[k])).map(([k, l, f]) => fact(l, f(m[k]), k === 'sahm' ? (m[k] >= 0.5 ? 'RECESSION SIGNAL' : 'NO SIGNAL (NEEDS 0.5)') : '')).join('');
    const vit = ['population', 'life_exp', 'age65', 'fertility', 'health_spend', 'net_migration', 'urban', 'gdp_pc', 'gini'].filter((k) => V[k])
      .map((k) => fact(V[k].label, big(V[k].value) + (V[k].unit.startsWith('%') ? '%' : ''), `${esc(V[k].unit).toUpperCase()} · ${V[k].year}${ok(V[k].ten_years_ago) ? ' · 10Y AGO ' + big(V[k].ten_years_ago) : ''}`)).join('');
    $('detail').innerHTML = `<div class="detail"><h3>${esc(e.name)}</h3><div class="score" style="font-size:56px">${ok(e.score) ? Math.round(e.score) : '—'}<small>/100</small></div>
      <span class="pill ${esc(e.label)}">${esc(e.label)}</span><span class="mono small" style="margin-left:10px">${esc(e.coverage || '')} PILLARS</span>
      <p class="plain">${esc(plain(e)) || 'Detailed data fills in after the first automated run.'}</p>
      ${live ? `<h3>Live indicators</h3><ul class="facts">${live}</ul>` : ''}${mth ? `<h3>Formulas</h3><ul class="facts">${mth}</ul>` : ''}
      ${gov ? `<h3>Government and trade</h3><ul class="facts">${gov}</ul>` : ''}${vit ? `<h3>People and health</h3><ul class="facts">${vit}</ul>` : ''}</div>`;
  }
  document.querySelectorAll('.eco').forEach((b) => b.addEventListener('click', () => showDetail(+b.dataset.i)));

  // ---------------- scorecard ----------------
  const I_ = (e, k) => e.indicators?.[k]?.latest;
  $('scorecard').innerHTML = table(['Economy', 'Score', 'GDP', 'Inflation', 'Jobless', 'Policy rate', 'Real rate', 'Misery', 'Taylor gap', 'Sahm', '10y − policy'],
    E.map((e) => `<tr><td>${esc(e.name)}</td><td>${ok(e.score) ? Math.round(e.score) : '—'}</td><td class="${cls(I_(e, 'gdp'))}">${sg(I_(e, 'gdp'))}</td><td>${num(I_(e, 'inflation'))}%</td><td>${num(I_(e, 'unemployment'))}%</td>
      <td>${num(I_(e, 'policy_rate'), 2)}</td><td>${sg(e.math?.real_rate, 2, '')}</td><td>${num(e.math?.misery)}</td><td>${sg(e.math?.taylor_gap, 2, '')}</td>
      <td class="${ok(e.math?.sahm) && e.math.sahm >= 0.5 ? 'neg' : ''}">${num(e.math?.sahm, 2)}</td><td class="${cls(e.math?.curve)}">${sg(e.math?.curve, 2, '')}</td></tr>`));

  // ---------------- fundamentals ----------------
  const F_ = (e, k) => e.fundamentals?.[k];
  const fv = (e, k, signed) => { const x = F_(e, k); return x ? `${signed ? sg(x.value, 1, '') : num(x.value, 0)}${x.estimate ? '*' : ''}` : '—'; };
  $('fund').innerHTML = table(['Economy', 'GDP', 'Debt % GDP', 'Budget bal.', 'Primary bal.', 'Current acct', 'Exports', 'Imports', 'Trade bal.', 'Twin bal.', 'FX reserves'],
    E.map((e) => `<tr><td>${esc(e.name)}</td><td>${usd(F_(e, 'gdp_usd')?.value)}</td><td>${fv(e, 'gov_debt')}</td><td class="${cls(F_(e, 'gov_balance')?.value)}">${fv(e, 'gov_balance', 1)}</td>
      <td class="${cls(F_(e, 'primary_balance')?.value)}">${fv(e, 'primary_balance', 1)}</td><td class="${cls(F_(e, 'current_account')?.value)}">${fv(e, 'current_account', 1)}</td>
      <td>${usd(F_(e, 'exports_usd')?.value)}</td><td>${usd(F_(e, 'imports_usd')?.value)}</td><td class="${cls(e.derived?.trade_balance_usd?.value)}">${usd(e.derived?.trade_balance_usd?.value)}</td>
      <td class="${cls(e.derived?.twin)}">${sg(e.derived?.twin, 1, '')}</td><td>${usd(F_(e, 'reserves_usd')?.value)}</td></tr>`));
  const comp = E.filter((e) => F_(e, 'consumption') && F_(e, 'investment') && F_(e, 'gov_consumption'));
  $('comp').innerHTML = comp.length ? `<div class="bars">${comp.map((e) => {
    const c = F_(e, 'consumption').value, i = F_(e, 'investment').value, g = F_(e, 'gov_consumption').value, nx = F_(e, 'net_exports')?.value ?? 100 - c - i - g;
    const parts = [[c, 'var(--c1)', 'C'], [i, 'var(--c2)', 'I'], [g, 'var(--c3)', 'G'], [Math.max(nx, 0), 'var(--c4)', 'NX']], tot = parts.reduce((a, p) => a + p[0], 0);
    return `<div class="row"><div>${esc(e.name)}<div class="m">${F_(e, 'consumption').year} · NX ${sg(nx, 1)}</div></div><div class="stack">${parts.filter((p) => p[0] > 0).map(([v, col, l]) => `<span style="width:${(v / tot) * 100}%;background:${col}" title="${l} ${num(v)}%">${v / tot > 0.09 ? l + ' ' + Math.round(v) : ''}</span>`).join('')}</div></div>`;
  }).join('')}</div>` : '<p class="sub">Fills in on the first automated run.</p>';
  const dm = E.filter((e) => ok(e.derived?.r_minus_g));
  $('debtmath').innerHTML = dm.length ? table(['Economy', '10y yield (r)', 'Nominal growth (g)', 'r − g', 'Debt % GDP', 'Primary bal. needed', 'Actual primary bal.', 'Debt ratio'],
    dm.map((e) => { const d = e.derived, pb = F_(e, 'primary_balance')?.value;
      return `<tr><td>${esc(e.name)}</td><td>${num(I_(e, 'long_rate'), 2)}%</td><td>${num(d.nominal_growth)}%</td><td class="${cls(d.r_minus_g, false)}">${sg(d.r_minus_g, 1, ' pp')}</td><td>${num(F_(e, 'gov_debt')?.value, 0)}%</td>
        <td>${sg(d.pb_stabilizing, 1)}</td><td>${sg(pb, 1)}</td><td>${!ok(d.fiscal_gap) ? '—' : d.fiscal_gap >= 0 ? '<span class="pill Strong">Falling</span>' : '<span class="pill Stressed">Rising</span>'}</td></tr>`; }))
    : '<p class="sub" style="padding:14px">Needs bond yields, growth and inflation. Fills in on the first automated run.</p>';

  // ---------------- trade ----------------
  if (T?.regions) {
    $('tradesub').textContent = `Cargo (metric tons) through each region's busiest ports, ${T.window[0]} to ${T.window[1]}, vs the same days a year ago.`;
    const P = Object.keys(D.products || {}), H = { tanker: 'Oil & gas', container: 'Goods', dry_bulk: 'Ores & grain', general_cargo: 'Steel', roro: 'Vehicles', total: 'Total' };
    const rows = [...T.regions].sort((a, b) => (a.total ?? 0) - (b.total ?? 0));
    if (T.global) rows.push({ region: 'ALL TRACKED PORTS', ...T.global });
    $('heat').innerHTML = `<table class="hm"><thead><tr><th>Region</th>${[...P, 'total'].map((k) => `<th style="text-align:center">${H[k]}</th>`).join('')}</tr></thead><tbody>` +
      rows.map((r) => `<tr><td>${esc(r.region)}</td>${[...P, 'total'].map((k) => `<td class="c" style="background:${div(r[k], 40)};color:${ok(r[k]) && Math.abs(r[k]) > 22 ? '#000' : 'var(--ink)'}">${ok(r[k]) ? sg(r[k], 0, '') : '—'}</td>`).join('')}</tr>`).join('') + '</tbody></table>';
    $('impexp').innerHTML = [...T.regions].sort((a, b) => (a.region > b.region ? 1 : -1)).map((r) => `<div class="row"><div>${esc(r.region)}<div class="m">IMPORTS / EXPORTS Y/Y</div></div><div>${bar(r.imports, 'var(--c1)')}${bar(r.exports, 'var(--c4)')}</div></div>`).join('')
      + '<div class="legend-row mono" style="margin-top:10px"><i style="background:var(--c1)"></i>Imports <i style="background:var(--c4)"></i>Exports</div>';
    $('choke').innerHTML = [...(T.chokepoints || [])].sort((a, b) => (a.transits_yoy ?? 0) - (b.transits_yoy ?? 0)).map((c) =>
      `<div class="row"><div>${esc(c.name)}<div class="m">${num(c.daily_transits, 0)} SHIPS/DAY</div></div>${bar(c.transits_yoy, (c.transits_yoy ?? 0) < 0 ? 'var(--neg)' : 'var(--pos)')}</div>`).join('');
  } else { $('heat').innerHTML = '<p class="sub" style="padding:14px">Port data pending.</p>'; }

  // ---------------- commodities ----------------
  const vol = (s) => (T?.global && s ? T.global[s] : null);
  $('prices').innerHTML = (D.prices || []).map((p) => `<div class="row"><div>${esc(p.name)}<div class="m">${num(p.level, 2)} · ${esc(String(p.date).slice(0, 7))}</div></div><div>${bar(p.yoy, 'var(--warm)', 100)}${p.ship ? bar(vol(p.ship), 'var(--dim)', 100) : ''}</div></div>`).join('') || '<p class="sub">Fills in on the first automated run.</p>';

  // ---------------- markets ----------------
  const mrow = (r, pp) => `<tr><td>${esc(r.name)}</td><td>${num(r.latest, r.latest < 10 ? 4 : 2)}</td><td class="${cls(r.m1)}">${pp ? sg(r.m1, 2, ' pp') : sg(r.m1, 1)}</td><td class="${cls(r.y1)}">${pp ? sg(r.y1, 2, ' pp') : sg(r.y1, 1)}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(r.date)}</td></tr>`;
  $('fx').innerHTML = (M.fx || []).length ? table(['Currency', 'Latest', '1 month', '1 year', '12 months', 'Date'], M.fx.map((r) => mrow(r))) : '<p class="sub" style="padding:14px">Fills in on the first automated run.</p>';
  $('rates').innerHTML = (M.rates || []).length ? table(['Rate', 'Latest %', '1 month', '1 year', '12 months', 'Date'], M.rates.map((r) => mrow(r, 1))) : '<p class="sub" style="padding:14px">Fills in on the first automated run.</p>';
  $('usfiscal').innerHTML = (M.us_fiscal || []).map((r) => `<h3>${esc(r.name)}</h3><div class="score" style="font-size:44px">${usd(r.latest)}</div><p class="mono small">${esc(r.date)} · ${ok(r.y1_abs) ? usd(r.y1_abs) + ' IN 12 MONTHS (' + sg(r.y1, 1) + ')' : ''}</p>`).join('');

  // ---------------- people ----------------
  const VK = [['population', 'Population'], ['pop_growth', 'Growth %'], ['life_exp', 'Life exp.'], ['age65', '65+ %'], ['fertility', 'Births/woman'], ['health_spend', 'Health % GDP'], ['net_migration', 'Net migration'], ['urban', 'Urban %'], ['gdp_pc', 'GDP/person $']];
  $('vitals').innerHTML = E.some((e) => Object.keys(e.vitals || {}).length) ? table(['Economy', ...VK.map((v) => v[1])], E.map((e) => `<tr><td>${esc(e.name)}</td>${VK.map(([k]) => `<td>${e.vitals?.[k] ? big(e.vitals[k].value) : '—'}</td>`).join('')}</tr>`)) : '<p class="sub" style="padding:14px">Fills in on the first automated run.</p>';

  // ---------------- formulas ----------------
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
  ];
  $('formulas').innerHTML = FX.map(([t, tex, txt]) => `<div class="fx-row"><div class="mono small">${esc(t).toUpperCase()}</div><div class="tex" data-tex="${esc(tex)}"></div><div class="small">${esc(txt)}</div></div>`).join('');
  document.querySelectorAll('.tex').forEach((el) => { try { katex.render(el.dataset.tex, el, { displayMode: true, throwOnError: false }); } catch (e) { el.textContent = el.dataset.tex; } });

  const st = Object.entries(D.status || {});
  $('status').innerHTML = st.length ? `<p class="mono small">${st.filter(([, v]) => v.ok).length} OF ${st.length} SOURCES LOADED</p>` + st.map(([k, v]) => `<span class="${v.ok ? 'ok' : 'no'}" title="${esc(v.note)}">${esc(k)}</span>`).join('') : '';
})();
