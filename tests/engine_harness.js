// Runs the browser engine under Node for tests/test_engine_js.py.
// Usage: node engine_harness.js <power.json> <jobs.json>
const fs = require('fs');
const E = require('../cassandra/web/engine.js');
const rows = E.parsePower(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
const jobs = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = jobs.map(j => {
  if (j.kind === 'analyse') {
    const r = E.analyse(rows, j.variable, j.season, { N: 1000, seed: E.hashSeed(JSON.stringify(j)), cutoff: j.cutoff });
    return { p: r.test.p, real: r.test.real, phi: r.test.fit.phi, sigma: r.test.fit.sigma, trend: r.trend_per_decade,
             shift: r.recent_shift, n: r.n_years, last: r.last_year, normal: r.normal, verdict: r.verdict.key };
  }
  if (j.kind === 'forecast') {
    try { return E.forecast(rows, j.variable, j.season, j.year, j.cutoff); } catch (e) { return { error: e.message }; }
  }
  if (j.kind === 'hindcast') { const h = E.hindcasts(rows, j.variable, j.season, 1996); return { n: h.n, rpss: h.rpss }; }
  if (j.kind === 'gamma') { const tot = E.seasonal(rows, r => r.p, j.season, 'sum');
    const base = tot.values.filter((v, i) => tot.years[i] >= 1981 && tot.years[i] <= 2010);
    const f = new E.GammaFit(base); return { a: f.a, scale: f.scale, spi: tot.values.map(v => f.spi(v)), inv: f.inverse(0.7) }; }
});
process.stdout.write(JSON.stringify(out));
