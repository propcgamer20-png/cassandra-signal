/* Runs the heavy maths off the page's main thread. */
importScripts('engine.js');
var E = self.CassandraEngine, cache = {};

self.onmessage = function (ev) {
  var msg = ev.data, say = function (step) { self.postMessage({ id: msg.id, type: 'progress', step: step }); };
  try {
    if (msg.cmd === 'analyse') {
      var rows = cache[msg.key] || (cache[msg.key] = E.parsePower(msg.raw));
      var o = msg.opts, seed = E.hashSeed(msg.key + '|' + o.variable + '|' + o.season + '|' + (o.cutoff ? o.cutoff.join('-') : 'all'));
      say('anomalies');
      var res = E.analyse(rows, o.variable, o.season, { N: 1000, seed: seed, cutoff: o.cutoff, robust: false });
      if (res.insufficient) { self.postMessage({ id: msg.id, type: 'done', result: res }); return; }
      say('robust');
      var ri = E.nullTest(E.seasonalSeries(E.truncate(rows, o.cutoff), o.variable, o.season).stat, res.arrays.years,
                          'iaaft', 300, E.makeRng(seed + 1), false);
      res.robustness = { iaaft: { p: ri.p, outside: ri.outside, N: ri.N, verdict: ri.verdict.key } };
      say('forecast');
      var lastYear = res.last_year, target = lastYear + 1;
      try { res.forecast = E.forecast(rows, o.variable, o.season, target, o.cutoff); } catch (e) { res.forecast = { error: e.message }; }
      if (o.cutoff && res.forecast && !res.forecast.error && res.after && res.after.years[0] === target) {
        var sv = E.seasonal(rows, o.variable === 'T' ? function (r) { return r.t; } : function (r) { return r.p; },
                            o.season, o.variable === 'T' ? 'mean' : 'sum');
        var v = sv.values[sv.years.indexOf(target)], ed = res.forecast.tercile_edges;
        res.forecast.observed_value = v;
        res.forecast.observed = v < ed[0] ? 'below' : v > ed[1] ? 'above' : 'near';
      }
      var h = E.hindcasts(rows, o.variable, o.season, 1996, o.cutoff ? o.cutoff[0] : null);
      res.hindcast = { n: h.n, rpss: h.rpss, hit_rate: h.hit_rate, first_year: h.first_year, last_year: h.last_year };
      res.seed = seed;
      self.postMessage({ id: msg.id, type: 'done', result: res });
    } else if (msg.cmd === 'selfcheck') {
      var out = {};
      ['none', 'real'].forEach(function (which, k) {
        out[which] = E.selfCheck(msg.fit, msg.years, { M: 200, N: 200, seed: msg.seed + 11 + k,
          trendPerYear: which === 'none' ? 0 : msg.trendPerYear,
          onProgress: function (f) { self.postMessage({ id: msg.id, type: 'progress', step: which, fraction: f }); } });
      });
      self.postMessage({ id: msg.id, type: 'done', result: out });
    }
  } catch (err) {
    self.postMessage({ id: msg.id, type: 'error', message: String(err && err.message || err) });
  }
};
