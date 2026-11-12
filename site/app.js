(async function () {
  const $ = (id) => document.getElementById(id);
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  const MID = dark ? [44, 44, 42] : [239, 238, 233], NEG = dark ? [230, 103, 103] : [208, 59, 59], POS = dark ? [57, 135, 229] : [42, 120, 214];
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const num = (v, d = 1) => (v === null || v === undefined || isNaN(v) ? '—' : Number(v).toFixed(d));
  const sgn = (v, d = 0) => (v === null || v === undefined || isNaN(v) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%');
  const big = (v) => v == null ? '—' : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + 'bn' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'm' : Math.abs(v) >= 1e4 ? Math.round(v).toLocaleString() : num(v);
  function col(v, cap = 40) {
    if (v === null || v === undefined || isNaN(v)) return ['transparent', 'var(--mute)'];
    const t = Math.max(-1, Math.min(1, v / cap)), e = t < 0 ? NEG : POS, a = Math.abs(t);
    const c = MID.map((m, i) => Math.round(m + (e[i] - m) * a));
    return [`rgb(${c})`, a > 0.55 ? '#fff' : 'var(--ink)'];
  }

  let D;
  try { D = await (await fetch('data/heartbeat.json', { cache: 'no-store' })).json(); }
  catch (e) { $('hero').innerHTML = '<p>Data not available yet. The first daily run will create it.</p>'; return; }

  if (D.seed) $('banner').innerHTML = `<div class="banner">${esc(D.seed_note || 'Preview data. Live data fills in after the first automated run.')}</div>`;
  $('gen').textContent = 'Last updated ' + D.generated_at + '.';

  // ---------- hero ----------
  const w = D.world || {};
  $('hero').innerHTML = `<div><div class="big">${w.score == null ? '—' : Math.round(w.score)}<small> / 100</small></div>
    <span class="pill ${esc(w.label || 'Pending')}">${esc(w.label || 'Pending')}</span></div>
    <div><p class="headline">${esc(w.headline || '')}</p>
    <div class="meta">World score: average of ${D.economies.filter(e => e.score != null).length} major economies. Updated ${esc(D.generated_at)}.</div></div>`;

  $('drivers').innerHTML = (D.drivers || []).map((d) => `<li>${esc(d)}</li>`).join('') || '<li>Waiting for first data run.</li>';

  // ---------- economies ----------
  const PIL = { activity: 'Activity', labor: 'Jobs', prices: 'Prices', trade: 'Trade' };
  const arrow = (z) => z == null ? '·' : z > 0.5 ? '▲' : z < -0.5 ? '▼' : '●';
  $('econ').innerHTML = D.economies.map((e, i) => `<button class="eco" data-i="${i}">
      <div class="n">${esc(e.name)}</div><div class="s">${e.score == null ? '—' : Math.round(e.score)}</div>
      <span class="pill ${esc(e.label)}">${esc(e.label)}</span>
      <div class="chips">${Object.entries(PIL).map(([k, l]) => { const z = e.pillars?.[k]; const [b, f] = col(z == null ? null : z * 20); return `<span class="chip" style="background:${b};color:${f}" title="${l}: ${z == null ? 'no data' : z.toFixed(2)}">${l} ${arrow(z)}</span>`; }).join('')}</div>
    </button>`).join('');

  function sparkSVG(pts) {
    if (!pts || pts.length < 3) return '';
    const v = pts.map((p) => p[1]), mn = Math.min(...v), mx = Math.max(...v), W = 220, H = 36;
    const xy = v.map((y, i) => `${(i / (v.length - 1)) * W},${H - ((y - mn) / (mx - mn || 1)) * (H - 4) - 2}`).join(' ');
    return `<svg class="spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline fill="none" stroke="var(--ink2)" stroke-width="1.5" points="${xy}"/></svg>`;
  }
  const IND = {
    gdp: ['GDP growth', (x) => sgn(x.latest, 1), (x) => x.year_ago == null ? 'vs a year ago' : `vs a year ago · prior year ${sgn(x.year_ago, 1)}`],
    inflation: ['Inflation', (x) => `${num(x.latest)}%`, (x) => x.year_ago == null ? '' : `A year ago: ${num(x.year_ago)}%`],
    unemployment: ['Unemployment', (x) => `${num(x.latest)}%`, (x) => x.year_ago == null ? '' : `A year ago: ${num(x.year_ago)}%`],
    industry: ['Factory output', (x) => sgn(x.latest, 1), () => 'vs a year ago'],
    policy_rate: ['Central bank rate', (x) => `${num(x.latest, 2)}%`, (x) => x.year_ago == null ? '' : `A year ago: ${num(x.year_ago, 2)}%`],
    long_rate: ['10-year bond yield', (x) => `${num(x.latest, 2)}%`, (x) => x.year_ago == null ? '' : `A year ago: ${num(x.year_ago, 2)}%`],
  };
  function plain(e) {
    const s = [], I = e.indicators || {};
    if (I.gdp) s.push(`The economy is ${I.gdp.latest >= 0 ? 'growing' : 'shrinking'} at ${Math.abs(I.gdp.latest).toFixed(1)}% a year.`);
    if (I.inflation) s.push(`Prices are rising ${num(I.inflation.latest)}% a year${I.inflation.year_ago != null ? (I.inflation.latest > I.inflation.year_ago ? ', faster than a year ago' : ', slower than a year ago') : ''}.`);
    if (I.unemployment) s.push(`${num(I.unemployment.latest)}% of workers who want a job can't find one.`);
    if (I.industry) s.push(`Factories are producing ${Math.abs(I.industry.latest).toFixed(1)}% ${I.industry.latest >= 0 ? 'more' : 'less'} than a year ago.`);
    if (e.trade_yoy != null) s.push(`Cargo through its main ports is ${e.trade_yoy >= 0 ? 'up' : 'down'} ${Math.abs(e.trade_yoy).toFixed(0)}% on last year.`);
    return s.join(' ');
  }
  function showDetail(i) {
    document.querySelectorAll('.eco').forEach((b) => b.classList.toggle('on', +b.dataset.i === i));
    const e = D.economies[i], I = e.indicators || {}, V = e.vitals || {};
    const facts = Object.entries(IND).filter(([k]) => I[k]).map(([k, [lab, f, sub]]) =>
      `<li><span class="k">${lab} · ${esc(I[k].date)}</span><b>${f(I[k])}</b><span class="k">${sub(I[k])}</span>${sparkSVG(I[k].spark)}</li>`).join('');
    const vit = ['population', 'life_exp', 'age65', 'fertility', 'health_spend', 'net_migration', 'gdp_pc', 'gini'].filter((k) => V[k]).map((k) =>
      `<li><span class="k">${esc(V[k].label)} · ${V[k].year}</span><b>${big(V[k].value)}${V[k].unit && V[k].unit.startsWith('%') ? '%' : ''}</b><span class="k">${esc(V[k].unit)}${V[k].ten_years_ago != null ? ' · 10 yrs ago ' + big(V[k].ten_years_ago) : ''}</span></li>`).join('');
    $('detail').innerHTML = `<div class="detail"><h3>${esc(e.name)} <span class="pill ${esc(e.label)}">${esc(e.label)}</span></h3>
      <p>${esc(plain(e)) || 'Detailed data fills in after the first automated run.'}</p>
      ${facts ? `<ul class="facts">${facts}</ul>` : ''}
      ${vit ? `<h3 style="margin-top:18px;font-size:15px">People and health</h3><ul class="facts">${vit}</ul>` : ''}
      <p class="meta">Coverage: ${esc(e.coverage || '')}</p></div>`;
  }
  document.querySelectorAll('.eco').forEach((b) => b.addEventListener('click', () => showDetail(+b.dataset.i)));

  // ---------- trade heat map ----------
  const T = D.trade;
  if (T && T.regions) {
    $('tradesub').textContent = `Cargo (metric tons) through each region's busiest ports, ${T.window[0]} to ${T.window[1]}, vs the same days last year.`;
    const P = Object.keys(D.products), H = { tanker: 'Oil & gas', container: 'Goods', dry_bulk: 'Ores & grain', general_cargo: 'Steel', roro: 'Vehicles', total: 'Total' };
    const rows = [...T.regions].sort((a, b) => (a.total ?? 0) - (b.total ?? 0));
    if (T.global) rows.push({ region: 'All tracked ports', ...T.global });
    $('heat').innerHTML = `<table class="hm"><tr><th></th>${[...P, 'total'].map((k) => `<th>${H[k]}</th>`).join('')}</tr>` +
      rows.map((r) => `<tr><td class="l">${esc(r.region)}</td>${[...P, 'total'].map((k) => { const [b, f] = col(r[k]); return `<td style="background:${b};color:${f}" title="${esc(r.region)} ${H[k]}: ${sgn(r[k], 1)}">${r[k] == null ? '—' : Math.round(r[k])}</td>`; }).join('')}</tr>`).join('') + '</table>';
  } else $('heat').innerHTML = '<p class="sub" style="padding:8px">Port data pending.</p>';

  // ---------- diverging bars ----------
  function bar(v, color, cap = 100) {
    if (v == null) return `<div class="trk"><div class="ax"></div><span class="val" style="left:52%">n/a</span></div>`;
    const w = Math.min(Math.abs(v), cap) / cap * 50, l = v < 0 ? 50 - w : 50, pos = v < 0 ? `right:${50 + w + 1}%` : `left:${50 + w + 1}%`;
    return `<div class="trk"><div class="ax"></div><div class="bar" style="left:${l}%;width:${w}%;background:${color}"></div><span class="val" style="${pos}">${sgn(v)}${Math.abs(v) > cap ? '*' : ''}</span></div>`;
  }
  if (T && T.chokepoints && T.chokepoints.length) {
    $('choke').innerHTML = [...T.chokepoints].sort((a, b) => (a.transits_yoy ?? 0) - (b.transits_yoy ?? 0)).map((c) =>
      `<div class="row"><div>${esc(c.name)}<div class="meta">${num(c.daily_transits, 0)} ships/day</div></div>${bar(c.transits_yoy, (c.transits_yoy ?? 0) < 0 ? 'var(--neg)' : 'var(--pos)')}</div>`).join('');
  } else $('choke').innerHTML = '<p class="sub">Chokepoint data pending.</p>';

  const vol = (ship) => (T && T.global && ship ? T.global[ship] : null);
  $('prices').innerHTML = (D.prices || []).map((p) => `<div class="row"><div>${esc(p.name)}<div class="meta">${esc(p.date)}</div></div>
     <div>${bar(p.yoy, '#eb6834')}${p.ship ? bar(vol(p.ship), '#888780') : ''}</div></div>`).join('') || '<p class="sub">Price data pending.</p>';

  $('usfast').innerHTML = (D.us_fast || []).length ? `<table><tr><th>Indicator</th><th>Latest</th><th>vs a year ago</th><th>Date</th></tr>` +
    D.us_fast.map((u) => `<tr><td>${esc(u.name)}</td><td>${big(u.latest)}</td><td>${sgn(u.yoy, 1)}</td><td>${esc(u.date)}</td></tr>`).join('') + '</table>' : '<p class="sub" style="padding:8px">Pending.</p>';

  // ---------- markets ----------
  const M = D.markets || {};
  const fmtL = (v) => v == null ? '—' : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : Number(v).toFixed(Math.abs(v) < 10 ? 3 : 2);
  const ch = (v, u) => v == null ? '—' : u === 'pp' ? (v > 0 ? '+' : '') + v.toFixed(2) + ' pp' : sgn(v, 1);
  $('markets').innerHTML = Object.keys(M).length ? Object.entries(M).map(([g, rows]) => rows.length ? `<h3 class="mh">${esc(g)}</h3><div class="scroll"><table><tr><th>Name</th><th>Latest</th><th>1 month</th><th>1 year</th><th>Date</th></tr>` +
    rows.map((r) => `<tr><td>${esc(r.name)}</td><td>${fmtL(r.latest)}</td><td>${ch(r.m1, r.unit)}</td><td>${ch(r.y1, r.unit)}</td><td>${esc(r.date)}</td></tr>`).join('') + '</table></div>' : '').join('') : '<p class="sub">Market data fills in on the first automated run.</p>';

  // ---------- vitals table ----------
  const VK = [['population', 'Population'], ['life_exp', 'Life exp.'], ['age65', '65+ %'], ['fertility', 'Births/woman'], ['health_spend', 'Health % GDP'], ['net_migration', 'Net migration'], ['gdp_pc', 'GDP/person $']];
  const anyV = D.economies.some((e) => e.vitals && Object.keys(e.vitals).length);
  $('vitals').innerHTML = anyV ? `<table><tr><th>Economy</th>${VK.map(([, l]) => `<th>${l}</th>`).join('')}</tr>` +
    D.economies.map((e) => `<tr><td>${esc(e.name)}</td>${VK.map(([k]) => `<td>${e.vitals?.[k] ? big(e.vitals[k].value) : '—'}</td>`).join('')}</tr>`).join('') + '</table>' : '<p class="sub" style="padding:8px">Pending first run.</p>';

  // ---------- status ----------
  const st = Object.entries(D.status || {});
  $('status').innerHTML = st.length ? `<p class="meta">${st.filter(([, v]) => v.ok).length} of ${st.length} sources loaded.</p>` +
    st.map(([k, v]) => `<span class="${v.ok ? 'ok' : 'no'}" title="${esc(v.note)}">${esc(k)}</span>`).join('') : '';
})();
