/* Cassandra Signal engine: the same method as the Python pipeline
 * (cassandra/climate.py, stats.py, analysis.py, forecasts.py), for browsers,
 * web workers and Node. The random number generator differs from NumPy's, so
 * p-values can differ slightly from the published cards; everything else is
 * computed identically. tests/test_engine_js.py checks the two agree.
 */
(function (root) {
  'use strict';

  var BASELINE = [1981, 2010];
  var LETTERS = 'JFMAMJJASONDJFMAMJJASOND';
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var VERDICTS = [
    [0.001, 'no_alibi', 'Natural variation has no alibi', 'red'],
    [0.01, 'very_unlikely', 'Very unlikely to be natural variation alone', 'red'],
    [0.05, 'probable', 'Probably a real change', 'amber'],
    [1.01, 'not_yet', 'Not yet distinguishable from natural variation', 'grey']
  ];
  var MIN_SEASONS = 15;

  // ------------------------------------------------------------ random numbers
  function hashSeed(str) {               // FNV-1a, 32-bit
    var h = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193); }
    return h >>> 0;
  }
  function makeRng(seed) {               // sfc32 seeded through splitmix32
    var s = seed >>> 0;
    function sm() { s = (s + 0x9e3779b9) | 0; var z = s; z = Math.imul(z ^ (z >>> 16), 0x85ebca6b);
      z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35); return (z ^ (z >>> 16)) >>> 0; }
    var a = sm(), b = sm(), c = sm(), d = sm(), spare = null;
    function u() {
      a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0;
      var t = (a + b) | 0; a = b ^ (b >>> 9); b = (c + (c << 3)) | 0; c = (c << 21) | (c >>> 11);
      d = (d + 1) | 0; t = (t + d) | 0; c = (c + t) | 0;
      return ((t >>> 0) + 0.5) / 4294967296;
    }
    function normal() {
      if (spare !== null) { var r = spare; spare = null; return r; }
      var x, y, s2;
      do { x = 2 * u() - 1; y = 2 * u() - 1; s2 = x * x + y * y; } while (s2 >= 1 || s2 === 0);
      var m = Math.sqrt(-2 * Math.log(s2) / s2); spare = y * m; return x * m;
    }
    function gamma(k) {                   // Marsaglia-Tsang, shape k, scale 1
      if (k < 1) return gamma(k + 1) * Math.pow(u(), 1 / k);
      var dd = k - 1 / 3, cc = 1 / Math.sqrt(9 * dd);
      for (;;) {
        var x, v;
        do { x = normal(); v = 1 + cc * x; } while (v <= 0);
        v = v * v * v; var uu = u();
        if (uu < 1 - 0.0331 * x * x * x * x || Math.log(uu) < 0.5 * x * x + dd * (1 - v + Math.log(v))) return dd * v;
      }
    }
    return { uniform: u, normal: normal, chisq: function (df) { return 2 * gamma(df / 2); },
      permutation: function (arr) { var p = arr.slice(); for (var i = p.length - 1; i > 0; i--) {
        var j = Math.floor(u() * (i + 1)); var tmp = p[i]; p[i] = p[j]; p[j] = tmp; } return p; } };
  }

  // ------------------------------------------------------------ special functions
  function erfc(x) {                     // Numerical Recipes erfcc, then refined below
    var z = Math.abs(x), t = 1 / (1 + 0.5 * z);
    var r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 +
      t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
    return x >= 0 ? r : 2 - r;
  }
  function normCdf(x) { return 0.5 * erfc(-x / Math.SQRT2); }
  function normPpf(p) {                  // Acklam, plus one Halley step
    if (p <= 0) return -Infinity; if (p >= 1) return Infinity;
    var a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
    var b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01];
    var c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
    var d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00];
    var q, r, x;
    if (p < 0.02425) { q = Math.sqrt(-2 * Math.log(p));
      x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    } else if (p > 1 - 0.02425) { q = Math.sqrt(-2 * Math.log(1 - p));
      x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    } else { q = p - 0.5; r = q * q;
      x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
    }
    var e = normCdf(x) - p, uu = e * Math.sqrt(2 * Math.PI) * Math.exp(x * x / 2);
    return x - uu / (1 + x * uu / 2);
  }
  function lgamma(x) {
    var g = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
    var y = x, tmp = x + 5.5; tmp -= (x + 0.5) * Math.log(tmp); var ser = 1.000000000190015;
    for (var j = 0; j < 6; j++) ser += g[j] / ++y;
    return -tmp + Math.log(2.5066282746310005 * ser / x);
  }
  function digamma(x) { var r = 0; while (x < 6) { r -= 1 / x; x += 1; } var f = 1 / (x * x);
    return r + Math.log(x) - 0.5 / x - f * (1 / 12 - f * (1 / 120 - f * (1 / 252 - f * (1 / 240 - f / 132)))); }
  function trigamma(x) { var r = 0; while (x < 6) { r += 1 / (x * x); x += 1; } var f = 1 / (x * x);
    return r + 1 / x + f / 2 + f / x * (1 / 6 - f * (1 / 30 - f * (1 / 42 - f / 30))); }
  function gammaP(a, x) {                // regularised lower incomplete gamma
    if (x <= 0) return 0;
    var gln = lgamma(a);
    if (x < a + 1) { var ap = a, sum = 1 / a, del = sum;
      for (var n = 0; n < 500; n++) { ap += 1; del *= x / ap; sum += del; if (Math.abs(del) < Math.abs(sum) * 1e-15) break; }
      return sum * Math.exp(-x + a * Math.log(x) - gln); }
    var b = x + 1 - a, c = 1e300, d = 1 / b, h = d;
    for (var i = 1; i < 500; i++) { var an = -i * (i - a); b += 2; d = an * d + b; if (Math.abs(d) < 1e-300) d = 1e-300;
      c = b + an / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; var del2 = d * c; h *= del2; if (Math.abs(del2 - 1) < 1e-15) break; }
    return 1 - Math.exp(-x + a * Math.log(x) - gln) * h;
  }
  function gammaPpf(p, a) {              // bisection-guarded Newton
    if (p <= 0) return 0;
    var lo = 0, hi = Math.max(1, a) * 10; while (gammaP(a, hi) < p) hi *= 2;
    var x = a, gln = lgamma(a);
    for (var i = 0; i < 100; i++) {
      var f = gammaP(a, x) - p; if (Math.abs(f) < 1e-12) break;
      if (f > 0) hi = x; else lo = x;
      var dens = Math.exp((a - 1) * Math.log(x) - x - gln), nx = x - f / dens;
      x = (nx > lo && nx < hi && isFinite(nx)) ? nx : (lo + hi) / 2;
    }
    return x;
  }

  // ------------------------------------------------------------ small helpers
  function mean(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s / a.length; }
  function std(a, ddof) { var m = mean(a), s = 0; for (var i = 0; i < a.length; i++) s += (a[i] - m) * (a[i] - m);
    return Math.sqrt(s / (a.length - (ddof || 0))); }
  function median(sorted) { var n = sorted.length, h = n >> 1; return n % 2 ? sorted[h] : (sorted[h - 1] + sorted[h]) / 2; }
  function quantile(a, q) { var s = a.slice().sort(function (x, y) { return x - y; }); var h = (s.length - 1) * q, lo = Math.floor(h);
    return lo + 1 < s.length ? s[lo] + (h - lo) * (s[lo + 1] - s[lo]) : s[lo]; }
  function percentile(col, q) { return quantile(col, q / 100); }
  function clip(x, lo, hi) { return Math.min(Math.max(x, lo), hi); }

  // ------------------------------------------------------------ data
  function parsePower(raw) {
    var params = raw.properties.parameter, rows = {};
    Object.keys(params).forEach(function (name) {
      var series = params[name];
      Object.keys(series).forEach(function (key) {
        var y = +key.slice(0, 4), m = +key.slice(4); if (m === 13) return;
        var v = series[key]; v = (v === null || v <= -998.5) ? NaN : +v;
        var k = y * 100 + m; rows[k] = rows[k] || { y: y, m: m, t: NaN, p: NaN };
        if (name === 'T2M') rows[k].t = v;
        if (name === 'PRECTOTCORR') rows[k].p = v * new Date(Date.UTC(y, m, 0)).getUTCDate();
      });
    });
    var out = Object.keys(rows).map(Number).sort(function (a, b) { return a - b; }).map(function (k) { return rows[k]; });
    while (out.length && isNaN(out[out.length - 1].t) && isNaN(out[out.length - 1].p)) out.pop();
    return out;
  }

  function seasonMonths(s) {
    s = s.toUpperCase(); if (s === 'ANN') return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
    var i = LETTERS.indexOf(s); if (i < 0 || i > 11 || s.length > 12) throw new Error('unknown season ' + s);
    var out = []; for (var k = 0; k < s.length; k++) out.push((i + k) % 12 + 1); return out;
  }
  function seasonLabel(s) { if (s.toUpperCase() === 'ANN') return 'Calendar year';
    var m = seasonMonths(s); return MONTHS[m[0] - 1] + '-' + MONTHS[m[m.length - 1] - 1]; }
  function seasonStart(s, year) { var m = seasonMonths(s); return [m[m.length - 1] < m[0] ? year - 1 : year, m[0]]; }
  function monthBefore(ym) { return ym[1] === 1 ? [ym[0] - 1, 12] : [ym[0], ym[1] - 1]; }
  function ymKey(ym) { return ym[0] * 100 + ym[1]; }
  function truncate(rows, cutoff) { if (!cutoff) return rows; var c = ymKey(cutoff);
    return rows.filter(function (r) { return r.y * 100 + r.m <= c; }); }
  function inBase(y) { return y >= BASELINE[0] && y <= BASELINE[1]; }

  function climatology(rows, key) {
    var s = {}, n = {};
    rows.forEach(function (r) { if (inBase(r.y) && !isNaN(r[key])) { s[r.m] = (s[r.m] || 0) + r[key]; n[r.m] = (n[r.m] || 0) + 1; } });
    var c = {}; for (var m = 1; m <= 12; m++) c[m] = n[m] ? s[m] / n[m] : NaN; return c;
  }
  // values: function(row) -> number. Returns {years:[], values:[]} for complete seasons.
  function seasonal(rows, values, season, how) {
    var months = seasonMonths(season), crosses = months[months.length - 1] < months[0], g = {};
    rows.forEach(function (r) {
      if (months.indexOf(r.m) < 0) return;
      var y = (crosses && r.m >= months[0]) ? r.y + 1 : r.y, v = values(r);
      g[y] = g[y] || { s: 0, n: 0 }; if (!isNaN(v)) { g[y].s += v; g[y].n += 1; }
    });
    var years = Object.keys(g).map(Number).sort(function (a, b) { return a - b; }).filter(function (y) { return g[y].n === months.length; });
    return { years: years, values: years.map(function (y) { return how === 'sum' ? g[y].s : g[y].s / g[y].n; }) };
  }

  function GammaFit(values) {
    var v = values.filter(isFinite); if (v.length < 8) throw new Error('need at least 8 values to fit a gamma distribution');
    var pos = v.filter(function (x) { return x > 0; });
    this.q = 1 - pos.length / v.length;
    if (pos.length < 5 || pos.every(function (x) { return x === pos[0]; })) throw new Error('too few non-zero totals (dry season?)');
    var mpos = mean(pos), s = Math.log(mpos) - mean(pos.map(Math.log));
    var a = (1 + Math.sqrt(1 + 4 * s / 3)) / (4 * s);
    for (var i = 0; i < 100; i++) { var f = Math.log(a) - digamma(a) - s, d = 1 / a - trigamma(a), na = a - f / d;
      if (na <= 0) na = a / 2; if (Math.abs(na - a) < 1e-12 * a) { a = na; break; } a = na; }
    this.a = a; this.scale = mpos / a; this.mean = mean(v);
  }
  GammaFit.prototype.cdf = function (x) { return x <= 0 ? this.q : this.q + (1 - this.q) * gammaP(this.a, x / this.scale); };
  GammaFit.prototype.spi = function (x) {
    var p = x <= 0 ? Math.max(this.q / 2, 1e-6) : clip(this.cdf(x), 1e-6, 1 - 1e-6); return normPpf(p); };
  GammaFit.prototype.inverse = function (z) { var p = normCdf(z); if (p <= this.q) return 0;
    return gammaPpf(clip((p - this.q) / (1 - this.q), 0, 1 - 1e-12), this.a) * this.scale; };

  function seasonalSeries(rows, variable, season) {
    if (variable === 'T') {
      var clim = climatology(rows, 't');
      var s = seasonal(rows, function (r) { return r.t - clim[r.m]; }, season, 'mean');
      var abs = seasonal(rows, function (r) { return r.t; }, season, 'mean');
      var base = abs.years.filter(inBase);
      var normal = mean(base.map(function (y) { return abs.values[abs.years.indexOf(y)]; }));
      return { years: s.years, stat: s.values, plot: s.values.slice(), normal: normal, unit: '°C',
        baseline: [Math.min.apply(null, base), Math.max.apply(null, base)], clim: clim };
    }
    var tot = seasonal(rows, function (r) { return r.p; }, season, 'sum');
    var baseT = tot.years.filter(inBase), baseVals = baseT.map(function (y) { return tot.values[tot.years.indexOf(y)]; });
    var fit = new GammaFit(baseVals), normalP = mean(baseVals);
    return { years: tot.years, stat: tot.values.map(function (v) { return fit.spi(v); }),
      plot: tot.values.map(function (v) { return v / normalP * 100; }), totals: tot.values, normal: normalP,
      unit: '% of normal', baseline: [Math.min.apply(null, baseT), Math.max.apply(null, baseT)], fit: fit };
  }

  // ------------------------------------------------------------ statistics
  function pairIndex(n) { var I = [], J = []; for (var i = 0; i < n; i++) for (var j = i + 1; j < n; j++) { I.push(i); J.push(j); }
    return { I: I, J: J }; }
  function senSlope(y, t) {
    var n = y.length, P = pairIndex(n), s = new Float64Array(P.I.length);
    for (var k = 0; k < s.length; k++) s[k] = (y[P.J[k]] - y[P.I[k]]) / (t[P.J[k]] - t[P.I[k]]);
    s.sort(); return median(s);
  }
  function senSlopeMany(rowsArr, t) {
    var n = t.length, P = pairIndex(n), dt = new Float64Array(P.I.length), buf = new Float64Array(P.I.length), out = new Float64Array(rowsArr.length);
    for (var k = 0; k < dt.length; k++) dt[k] = t[P.J[k]] - t[P.I[k]];
    for (var r = 0; r < rowsArr.length; r++) { var y = rowsArr[r];
      for (k = 0; k < dt.length; k++) buf[k] = (y[P.J[k]] - y[P.I[k]]) / dt[k];
      buf.sort(); out[r] = median(buf); }
    return out;
  }
  function senLine(y, t) { var b = senSlope(y, t); var r = y.map(function (v, i) { return v - b * t[i]; }).sort(function (a, c) { return a - c; });
    return [b, median(r)]; }
  function recentShift(y) { if (y.length < 30) return NaN; return mean(y.slice(-10)) - mean(y.slice(0, 20)); }
  function detrend(y, t) {
    var mt = mean(t), my = mean(y), sxy = 0, sxx = 0;
    for (var i = 0; i < y.length; i++) { sxy += (t[i] - mt) * (y[i] - my); sxx += (t[i] - mt) * (t[i] - mt); }
    var b = sxy / sxx, a = my - b * mt; return y.map(function (v, i) { return v - (a + b * t[i]); });
  }
  function fitAR1(resid) {
    var m = mean(resid), r = resid.map(function (v) { return v - m; }), n = r.length, num = 0, den = 0;
    for (var i = 0; i < n; i++) { den += r[i] * r[i]; if (i) num += r[i] * r[i - 1]; }
    var r1 = num / den, phi = clip((r1 + 2 / n) / (1 - 5 / n), -0.9, 0.95);
    var shrink = Math.max(1 - 2 * (1 + phi) / (n * (1 - phi)), 0.3);
    return { phi: phi, phi_raw: r1, sigma: std(r, 0) / Math.sqrt(shrink), n_eff: Math.max(n * (1 - phi) / (1 + phi), 4), n: n };
  }
  function simulateAR1(phis, sigmas, n, N, rng) {
    var out = new Array(N);
    for (var s = 0; s < N; s++) { var phi = phis[s], sg = sigmas[s], e = sg * Math.sqrt(1 - phi * phi), x = new Float64Array(n);
      x[0] = rng.normal() * sg; for (var k = 1; k < n; k++) x[k] = phi * x[k - 1] + e * rng.normal(); out[s] = x; }
    return out;
  }
  function simulateAR1Uncertain(fit, n, N, rng) {
    var se = Math.sqrt((1 - fit.phi * fit.phi) / fit.n), phis = [], sigmas = [];
    for (var s = 0; s < N; s++) { phis.push(clip(fit.phi + se * rng.normal(), -0.9, 0.97));
      sigmas.push(fit.sigma * Math.sqrt(fit.n_eff / rng.chisq(fit.n_eff))); }
    return simulateAR1(phis, sigmas, n, N, rng);
  }
  function iaaft(x, N, rng, nIter) {
    nIter = nIter || 100;
    var n = x.length, sorted = x.slice().sort(function (a, b) { return a - b; }), C = [], S = [], amp = new Float64Array(n);
    for (var k = 0; k < n; k++) { C.push(new Float64Array(n)); S.push(new Float64Array(n));
      for (var j = 0; j < n; j++) { C[k][j] = Math.cos(2 * Math.PI * k * j / n); S[k][j] = Math.sin(2 * Math.PI * k * j / n); } }
    for (k = 0; k < n; k++) { var re = 0, im = 0; for (j = 0; j < n; j++) { re += x[j] * C[k][j]; im -= x[j] * S[k][j]; } amp[k] = Math.hypot(re, im); }
    var out = new Array(N), Re = new Float64Array(n), Im = new Float64Array(n), idx = new Array(n);
    for (var s = 0; s < N; s++) {
      var y = Float64Array.from(rng.permutation(x));
      for (var it = 0; it < nIter; it++) {
        for (k = 0; k < n; k++) { re = 0; im = 0; for (j = 0; j < n; j++) { re += y[j] * C[k][j]; im -= y[j] * S[k][j]; }
          var mag = Math.hypot(re, im) || 1; Re[k] = amp[k] * re / mag; Im[k] = amp[k] * im / mag; }
        for (j = 0; j < n; j++) { var v = 0; for (k = 0; k < n; k++) v += Re[k] * C[k][j] - Im[k] * S[k][j]; y[j] = v / n; }
        for (j = 0; j < n; j++) idx[j] = j;
        idx.sort(function (a, b) { return y[a] - y[b]; });
        var z = new Float64Array(n); for (j = 0; j < n; j++) z[idx[j]] = sorted[j]; y = z;
      }
      out[s] = y;
    }
    return out;
  }
  function empiricalP(real, nulls) { var N = nulls.length, c = 0;
    for (var i = 0; i < N; i++) if (Math.abs(nulls[i]) >= Math.abs(real)) c++;
    return { count: c, N: N, outside: N - c, p: (c + 1) / (N + 1) }; }
  function verdictFor(p) { for (var i = 0; i < VERDICTS.length; i++) if (p < VERDICTS[i][0])
    return { key: VERDICTS[i][1], text: VERDICTS[i][2], colour: VERDICTS[i][3] }; }
  function nullTest(y, t, generator, N, rng, keep) {
    var real = senSlope(y, t), resid = detrend(y, t), fit = {}, sims;
    if (generator === 'iaaft') sims = iaaft(resid, N, rng, 60);
    else { fit = fitAR1(resid); sims = simulateAR1Uncertain(fit, y.length, N, rng); }
    var nulls = senSlopeMany(sims, t), res = empiricalP(real, nulls);
    res.real = real; res.fit = fit; res.generator = generator; res.verdict = verdictFor(res.p);
    if (keep) { res.sims = sims; res.nulls = nulls; }
    return res;
  }

  // ------------------------------------------------------------ the trial
  function analyse(allRows, variable, season, opts) {
    opts = opts || {};
    var N = opts.N || 1000, rows = truncate(allRows, opts.cutoff), info = seasonalSeries(rows, variable, season);
    var years = info.years, y = info.stat, last = rows[rows.length - 1];
    var out = { variable: variable, variable_name: variable === 'T' ? 'temperature' : 'precipitation', season: season,
      season_label: seasonLabel(season), unit: info.unit, n_years: years.length, baseline: info.baseline, normal: info.normal,
      first_year: years[0], last_year: years[years.length - 1],
      data_cutoff: last.y + '-' + (last.m < 10 ? '0' : '') + last.m, seed: opts.seed >>> 0 };
    if (years.length < MIN_SEASONS) { out.insufficient = true; return out; }
    var rng = makeRng(opts.seed || 1981), t = years.slice();
    var test = nullTest(y, t, 'ar1', N, rng, true);
    out.test = { p: test.p, count: test.count, N: test.N, outside: test.outside, real: test.real, fit: test.fit };
    out.verdict = test.verdict;
    var slopePlot = senSlope(info.plot, t);
    out.trend_per_decade = slopePlot * 10;
    out.change_over_record = slopePlot * (t[t.length - 1] - t[0]);
    out.recent_shift = recentShift(info.plot);
    out.direction = variable === 'T' ? (test.real > 0 ? 'warmer' : 'cooler') : (test.real > 0 ? 'wetter' : 'drier');
    if (variable === 'P') out.normal_mm = info.normal;
    if (opts.robust) { var ri = nullTest(y, t, 'iaaft', opts.robustN || 300, makeRng((opts.seed || 1981) + 1), false);
      out.robustness = { iaaft: { p: ri.p, outside: ri.outside, N: ri.N, verdict: ri.verdict.key } }; }
    // the band of imaginary histories, in plain units, centred on the baseline level
    var baseIdx = []; years.forEach(function (yy, i) { if (inBase(yy)) baseIdx.push(i); });
    var centre = mean(baseIdx.map(function (i) { return y[i]; }));
    var band = test.sims.map(function (row) { return Array.from(row, function (v) {
      return variable === 'T' ? v + centre : info.fit.inverse(v + centre) / info.normal * 100; }); });
    var lo = [], mid = [], hi = [];
    for (var k = 0; k < years.length; k++) { var col = band.map(function (r) { return r[k]; });
      lo.push(percentile(col, 5)); mid.push(percentile(col, 50)); hi.push(percentile(col, 95)); }
    out.arrays = { years: years, plot: info.plot, band_lo: lo, band_mid: mid, band_hi: hi, samples: band.slice(0, 60),
      null_trends: Array.from(test.nulls, function (v) { return v * 10; }), real_trend: test.real * 10 };
    out.fit_info = { phi: test.fit.phi, sigma: test.fit.sigma };
    // what happened after the cut-off, measured against the baseline known then
    if (opts.cutoff) {
      var after;
      if (variable === 'T') after = seasonal(allRows, function (r) { return r.t - info.clim[r.m]; }, season, 'mean');
      else { var tt = seasonal(allRows, function (r) { return r.p; }, season, 'sum');
        after = { years: tt.years, values: tt.values.map(function (v) { return v / info.normal * 100; }) }; }
      var ay = [], av = [];
      after.years.forEach(function (yy, i) { if (yy > out.last_year) { ay.push(yy); av.push(after.values[i]); } });
      out.after = { years: ay, plot: av };
    }
    return out;
  }

  // ------------------------------------------------------------ forecasts
  var CATS = ['below', 'near', 'above'], CLIM = { below: 1 / 3, near: 1 / 3, above: 1 / 3 };
  function seasonValues(rows, variable, season) {
    return variable === 'T' ? seasonal(rows, function (r) { return r.t; }, season, 'mean')
      : seasonal(rows, function (r) { return r.p; }, season, 'sum');
  }
  function forecast(rows, variable, season, target, cutoff) {
    var start = seasonStart(season, target), cut = monthBefore(start);
    if (cutoff && ymKey(cutoff) < ymKey(cut)) cut = cutoff;
    var past = truncate(rows, cut), sv = seasonValues(past, variable, season), years = [], vals = [];
    sv.years.forEach(function (y, i) { if (y < target) { years.push(y); vals.push(sv.values[i]); } });
    var base = []; years.forEach(function (y, i) { if (inBase(y)) base.push(vals[i]); });
    if (base.length < 10) throw new Error('fewer than 10 baseline seasons');
    var edges = [quantile(base, 1 / 3), quantile(base, 2 / 3)], x, e, fit = null;
    if (variable === 'P') {
      if (edges[1] - edges[0] < 1 || quantile(base, 0.5) < 10) throw new Error('dry season: normal rainfall is close to zero, so above/below normal means little');
      fit = new GammaFit(base); x = vals.map(function (v) { return fit.spi(v); }); e = edges.map(function (v) { return fit.spi(v); });
    } else { x = vals; e = edges; }
    var bl = senLine(x, years), b = bl[0], a = bl[1], n = x.length;
    var resid = x.map(function (v, i) { return v - (a + b * years[i]); }), s = std(resid, 2), tbar = mean(years), sxx = 0;
    years.forEach(function (y) { sxx += (y - tbar) * (y - tbar); });
    var sd = s * Math.sqrt(1 + 1 / n + (target - tbar) * (target - tbar) / sxx), mu = a + b * target;
    var pb = normCdf((e[0] - mu) / sd), pa = 1 - normCdf((e[1] - mu) / sd);
    var pr = [Math.max(pb, 0.02), Math.max(1 - pb - pa, 0.02), Math.max(pa, 0.02)], sum = pr[0] + pr[1] + pr[2];
    pr = pr.map(function (v) { return Math.round(v / sum * 1000) / 1000; }); pr[1] = Math.round((1 - pr[0] - pr[2]) * 1000) / 1000;
    var lastRow = past[past.length - 1];
    return { variable: variable, season: season, target_year: target, probabilities: { below: pr[0], near: pr[1], above: pr[2] },
      tercile_edges: edges, unit: variable === 'T' ? '°C' : 'mm', centre: variable === 'T' ? mu : fit.inverse(mu),
      seasons_used: n, data_cutoff: lastRow.y + '-' + (lastRow.m < 10 ? '0' : '') + lastRow.m };
  }
  function category(v, edges) { return v < edges[0] ? 'below' : v > edges[1] ? 'above' : 'near'; }
  function rps(p, obs) { var f = 0, o = 0, s = 0; for (var i = 0; i < 2; i++) { f += p[CATS[i]]; o += CATS[i] === obs ? 1 : 0; s += (f - o) * (f - o); } return s / 2; }
  function hindcasts(rows, variable, season, firstYear, lastYear) {
    var sv = seasonValues(rows, variable, season), out = [];
    sv.years.forEach(function (y, i) {
      if (y < (firstYear || 1996) || (lastYear && y > lastYear)) return;
      try { var fc = forecast(rows, variable, season, y); } catch (err) { return; }
      var obs = category(sv.values[i], fc.tercile_edges);
      out.push({ year: y, p: fc.probabilities, observed: obs, rps: rps(fc.probabilities, obs), rps_clim: rps(CLIM, obs) });
    });
    if (!out.length) return { n: 0 };
    var f = mean(out.map(function (r) { return r.rps; })), c = mean(out.map(function (r) { return r.rps_clim; }));
    var hits = out.filter(function (r) { var k = CATS.reduce(function (a, b) { return r.p[a] >= r.p[b] ? a : b; }); return k === r.observed; }).length;
    return { n: out.length, first_year: out[0].year, last_year: out[out.length - 1].year, rpss: 1 - f / c, hit_rate: hits / out.length, rows: out };
  }

  // ------------------------------------------------------------ check the checker
  // Make M fake records with this place's own noise (fitted AR(1)) and a known
  // trend (0 = none), run the whole test on each, and count how many are flagged.
  function selfCheck(fit, years, opts) {
    var M = opts.M || 200, N = opts.N || 200, rng = makeRng(opts.seed || 7), n = years.length, flagged = 0;
    var phis = new Array(M).fill(fit.phi), sig = new Array(M).fill(fit.sigma), fakes = simulateAR1(phis, sig, n, M, rng);
    for (var i = 0; i < M; i++) {
      var y = Array.from(fakes[i], function (v, k) { return v + (opts.trendPerYear || 0) * (years[k] - years[0]); });
      if (nullTest(y, years, 'ar1', N, rng, false).p < 0.05) flagged++;
      if (opts.onProgress && i % 20 === 19) opts.onProgress((i + 1) / M);
    }
    return { M: M, flagged: flagged, rate: flagged / M };
  }

  var api = { BASELINE: BASELINE, MONTHS: MONTHS, hashSeed: hashSeed, makeRng: makeRng, normCdf: normCdf, normPpf: normPpf,
    gammaP: gammaP, gammaPpf: gammaPpf, GammaFit: GammaFit, parsePower: parsePower, seasonMonths: seasonMonths,
    seasonLabel: seasonLabel, seasonStart: seasonStart, monthBefore: monthBefore, truncate: truncate, seasonal: seasonal,
    seasonalSeries: seasonalSeries, senSlope: senSlope, senSlopeMany: senSlopeMany, recentShift: recentShift, detrend: detrend,
    fitAR1: fitAR1, iaaft: iaaft, empiricalP: empiricalP, verdictFor: verdictFor, nullTest: nullTest, analyse: analyse,
    forecast: forecast, hindcasts: hindcasts, rps: rps, selfCheck: selfCheck };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.CassandraEngine = api;
})(typeof self !== 'undefined' ? self : this);
