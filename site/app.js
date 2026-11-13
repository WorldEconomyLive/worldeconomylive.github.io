(async function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ok = (v) => v !== null && v !== undefined && !Number.isNaN(v);
  const num = (v, d = 1) => (ok(v) ? Number(v).toFixed(d) : '—');
  const sg = (v, d = 1, suf = '%') => { if (!ok(v)) return '—'; const a = Math.abs(v).toFixed(d), z = +a === 0; return (z ? '' : v > 0 ? '+' : '−') + a + suf; };
  const cls = (v, goodUp = true) => (!ok(v) || v === 0 ? '' : (v > 0) === goodUp ? 'pos' : 'neg');
  const big = (v) => !ok(v) ? '—' : Math.abs(v) >= 1e12 ? (v / 1e12).toFixed(2) + 'tn' : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(1) + 'bn' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'm' : Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : num(v);
  const usd = (v) => !ok(v) ? '—' : (v < 0 ? '−$' : '$') + big(Math.abs(v));
  const bn = (v) => !ok(v) ? '—' : (v < 0 ? '−$' : '$') + (Math.abs(v) >= 1000 ? (Math.abs(v) / 1000).toFixed(2) + 'tn' : Math.abs(v).toFixed(1) + 'bn');
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
  // when a figure counts as released, for a site rebuilt for a past date (standard delay per source)
  function lagWhen(R, hi, f) {
    const E_ = window.WELEngine; if (!E_ || !hi) return 'release date not published by source';
    const n = E_.parse(hi), y = E_.ymd(n)[0];
    if (R.basis === 'weo') { const [m, d] = D.asof.weo_md; return `counted as released ${mdy(E_.iso(E_.dn(y, m, d)))} (October WEO of that year)`; }
    if (R.basis === 'wb') { const [m, d] = D.asof.wb_md; return `counted as released ${mdy(E_.iso(E_.dn(y + 1, m, d)))} (World Bank, July of the following year)`; }
    const L = R.lag ?? 0, at = E_.periodEnd(n, f || 'D') + L;
    return `counted as released ${mdy(E_.iso(at))} (${L ? `standard ${L}-day delay after the period ends` : 'published the same day'})`;
  }
  // credit and notice lines each source's terms ask for, added under any panel that shows its data
  const lnk = (u) => `<a href="https://${u}" target="_blank" rel="noopener">${u}</a>`;
  const OECD_DS = { 'DSD_PRICES@DF_PRICES_ALL': 'Consumer price indices', 'DSD_LFS@DF_IALFS_UNE_M': 'Infra-annual labour statistics, unemployment rates',
    'DSD_STES@DF_INDSERV': 'Production and sales (industry)', 'DSD_NAMAIN1@DF_QNA': 'Quarterly national accounts', 'DSD_STES@DF_FINMARK': 'Financial market statistics',
    'DSD_IMTS@DF_IMTS': 'International merchandise trade statistics' };
  function notice(k, hi) {
    const dk = DORDER.find((x) => DV?.keys?.[x]?.rel === k);
    if (dk) return ['dev:' + dk, `${esc(DV.keys[dk].label)}: ${esc(DV.keys[dk].credit)} Latest year and changes selected and computed by this site.`];
    const yr = String(LIVE?.asof?.today || LIVE?.generated_at || '').slice(0, 4), imf = `IMF terms: ${lnk('www.imf.org/en/about/copyright-and-terms')}`;
    if (k.startsWith('oecd:')) { const id = k.slice(5); return ['oecd', `${esc(OECD_DS[id] || id)} (${esc(id)})`, yr]; }
    if (k === 'weo') return ['weo', `Source: International Monetary Fund, World Economic Outlook database${(D.rel?.weo?.label || LIVE?.rel?.weo?.label) ? ' (' + esc(D.rel?.weo?.label || LIVE.rel.weo.label) + ')' : ''}, ${lnk('data.imf.org')}. Changes and scores computed by this site. ${imf}.`];
    if (k === 'portwatch') return ['portwatch', `Source: International Monetary Fund, PortWatch (satellite ship-tracking data from the UN Global Platform), ${lnk('portwatch.imf.org')}. Summed into 28-day windows and compared by this site. ${imf}.`];
    if (k === 'bis') return ['bis', `Source: BIS, central bank policy rates (${lnk('data.bis.org')}), compiled from each country's national central bank. The BIS does not guarantee the accuracy or completeness of the statistics; nothing here is an investment recommendation or advice.`];
    if (k.startsWith('eurostat:') || k.startsWith('dbn:Eurostat')) return ['eurostat', 'Source: Eurostat. Changes and windows computed by this site; Eurostat bears no responsibility for this reuse.'];
    if (k === 'ecb') return ['ecb', 'Source: ECB statistics (euro foreign exchange reference rates). Converted to US-dollar pairs and percent changes by this site.'];
    if (k === 'pink') return ['pink', `Source: World Bank, Commodity Price Data (The Pink Sheet), CC BY 4.0. Changes computed by this site; no endorsement by the World Bank is implied.`];
    if (k.startsWith('wb:')) return ['wb', `Source: World Bank, World Development Indicators, CC BY 4.0 (${lnk('data.worldbank.org')}). Changes computed by this site; no endorsement by the World Bank is implied.`];
    if (k === 'eia_intl') return ['eia', `Source: U.S. Energy Information Administration, International Energy Statistics (${lnk('www.eia.gov/international/data/world')}), a U.S. government work in the public domain. Shares computed by this site.`];
    if (k === 'ember_yearly') return ['ember_y', `Source: Ember, Yearly Electricity Data, CC BY 4.0 (${lnk('ember-energy.org')}). Shares computed by this site.`];
    if (k === 'ember') return ['ember', `Source: Ember, Monthly Electricity Data, CC BY 4.0 (${lnk('ember-energy.org')}). 3-month sums and changes computed by this site.`];
    if (k === 'statcan') return ['statcan', `Adapted from Statistics Canada, Table 23-10-0216-01, Railway carloadings, ${esc(hi)}. This does not constitute an endorsement by Statistics Canada of this product.`];
    if (k === 'nyfed') return ['nyfed', NYFED];
    return null;
  }
  const NYFED = 'The Effective Federal Funds Rate is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the Effective Federal Funds Rate by World Economy Live, does not sanction or endorse any particular republication, and has no liability for your use.';
  function foot(word = 'Latest') {
    const rel = new Map(), items = [];
    return {
      // span = the dates are a history shown in the panel (e.g. a table of years), not latest values
      rel(key, date, f, what, fallback, span = false) {
        if (!date) return;
        const k = key || fallback || 'other';
        if (!rel.has(k)) rel.set(k, { dates: [], f, what: new Set(), fallback, span });
        const r = rel.get(k); r.dates.push(String(date).slice(0, 10)); if (what) r.what.add(what); if (!r.f) r.f = f; if (span) r.span = true;
      },
      add(name, o) { if (o) items.push([name, o]); },
      _rel: rel, _items: items,
      absorb(G) {
        for (const [k, r] of G._rel) { if (!rel.has(k)) rel.set(k, { dates: [], f: r.f, what: new Set(), fallback: r.fallback, span: r.span });
          const t = rel.get(k); t.dates.push(...r.dates); r.what.forEach((w) => t.what.add(w)); if (r.span) t.span = true; }
        items.push(...G._items); return this;
      },
      // condensed: one line per source (what was used and its latest period, publication dates as one range), then every
      // credit or notice the sources ask for, each once
      htmlc(extraNotes = []) {
        const groups = new Map(), lic = new Map(), oecd = new Set(), orig = new Set(), undated = new Set(); let oyr = '', siteW = null;
        const shortM = (t) => t.replace(/\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/g, (m) => m.slice(0, 3));
        for (const [k, r] of rel) {
          const ds = [...r.dates].sort(), hi = plab(ds[ds.length - 1], r.f);
          const n = notice(k, hi);
          if (n && n[0] === 'oecd') { oecd.add(n[1]); oyr = n[2]; }
          else if (n && n[0].startsWith('dev:')) { const dk = n[0].slice(4); if (DEVLIC[dk]) lic.set(DEVLIC[dk][0], DEVLIC[dk][1]); else orig.add(DSHORT[dk] || ''); }
          else if (n && !lic.has(n[0])) lic.set(n[0], n[1]);
          if (k === 'site') { siteW = [...r.what]; continue; }
          const R = (D.rel || {})[k] || (D.rebuilt && window.WELEngine ? { source: r.fallback, basis: k === 'weo' ? 'weo' : k.startsWith('wb:') ? 'wb' : 'lag', lag: window.WELEngine.lagOf(k) } : {});
          const when = ['lag', 'weo', 'wb'].includes(R.basis) ? lagWhen(R, ds[ds.length - 1], r.f)
            : R.released ? (R.basis === 'dataset' ? `dataset last updated ${mdy(R.released)}` : `released ${mdy(R.released)}`) : '';
          const prov = k.startsWith('oecd:') ? 'OECD' : k === 'weo' ? `IMF World Economic Outlook${R.label ? ' (' + R.label + ')' : ''}` : k.startsWith('wb:') ? 'World Bank WDI'
            : k.startsWith('owid:') ? 'Our World in Data' : k === 'eia_intl' ? 'U.S. EIA' : k.startsWith('ember') ? 'Ember' : k === 'portwatch' ? 'IMF PortWatch' : (R.source || r.fallback || k);
          if (!groups.has(prov)) groups.set(prov, { by: new Map(), dates: [], counted: false });
          const g = groups.get(prov), lab = shortM(r.span && ds.length > 1 && plab(ds[0], r.f) !== hi ? `${plab(ds[0], r.f)}–${hi}` : hi);
          if (!g.by.has(lab)) g.by.set(lab, new Set());
          (r.what.size ? r.what : new Set([''])).forEach((w) => g.by.get(lab).add(CANON[w] || w));
          const m = when.match(/\d\d\/\d\d\/\d{4}/); if (m) { g.dates.push(m[0]); if (/counted/.test(when)) g.counted = true; } else undated.add(prov);
        }
        const toISO = (x) => x.slice(6) + x.slice(0, 2) + x.slice(3, 5);
        const lines = [];
        for (const [prov, g] of groups) {
          const parts = [...g.by].map(([lab, ws]) => `${esc([...ws].filter(Boolean).join(', '))} ${esc(lab)}`.trim());
          const dd = [...new Set(g.dates)].sort((a, b) => toISO(a).localeCompare(toISO(b)));
          const when = dd.length ? ` · ${g.counted ? 'counted as released' : 'published'} ${dd[0]}${dd.length > 1 ? '–' + dd[dd.length - 1] : ''}` : '';
          lines.push(`<b>${esc(prov)}</b>: ${parts.join('; ')}${when}`);
        }
        if (siteW) lines.push(`<b>This site</b>: ${esc(siteW.join(', '))} — ${D.rebuilt ? `rebuilt for ${mdy(D.asof_view)} with today's method` : `computed ${mdy(D.generated_at)}`} from the sources above.`);
        if (undated.size) lines.push(`Release dates not published by: ${esc([...undated].join(', '))}.`);
        // the n/a explanations, as in the full footnote
        const by = { s: new Map(), f: [], g: [], x: [], z: [] }; let avg = false, perYear = false;
        for (const [n, o] of items) { const r = o.r?.[PI]; if (o.a?.[PI] === '1') avg = true; if (o.k === 'pct' && PI >= 4 && ok(o.v?.[PI])) perYear = true;
          if (r === 's') { const k = o.s || 'n/a'; if (!by.s.has(k)) by.s.set(k, []); by.s.get(k).push(n); } else if (r === 'f') by.f.push(n); else if (r === 'g') by.g.push(n); else if (r === 'x') by.x.push(n); else if (r === 'z') by.z.push(n); }
        const names = (a) => { const u = [...new Set(a)]; return esc(u.slice(0, 4).join(', ')) + (u.length > 4 ? ` and ${u.length - 4} more` : ''); };
        const na = [];
        for (const [start, ns] of [...by.s].sort()) na.push(start === 'n/a' ? `no history yet: ${names(ns)}` : `history begins ${esc(start)}: ${names(ns)}`);
        if (by.f.length) na.push(`too infrequent for ${PERS[PI]}: ${names(by.f)}`);
        if (by.g.length) na.push(`comparison point missing at source: ${names(by.g)}`);
        if (by.x.length) na.push(`not meaningful at or below zero: ${names(by.x)}`);
        if (by.z.length) na.push(`seasonal, compared 1 year or more apart: ${names(by.z)}`);
        const notes = [...extraNotes];
        if (na.length) notes.push(`n/a for ${PERS[PI]} — ${na.join('; ')}.`);
        if (avg) notes.push(`${PERS[PI]} compares 12-month averages.`);
        if (perYear) notes.push('Changes over 3 years or more are compound annual rates.');
        // credits: required wording kept as written; the rest shortened to source and licence
        const SHORT = { weo: `IMF data: subject to the IMF's terms (${lnk('www.imf.org/en/about/copyright-and-terms')})`, portwatch: `IMF data: subject to the IMF's terms (${lnk('www.imf.org/en/about/copyright-and-terms')})`,
          wb: 'World Bank WDI, CC BY 4.0', pink: 'World Bank Pink Sheet, CC BY 4.0', ember: 'Ember, CC BY 4.0', ember_y: 'Ember, CC BY 4.0', eia: 'U.S. EIA, public domain' };
        const credits = new Set();
        if (oecd.size) credits.add(`OECD (${oyr}), ${[...oecd].join('; ')}, OECD Data Explorer, ${lnk('data-explorer.oecd.org')}`);
        for (const [k, t] of lic) credits.add(SHORT[k] || t.replace(/\s*(Changes|Shares|3-month sums)[^.]*computed by this site[^.]*\.?/g, '').replace(/\s*No endorsement[^.]*\.?/gi, '').trim());
        orig.delete(''); if (orig.size) credits.add(`Original sources: ${[...orig].join('; ')}${[...groups.keys()].includes('Our World in Data') ? '; Our World in Data processing, CC BY 4.0' : ''}`);
        const credit = [...credits].map((c) => c.replace(/\.$/, '')).join('. ') + (credits.size ? '. ' : '') + 'Changes, shares and scores computed by this site; no endorsement by any source is implied.';
        return `<div class="foot fc">${lines.map((l) => `<p>${l}</p>`).join('')}${notes.map((l) => `<p class="fn">${l}</p>`).join('')}<p class="lic">${credit}</p></div>`;
      },
      html() {
        const lines = [], merged = new Map(), lic = new Map(), oecd = new Set(); let oyr = '';
        for (const [k, r] of rel) {
          { const ds_ = [...r.dates].sort(), n = notice(k, plab(ds_[ds_.length - 1], r.f));
            if (n && n[0] === 'oecd') { oecd.add(n[1]); oyr = n[2]; } else if (n && !lic.has(n[0])) lic.set(n[0], n[1]); }
          if (k === 'site') {
            lines.push(D.rebuilt ? `${esc([...r.what].join(', '))} — rebuilt for ${mdy(D.asof_view)} by this site with today's method, from the sources listed in this note and in Method as they publish them today.`
              : `${esc([...r.what].join(', '))} — last computed ${mdy(r.dates.sort().pop())} by this site from the sources listed in this note and in Method.`); continue;
          }
          const R = (D.rel || {})[k] || (D.rebuilt && window.WELEngine ? { source: r.fallback, basis: k === 'weo' ? 'weo' : k.startsWith('wb:') ? 'wb' : 'lag', lag: window.WELEngine.lagOf(k) } : {});
          const ds = r.dates.sort(), lo = plab(ds[0], r.f), hi = plab(ds[ds.length - 1], r.f);
          const when = ['lag', 'weo', 'wb'].includes(R.basis) ? lagWhen(R, ds[ds.length - 1], r.f)
            : R.released ? (R.basis === 'dataset' ? `dataset last updated ${mdy(R.released)}` : `released ${mdy(R.released)}${R.basis === 'daily' ? ' (published daily)' : ''}`) : 'release date not published by source';
          const src = (R.source || r.fallback || k) + (R.label ? `, ${R.label}` : '');
          const key = [lo, hi, when, src, r.span ? 1 : 0].join('|');
          if (!merged.has(key)) merged.set(key, { what: new Set(), lo, hi, when, src, span: r.span });
          r.what.forEach((w) => merged.get(key).what.add(w));
        }
        for (const m of merged.values()) {
          const range = m.lo === m.hi ? `${word}: ${m.hi}` : m.span ? `History: ${m.lo} to ${m.hi} · Latest: ${m.hi}` : `${word}: ${m.lo} to ${m.hi}`;
          lines.push(`${m.what.size ? esc([...m.what].join(', ')) + ' — ' : ''}${esc(range)} · ${esc(m.when)} · source: ${esc(m.src)}`);
        }
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
        return `<div class="foot">${lines.map((l) => `<p>${l}</p>`).join('')}${notes.map((l) => `<p class="fn">${l}</p>`).join('')}${(oecd.size ? [`OECD (${oyr}), ${[...oecd].join('; ')}, OECD Data Explorer, ${lnk('data-explorer.oecd.org')}. Changes, ratios and scores computed by this site.`] : []).concat([...lic.values()]).map((l) => `<p class="lic">${l}</p>`).join('')}</div>`;
      },
    };
  }

  let D, LIVE, E, T, M;
  try { LIVE = D = await (await fetch('data/heartbeat.json', { cache: 'no-store' })).json(); }
  catch (e) { $('headline').textContent = 'Data not available yet. The first daily run will create it.'; return; }
  const bind = () => { E = D.economies || []; T = D.trade; M = D.markets || {}; };
  bind();
  $('upd').textContent = 'UPDATED ' + (D.generated_at || '');
  $('gen').textContent = 'LAST UPDATE ' + (D.generated_at || '');
  if ($('fnotice')) $('fnotice').textContent = NYFED;
  dispatchEvent(new Event('resize'));       // the header just changed width: re-check whether the section links fit
  // map features carry ISO numeric ids; Kosovo has none in the map file, so it is matched by name
  const NAMEKEY = { Kosovo: 'XKX' };
  const fid = (d) => (d.id != null ? String(+d.id) : NAMEKEY[d.properties?.name] || '');
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
    // development layers: latest published year per country (data/dev.json)
    poverty: { get: (r) => devPt(r.iso3, 'poverty')?.v, dev: 'poverty', color: (v) => seq(v, 0, 40, NEG), legend: ['0%', '', '40%+ in extreme poverty'], ramp: [seq(0, 0, 40, NEG), seq(40, 0, 40, NEG)] },
    dev: { get: (r) => devPt(r.iso3, DKEY)?.v, dev: true, color: (v) => devColor(v), legend: () => devLegend(), get ramp() { return devRamp(); } },
  };
  // ---------------- development & environment (slow annual indicators) ----------------
  let DV = null, DKEY = 'rd', DSC = null;
  const DORDER = ['rd', 'poverty', 'gdp_pc_long', 'productivity', 'hdi', 'child_mort', 'school', 'undernourish', 'labor_part', 'female_lab', 'co2_pc', 'fossil_energy', 'clean_elec', 'warming'];
  const DSHORT = { rd: 'UNESCO Institute for Statistics via World Bank (CC BY-SA 3.0 IGO)', poverty: 'World Bank Poverty and Inequality Platform', gdp_pc_long: 'Maddison Project Database 2023 (CC BY 4.0)',
    productivity: 'Penn World Table 11.0 (CC BY 4.0)', hdi: 'UNDP Human Development Report (CC BY 3.0 IGO)', child_mort: 'UN IGME', school: 'World Bank Human Capital Index', undernourish: 'FAO (CC BY 4.0)',
    labor_part: 'ILO (CC BY 4.0)', female_lab: 'ILO (CC BY 4.0)', co2_pc: 'Global Carbon Project (CC BY 4.0)', clean_elec: 'Ember (CC BY 4.0)', fossil_energy: 'U.S. EIA (public domain)', warming: 'Jones et al. (CC BY 4.0)' };
  const DEVLIC = { clean_elec: ['ember', 'Ember, CC BY 4.0'], fossil_energy: ['eia', 'U.S. EIA, public domain'] };
  // the year-by-year table's short column names, folded into the readout's names in the condensed footnote
  const CANON = { 'Gov. debt % GDP': 'Government debt', 'Budget bal. % GDP': 'Budget balance', 'Current acct % GDP': 'Current account', 'Life exp.': 'Life expectancy',
    'GDP/person': 'GDP per person', 'Trade bal. % GDP': 'Net exports', 'Pop.': 'Population' };
  const DEV_MAX_AGE = 15;   // years: older figures are not shown as a country's latest
  async function loadDev() {
    if (DV) return DV;
    try { const r = await fetch('data/dev.json', { cache: 'no-cache' }); DV = r.ok ? await r.json() : null; } catch (e) { DV = null; }
    DV = DV || { keys: {}, data: {}, names: {}, rel: {} };
    return DV;
  }
  // past dates: an annual figure for year Y counts as published on July 1 of Y+1
  const devCut = () => { if (D === LIVE) return 9999; const v = String(D.asof_view || D.asof?.today || ''); const y = +v.slice(0, 4); return v.slice(5, 10) >= '07-01' ? y - 1 : y - 2; };
  const devRef = () => (D === LIVE ? viewYear() : devCut() + 1);
  const devPt = (iso, k, upto) => {
    const a = DV?.data?.[iso]?.[k]; if (!a) return null;
    const cut = Math.min(upto ?? 9999, devCut());
    for (let j = Math.min(a[1].length - 1, cut - a[0]); j >= 0; j--) if (ok(a[1][j])) return upto === undefined && a[0] + j < devRef() - DEV_MAX_AGE ? null : { v: a[1][j], y: a[0] + j };
    return null;
  };
  // energy and electricity by source (latest year within the age limit)
  const MIXCOL = { oil: '#c9733f', gas: '#e0a94a', coal: '#7a6a5c', other_fossil: '#9b5f45', nuclear: '#a78bfa', renewables: '#3ee6c4', lowcarbon: '#3ee6c4', hydro: '#4aa3e0', wind: '#7dd3fc', solar: '#f5d76e', bio: '#7bc47f', other_ren: '#3ee6c4' };
  const MIXLAB = { oil: 'Oil', gas: 'Gas', coal: 'Coal', other_fossil: 'Other fossil', nuclear: 'Nuclear', renewables: 'Renewables', lowcarbon: 'Nuclear and renewables', hydro: 'Hydro', wind: 'Wind', solar: 'Solar', bio: 'Bioenergy', other_ren: 'Other renewables' };
  const mixPt = (kind, iso, year) => {
    const M = DV?.mix?.[kind], a = M?.data?.[iso]; if (!a) return null;
    const cut = Math.min(year ?? 9999, devCut());
    for (let j = Math.min(a[1].length - 1, cut - a[0]); j >= 0; j--) if (a[1][j]) return a[0] + j < devRef() - DEV_MAX_AGE ? null : { y: a[0] + j, s: a[1][j], order: M.order };
    return null;
  };
  const mixBar = (m, h = 12) => `<div class="mixbar" style="height:${h}px">${m.order.map((k, i) => (m.s[i] > 0 ? `<span style="width:${m.s[i]}%;background:${MIXCOL[k]}" title="${MIXLAB[k]} ${num(m.s[i], 1)}%"></span>` : '')).join('')}</div>`;
  const mixLegend = (m) => m.order.map((k, i) => [k, m.s[i]]).filter(([, v]) => v >= 0.5).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span class="mixk"><i style="background:${MIXCOL[k]}"></i>${MIXLAB[k]} ${num(v, v < 10 ? 1 : 0)}%</span>`).join('');
  function mixBlocks(iso, F) {
    let out = '';
    for (const [kind, title] of [['energy', 'Energy use by source'], ['elec', 'Electricity generation by source']]) {
      const m = mixPt(kind, iso); if (!m) continue;
      const rk = DV.mix[kind].rel; F.rel(rk, `${m.y}-07-01`, 'A', title, kind === 'energy' ? 'U.S. EIA' : 'Ember');
      out += `<h3>${title} <span class="na mono small">${m.y}</span></h3>${mixBar(m)}<div class="mixleg mono small">${mixLegend(m)}</div>`;
    }
    return out;
  }
  const devAgo = (iso, k, x) => { const a = x && devPt(iso, k, x.y - 10); return a && a.y >= x.y - 12 ? a : null; };
  const devFmt = (k, v) => { const K = DV?.keys?.[k]; if (!K || !ok(v)) return '—'; if (K.unit.startsWith('int.-$')) return '$' + big(v); if (k === 'warming' && Math.abs(v) < 0.01) return v === 0 ? '0' : Number(v.toPrecision(2)).toString(); return num(v, K.dec) + (K.unit.startsWith('%') ? '%' : ''); };
  const devSrcName = (K) => (K.src === 'owid' ? 'Our World in Data' : K.src === 'ember' ? 'Ember' : K.src === 'eia' ? 'U.S. Energy Information Administration' : 'World Bank');
  const devDelta = (k, x, a) => {
    if (!a) return '';
    const K = DV.keys[k], d = x.v - a.v, g = K.better || 0;
    const t = K.unit.startsWith('int.-$') || k === 'co2_pc' || k === 'warming' ? (a.v ? sg((x.v / a.v - 1) * 100, 0) : '—') : sg(d, K.dec, K.unit.startsWith('%') ? ' pp' : '');
    return `<span class="chg ${g ? cls(d, g > 0) : ''}">${t}</span>`;
  };
  function devScale() {
    const vals = Object.keys(DV?.data || {}).map((i) => devPt(i, DKEY)?.v).filter(ok).sort((a, b) => a - b);
    const q = (p) => vals[Math.min(vals.length - 1, Math.max(0, Math.round(p * (vals.length - 1))))];
    DSC = vals.length ? { lo: q(0.05), hi: q(0.95), k: DKEY } : null;
    return DSC;
  }
  const devColor = (v) => { const S_ = DSC?.k === DKEY ? DSC : devScale(); if (!S_ || !ok(v)) return '#111317'; const g = DV.keys[DKEY]?.better ?? 1; return seq(v, S_.lo, S_.hi, g < 0 ? NEG : POS); };
  const devLegend = () => { const S_ = DSC?.k === DKEY ? DSC : devScale(), K = DV?.keys?.[DKEY]; return S_ && K ? [devFmt(DKEY, S_.lo), '', `${devFmt(DKEY, S_.hi)} ${K.label.toLowerCase()}`] : ['', '', '']; };
  const devRamp = () => { const S_ = DSC?.k === DKEY ? DSC : devScale(); if (!S_) return ['#111317', '#111317']; return [devColor(S_.lo), devColor(S_.hi)]; };
  function devFacts(iso, F) {
    if (!DV) return '';
    return DORDER.filter((k) => DV.keys[k]).map((k) => {
      const K = DV.keys[k], x = devPt(iso, k);
      if (!x) return '';
      const a = devAgo(iso, k, x);
      F.rel(K.rel, `${x.y}-07-01`, 'A', K.label, devSrcName(K), true);
      return fact(K.label, devFmt(k, x.v), `${esc(K.unit.toUpperCase())} · ${x.y}${a ? ` · ${a.y}: ${devFmt(k, a.v)}` : ''}`, devDelta(k, x, a));
    }).join('');
  }
  function renderDev() {
    if (!DV || !D || !$('devtbl')) return;
    D.rel = Object.assign({}, DV.rel || {}, D.rel || {});
    const keys = DORDER.filter((k) => DV.keys[k]);
    if (!keys.includes(DKEY)) DKEY = keys[0];
    $('devsel').innerHTML = keys.map((k) => `<button data-d="${k}" class="${k === DKEY ? 'on' : ''}">${esc(DV.keys[k].label)}</button>`).join('');
    $('devsel').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { DKEY = b.dataset.d; DSC = null; renderDev(); if (layer === 'dev') paint(); }));
    const K = DV.keys[DKEY], qq = ($('dq').value || '').trim().toLowerCase(), F = foot();
    $('devabout').textContent = `${K.label} (${K.unit}). ${K.better > 0 ? 'Higher is better.' : K.better < 0 ? 'Lower is better.' : ''}`;
    const rows = Object.keys(DV.data).map((i) => { const x = devPt(i, DKEY); return x ? { i, x, a: devAgo(i, DKEY, x) } : null; }).filter(Boolean)
      .filter((r) => !qq || (DV.names[r.i] || '').toLowerCase().includes(qq)).sort((a, b) => b.x.v - a.x.v);
    rows.forEach((r) => F.rel(K.rel, `${r.x.y}-07-01`, 'A', K.label, devSrcName(K), true));
    const trend = (i) => { const a = DV.data[i][DKEY], c = devCut(), p = []; a[1].forEach((v, j) => { if (ok(v) && a[0] + j <= c) p.push([a[0] + j, v]); }); return spark(p, 110, 22); };
    const mk = null;   // splits by source live in the Energy section
    if (mk && DV.mix?.[mk]) rows.forEach((r) => { const m = mixPt(mk, r.i, r.x.y); if (m) F.rel(DV.mix[mk].rel, `${m.y}-07-01`, 'A', mk === 'energy' ? 'Energy use by source' : 'Electricity by source', mk === 'energy' ? 'U.S. EIA' : 'Ember', true); });
    $('devtbl').innerHTML = rows.length ? table(['#', 'Country', K.label, 'Year', 'About 10 years earlier', 'Change', mk ? 'Split by source' : 'Trend'], rows.map((r, n) =>
      `<tr class="click" data-iso="${r.i}"><td class="na">${n + 1}</td><td>${esc(DV.names[r.i] || r.i)}</td><td>${devFmt(DKEY, r.x.v)}</td><td>${r.x.y}</td><td>${r.a ? `${devFmt(DKEY, r.a.v)} <span class="na">(${r.a.y})</span>` : '<span class="na">—</span>'}</td><td>${devDelta(DKEY, r.x, r.a) || '<span class="na">n/a</span>'}</td><td>${mk ? (() => { const m = mixPt(mk, r.i, r.x.y); return m ? `<div class="mixcell">${mixBar(m, 10)}</div>` : '<span class="na">—</span>'; })() : trend(r.i)}</td></tr>`))
      : `<p class="sub na" style="padding:14px">n/a — no figures published for this indicator ${D === LIVE ? 'yet' : 'on or before ' + mdy(D.asof_view || D.asof?.today)}.</p>`;
    $('devtbl').querySelectorAll('tr[data-iso]').forEach((tr) => tr.addEventListener('click', () => openCountry(tr.dataset.iso)));
    const legendRow = mk && DV.mix?.[mk] ? `<div class="mixleg mono small">${DV.mix[mk].order.map((k) => `<span class="mixk"><i style="background:${MIXCOL[k]}"></i>${MIXLAB[k]}</span>`).join('')}</div>` : '';
    $('f-dev').innerHTML = legendRow + F.html() + `<div class="foot"><p class="fn">Change: percentage points for shares and rates; percent for income, productivity and emissions. ${D === LIVE ? '' : 'For past dates, a figure for year Y counts as published on July 1 of Y+1. '}Ranked by the latest year each country has (figures more than ${DEV_MAX_AGE} years old are left out); years differ between countries.${mk === 'energy' ? ' Energy use is primary energy consumption as measured by the EIA (quadrillion Btu), split by fuel.' : ''}</p></div>`;
  }
  // ---------------- energy use and electricity by source (Energy section) ----------------
  let MIXK = 'energy';
  function renderMix() {
    if (!D || !$('mixtbl')) return;
    const M = DV?.mix?.[MIXK], F = foot(), qq = ($('mq').value || '').trim().toLowerCase(), PWR = D.power || {};
    $('mixsel').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.m === MIXK));
    const gdp = {}; for (const r of Object.values(D.map || {})) if (ok(r.gdp_usd)) gdp[r.iso3] = r.gdp_usd;
    const nm = (i) => DV?.names?.[i] || mapName(i);
    const FOS = MIXK === 'energy' ? ['oil', 'gas', 'coal'] : ['coal', 'gas', 'other_fossil'];
    const isos = new Set([...Object.keys(M?.data || {}), ...Object.keys(PWR)]);
    const rows = [...isos].map((i) => ({ i, m: M ? mixPt(MIXK, i) : null, p: PWR[i] })).filter((r) => (r.m || r.p) && (!qq || String(nm(r.i)).toLowerCase().includes(qq)))
      .sort((a, b) => (gdp[b.i] ?? -1) - (gdp[a.i] ?? -1) || String(nm(a.i)).localeCompare(String(nm(b.i))));
    rows.forEach((r) => {
      if (r.m) F.rel(M.rel, `${r.m.y}-07-01`, 'A', MIXK === 'energy' ? 'Energy use by source' : 'Electricity generation by source', MIXK === 'energy' ? 'U.S. Energy Information Administration' : 'Ember', true);
      if (r.p) { F.add(`${nm(r.i)} electricity demand`, r.p.chg); F.rel(r.p.rel || 'ember', r.p.date, 'M', 'Electricity demand', 'Ember'); }
    });
    const fos = (m) => m.order.reduce((a, k, j) => a + (FOS.includes(k) ? m.s[j] : 0), 0);
    const top = (m) => { let j = 0; m.s.forEach((v, n) => { if (v > m.s[j]) j = n; }); return `${MIXLAB[m.order[j]]} ${num(m.s[j], 0)}%`; };
    $('mixleg').innerHTML = M ? `<div class="mixleg mono small">${M.order.map((k) => `<span class="mixk"><i style="background:${MIXCOL[k]}"></i>${MIXLAB[k]}</span>`).join('')}</div>` : '';
    const NA_ = '<span class="na">—</span>';
    $('mixtbl').innerHTML = rows.length ? table(['Country', 'Split by source', 'Fossil', 'Low-carbon', 'Year', 'Power demand', 'Trend'], rows.map((r) => {
      const f = r.m ? fos(r.m) : null;
      return `<tr class="click" data-iso="${r.i}"><td>${esc(nm(r.i))}</td><td>${r.m ? `<div class="mixcell" title="${esc(top(r.m))} is the largest source">${mixBar(r.m, 12)}</div>` : NA_}</td><td>${r.m ? num(f, 0) + '%' : NA_}</td><td>${r.m ? num(100 - f, 0) + '%' : NA_}</td><td>${r.m ? r.m.y : NA_}</td>`
        + `<td>${r.p ? `${num(r.p.twh, 1)} TWh <span class="na mono small">${esc(String(r.p.date).slice(0, 7))}</span>${chg(r.p.chg)}` : NA_}</td><td>${r.p ? spark(r.p.spark, 80, 22) : ''}</td></tr>`;
    })) : (isos.size ? '<p class="sub na" style="padding:14px">No country matches.</p>' : '<p class="sub" style="padding:14px">Fills in on the next automated run.</p>');
    $('mixtbl').querySelectorAll('tr[data-iso]').forEach((tr) => tr.addEventListener('click', () => openCountry(tr.dataset.iso)));
    $('f-mix').innerHTML = F.html() + `<div class="foot"><p class="fn">${MIXK === 'energy' ? 'Energy use: primary energy consumption as measured by the EIA (quadrillion Btu), split into oil, natural gas, coal, nuclear and renewables.' : 'Electricity: generation (TWh) by source; low-carbon is nuclear plus renewables.'} Shares computed by this site; latest year each country has (figures more than ${DEV_MAX_AGE} years old are left out)${D === LIVE ? '' : '; for past dates, a figure for year Y counts as published on July 1 of Y+1'}. Electricity demand change compares the latest 3 months with the same 3 months ${PI < 3 ? '1 year or more' : PWORD[PI]} earlier (not seasonally adjusted, so shorter periods are not shown). Tap a country for its full readout.</p></div>`;
  }
  $('mixsel')?.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { MIXK = b.dataset.m; renderMix(); }));
  $('mq')?.addEventListener('input', () => renderMix());
  $('dq')?.addEventListener('input', () => renderDev());
  $('devmap')?.addEventListener('click', () => { layer = 'dev'; document.querySelectorAll('#layers button').forEach((b) => b.classList.toggle('on', b.dataset.l === 'dev')); DSC = null; paint(); $('map').scrollIntoView({ behavior: 'smooth', block: 'start' }); });
  loadDev().then(() => { if (!D) return; renderDev(); renderMix(); if (LAYERS[layer]?.dev) paint(); try { if (openIdx !== null) showDetail(openIdx); } catch (e) { /* economies not set up yet */ } });
  const viewYear = () => +String(D.asof_view || D.asof?.today || new Date().toISOString()).slice(0, 4);
  const LAYER_SRC = { score: 'Score', gdp: 'GDP growth', inflation: 'Inflation', unemployment: 'Unemployment', debt: 'Government debt', ca: 'Current account', tb: 'Trade balance', power: 'Electricity demand', trade: 'Port cargo', poverty: 'Extreme poverty', get dev() { return DV?.keys?.[DKEY]?.label || 'Development'; } };
  let layer = 'score', paths, cpG, proj, drawCP = () => {};
  const tip = $('tip');
  // tooltip next to the cursor, flipped above or to the left when it would run off the map
  function showTip(ev, html) {
    const r = $('map').getBoundingClientRect(); tip.innerHTML = html; tip.style.opacity = 1;
    const x = ev.clientX - r.left, y = ev.clientY - r.top, w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, x + 14 + w > r.width - 8 ? x - 14 - w : x + 14) + 'px';
    tip.style.top = Math.max(8, y + 14 + h > r.height - 8 ? y - 14 - h : y + 14) + 'px';
  }
  const hideTip = () => { tip.style.opacity = 0; };
  function mapFoot() {
    const L = LAYERS[layer], F = foot();
    if (L.dev) {
      const k = L.dev === true ? DKEY : L.dev, K = DV?.keys?.[k];
      if (K) for (const r of Object.values(D.map || {})) { const x = devPt(r.iso3, k); if (x) F.rel(K.rel, `${x.y}-07-01`, 'A', K.label, devSrcName(K)); }
      D.rel = Object.assign({}, DV?.rel || {}, D.rel || {});
      $('f-map').innerHTML = `<p class="fl">MAP COLORS · ${esc(LAYER_SRC[layer].toUpperCase())} (LATEST PUBLISHED YEAR PER COUNTRY; YEARS DIFFER)</p>` + F.html();
      return;
    }
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
      if (yrs) {
        const anyK = layer === 'tb' ? 'wb:NE.RSB.GNFS.ZS' : 'weo', vd = String(D.asof_view || D.asof?.today || '').slice(5, 10), y = viewYear();
        const yr = layer === 'tb' ? (vd >= '07-01' ? y - 1 : y - 2) : (vd >= '10-15' ? y : y - 1);   // latest year each source has out on the view date
        F.rel(anyK, `${yr}-07-01`, 'A', 'Annual figures', layer === 'tb' ? 'World Bank' : 'IMF WEO');
      }
    }
    if (layer === 'score') F.rel('site', D.generated_at, 'D', 'Scores (computed by this site from the series below)', 'World Economy Live');
    $('f-map').innerHTML = `<p class="fl">MAP COLORS · ${esc(LAYER_SRC[layer].toUpperCase())} (CURRENT VALUES) · TOOLTIP CHANGES OVER ${PERS[PI]}</p>` + F.html();
  }
  function paint() {
    if (LAYERS[layer].dev && !DV) { loadDev().then(paint); return; }
    const L = LAYERS[layer], lg = typeof L.legend === 'function' ? L.legend() : L.legend;
    if (paths) paths.attr('fill', (d) => { const r = D.map?.[fid(d)]; return r ? L.color(L.get(r)) : '#0d0f12'; });
    $('legend').innerHTML = `<span>${lg[0]}</span><span class="ramp" style="background:linear-gradient(90deg,${L.ramp.join(',')})"></span><span>${lg[2]}</span>${layer === 'power' || layer === 'trade' ? '<span class="na">· vs a year ago</span>' : ''}`;
    document.querySelectorAll('#layers button').forEach((b) => b.classList.toggle('on', b.dataset.l === layer));
    mapFoot();
  }
  document.querySelectorAll('#layers button').forEach((b) => b.addEventListener('click', () => { layer = b.dataset.l; paint(); }));
  const tipLine = (lab, val, o, good, abs) => `<br>${lab} ${val}${o ? ' <span class="tc">' + (ctext(o, abs) ?? 'n/a') + '</span>' : ''}`;
  try {
    const world = await (await fetch('vendor/countries-110m.json')).json();
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
        const r = D.map?.[fid(d)], c = r?.c || {};
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
          const L_ = LAYERS[layer];
          if (L_.dev) { const k = L_.dev === true ? DKEY : L_.dev, x = devPt(r.iso3, k); h += `<br><b>${esc(DV?.keys?.[k]?.label || '')}</b> ${x ? devFmt(k, x.v) + ` <span class="tc">${x.y}</span>` : '<span class="tc">not published</span>'}`; }
          if (!r.tracked) h += `<br><span style="color:#5f646d">${r.basis === 'annual' ? 'score from completed-year annual data' + (c.trade || c.power ? ' + live port/power data' : '') : 'annual data (IMF/World Bank)'}</span>`;
          if (!ok(r.score)) h += `<br><span style="color:#5f646d">no score · tap for the data the site has</span>`;
        } else h += '<br><span style="color:#5f646d">No data available</span>';
        showTip(ev, h);
      })
      .on('mouseleave', () => { hideTip(); hl.style('opacity', 0); })
      .on('click', (ev, d) => { const r = D.map?.[fid(d)]; if (r) openCountry(r.iso3); });
    paths.style('cursor', (d) => (D.map?.[fid(d)] ? 'pointer' : 'default'));
    cpG = svg.append('g');
    drawCP = () => { cpG.selectAll('*').remove(); drawChokepoints(); };
    drawChokepoints();
  } catch (e) { $('globe').innerHTML = '<p class="sub" style="padding:120px 30px;text-align:right">Map unavailable.</p>'; }
  function drawChokepoints() {
    if (!cpG || !proj) return;
    const cps = (T?.chokepoints || []).filter((c) => ok(c.lon));
    cps.forEach((c) => {
      const [x, y] = proj([c.lon, c.lat]), r = 2.5 + Math.min(6, Math.sqrt(c.daily_transits || 1) / 2);
      const col = div(c.transits_yoy, 40);
      cpG.append('circle').attr('class', 'cpring').attr('cx', x).attr('cy', y).attr('r', 3).attr('stroke', col);
      cpG.append('circle').attr('class', 'cp').attr('cx', x).attr('cy', y).attr('r', r).attr('fill', col)
        .on('mousemove', (ev) => showTip(ev, `<b>${esc(c.name)}</b><br>${num(c.daily_transits, 0)} ships/day<br>${sg(c.transits_yoy, 0)} vs a year ago${PI !== 3 ? `<br><span class="tc">${ctext(c.chg) ?? 'n/a'} over ${PERS[PI]}</span>` : ''}`)).on('mouseleave', hideTip);
    });
  }

  // ---------------- economies (grid + detail) ----------------
  const PIL = { activity: 'ACT', labor: 'JOBS', prices: 'PRICE', trade: 'TRADE' };
  let filt = 'g20', q = '', openIdx = null;
  let READF = null;   // the open readout's footnote, joined with the year-by-year one at the end of the readout
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
      .filter(([k]) => ok(m[k]) || k === 'sahm').map(([k, l, f]) => (k === 'sahm' && !ok(m[k]) ? fact(l, '<span class="na">n/a</span>', 'NEEDS MONTHLY UNEMPLOYMENT')
        : fact(l, f(m[k]), k === 'sahm' ? (m[k] >= 0.5 ? 'RECESSION SIGNAL' : 'NO SIGNAL (NEEDS 0.5)') : ''))).join('');
    const vit = [['population', 0], ['life_exp', 1], ['age65', 0], ['fertility', 0], ['health_spend', 0], ['net_migration', 0], ['urban', 0], ['gdp_pc', 1], ['gini', -1]].filter(([k]) => V[k])
      .map(([k]) => { F.rel(V[k].rel, `${V[k].year}-07-01`, 'A', V[k].label, 'World Bank');
        return fact(V[k].label, big(V[k].value) + (V[k].unit.startsWith('%') ? '%' : ''), `${esc(V[k].unit).toUpperCase()} · ${V[k].year}${ok(V[k].ten_years_ago) ? ' · 10Y AGO ' + big(V[k].ten_years_ago) : ''}`); }).join('');
    F.add('Score', e.score_chg);
    READF = F;
    $('detail').innerHTML = `<div class="detail"><div class="dtop"><button class="back" id="dback">← All economies</button><button class="back" id="dclose" aria-label="Close">✕</button></div><h3>${esc(e.name)}</h3><div class="score" style="font-size:56px">${ok(e.score) ? Math.round(e.score) : '—'}<small>/100</small></div>
      <div class="cc big">${chg(e.score_chg, 1) || ''} <span class="na mono small">over ${PERS[PI]}</span></div>
      <span class="pill ${esc(e.label)}">${esc(e.label)}</span><span class="mono small" style="margin-left:10px">${esc(e.coverage || '')} PILLARS</span>
      ${ok(e.score) ? '' : `<p class="plain"><b>Not scored:</b> fewer than two pillars available (output, jobs, prices, trade). ${(() => { const h = Object.entries({ activity: 'output', labor: 'jobs', prices: 'prices', trade: 'trade' }).filter(([k]) => ok(e.pillars?.[k])).map(([, v]) => v); return h.length ? `Available: ${h.join(', ')}.` : 'None of the four is available.'; })()}</p>`}
      <p class="plain">${esc(plain(e)) || 'Detailed data fills in after the first automated run.'}</p>
      ${e.contrib ? `<h3>What moved the score (points vs 50)</h3><div class="bars contrib">${Object.entries(e.contrib).map(([k, v]) => `<div class="row"><div>${esc(k)}</div>${bar(v, v < 0 ? 'var(--neg)' : 'var(--pos)', 25, sg(v, 0, ''))}</div>`).join('')}</div>` : ''}
      ${live ? `<h3>Live indicators</h3><ul class="facts">${live}</ul>` : ''}${mth ? `<h3>Formulas</h3><ul class="facts">${mth}</ul>` : ''}
      ${gov ? `<h3>Government and trade</h3><ul class="facts">${gov}</ul>` : ''}${vit ? `<h3>People and health</h3><ul class="facts">${vit}</ul>` : ''}${(() => { const dv = devFacts(e.iso3, F); return dv ? `<h3>Development and environment</h3><ul class="facts">${dv}</ul>` : ''; })()}${DV ? mixBlocks(e.iso3, F) : ''}
      <div class="dyr"><h3>Year by year</h3><select id="dysel" aria-label="Calendar year"></select></div><ul class="facts" id="dyfacts"></ul><div id="dyfoot"></div></div>`;
    detailYear(e.iso3);
  }
  // ---------------- readout for any country on the map ----------------
  function openCountry(iso3) {
    const i = E.findIndex((e) => e.iso3 === iso3);
    if (i >= 0) { filt = 'all'; renderGrid(); openDetail(i); return; }
    showCountry(iso3).then(() => requestAnimationFrame(() => $('detail').scrollIntoView({ behavior: 'smooth', block: 'start' })));
  }
  const NA = '<span class="na">n/a</span>';
  async function showCountry(iso3) {
    openIdx = null; document.querySelectorAll('.eco').forEach((b) => b.classList.remove('on'));
    await loadAnnual(); await loadDev();
    const r = Object.values(D.map || {}).find((x) => x.iso3 === iso3) || { iso3, name: iso3, c: {} }, c = r.c || {}, F = foot();
    const A = AN?.data?.[iso3] || {}, vy = viewYear(), kk = (k) => AK(iso3, k);
    const latest = (k) => { k = kk(k); const a = A[k]; if (!a) return null; for (let j = a[1].length - 1; j >= 0; j--) if (ok(a[1][j]) && a[0] + j <= vy) return { v: a[1][j], y: a[0] + j, k }; return null; };
    const series = (k) => { k = kk(k); const a = A[k]; if (!a || !window.WELEngine) return null; const t_ = [], v_ = []; a[1].forEach((x, j) => { if (ok(x) && a[0] + j <= vy) { t_.push(window.WELEngine.dn(a[0] + j, 7, 1)); v_.push(x); } }); return t_.length ? { t: t_, v: v_ } : null; };
    const achg = (k) => { const s = series(k); k = kk(k); return s ? A1(window.WELEngine.change(s, AN.keys[k]?.kind || 'pp', 'A')) : null; };
    const src = (k) => (AN.keys[kk(k)]?.rel === 'weo' ? 'IMF WEO' : 'WORLD BANK');
    const item = (lab, k, f, good = 0) => {
      const x = latest(k);
      if (!x) return fact(lab, NA, 'NOT PUBLISHED FOR THIS COUNTRY');
      const o = achg(k); k = kk(k); F.add(`${lab.toLowerCase()}`, o); F.rel(AN.keys[k]?.rel, `${x.y}-07-01`, 'A', lab, AN.keys[k]?.rel === 'weo' ? 'IMF World Economic Outlook' : 'World Bank');
      const est = AN.keys[k]?.rel === 'weo' && x.y >= AN.estimate_from;
      return fact(lab, f(x.v), `${x.y}${est ? ' EST' : ''} · ${src(k)}`, chg(o, good));
    };
    const X = latest('exports_usd_a'), Mx = latest('imports_usd_a'), tb = X && Mx && X.y === Mx.y ? X.v - Mx.v : null;
    const pw = D.power?.[iso3];
    if (pw) F.rel('ember', pw.date, 'M', 'Electricity demand', 'Ember');
    if (c.trade) { F.add('port cargo', c.trade); F.rel('portwatch', T?.window?.[1], 'D', 'Port cargo', 'IMF PortWatch'); }
    const out = [item('GDP growth', 'gdp_growth', (v) => sg(v), 1), item('Inflation', 'inflation_a', (v) => num(v) + '%', -1), item('Unemployment', 'unemployment_a', (v) => num(v) + '%', -1)].join('');
    const gov = [item('GDP', 'gdp_usd', usd, 1), item('Government debt', 'gov_debt', (v) => num(v, 0) + '% of GDP', -1), item('Budget balance', 'gov_balance', (v) => sg(v, 1, '% of GDP'), 1),
      item('Primary balance', 'primary_balance', (v) => sg(v, 1, '% of GDP'), 1), item('Current account', 'current_account', (v) => sg(v, 1, '% of GDP')),
      item('Exports, goods & services', 'exports_usd_a', usd, 1), item('Imports, goods & services', 'imports_usd_a', usd),
      fact('Trade balance (X − M)', ok(tb) ? usd(Math.abs(tb)) + (tb >= 0 ? ' surplus' : ' deficit') : NA, ok(tb) ? `${X.y} · WORLD BANK` : 'NOT PUBLISHED FOR THIS COUNTRY'),
      item('Net exports', 'net_exports', (v) => sg(v, 1, '% of GDP') + sd(v), 1), item('FX reserves', 'reserves_usd', usd)].join('');
    const live = [fact('Port cargo', ok(r.trade) ? sg(r.trade, 0) : NA, ok(r.trade) ? `28 DAYS Y/Y · TO ${esc(mdy(T?.window?.[1]))} · IMF PORTWATCH` : 'NO TRACKED PORTS', c.trade ? chg(c.trade, 1) : ''),
      fact('Electricity demand', pw ? sg(pw.yoy_3m) : NA, pw ? `3 MONTHS Y/Y · ${esc(String(pw.date).slice(0, 7))} · EMBER` : 'NOT IN EMBER DATA', pw ? chg(pw.chg, 1) : '')].join('');
    const ppl = [item('Population', 'population', big), item('Population growth', 'pop_growth', (v) => sg(v, 2)), item('Life expectancy', 'life_exp', (v) => num(v, 1) + ' years', 1),
      item('Aged 65+', 'age65', (v) => num(v, 1) + '%'), item('Births per woman', 'fertility', (v) => num(v, 2)), item('Health spending', 'health_spend', (v) => num(v, 1) + '% of GDP'),
      item('Net migration', 'net_migration', (v) => (v < 0 ? '−' : '+') + big(Math.abs(v))), item('Urban population', 'urban', (v) => num(v, 0) + '%'),
      item('GDP per person', 'gdp_pc', usd, 1), item('Inequality (Gini)', 'gini', (v) => num(v, 1), -1)].join('');
    const PN = ['output', 'jobs', 'prices', 'trade'], have = r.why || [];
    let top;
    if (ok(r.score)) {
      F.add('Score', c.score); F.rel('site', D.generated_at, 'D', 'Score (computed by this site)', 'World Economy Live');
      top = `<div class="score" style="font-size:56px">${Math.round(r.score)}<small>/100</small></div><div class="cc big">${chg(c.score, 1) || ''} <span class="na mono small">over ${PERS[PI]}</span></div>
        <span class="pill ${esc(r.label)}">${esc(r.label)}</span><span class="mono small" style="margin-left:10px">SCORED FROM COMPLETED-YEAR ANNUAL DATA (IMF WEO; WORLD BANK WHERE IMF HAS NONE)${c.trade || c.power ? ' + LIVE PORT/POWER DATA' : ''}</span>
        ${r.contrib ? `<h3>What moved the score (points vs 50)</h3><div class="bars contrib">${Object.entries(r.contrib).map(([k, v]) => `<div class="row"><div>${esc(k)}</div>${bar(v, v < 0 ? 'var(--neg)' : 'var(--pos)', 25, sg(v, 0, ''))}</div>`).join('')}</div>` : ''}`;
    } else {
      const old_ = Object.entries(r.why_old || {}).map(([k, y]) => `${k} (latest ${y})`);
      top = `<p class="plain"><b>Not scored:</b> fewer than two pillars available (${PN.join(', ')}). ${have.length ? `Available: ${esc(have.join(', '))}.` : 'None of the four is available.'}${old_.length ? ` Published but too old to score (scores use completed years no more than 2 years old): ${esc(old_.join(', '))}.` : ''}</p>`;
    }
    $('detail').innerHTML = `<div class="detail"><div class="dtop"><button class="back" id="dback">← Map</button><button class="back" id="dclose" aria-label="Close">✕</button></div><h3>${esc(r.name)}</h3>${top}
      <h3>Output, prices and jobs</h3><ul class="facts">${out}</ul><h3>Live activity</h3><ul class="facts">${live}</ul>
      <h3>Government and trade</h3><ul class="facts">${gov}</ul><h3>People and health</h3><ul class="facts">${ppl}</ul>${(() => { const dv = devFacts(iso3, F); return dv ? `<h3>Development and environment</h3><ul class="facts">${dv}</ul>` : ''; })()}${DV ? mixBlocks(iso3, F) : ''}
      <div class="dyr"><h3>Year by year</h3><select id="dysel" aria-label="Calendar year"></select></div><ul class="facts" id="dyfacts"></ul><div id="dyfoot"></div></div>`;
    READF = F;
    $('dback').addEventListener('click', () => $('map').scrollIntoView({ behavior: 'smooth', block: 'start' }));
    $('dclose').addEventListener('click', () => { $('detail').innerHTML = ''; $('map').scrollIntoView({ behavior: 'smooth', block: 'start' }); });
    await detailYear(iso3);
  }

  async function detailYear(iso) {
    await loadAnnual();
    if (!AN.years || !$('dysel')) return;
    if (YEAR === null || YEAR > AN.years[1] || YEAR < AN.years[0]) YEAR = Math.min(AN.years[1], AN.estimate_from - 1);
    const sel = $('dysel');
    sel.innerHTML = '';
    for (let y = AN.years[1]; y >= AN.years[0]; y--) sel.insertAdjacentHTML('beforeend', `<option value="${y}">${y}${y >= AN.estimate_from ? ' (est.)' : ''}</option>`);
    sel.value = String(YEAR);
    sel.onchange = () => { YEAR = +sel.value; detailYear(iso); renderYears(); };
    const star = YEAR >= AN.estimate_from ? '*' : '';
    const items = YCOLS.map(([k, l, f]) => { const x = anLag(iso, k, YEAR); return x ? fact(l, anCell(x, f, k, star), `${x.y}${x.lag ? ' · LATEST PUBLISHED' : ''} · ${AN.keys[x.k || k]?.rel === 'weo' ? 'IMF WEO' : 'WORLD BANK'}`) : ''; }).join('');
    $('dyfacts').innerHTML = items || `<li><div class="m">No annual data published for ${YEAR}.</div></li>`;
    { const yp = yearFootParts(YEAR, [iso]), all = foot().absorb(READF || foot()).absorb(yp.F);
      const relSrc = D.rel; D.rel = { ...(AN.rel || {}), ...(DV?.rel || {}), ...(relSrc || {}) };
      $('dyfoot').innerHTML = all.htmlc(yp.notes.map(esc)); D.rel = relSrc; }
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
    if (!$('schart')) return;
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
      + (scCol === 'score' ? `Weekly points. Before ${mdy(D.asof?.archive_start)} the score is rebuilt with today's method from data as published today; from then on it is the score as shown each day. ` : '') + 'Sources and release dates: see the note under the table.';
  }

  // ---------------- everything that follows the period toggle ----------------
  const v1 = (val, o, good = 0, abs) => `${val}${chg(o, good, abs)}`;
  // empty panel: live = waiting for the first run; past date = nothing published yet by that date
  const pend = (liveMsg) => (D === LIVE ? `<p class="sub" style="padding:14px">${liveMsg}</p>` : `<p class="sub na" style="padding:14px">n/a — no data published on or before ${mdy(D.asof_view || D.asof?.today)}; the series begins later (see the note).</p>`);
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

    // ticker: follows the toggle, same units and "per year" rule as everywhere else
    const tk = [], tch = (o, good = 0) => { const s = ctext(o); return `<em class="${s === null ? 'na' : good ? cls(o.v[PI], good > 0) : cls(o.v[PI])}">${s ?? 'n/a'} ${PERS[PI].toLowerCase()}</em>`; };
    (D.prices || []).filter((p) => ['Brent crude', 'Gold', 'Copper', 'Wheat', 'Asia LNG'].includes(p.name)).forEach((p) => tk.push(`<span>${esc(p.name.toUpperCase())}<b>${num(p.level, 2)}</b>${tch(p.chg)}</span>`));
    (M.fx || []).filter((f) => ['EUR', 'JPY', 'CNY', 'GBP'].includes(f.code)).forEach((f) => tk.push(`<span>${esc(f.pair)}<b>${num(f.latest, f.latest < 10 ? 4 : 2)}</b>${tch(f.chg)}</span>`));
    (M.rates || []).filter((r) => /10-year Treasury|Fed funds/.test(r.name)).forEach((r) => tk.push(`<span>${esc(r.name.toUpperCase())}<b>${num(r.latest, 2)}%</b>${tch(r.chg)}</span>`));
    if (T?.pc?.global?.total) tk.push(`<span>GLOBAL PORT CARGO ${tch(T.pc.global.total)}</span>`);
    $('ticker').innerHTML = tk.length ? tk.join('') + tk.join('') : '<span>Markets fill in on the first automated run.</span>';

    // what changed (not period-driven: a summary of recent changes)
    {
      $('drivers').innerHTML = (D.drivers || []).map((x) => `<li>${esc(x)}</li>`).join('') || '<li>Waiting for the first data run.</li>';
      const F = foot();
      (D.prices || []).forEach((p) => F.rel(p.rel, p.date, 'M', 'Commodity prices', 'World Bank Pink Sheet'));
      if (T?.window) F.rel('portwatch', T.window[1], 'D', 'Ships and port cargo', 'IMF PortWatch');
      E.forEach((e) => { const x = e.indicators?.unemployment; if (x && !x.annual && ok(e.math?.sahm)) F.rel(x.rel, x.date, x.chg?.f, 'Unemployment (Sahm rule)', x.source); });
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
          <td class="${ok(e.math?.sahm) && e.math.sahm >= 0.5 ? 'neg' : ''}">${ok(e.math?.sahm) ? v1(num(e.math.sahm, 2), mc.sahm, -1) : '<span class="na" title="The Sahm rule needs monthly unemployment">n/a</span>'}</td><td class="${cls(e.math?.curve)}">${v1(sg(e.math?.curve, 2, ''), mc.curve)}</td>
          <td class="${cls(e.trade_m?.balance_12m)}">${ok(e.trade_m?.balance_12m) ? v1(bn(Math.abs(e.trade_m.balance_12m)) + sd(e.trade_m.balance_12m), e.trade_m?.c?.balance_12m, 1, absBn) : '—'}</td></tr>`;
        }));
      F.rel('site', D.generated_at, 'D', 'Scores and formulas (computed by this site)', 'World Economy Live');
      const noSahm = E.filter((e) => !ok(e.math?.sahm)).map((e) => e.name);
      $('f-scorecard').innerHTML = F.html() + (noSahm.length ? `<div class="foot"><p class="fn">Sahm rule n/a — calculated only from monthly unemployment (3-month average vs its lowest 3-month average over the prior 12 months); no monthly series for ${esc(noSahm.join(', '))}.</p></div>` : '');
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
      }).join('')}</div>` : pend('Fills in on the first automated run.');
      $('f-comp').innerHTML = G.html();

      const H = foot();
      const dm = E.filter((e) => ok(e.derived?.r_minus_g));
      $('debtmath').innerHTML = dm.length ? table(['Economy', '10y yield (r)', 'Nominal growth (g)', 'r − g', 'Debt % GDP', 'Primary bal. needed', 'Actual primary bal.', 'Debt ratio'],
        dm.map((e) => { const d = e.derived, pb0 = F_(e, 'primary_balance'), pb = pb0 && { ...pb0, chg: A1(pb0.chg) }, dc = Object.fromEntries(Object.entries(e.dchg || {}).map(([k, o]) => [k, A1(o)])), lr0 = e.indicators?.long_rate, lr = lr0 && { ...lr0, chg: A1(lr0.chg) };
          [['10y yield', lr?.chg], ['nominal growth', dc.nominal_growth], ['r − g', dc.r_minus_g], ['debt', A1(F_(e, 'gov_debt')?.chg)], ['primary balance needed', dc.pb_stabilizing], ['primary balance', pb?.chg]].forEach(([n, o]) => H.add(`${e.name} ${n}`, o));
          if (lr) H.rel(lr.rel, lr.date, lr0.chg?.f, '10-year yields', lr.source);
          if (F_(e, 'gov_debt')) H.rel(F_(e, 'gov_debt').rel, `${F_(e, 'gov_debt').year}-07-01`, 'A', 'Debt and primary balance', F_(e, 'gov_debt').source);
          return `<tr><td>${esc(e.name)}</td><td>${v1(num(I_(e, 'long_rate'), 2) + '%', lr?.chg)}</td><td>${v1(num(d.nominal_growth) + '%', dc.nominal_growth)}</td><td class="${cls(d.r_minus_g, false)}">${v1(sg(d.r_minus_g, 1, ' pp'), dc.r_minus_g, -1)}</td><td>${v1(num(F_(e, 'gov_debt')?.value, 0) + '%', A1(F_(e, 'gov_debt')?.chg), -1)}</td>
            <td>${v1(sg(d.pb_stabilizing, 1), dc.pb_stabilizing)}</td><td>${v1(sg(pb?.value, 1), pb?.chg, 1)}</td><td>${!ok(d.fiscal_gap) ? '—' : d.fiscal_gap >= 0 ? '<span class="pill Strong">Falling</span>' : '<span class="pill Stressed">Rising</span>'}</td></tr>`; }))
        : pend('Needs bond yields, growth and inflation. Fills in on the first automated run.');
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
    } else {
      const st = LIVE.trade?.pc?.global?.total?.s;
      $('tradesub').textContent = "Cargo (metric tons) through each region's busiest ports.";
      ['heat', 'impexp', 'choke'].forEach((id) => { $(id).innerHTML = pend('Port data pending.'); });
      ['f-heat', 'f-impexp', 'f-choke'].forEach((id) => { $(id).innerHTML = D === LIVE ? '' : `<div class="foot"><p class="fn">n/a — history begins ${esc(st || '01/2019')}: IMF PortWatch port and chokepoint data.</p></div>`; });
    }

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
      } else { $('tradeusd').innerHTML = pend('Fills in on the next automated run.'); }
      $('f-tradeusd').innerHTML = F.html();
    }

    // energy & transport
    {
      const F = foot();
      renderMix();   // energy by country: split by source + electricity demand in one table
      const G = foot();
      const TR = [...(D.transport || []).map((r) => ({ country: r.country || 'United States', mode: r.name, latest: r.latest, unit: '', chg: r.chg, spark: r.spark, date: r.date, rel: r.rel || 'bts' })),
        ...(D.freight || []).sort((a, b) => a.mode.localeCompare(b.mode) || (b.latest ?? 0) - (a.latest ?? 0))];
      $('transport').innerHTML = TR.length ? table(['Country', 'Mode', 'Latest', 'Trend', 'Period'],
        TR.map((r) => { G.add(`${r.country} ${r.mode.toLowerCase()}`, r.chg); G.rel(r.rel, r.date, r.chg?.f, '', r.rel === 'bts' ? 'US Bureau of Transportation Statistics' : r.rel === 'statcan' ? 'Statistics Canada' : 'Eurostat');
          return `<tr><td>${esc(r.country)}</td><td>${esc(r.mode)}</td><td>${v1(big(r.latest) + (r.unit ? ' <span class="na">' + esc(r.unit) + '</span>' : ''), r.chg)}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(r.chg?.f === 'Q' ? plab(r.date, 'Q') : String(r.date).slice(0, 7))}</td></tr>`; }))
        : pend('Fills in on the next automated run.');
      $('f-transport').innerHTML = G.html() + '<div class="foot"><p class="fn">Like-for-like windows, not seasonally adjusted: US series compare the latest month with the same month in the earlier year; European air freight and Canadian rail compare the latest 3 months; European rail compares the latest quarter.</p></div>';
    }

    // commodities + ship types
    {
      const F = foot();
      $('prices').innerHTML = (D.prices || []).length ? table(['Commodity', 'Price', 'Unit', 'Trend', 'Month'],
        D.prices.map((p) => { F.add(p.name, p.chg); F.rel(p.rel || 'pink', p.date, 'M', '', 'World Bank Pink Sheet');
          return `<tr><td>${esc(p.name)}</td><td>${v1(num(p.level, p.level < 10 ? 2 : 1), p.chg)}</td><td class="na">${esc(p.unit || '')}</td><td>${p.spark ? spark(p.spark, 90, 22) : ''}</td><td class="na">${esc(String(p.date).slice(0, 7))}</td></tr>`; }))
        : pend('Fills in on the first automated run.');
      $('f-prices').innerHTML = F.html();
      const SHIP = [['tanker', 'Tankers — crude, fuel, gas, chemicals'], ['dry_bulk', 'Dry bulk — ores, coal, grain, fertilizer'],
        ['container', 'Containers — manufactured goods, coffee, cotton'], ['general_cargo', 'General cargo — steel, machinery'], ['roro', 'Ro-ro — cars and trucks'], ['total', 'All cargo']];
      const G = T?.pc?.global || {}, H = foot();
      $('shiptypes').innerHTML = SHIP.filter(([k]) => G[k]).map(([k, n]) => { H.add(n.split(' — ')[0], G[k]); const v = G[k].v?.[PI];
        return `<div class="row"><div>${n}<div class="m">${ctext(G[k]) ?? 'n/a'} over ${PERS[PI]}</div></div><div>${bar(v, 'var(--pos)', PI >= 4 ? 10 : 30, ok(v) ? sg(v, 0) : undefined)}</div></div>`; }).join('')
        || pend('Fills in on the next automated run.');
      if (T?.window) H.rel('portwatch', T.window[1], 'D', '', 'IMF PortWatch');
      $('f-ship').innerHTML = H.html();
    }

    // markets
    {
      const F = foot();
      $('fxnote').textContent = (M.fx_note || '') + ` "Currency vs USD" shows whether that currency gained (+) or lost (−) value against the dollar over ${PWORD[PI]}.`;
      $('fx').innerHTML = (M.fx || []).length ? table(['Pair', 'Means', 'Spot', 'Currency vs USD', '12 months', 'Date'], M.fx.map((r) => { F.add(r.pair, r.chg); F.add(`${r.code} vs USD`, r.ccy_chg); F.rel(r.rel || 'ecb', r.date, 'D', '', 'ECB');
        return `<tr><td class="mono">${esc(r.pair || r.name)}</td><td class="def">${esc(r.meaning || r.name)}</td><td>${v1(num(r.latest, r.latest < 10 ? 4 : 2), r.chg)}</td><td>${chg(r.ccy_chg, 1) || '—'}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(r.date)}</td></tr>`; })) : pend('Fills in on the first automated run.');
      $('f-fx').innerHTML = F.html();
      const G = foot(), GR = M.global_rates || [];
      $('grates').innerHTML = GR.length ? table(['Economy', 'Policy rate', '10-year yield', 'Real policy rate', 'Curve (10y − policy)', 'Source', 'Date'],
        GR.map((r) => { const c = r.c || {}; G.add(`${r.name} policy rate`, c.policy); G.add(`${r.name} 10-year`, c.long); G.add(`${r.name} real rate`, r.real_est ? null : c.real); G.add(`${r.name} curve`, c.curve);
          G.rel(r.rel, r.date, 'M', 'Policy rates', r.policy_src); if (r.rel_long) G.rel(r.rel_long, r.date, 'M', '10-year yields', 'OECD');
          return `<tr><td>${esc(r.name)}</td><td>${ok(r.policy) ? v1(num(r.policy, 2) + '%', c.policy) : '—'}</td><td>${ok(r.long) ? v1(num(r.long, 2) + '%', c.long) : '—'}</td><td class="${cls(r.real)}">${v1(sg(r.real, 2, '%') + (r.real_est ? '*' : ''), r.real_est ? { v: Array(9).fill(null), r: 'xxxxxxxxx' } : c.real)}</td><td class="${cls(r.curve)}">${v1(sg(r.curve, 2, ' pp'), c.curve)}</td><td class="na">${esc(r.policy_src || 'OECD')}</td><td class="na">${esc(String(r.date || '').slice(0, 7))}</td></tr>`; }))
        : pend('Fills in on the next automated run.');
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
        return `<tr><td>${esc(r.name)}</td><td>${v1(num(r.latest, 2), r.chg)}</td><td>${spark(r.spark, 90, 22)}</td><td class="na">${esc(r.date)}</td></tr>`; })) : pend('Fills in on the first automated run.');
      $('f-rates').innerHTML = H.html();
      const J = foot();
      $('usfiscal').innerHTML = (M.us_fiscal || []).map((r) => { J.add(r.name, r.chg); J.rel(r.rel || 'fiscaldata', r.date, 'D', '', 'US Treasury Fiscal Data');
        return `<h3>${esc(r.name)}</h3><div class="score" style="font-size:44px">${usd(r.latest)}</div><div class="cc big">${chg(r.chg, -1)} <span class="na mono small">over ${PERS[PI]}</span></div><p class="mono small">${esc(r.date)}</p>`; }).join('') + J.html();
      const FY = M.us_fy || [], K = foot();
      const mon = (d) => { const p = String(d).slice(0, 10).split('-'); return `${MON[+p[1] - 1]} ${p[0]}`; };
      $('usfy').innerHTML = FY.length ? table(['Fiscal year', 'Receipts', 'Outlays', 'Surplus / deficit', 'Debt at year end', 'Debt added in year'], FY.map((r) => {
        K.rel('mts', r.through, 'M', 'Receipts, outlays, surplus/deficit', 'US Treasury, Monthly Treasury Statement', true);
        if (r.debt_end) K.rel('fiscaldata', `${r.fy}-09-30`, 'D', 'Debt at fiscal year end', 'US Treasury Fiscal Data', true);
        return `<tr><td>FY${r.fy}${r.complete ? '' : `<div class="m na">to date, through ${esc(mon(r.through))}</div>`}</td><td>${usd(r.receipts)}</td><td>${usd(r.outlays)}</td><td class="${cls(r.balance)}">${usd(Math.abs(r.balance))}${sd(r.balance)}</td><td>${r.debt_end ? usd(r.debt_end) : '<span class="na">—</span>'}</td><td>${ok(r.debt_change) ? usd(r.debt_change) : '<span class="na">—</span>'}</td></tr>`; }))
        : pend('Fills in on the next automated run.');
      $('f-usfy').innerHTML = K.html() + '<div class="foot"><p class="fn">Fiscal years are not affected by the change-period toggle. Debt columns start where the daily debt series the site loads begins.</p></div>';
    }

    // people
    {
      const F = foot();
      const VK = [['population', 'Population'], ['pop_growth', 'Growth %'], ['life_exp', 'Life exp.'], ['age65', '65+ %'], ['fertility', 'Births/woman'], ['health_spend', 'Health % GDP'], ['net_migration', 'Net migration'], ['urban', 'Urban %'], ['gdp_pc', 'GDP/person $']];
      $('vitals').innerHTML = E.some((e) => Object.keys(e.vitals || {}).length) ? table(['Economy', ...VK.map((v) => v[1])], E.map((e) => `<tr><td>${esc(e.name)}</td>${VK.map(([k, l]) => { const x = e.vitals?.[k]; if (!x) return '<td>—</td>';
        F.add(`${e.name} ${l.toLowerCase()}`, x.chg); F.rel(x.rel, `${x.year}-07-01`, 'A', x.label, 'World Bank');
        return `<td>${v1(big(x.value), x.chg, 0, k === 'net_migration' ? absPeople : undefined)}</td>`; }).join('')}</tr>`)) : pend('Fills in on the first automated run.');
      $('f-vitals').innerHTML = F.html();
    }
  }

  // ---------------- year by year (calendar years; not period-dependent) ----------------
  let AN = null, YEAR = null, yfilt = 'g20', yq = '';
  // World Bank stand-ins where the IMF WEO has no series for a country
  const FBK = { gdp_growth: 'gdp_growth_wb', inflation_a: 'inflation_wb', unemployment_a: 'unemployment_wb', gdp_usd: 'gdp_usd_wb' };
  const AK = (iso, k) => (AN?.data?.[iso]?.[k] || !FBK[k] || !AN?.data?.[iso]?.[FBK[k]] ? k : FBK[k]);
  const anVal = (iso, k, y) => { k = AK(iso, k); const r = AN?.data?.[iso]?.[k]; if (!r) return null; const v = r[1][y - r[0]]; return ok(v) ? v : null; };
  // value for year y, or — when the source has not published y yet — its latest year, with that year as a marker
  const anLag = (iso, k, y) => {
    k = AK(iso, k);
    const v = anVal(iso, k, y); if (ok(v)) return { v, y, k };
    const r = AN?.data?.[iso]?.[k]; if (!r) return null;
    const lastY = r[0] + r[1].length - 1; if (lastY >= y) return null;
    for (let j = r[1].length - 1; j >= 0; j--) if (ok(r[1][j])) return { v: r[1][j], y: r[0] + j, lag: true, k };
    return null;
  };
  const anCell = (x, f, k, star) => (x ? f(x.v) + (AN.keys[x.k || k]?.rel === 'weo' && !x.lag ? star : '') + (x.lag ? ` <span class="na">(${x.y})</span>` : '') : '<span class="na">—</span>');
  const YCOLS = [['gdp_growth', 'GDP growth', (v) => sg(v), 1], ['inflation_a', 'Inflation', (v) => num(v) + '%', -1], ['unemployment_a', 'Unemployment', (v) => num(v) + '%', -1],
    ['gdp_usd', 'GDP', (v) => usd(v), 0], ['gov_debt', 'Gov. debt % GDP', (v) => num(v, 0), 0], ['gov_balance', 'Budget bal. % GDP', (v) => sg(v, 1, ''), 1],
    ['current_account', 'Current acct % GDP', (v) => sg(v, 1, ''), 1], ['net_exports', 'Trade bal. % GDP', (v) => sg(v, 1, '') + sd(v), 1],
    ['population', 'Population', (v) => big(v), 0], ['gdp_pc', 'GDP/person', (v) => usd(v), 0], ['life_exp', 'Life exp.', (v) => num(v, 1), 0]];
  async function loadAnnual() {
    if (AN) return AN;
    if (D !== LIVE) return (AN = { data: {} });
    try { AN = await (await fetch('data/annual.json', { cache: 'no-store' })).json(); } catch (_) { AN = { data: {} }; }
    return AN;
  }
  function yearFootParts(y, isos) {
    const F = foot('Year shown'), est = AN.estimate_from;
    let lagged = false;
    for (const [k, l] of YCOLS) {
      const meta = AN.keys?.[k]; if (!meta) continue;
      const used = new Set(isos.map((i) => anLag(i, k, y)).filter(Boolean).map((x) => x.y + '|' + (x.k || k)));
      for (const u of used) { const [uy, kk] = u.split('|'), mk = AN.keys?.[kk] || meta; F.rel(mk.rel, `${uy}-07-01`, 'A', l, mk.rel === 'weo' ? 'IMF World Economic Outlook' : 'World Bank'); }
      const ys = new Set([...used].map((u) => +u.split('|')[0]));
      if (ys.size > 1 || (ys.size && !ys.has(y))) lagged = true;
    }
    const notes = [`Year by year: calendar year ${y} (January–December), as ${D.rebuilt ? `known on ${mdy(D.asof_view)}, with figures as published today` : 'currently published by each source'}.`];
    if (lagged) notes.push(`Where a source has not published ${y} yet, its latest year is shown with that year in brackets, e.g. "81.2 (${y - 1})".`);
    if (y >= est) notes.push(`IMF figures for ${est} are current-year estimates (*); recent years can still be revised by the source.`);
    else if (y >= est - 2) notes.push('IMF figures for the most recent years can still be estimates for some countries and may be revised.');
    return { F, notes };
  }
  function yearFoot(y, isos) {
    const { F, notes } = yearFootParts(y, isos);
    const relSrc = D.rel; D.rel = { ...(AN.rel || {}), ...(relSrc || {}) };  // release dates from the same pipeline run
    const h = F.html(); D.rel = relSrc;
    return h + `<div class="foot">${notes.map((t) => `<p class="fn">${esc(t)}</p>`).join('')}</div>`;
  }
  async function renderYears() {
    await loadAnnual();
    if (!AN.years) { $('ytbl').innerHTML = pend('Fills in on the next automated run.'); return; }
    if (YEAR === null) YEAR = AN.estimate_from - 1;
    const sel = $('ysel');
    const sk = AN.years.join('-') + ':' + AN.estimate_from;
    if (sel.dataset.k !== sk) { sel.innerHTML = ''; sel.dataset.k = sk; for (let y = AN.years[1]; y >= AN.years[0]; y--) sel.insertAdjacentHTML('beforeend', `<option value="${y}">${y}${y >= AN.estimate_from ? ' (est.)' : ''}</option>`); }
    if (!sel.dataset.on) { sel.dataset.on = 1; sel.addEventListener('change', () => { YEAR = +sel.value; renderYears(); if (openIdx !== null) showDetail(openIdx); }); }
    if (YEAR > AN.years[1] || YEAR < AN.years[0]) YEAR = Math.min(AN.years[1], AN.estimate_from - 1);
    sel.value = String(YEAR);
    document.querySelectorAll('.yfil button').forEach((b) => b.classList.toggle('on', b.dataset.y === yfilt));
    const g20 = new Set(AN.g20 || []);
    const isos = Object.keys(AN.data).filter((i) => (yfilt === 'all' || g20.has(i) || yq) && (!yq || (AN.names[i] || '').toLowerCase().includes(yq)))
      .sort((a, b) => (anVal(b, 'gdp_usd', YEAR) ?? -1) - (anVal(a, 'gdp_usd', YEAR) ?? -1));
    const star = YEAR >= AN.estimate_from ? '*' : '';
    $('ytbl').innerHTML = isos.length ? table(['Country', ...YCOLS.map((c) => c[1])], isos.map((i) => `<tr><td>${esc(AN.names[i])}</td>${YCOLS.map(([k, , f, good]) => { const x = anLag(i, k, YEAR);
      return `<td class="${good && x ? cls(x.v, good > 0) : ''}">${anCell(x, f, k, star)}</td>`; }).join('')}</tr>`))
      : '<p class="sub" style="padding:14px">No match.</p>';
    $('f-years').innerHTML = yearFoot(YEAR, isos);
  }
  document.querySelectorAll('.yfil button').forEach((b) => b.addEventListener('click', () => { yfilt = b.dataset.y; renderYears(); }));
  $('yq').addEventListener('input', (ev) => { yq = ev.target.value.trim().toLowerCase(); renderYears(); });
  renderYears();

  // ---------------- date picker: the whole site as of a chosen date ----------------
  const ASOF = $('asof'), TODAY = String(LIVE.asof?.today || LIVE.generated_at || '').slice(0, 10), EARLY = LIVE.asof?.earliest, A0 = LIVE.asof?.archive_start;
  let PACKS = null, ARCHIDX = null, SER_LIVE = null, AN_LIVE = null, VIEW = TODAY;
  if (ASOF) { ASOF.max = TODAY; if (EARLY) ASOF.min = EARLY; ASOF.value = TODAY; }
  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-store' }); if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    const buf = new Uint8Array(await r.arrayBuffer());
    if (buf[0] === 0x1f && buf[1] === 0x8b) {
      if (typeof DecompressionStream === 'undefined') throw new Error('this browser cannot open archived snapshots');
      return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
    }
    return JSON.parse(new TextDecoder().decode(buf));
  }
  const dow = (ds) => new Date(ds + 'T00:00:00Z').getUTCDay();
  function banner(mode, ds, extra = '') {
    const b = $('asofban'); if (!b) return;
    const wk = dow(ds) === 0 || dow(ds) === 6 ? ' · a weekend: each panel shows the latest data on or before it' : '';
    const txt = mode === 'live' ? `Viewing ${mdy(ds)} · latest data`
      : mode === 'archive' ? `Viewing ${mdy(ds)} · as shown on that date${extra}${wk}`
      : mode === 'rebuilt' ? `Viewing ${mdy(ds)} · rebuilt from data as published today; figures include later revisions · each figure counts as released after its source's usual delay (see Method)${wk}`
      : mode === 'loading' ? `Loading ${mdy(ds)}…` : extra;
    b.textContent = txt; b.title = txt; b.className = 'asofban mono ' + mode;
  }
  async function goDate(ds) {
    if (!ds || ds >= TODAY) ds = TODAY;
    let note = '';
    if (EARLY && ds < EARLY) { note = ` (earliest date with a score: ${mdy(EARLY)})`; ds = EARLY; }
    if (ASOF) ASOF.value = ds;
    VIEW = ds;
    try { const u = new URL(location.href); if (ds === TODAY) u.searchParams.delete('date'); else u.searchParams.set('date', ds); history.replaceState(null, '', u); } catch (_) { /* file:// */ }
    banner('loading', ds);
    let mode = 'live', extra = '';
    try {
      if (ds === TODAY) { if (SER && D !== LIVE) SER = SER_LIVE; D = LIVE; SER = SER_LIVE; AN = AN_LIVE; }
      else {
        if (D === LIVE) { SER_LIVE = SER; AN_LIVE = AN; }
        if (A0 && ds >= A0 && !ARCHIDX) ARCHIDX = await getJSON('data/archive/index.json').catch(() => ({ dates: {} }));
        const snaps = A0 && ds >= A0 ? Object.keys(ARCHIDX?.dates || {}).filter((x) => x <= ds).sort() : [];
        if (snaps.length) {
          const sd = snaps[snaps.length - 1], rec = ARCHIDX.dates[sd];
          const [h, s, a] = await Promise.all([getJSON('data/archive/' + rec.h), getJSON('data/archive/' + rec.s).catch(() => ({})), getJSON('data/archive/' + rec.a).catch(() => ({ data: {} }))]);
          D = h; SER = s; AN = a; mode = 'archive';
          for (const e of D.economies || []) if (e.history?.length) (SER[e.iso3] = SER[e.iso3] || {}).score = e.history.map(([x, v]) => [x, Math.round(v * 10) / 10]);
          if (sd !== ds) extra = ` (snapshot of ${mdy(sd)}, the latest on or before it)`;
        } else {
          if (!PACKS) { banner('loading', ds); PACKS = await window.WELEngine.loadPacks(); }
          await new Promise((r) => setTimeout(r, 0));
          const R = window.WELEngine.build(PACKS, ds, LIVE);
          D = R.D; SER = R.SER; AN = R.AN; mode = 'rebuilt';
        }
      }
    } catch (err) {
      D = LIVE; SER = SER_LIVE; AN = AN_LIVE; ds = TODAY; if (ASOF) ASOF.value = TODAY;
      bind(); refresh(); banner('error', ds, `Could not load that date (${err.message}). Showing ${mdy(TODAY)}.`); return;
    }
    bind(); refresh();
    banner(mode, ds, extra + note);
  }
  function refresh() {
    openIdx = null; $('detail').innerHTML = '';
    drawCP(); renderAll(); renderYears(); renderDev(); renderMix();
    if (scIso && $('schart').innerHTML) showHist(scIso);
  }
  if (ASOF) {
    ASOF.addEventListener('change', () => goDate(ASOF.value));
    $('asofnow')?.addEventListener('click', () => goDate(TODAY));
  }

  // period toggle
  $('period').innerHTML = PERS.map((p, i) => `<button data-p="${i}" title="Change over ${PWORD[i]}">${p}</button>`).join('');
  document.querySelectorAll('#period button').forEach((b) => b.addEventListener('click', () => {
    PI = +b.dataset.p;
    try { localStorage.setItem('wel-period', PERS[PI]); } catch (_) { /* storage unavailable */ }
    renderAll();
  }));
  renderAll();
  banner('live', TODAY);
  { const q0 = new URLSearchParams(location.search).get('date'); if (q0 && /^\d{4}-\d{2}-\d{2}$/.test(q0) && q0 < TODAY) goDate(q0); }

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
    ['Sahm rule', '\\bar{u}_{3m,t} - \\min_{t-12 \\le s \\le t-1}\\bar{u}_{3m,s} \\geq 0.5', 'A recession signal when the 3-month average of monthly unemployment rises 0.5 points or more above its lowest 3-month average over the prior 12 months. Monthly data only; n/a where a country has no monthly unemployment series.'],
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
  // the change-period toggle only shows in sections whose figures follow it (the date picker always shows)
  const PERSEC = new Set(['scorecard', 'fundamentals', 'trade', 'energy', 'commodities', 'markets', 'people']);
  // when the section links don't fit across the header, they move into a Sections menu
  const nav = document.querySelector('header.bar nav'), btn = document.getElementById('navbtn');
  // links in a row if they fit; then a tighter row (smaller spacing, update time hidden); only then the Sections menu
  const fit = () => {
    document.body.classList.remove('navmenu', 'navtight'); nav.classList.remove('open'); btn.setAttribute('aria-expanded', 'false');
    const fits = () => { const gap = parseFloat(getComputedStyle(nav).columnGap) || 0;
      return links.reduce((s, a) => s + a.getBoundingClientRect().width, 0) + gap * (links.length - 1) <= nav.clientWidth + 1; };
    if (!fits()) { document.body.classList.add('navtight'); if (!fits()) { document.body.classList.remove('navtight'); document.body.classList.add('navmenu'); } }
    hdrVar();
  };
  // sections stop just below the header, whatever its height
  const hdrVar = () => document.documentElement.style.setProperty('--hdr', document.querySelector('header.bar').offsetHeight + 'px');
  btn.addEventListener('click', (ev) => { ev.stopPropagation(); const o = nav.classList.toggle('open'); btn.setAttribute('aria-expanded', String(o)); });
  links.forEach((a) => a.addEventListener('click', () => { nav.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }));
  document.addEventListener('click', (ev) => { if (!nav.contains(ev.target)) { nav.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); } });
  addEventListener('resize', fit); fit(); document.fonts?.ready.then(fit);
  // a jump from the section links: let it finish before the header row may change height, then settle on the section
  let jumping = 0;
  links.forEach((a) => a.addEventListener('click', (ev) => {
    const sec = document.getElementById(a.getAttribute('href').slice(1)); if (!sec) return;
    ev.preventDefault(); clearTimeout(jumping);
    sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const done = () => { clearTimeout(jumping); jumping = 0; removeEventListener('scrollend', done); pick(); requestAnimationFrame(() => sec.scrollIntoView({ behavior: 'instant', block: 'start' })); history.replaceState(null, '', location.pathname + location.search + '#' + sec.id); };
    addEventListener('scrollend', done); jumping = setTimeout(done, 1600);
  }));
  const set = (id) => { links.forEach((a) => a.classList.toggle('on', a === byId[id]));
    if (byId[id]) btn.textContent = byId[id].textContent + ' ▾';
    const hdr = document.querySelector('header.bar'), h0 = hdr.offsetHeight;
    document.body.classList.toggle('noper', !PERSEC.has(id));
    const dh = hdr.offsetHeight - h0;            // keep the page still when the header row appears or goes (narrow screens)
    if (dh && scrollY > 0 && !jumping) window.scrollBy({ top: dh, behavior: 'instant' });
    if (dh) hdrVar();
    const a = byId[id], n = a && a.parentNode;
    if (n && n.scrollWidth > n.clientWidth) n.scrollTo({ left: a.offsetLeft - n.offsetLeft - n.clientWidth / 2 + a.offsetWidth / 2, behavior: 'smooth' }); };
  let ticking = false;
  const pick = () => { ticking = false; let cur = secs[0]?.id;
    const lim = document.querySelector('header.bar').offsetHeight + 12;
    for (const sec of secs) if (sec.getBoundingClientRect().top <= lim) cur = sec.id;
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
