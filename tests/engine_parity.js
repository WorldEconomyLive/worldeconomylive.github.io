// Parity test: the browser engine, run for today with every release delay set to zero, must reproduce the
// heartbeat the Python pipeline wrote (same values, same change objects, same n/a reasons).
// Usage: node tests/engine_parity.js [packs dir] [heartbeat.json]
const fs = require('fs'), path = require('path'), vm = require('vm');
const dir = process.argv[2] || path.join(__dirname, 'mock_site/data/packs');
const hbPath = process.argv[3] || path.join(__dirname, 'mock_heartbeat.json');
const ctx = { window: {}, console, fetch: async (u) => ({ ok: true, json: async () => JSON.parse(fs.readFileSync(path.join(dir, path.basename(u)))) }) };
vm.createContext(ctx); vm.runInContext(fs.readFileSync(path.join(__dirname, '../site/engine.js'), 'utf8'), ctx, { filename: 'engine.js' });
const E = ctx.window.WELEngine;
(async () => {
  const P = await E.loadPacks(dir + '/');
  const live = JSON.parse(fs.readFileSync(hbPath));
  P.meta.asof = { ...P.meta.asof, lags: Object.fromEntries(Object.keys(P.meta.asof.lags).map((k) => [k, 0])), default_lag: 0, weo_md: [1, 1], wb_md: [1, 1], port_lag: 0 };
  const { D } = E.build(P, live.asof.today, live);
  let n = 0, bad = 0; const out = [];
  const near = (a, b) => Math.abs(a - b) <= 2e-3 + 2e-3 * Math.max(Math.abs(a), Math.abs(b));
  const SKIP = new Set(['pillars', 'contrib', 'coverage', 'label', 'history', 'rel', 'status', 'coverage', 'asof', 'generated_at', 'weo_release', 'weekly', 'ports', 'mix', 'spark', 'field', 'policy_src', 'why', 'z']);
  function cmp(a, b, p) {
    if (SKIP.has(p.split('.').pop())) return;
    if (typeof a === 'number' || typeof b === 'number') { n++; if (!(typeof a === 'number' && typeof b === 'number' && near(a, b)) && !(a == null && b == null)) { bad++; if (out.length < 40) out.push(`${p}: python ${a} js ${b}`); } return; }
    if (a === null || b === null || a === undefined || b === undefined) { if ((a ?? null) !== (b ?? null)) { n++; bad++; if (out.length < 40) out.push(`${p}: python ${JSON.stringify(a)?.slice(0, 80)} js ${JSON.stringify(b)?.slice(0, 80)}`); } return; }
    if (typeof a === 'string' || typeof a === 'boolean') { n++; if (String(a) !== String(b)) { bad++; if (out.length < 40) out.push(`${p}: python ${a} js ${b}`); } return; }
    if (Array.isArray(a)) { if (!Array.isArray(b) || a.length !== b.length) { n++; bad++; if (out.length < 40) out.push(`${p}: length python ${a.length} js ${b?.length}`); return; } a.forEach((x, i) => cmp(x, b[i], `${p}.${i}`)); return; }
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) cmp(a[k], b[k], `${p}.${k}`);
  }
  const by = (arr, k) => Object.fromEntries((arr || []).map((x) => [x[k], x]));
  cmp(by(live.economies, 'iso3'), by(D.economies, 'iso3'), 'economies');
  cmp(live.map, D.map, 'map');
  cmp(by(live.prices, 'name'), by(D.prices, 'name'), 'prices');
  cmp(by(live.markets.fx, 'code'), by(D.markets.fx, 'code'), 'fx');
  cmp(by(live.markets.rates, 'name'), by(D.markets.rates, 'name'), 'rates');
  cmp(live.markets.curve, D.markets.curve, 'curve');
  cmp(live.markets.us_fy, D.markets.us_fy, 'us_fy');
  cmp(live.markets.us_fiscal, D.markets.us_fiscal, 'us_fiscal');
  cmp(by(live.markets.global_rates, 'iso3'), by(D.markets.global_rates, 'iso3'), 'global_rates');
  cmp({ ...live.trade, regions: by(live.trade.regions, 'region'), chokepoints: by(live.trade.chokepoints, 'name') }, { ...D.trade, regions: by(D.trade.regions, 'region'), chokepoints: by(D.trade.chokepoints, 'name') }, 'trade');
  cmp(by(live.transport, 'name'), by(D.transport, 'name'), 'transport');
  cmp(by(live.freight, 'iso3' + 'mode'), by(D.freight, 'iso3' + 'mode'), 'freight');
  cmp(live.trade_totals, D.trade_totals, 'trade_totals');
  cmp(live.world, D.world, 'world');
  cmp(live.drivers, D.drivers, 'drivers');
  cmp(live.power, D.power, 'power');
  console.log(out.join('\n'));
  console.log(`compared ${n} values · mismatches ${bad}`);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
