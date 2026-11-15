/* Cassandra Signal live checker: pick a place, put its record on trial. */
(function () {
  'use strict';
  var E = window.CassandraEngine, $ = function (id) { return document.getElementById(id); };
  var app = $('checker'), ROOT = app.dataset.root || '../';
  var POWER = 'https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M,PRECTOTCORR&community=AG';
  var GEO = 'https://geocoding-api.open-meteo.com/v1/search?count=6&language=en&format=json&name=';
  var worker = new Worker(ROOT + 'js/worker.js'), jobs = {}, jobId = 0, rawCache = {}, gistemp = null, map = null, marker = null;
  var state = { name: '', last: null };

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function signed(v, d) { return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d); }
  function pct(x) { return Math.round(x * 100) + '%'; }
  function pWords(p) { return p < 0.001 ? 'p < 0.001' : 'p = ' + p.toFixed(3); }
  function coordName(lat, lon) { return Math.abs(lat).toFixed(2) + '°' + (lat >= 0 ? 'N' : 'S') + ', ' + Math.abs(lon).toFixed(2) + '°' + (lon >= 0 ? 'E' : 'W'); }

  worker.onmessage = function (ev) { var j = jobs[ev.data.id]; if (!j) return;
    if (ev.data.type === 'progress') j.progress(ev.data); else { delete jobs[ev.data.id];
      ev.data.type === 'done' ? j.resolve(ev.data.result) : j.reject(new Error(ev.data.message)); } };
  function ask(msg, progress) { return new Promise(function (resolve, reject) { var id = ++jobId; msg.id = id;
    jobs[id] = { resolve: resolve, reject: reject, progress: progress || function () {} }; worker.postMessage(msg); }); }

  // ------------------------------------------------------------ place picking
  function setPlace(lat, lon, name, pan) {
    $('lat').value = (+lat).toFixed(3); $('lon').value = (+lon).toFixed(3); state.name = name || '';
    $('placename').textContent = name ? name + ' (' + coordName(+lat, +lon) + ')' : coordName(+lat, +lon);
    if (map) { if (!marker) marker = L.marker([lat, lon]).addTo(map); else marker.setLatLng([lat, lon]);
      if (pan) map.setView([lat, lon], Math.max(map.getZoom(), 5)); }
  }
  if (window.L) {
    map = L.map('map', { worldCopyJump: true }).setView([20, 10], 2);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 12,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
    map.on('click', function (e) { var ll = e.latlng.wrap(); setPlace(ll.lat, ll.lng, '', false); });
  } else { $('map').hidden = true; }
  var t0 = null;
  $('q').addEventListener('input', function () {
    clearTimeout(t0); var q = this.value.trim(); if (q.length < 2) { $('results').innerHTML = ''; return; }
    t0 = setTimeout(function () {
      fetch(GEO + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
        var ul = $('results'); ul.innerHTML = '';
        (d.results || []).forEach(function (p) {
          var li = document.createElement('li'), b = document.createElement('button');
          b.type = 'button'; b.textContent = [p.name, p.admin1, p.country].filter(Boolean).join(', ');
          b.onclick = function () { setPlace(p.latitude, p.longitude, [p.name, p.country].filter(Boolean).join(', '), true);
            ul.innerHTML = ''; $('q').value = ''; };
          li.appendChild(b); ul.appendChild(li);
        });
        if (!(d.results || []).length) ul.innerHTML = '<li class="muted small">No match. Try another spelling, or click the map.</li>';
      }).catch(function () { $('results').innerHTML = '<li class="muted small">Search is unavailable right now; click the map or type coordinates.</li>'; });
    }, 300);
  });
  $('geo').onclick = function () {
    if (!navigator.geolocation) return alert('Your browser cannot share its location.');
    navigator.geolocation.getCurrentPosition(function (p) { setPlace(p.coords.latitude, p.coords.longitude, 'My location', true); },
      function () { alert('Location was not shared. Search or click the map instead.'); });
  };
  ['lat', 'lon'].forEach(function (id) { $(id).addEventListener('change', function () {
    if ($('lat').value && $('lon').value) setPlace(+$('lat').value, +$('lon').value, '', true); }); });
  fetch(ROOT + 'data/places.json').then(function (r) { return r.json(); }).then(function (ps) {
    ps.forEach(function (p) { var b = document.createElement('button'); b.type = 'button'; b.className = 'chip'; b.textContent = p.name.split(',')[0];
      b.onclick = function () { setPlace(p.lat, p.lon, p.name, true);
        var v = p.primary; document.querySelector('input[name=var][value=' + v + ']').checked = true;
        $('season').value = v === 'T' ? p.t_season : p.p_season; };
      $('chips').appendChild(b); });
  }).catch(function () {});
  fetch(ROOT + 'data/gistemp.json').then(function (r) { return r.json(); }).then(function (g) { gistemp = g; }).catch(function () {});
  $('usecut').onchange = function () { $('cut').disabled = !this.checked; };
  $('cut').oninput = function () { $('cutout').textContent = this.value; };

  // ------------------------------------------------------------ steps
  var STEPS = [['fetch', 'Download the monthly NASA POWER record for this point (1981 to now)'],
    ['anomalies', 'Turn it into seasonal anomalies against 1981–2010, then build 1,000 imaginary histories and rank the real trend'],
    ['robust', 'Robustness check: 300 IAAFT surrogates of the same record'],
    ['forecast', 'Seasonal forecast with the same data, and how that method did on past seasons']];
  function showSteps() { var ol = $('steps'); ol.hidden = false;
    ol.innerHTML = STEPS.map(function (s) { return '<li data-step="' + s[0] + '">' + esc(s[1]) + '</li>'; }).join(''); }
  function mark(step) { var seen = false; STEPS.forEach(function (s) { var li = document.querySelector('[data-step="' + s[0] + '"]');
    if (s[0] === step) { li.className = 'now'; seen = true; } else if (!seen) li.className = 'done'; }); }
  function finishSteps() { document.querySelectorAll('#steps li').forEach(function (li) { li.className = 'done'; }); }

  function getPower(lat, lon) {
    var key = lat.toFixed(3) + ',' + lon.toFixed(3); if (rawCache[key]) return Promise.resolve([key, rawCache[key]]);
    var y = new Date().getUTCFullYear();
    var url = function (end) { return POWER + '&longitude=' + lon.toFixed(3) + '&latitude=' + lat.toFixed(3) + '&start=1981&end=' + end + '&format=JSON'; };
    return fetch(url(y)).then(function (r) { if (!r.ok) return fetch(url(y - 1)); return r; })
      .then(function (r) { if (!r.ok) throw new Error('NASA POWER answered ' + r.status); return r.json(); })
      .then(function (raw) { if (!raw.properties) throw new Error('NASA POWER returned no data for this point'); rawCache[key] = raw; return [key, raw]; });
  }

  // ------------------------------------------------------------ run
  app.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var lat = +$('lat').value, lon = +$('lon').value;
    if (!$('lat').value || !$('lon').value || isNaN(lat) || isNaN(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      $('placename').textContent = 'Choose a place first: search, click the map or type coordinates.'; return; }
    var opts = { variable: document.querySelector('input[name=var]:checked').value, season: $('season').value,
      cutoff: $('usecut').checked ? [+$('cut').value, 12] : null };
    var params = new URLSearchParams({ lat: lat.toFixed(3), lon: lon.toFixed(3), var: opts.variable, season: opts.season });
    if (state.name) params.set('name', state.name); if (opts.cutoff) params.set('cutoff', opts.cutoff[0]);
    history.replaceState(null, '', '?' + params.toString());
    $('run').disabled = true; $('out').hidden = true; showSteps(); mark('fetch');
    getPower(lat, lon).then(function (kr) {
      mark('anomalies');
      return ask({ cmd: 'analyse', key: kr[0], raw: kr[1], opts: opts }, function (m) { mark(m.step); });
    }).then(function (res) {
      finishSteps(); state.last = { res: res, lat: lat, lon: lon, opts: opts, name: state.name, url: location.href };
      render(state.last);
    }).catch(function (err) {
      var msg = String(err.message || err);
      if (/dry season|non-zero totals/.test(msg)) msg = 'It almost never rains in this season here, so there is nothing to put on trial. Pick a wetter season (or temperature).';
      $('out').hidden = false; $('out').innerHTML = '<div class="box"><strong>Could not run the trial.</strong> ' + esc(msg) + '</div>';
    }).then(function () { $('run').disabled = false; });
  });

  // ------------------------------------------------------------ charts (SVG)
  function niceTicks(lo, hi, n) { var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / n))), err = span / n / step;
    step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1; var t = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) t.push(+v.toFixed(10)); return t; }
  function lineChart(r) {
    var a = r.arrays, W = 900, H = 380, m = { l: 56, r: 16, t: 14, b: 32 }, after = r.after || { years: [], plot: [] };
    var x0 = a.years[0], x1 = Math.max(a.years[a.years.length - 1], after.years.length ? after.years[after.years.length - 1] : 0);
    var vals = a.band_lo.concat(a.band_hi, a.plot, after.plot), lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * 0.06;
    lo -= pad; hi += pad;
    var X = function (y) { return m.l + (y - x0) / (x1 - x0) * (W - m.l - m.r); }, Y = function (v) { return m.t + (hi - v) / (hi - lo) * (H - m.t - m.b); };
    var path = function (xs, ys) { return xs.map(function (x, i) { return (i ? 'L' : 'M') + X(x).toFixed(1) + ',' + Y(ys[i]).toFixed(1); }).join(''); };
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart-svg" role="img" aria-label="Real record over the band of 1,000 imaginary histories">';
    niceTicks(lo, hi, 6).forEach(function (v) { s += '<line class="grid" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + Y(v) + '" y2="' + Y(v) + '"/><text class="tick" x="' + (m.l - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end">' + v + '</text>'; });
    for (var yy = Math.ceil(x0 / 5) * 5; yy <= x1; yy += 5) s += '<text class="tick" x="' + X(yy) + '" y="' + (H - 10) + '" text-anchor="middle">' + yy + '</text>';
    var ref = r.variable === 'T' ? 0 : 100; s += '<line class="ref" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + Y(ref) + '" y2="' + Y(ref) + '"/>';
    s += '<path class="band" d="' + path(a.years, a.band_hi) + 'L' + a.years.slice().reverse().map(function (x, i) { return X(x).toFixed(1) + ',' + Y(a.band_lo[a.years.length - 1 - i]).toFixed(1); }).join('L') + 'Z"/>';
    a.samples.forEach(function (row) { s += '<path class="hist" d="' + path(a.years, row) + '"/>'; });
    s += '<path class="mid" d="' + path(a.years, a.band_mid) + '"/>';
    var b = r.trend_per_decade / 10, res = a.plot.map(function (v, i) { return v - b * a.years[i]; }).sort(function (p, q) { return p - q; });
    var ic = res.length % 2 ? res[res.length >> 1] : (res[res.length / 2 - 1] + res[res.length / 2]) / 2, ty = [a.years[0], a.years[a.years.length - 1]];
    s += '<path class="trend" d="' + path(ty, ty.map(function (y) { return ic + b * y; })) + '"/>';
    if (after.years.length) {
      s += '<line class="cut" x1="' + X(a.years[a.years.length - 1] + 0.5) + '" x2="' + X(a.years[a.years.length - 1] + 0.5) + '" y1="' + m.t + '" y2="' + (H - m.b) + '"/>';
      s += '<text class="tick" x="' + (X(a.years[a.years.length - 1] + 0.5) + 6) + '" y="' + (m.t + 12) + '">what happened next →</text>';
      s += '<path class="after" d="' + path([a.years[a.years.length - 1]].concat(after.years), [a.plot[a.plot.length - 1]].concat(after.plot)) + '"/>';
    }
    s += '<path class="real ' + r.verdict.colour + '" d="' + path(a.years, a.plot) + '"/>';
    return s + '</svg>';
  }
  function histChart(r) {
    var v = r.arrays.null_trends, real = r.arrays.real_trend, W = 900, H = 170, m = { l: 16, r: 16, t: 8, b: 30 };
    var lo = Math.min(Math.min.apply(null, v), -Math.abs(real)), hi = Math.max(Math.max.apply(null, v), Math.abs(real)), nb = 45, w = (hi - lo) / nb, c = new Array(nb).fill(0);
    v.forEach(function (x) { c[Math.min(nb - 1, Math.floor((x - lo) / w))]++; }); var mx = Math.max.apply(null, c);
    var X = function (x) { return m.l + (x - lo) / (hi - lo) * (W - m.l - m.r); };
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart-svg" role="img" aria-label="Trends in the imaginary histories with the real trend marked">';
    c.forEach(function (k, i) { var h = k / mx * (H - m.t - m.b); s += '<rect class="bar-null" x="' + X(lo + i * w).toFixed(1) + '" y="' + (H - m.b - h).toFixed(1) + '" width="' + (X(lo + w) - X(lo) - 1).toFixed(1) + '" height="' + h.toFixed(1) + '"/>'; });
    s += '<line class="mirror" x1="' + X(-real) + '" x2="' + X(-real) + '" y1="' + m.t + '" y2="' + (H - m.b) + '"/>';
    s += '<line class="realline ' + r.verdict.colour + '" x1="' + X(real) + '" x2="' + X(real) + '" y1="' + m.t + '" y2="' + (H - m.b) + '"/>';
    s += '<text class="tick" x="' + W / 2 + '" y="' + (H - 8) + '" text-anchor="middle">Trend per decade in each imaginary history (' + (r.variable === 'T' ? '°C' : 'SPI units') + '). Bold line: the real trend.</text>';
    return s + '</svg>';
  }
  function bar(p) { return '<div class="bar">' + ['below', 'near', 'above'].map(function (k) {
    return '<span class="b-' + k + '" style="width:' + Math.max(p[k] * 100, 0.5).toFixed(1) + '%">' + (p[k] >= 0.16 ? k + ' ' : '') + Math.round(p[k] * 100) + '%</span>'; }).join('') + '</div>'; }

  // ------------------------------------------------------------ results
  function sentence(r) {
    var what = E.seasonLabel(r.season) + ' ' + r.variable_name, ch = r.variable === 'T' ? signed(r.trend_per_decade, 2) + ' °C per decade'
      : signed(r.trend_per_decade, 1) + ' percentage points of normal rain per decade';
    if (r.verdict.key === 'not_yet') return what + ' has a trend of ' + ch + ' since ' + r.first_year + ' (pointing ' + r.direction + '), but natural variation alone can produce a trend that size.';
    return what + ' is ' + ((r.direction === 'warmer' || r.direction === 'wetter') ? 'rising' : 'falling') + ': ' + ch + ' since ' + r.first_year + '.';
  }
  function floorPct(x) { return x >= 99 ? (Math.floor(x * 10) / 10).toFixed(1) : String(Math.floor(x)); }
  function nextSeason(r) {
    var f = r.after && r.after.first; if (!f) return '';
    var high = f.pct_below >= 50, T = r.variable === 'T';
    var word = high ? (T ? 'hotter' : 'wetter') : (T ? 'colder' : 'drier'), share = high ? f.pct_below : 100 - f.pct_below;
    var val = T ? signed(f.value, 2) + ' °C against the ' + r.baseline[0] + '–' + r.baseline[1] + ' average' : Math.round(f.value) + '% of normal rain';
    return '<div class="box"><strong>What happened next:</strong> ' + esc(E.seasonLabel(r.season)) + ' ' + f.year + ' came in at ' + val +
      ', ' + word + ' than <strong>' + floorPct(share) + '%</strong> of the years in the 1,000 natural histories built only from the data up to ' +
      r.last_year + '.</div>';
  }
  function planet(r) {
    if (!gistemp || r.variable !== 'T') return '';
    var g = gistemp.global.filter(function (d) { return d[0] >= r.first_year && d[0] <= Math.max(r.last_year, 0); });
    if (g.length < 10) return '';
    var gt = E.senSlope(g.map(function (d) { return d[1]; }), g.map(function (d) { return d[0]; })) * 10;
    var lat = state.last.lat, z = gistemp.zones.filter(function (z) { return lat >= z.lo && lat <= z.hi; })[0], zt = null;
    if (z) { var zz = z.data.filter(function (d) { return d[0] >= r.first_year && d[0] <= r.last_year; });
      zt = E.senSlope(zz.map(function (d) { return d[1]; }), zz.map(function (d) { return d[0]; })) * 10; }
    return '<h3>Your place vs the planet</h3><p>Here: <strong>' + signed(r.trend_per_decade, 2) + ' °C/decade</strong>. Whole planet over the same years: <strong>' +
      signed(gt, 2) + ' °C/decade</strong>' + (z ? '; the ' + esc(z.label) + ' band: <strong>' + signed(zt, 2) + ' °C/decade</strong>' : '') +
      ' (NASA GISTEMP v4, ' + g[0][0] + '–' + g[g.length - 1][0] + ').</p>';
  }
  function render(st) {
    var r = st.res, out = $('out'); out.hidden = false;
    var title = esc(st.name || coordName(st.lat, st.lon));
    if (r.insufficient) { out.innerHTML = '<div class="box">Only ' + r.n_years + ' complete seasons are available, too few for a fair trial (we need ' + 15 + '). Choose a later cut-off year.</div>'; return; }
    var t = r.test, f = r.fit_info, cut = st.opts.cutoff, fc = r.forecast, h = r.hindcast, ri = r.robustness.iaaft;
    var html = '<p class="muted small" style="margin:0">' + esc(coordName(st.lat, st.lon)) + ' · ' + esc(E.seasonLabel(r.season)) + ' ' + r.variable_name +
      ' · seasons ' + r.first_year + '–' + r.last_year + (cut ? ' · <strong>pretending it is the end of ' + cut[0] + '</strong>' : '') + '</p>' +
      '<h2 style="border:0;margin-top:.2em">' + title + '</h2>' +
      '<p class="verdict ' + r.verdict.colour + '">' + esc(r.verdict.text) + '</p>' +
      (r.variable === 'P' && r.normal_mm < 30 ? '<div class="box"><strong>Careful:</strong> this season normally brings only ' + Math.round(r.normal_mm) +
        ' mm of rain here, so a few showers more or less swing the numbers a lot. Treat this verdict with caution, or pick the rainy season.</div>' : '') +
      '<p class="lead">' + esc(sentence(r)) + ' The real trend is bigger than the trend in <strong>' + t.outside.toLocaleString() + ' of ' + t.N.toLocaleString() +
      '</strong> imaginary histories made of natural variation alone (' + pWords(t.p) + ').</p>' +
      '<div class="chartbox">' + lineChart(r) + '<p class="legend small"><span class="key real-key ' + r.verdict.colour + '"></span>real record ' +
      '<span class="key band-key"></span>where 90% of the 1,000 imaginary histories fall <span class="key trend-key"></span>trend' +
      (r.after && r.after.years.length ? ' <span class="key after-key"></span>what happened after the cut-off (not used in the trial)' : '') + '</p></div>' +
      nextSeason(r) +
      '<div class="chartbox">' + histChart(r) + '</div>' +
      '<dl class="facts"><div><dt>Trend (Sen\'s slope)</dt><dd>' + (r.variable === 'T' ? signed(r.trend_per_decade, 2) + ' °C per decade' : signed(r.trend_per_decade, 1) + ' points of normal per decade') + '</dd></div>' +
      '<div><dt>Size of the change</dt><dd>' + (r.variable === 'T' ? signed(r.change_over_record, 2) + ' °C' : signed(r.change_over_record, 1) + ' points') + ' over ' + r.first_year + '–' + r.last_year + '</dd></div>' +
      '<div><dt>Last 10 years vs first 20</dt><dd>' + (isNaN(r.recent_shift) ? 'record too short' : (r.variable === 'T' ? signed(r.recent_shift, 2) + ' °C' : signed(r.recent_shift, 0) + ' points of normal')) + '</dd></div>' +
      '<div><dt>Normal</dt><dd>' + (r.variable === 'T' ? r.normal.toFixed(1) + ' °C' : Math.round(r.normal_mm) + ' mm') + ' (' + r.baseline[0] + '–' + r.baseline[1] + ')</dd></div>' +
      '<div><dt>Natural-variation model</dt><dd>AR(1), lag-1 correlation ' + f.phi.toFixed(2) + ', seed ' + r.seed + '</dd></div>' +
      '<div><dt>Robustness: IAAFT surrogates</dt><dd>' + pWords(ri.p) + ' · outside ' + ri.outside + ' of ' + ri.N + '</dd></div>' +
      '<div><dt>Data used</dt><dd>' + r.n_years + ' seasons, months up to ' + r.data_cutoff + '</dd></div></dl>' + planet(r);
    // forecast
    html += '<h3>' + (cut ? 'What our forecast method would have said for ' : 'Chances for the next ') + esc(E.seasonLabel(r.season)) + ' (' + (fc && fc.target_year || (r.last_year + 1)) + ')</h3>';
    if (fc && !fc.error) {
      html += bar(fc.probabilities) + '<p class="small muted">Compared with 33% each if the climate were not shifting. Normal = ' + fc.tercile_edges[0].toFixed(1) + '–' + fc.tercile_edges[1].toFixed(1) + ' ' + fc.unit + '.' +
        (fc.observed ? ' <strong>What actually happened: ' + fc.observed + ' normal</strong> (' + fc.observed_value.toFixed(1) + ' ' + fc.unit + '); the method gave that ' + pct(fc.probabilities[fc.observed]) + '.' : '') +
        (cut ? '' : ' This forecast is computed now, in your browser; it is not locked. Locked, fingerprinted forecasts exist for our demo places.') + '</p>';
    } else html += '<p class="small">' + esc(fc ? fc.error : 'Not available.') + '</p>';
    if (h && h.n) html += '<p class="small">Track record of this method here: forecasting each ' + esc(E.seasonLabel(r.season)) + ' from ' + h.first_year + ' to ' + h.last_year +
      ' using only earlier data, it was ' + (h.rpss > 0.02 ? 'better than' : h.rpss < -0.02 ? 'worse than' : 'no better than') + ' saying 33/33/33 (skill score ' + signed(h.rpss, 2) +
      '), and its most likely category was right ' + pct(h.hit_rate) + ' of the time.</p>';
    // self-check
    html += '<div class="box" id="selfcheck"><h3 style="margin-top:0">Check the checker, for this place</h3><p>A test that sees climate change everywhere is useless. This makes 200 fake ' +
      'records with <em>this place\'s own</em> natural ups and downs and <strong>no trend</strong>, and runs the whole trial on each. A fair test flags about 5%. ' +
      'Then it makes 200 fake records with a real trend the size of this one, to show how often a change like this is caught in a record this long.</p>' +
      '<button type="button" id="runcheck">Run the check (a few seconds)</button><div id="checkout" aria-live="polite"></div></div>';
    html += '<h3>Share or keep this result</h3><div class="row"><input id="sharelink" readonly value="' + esc(st.url) + '" aria-label="Link to this result">' +
      '<button type="button" id="copylink">Copy link</button><button type="button" id="dljson">Download JSON</button><button type="button" id="dlcsv">Download CSV</button></div>' +
      '<p class="small muted">Same method as our cards, and the same link always gives the same answer. The imaginary histories come from a different random-number generator than the ' +
      'published cards, so p can differ from a card by a little; an automated test checks the two agree. Data: NASA POWER (fetched just now by your browser).</p>';
    out.innerHTML = html; out.scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('copylink').onclick = function () { $('sharelink').select(); try { navigator.clipboard.writeText($('sharelink').value); this.textContent = 'Copied'; } catch (e) { document.execCommand('copy'); } };
    $('dljson').onclick = function () { download('cassandra-signal.json', JSON.stringify({ place: { name: st.name, lat: st.lat, lon: st.lon }, settings: st.opts, result: r }, null, 1), 'application/json'); };
    $('dlcsv').onclick = function () { var a = r.arrays, lines = ['year,value,histories_p5,histories_p50,histories_p95,unit'];
      a.years.forEach(function (y, i) { lines.push([y, a.plot[i].toFixed(3), a.band_lo[i].toFixed(3), a.band_mid[i].toFixed(3), a.band_hi[i].toFixed(3), r.unit].join(',')); });
      if (r.after) r.after.years.forEach(function (y, i) { lines.push([y, r.after.plot[i].toFixed(3), '', '', '', r.unit + ' (after cut-off)'].join(',')); });
      download('cassandra-signal.csv', lines.join('\n') + '\n', 'text/csv'); };
    $('runcheck').onclick = function () {
      var btn = this; btn.disabled = true; var co = $('checkout');
      co.innerHTML = '<div class="progress"><span style="width:0"></span></div><p class="small muted" id="checkstep">Trend-free records…</p>';
      ask({ cmd: 'selfcheck', fit: r.test.fit, years: r.arrays.years, trendPerYear: r.test.real, seed: r.seed }, function (m) {
        var frac = (m.step === 'none' ? 0 : 0.5) + (m.fraction || 0) / 2; co.querySelector('.progress span').style.width = (frac * 100).toFixed(0) + '%';
        $('checkstep').textContent = m.step === 'none' ? 'Trend-free records…' : 'Records with a real trend this size…';
      }).then(function (c) {
        var fa = c.none, pw = c.real, fair = fa.rate <= 0.09;
        co.innerHTML = '<dl class="facts"><div><dt>False alarms (no trend)</dt><dd>' + fa.flagged + ' of ' + fa.M + ' flagged = ' + pct(fa.rate) + '</dd></div>' +
          '<div><dt>Caught (real trend this size)</dt><dd>' + pw.flagged + ' of ' + pw.M + ' = ' + pct(pw.rate) + '</dd></div></dl><p>' +
          (fair ? 'The test behaves fairly here: about 1 false alarm in 20 is what p &lt; 0.05 promises.' : 'More false alarms than promised here; treat amber verdicts for this place with extra caution.') + ' ' +
          (pw.rate < 0.5 ? 'A change as big as the one measured would be caught only ' + pct(pw.rate) + ' of the time in a record this long, so "not yet" can simply mean "not enough years yet".'
            : 'A real change of this size would usually be caught (' + pct(pw.rate) + ' of the time).') + '</p>' +
          '<p class="small muted">With 200 fake records the rate itself is uncertain by about ±3 percentage points.</p>';
      }).catch(function (e) { co.textContent = 'The check failed: ' + e.message; }).then(function () { btn.disabled = false; });
    };
  }
  function download(name, text, type) { var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: type }));
    a.download = name; document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500); }

  // ------------------------------------------------------------ start from the link
  var qs = new URLSearchParams(location.search);
  if (qs.get('var') === 'P' || qs.get('var') === 'T') document.querySelector('input[name=var][value=' + qs.get('var') + ']').checked = true;
  if (qs.get('season') && $('season').querySelector('option[value="' + qs.get('season').toUpperCase() + '"]')) $('season').value = qs.get('season').toUpperCase();
  if (qs.get('cutoff')) { $('usecut').checked = true; $('cut').disabled = false; $('cut').value = qs.get('cutoff'); $('cutout').textContent = $('cut').value; }
  if (qs.get('lat') && qs.get('lon') && !isNaN(+qs.get('lat')) && !isNaN(+qs.get('lon'))) {
    setPlace(+qs.get('lat'), +qs.get('lon'), qs.get('name') || '', true);
    app.requestSubmit ? app.requestSubmit() : app.dispatchEvent(new Event('submit', { cancelable: true }));
  }
})();
