"""Page bodies for the static site. Every number comes from the analysis dicts."""
from __future__ import annotations

import math

from .climate import season_label
from .render import change_short, change_words, esc, headline_sub, outside_words, p_words

SHORT_VERDICT = {"no_alibi": "natural variation has no alibi",
                 "very_unlikely": "very unlikely to be natural variation alone",
                 "probable": "probably a real change",
                 "not_yet": "not yet distinguishable from natural variation"}
VAR_WORD = {"T": "temperature", "P": "rain"}


def mid(label):
    """A season label for the middle of a sentence ('Annual' -> 'annual')."""
    return "annual" if label == "Annual" else label


def coords(place):
    return (f"{abs(place['lat']):.2f}°{'N' if place['lat'] >= 0 else 'S'}, "
            f"{abs(place['lon']):.2f}°{'E' if place['lon'] >= 0 else 'W'}")


def pct(x):
    return f"{100 * x:.0f}%"


def prob_bar(p, var=None):
    parts = []
    for k, cls, word in (("below", "b-below", "below"), ("near", "b-near", "near"),
                         ("above", "b-above", "above")):
        w = max(p[k] * 100, 0.5)
        label = (f"{word} {p[k] * 100:.0f}%" if p[k] >= 0.16 else
                 f"{p[k] * 100:.0f}%" if p[k] >= 0.08 else "")
        parts.append(f'<span class="{cls}" style="width:{w:.1f}%" title="{word} normal: '
                     f'{p[k] * 100:.0f}%">{label}</span>')
    return f'<div class="bar {(var or "").lower()}" role="img" aria-label="below {pct(p["below"])}, near {pct(p["near"])}, above {pct(p["above"])}">{"".join(parts)}</div>'


# ---------------------------------------------------------------- pieces

def verdict_block(res, chart, hist, big=True):
    v, t = res["verdict"], res["test"]
    rob = res.get("robustness", {})
    arma, ia = rob.get("arma"), rob.get("iaaft")
    fit = t["fit"]
    if res["variable"] == "T":
        size = (f"{res['change_over_record']:+.2f} °C over {res['first_year']}–{res['last_year']} "
                f"along the trend line")
        shift = f"{res['recent_shift']:+.2f} °C"
        normal = f"{res['normal']:.1f} °C average {mid(season_label(res['season']))} temperature, {res['baseline'][0]}–{res['baseline'][1]}"
    else:
        size = (f"{res['change_over_record']:+.1f} percentage points of normal over "
                f"{res['first_year']}–{res['last_year']} along the trend line")
        shift = f"{res['recent_shift']:+.0f} points of normal"
        normal = f"{res['normal_mm']:.0f} mm in a normal {'year' if res['season'] == 'ANN' else season_label(res['season'])}, {res['baseline'][0]}–{res['baseline'][1]}"
    tag = "p"
    verdict_html = (f'<p class="verdict {v["colour"]}">{esc(v["text"])}</p>' if big else
                    f'<h3><span class="pill {v["colour"]}">{esc(v["text"])}</span></h3>')
    ar = ""
    if arma:
        ar = (f"<div><dt>Robustness: ARMA({arma['fit']['p']},{arma['fit']['q']}) chosen by AIC</dt>"
              f"<dd>{p_words(arma['p'])} · outside {arma['outside']:,}</dd></div>"
              f"<div><dt>Robustness: IAAFT surrogates</dt><dd>{p_words(ia['p'])} · outside {ia['outside']:,}</dd></div>")
    return f"""
{verdict_html}
<{tag} class="lead">{esc(headline_sub(res))} The real trend is bigger than the trend in
<strong>{t['outside']:,} of {t['N']:,}</strong> imaginary histories made of natural variation alone ({p_words(t['p'])}).</{tag}>
<img class="chart" src="{chart}" width="1170" height="546" alt="{esc(season_label(res['season']))} {res['variable_name']} at this place, {res['first_year']} to {res['last_year']}: the real record drawn over a grey band of 1,000 imaginary histories without climate change.">
<img class="chart" src="{hist}" width="1170" height="338" alt="Histogram of the trends in the 1,000 imaginary histories, with the real trend marked.">
<dl class="facts">
<div><dt>Trend (Sen's slope)</dt><dd>{esc(change_words(res))}</dd></div>
<div><dt>Size of the change</dt><dd>{esc(size)}</dd></div>
<div><dt>Last 10 years vs first 20</dt><dd>{esc(shift)}</dd></div>
<div><dt>Normal</dt><dd>{esc(normal)}</dd></div>
<div><dt>Imaginary histories (default)</dt><dd>AR(1), lag-1 correlation {fit['phi']:.2f}, seed {t['seed']}</dd></div>
{ar}
<div><dt>Data used</dt><dd>{res['n_years']} seasons, months up to {res['data_cutoff']}</dd></div>
</dl>"""


def context_block(ctx, res_t):
    return f"""
<h2 id="planet">Your place vs the planet</h2>
<p>Here, {esc(mid(season_label(res_t['season'])))} temperature has changed by <strong>{esc(change_short(res_t))}</strong>
since {res_t['first_year']} (NASA POWER). Over the same years the whole planet warmed by
<strong>{ctx['global_trend']:+.2f} °C/decade</strong> and the {esc(ctx['zone_label'])} latitude band by
<strong>{ctx['zone_trend']:+.2f} °C/decade</strong> (NASA GISTEMP v4, annual means, {ctx['first']}–{ctx['last']}).
In {ctx['last']} the planet was <strong>{ctx['latest']:+.2f} °C</strong> warmer than its 1951–1980 average.</p>
<p class="small muted">GISTEMP blends land and ocean and covers whole years; POWER covers one point and one season,
so the numbers are context, not a like-for-like comparison.</p>"""


def warned_words(bt):
    res, exp = bt["result"], bt["expected_direction"]
    if bt["warned"]:
        return ("Yes", f"Before the event the record already showed a {exp} change that natural variation "
                       f"could not explain ({SHORT_VERDICT[res['verdict']['key']]}).")
    if res["verdict"]["key"] != "not_yet":
        return ("No", f"The record showed a significant change, but towards {res['direction']}, "
                      f"the opposite of this event.")
    return ("No", f"Before the event the {mid(season_label(res['season']))} record was not yet distinguishable "
                  f"from natural variation (the trend pointed {res['direction']}, {p_words(res['test']['p'])}).")


def observed_words(bt):
    o, res = bt["observed"], bt["result"]
    if res["variable"] == "T":
        s = f"{o['anomaly']:+.2f} °C against the {res['baseline'][0]}–{res['baseline'][1]} average"
        order = "hottest"
    else:
        s = f"{o['pct_of_normal']:.0f}% of normal rain ({o['total_mm']:.0f} mm, SPI {o['spi']:+.1f})"
        order = "driest" if bt["expected_direction"] == "drier" else "wettest"
    unit = "years" if res["season"] == "ANN" else "seasons"
    rank = (f"the {order} of the {o['record_years'] + 1} {unit} since {res['first_year']}"
            if o["rank_in_record"] == 1 else
            f"number {o['rank_in_record']} of {o['record_years'] + 1} by that measure")
    if "more_extreme_than_pct" in o:
        word = {"warmer": "hotter", "drier": "drier", "wetter": "wetter", "cooler": "colder"}[bt["expected_direction"]]
        x = o["more_extreme_than_pct"]
        shown = f"{math.floor(x * 10) / 10:.1f}" if x >= 99 else f"{math.floor(x):.0f}"
        rank += (f"; {word} than {shown}% of the years in 1,000 natural histories "
                 f"built only from the data before it")
    vis = {"extreme": "It stands out as extreme in this dataset",
           "unusual": "It shows as unusual, though not extreme, in this dataset",
           "not visible": "It barely shows in this dataset at this point"}[o["visibility"]]
    return s.replace("+-", "−"), rank, vis


def backtest_block(bts, place):
    if not bts:
        return ""
    out = ['<h2 id="backtest">Would it have warned? Backtests on real events</h2>',
           '<p>We rerun the whole trial using <em>only</em> the data that existed before each event: '
           'the record is cut at the end of the year before (or before the season starts, whichever is '
           'earlier), and the baseline, the fitted noise and the 1,000 histories are all rebuilt from '
           'that shorter record. Nothing after the cut-off is used.</p>']
    for bt in bts:
        ev, res = bt["event"], bt["result"]
        yes, why = warned_words(bt)
        obs, rank, vis = observed_words(bt)
        fc = bt["forecast_at_the_time"]
        fc_html = ""
        if "probabilities" in fc:
            exp_cat = "above" if bt["expected_direction"] in ("warmer", "wetter") else "below"
            fc_html = (f"<p>Our seasonal forecast method, run with the same data, would have said:</p>"
                       f"{prob_bar(fc['probabilities'], ev['variable'])}<p class='small muted'>Climatology says 33% each. "
                       f"It gave {pct(fc['probabilities'][exp_cat])} to <em>{exp_cat} normal</em>.</p>")
        missing = ("" if bt["observed"]["visibility"] != "not visible" else
                   "<p class='small'><strong>Data check:</strong> this event does not stand out in the NASA "
                   "POWER record at this point (a coarse reanalysis/satellite estimate), so no method using "
                   "these data could have flagged it. Station records or other datasets may tell a different "
                   "story.</p>")
        out.append(f"""<div class="box">
<h3>{esc(ev['name'])} <span class="muted small">({esc(season_label(ev['season']))} {VAR_WORD[ev['variable']]}, {ev['year']}) ·
<a href="{esc(ev['source'])}">source</a></span></h3>
<p><strong>Would the signal have warned? <span class="{'red' if yes == 'Yes' else 'grey'}">{yes}.</span></strong> {esc(why)}</p>
<p>Using data up to {bt['cutoff']} ({res['n_years']} seasons): <span class="pill {res['verdict']['colour']}">{esc(res['verdict']['text'])}</span>
· trend {esc(change_short(res))} · outside {res['test']['outside']:,} of {res['test']['N']:,} histories.</p>
<p>What happened: {esc(obs)}, {esc(rank)}. {esc(vis)}.</p>
{missing}{fc_html}<p class="small"><a href="{esc(check_link('../../', place, ev['variable'], ev['season'], int(bt['cutoff'][:4])))}">Re-run this backtest live, and move the cut-off year →</a></p></div>""")
    return "\n".join(out)


def forecast_block(locked, hind, repo_url, last10=None):
    out = ['<h2 id="forecasts">Forecast track record</h2>',
           '<p>Before a season starts we publish the chance that it will be <em>below</em>, <em>near</em> or '
           '<em>above</em> normal (the middle third of 1981–2010). Each forecast is a file committed to the '
           'public repository; the commit time and the file\'s SHA-256 fingerprint prove it was not changed '
           'after the fact. When the season\'s data arrive we score it, misses included.</p>']
    if locked:
        rows = []
        for lf in locked:
            d, g = lf["doc"], lf["git"]
            for var, fc in d["variables"].items():
                if "probabilities" not in fc:
                    rows.append(f"<tr><td>{d['season']} {d['target_year']}</td><td>{VAR_WORD[var]}</td>"
                                f"<td colspan='3' class='muted'>Not issued: {esc(fc['not_issued'])}</td></tr>")
                    continue
                sc = lf["scores"].get(var, {})
                if sc.get("status") == "scored":
                    status = (f"Observed <strong>{sc['observed']}</strong>. RPS {sc['rps']:.3f} vs "
                              f"climatology {sc['rps_clim']:.3f} "
                              f"({'better' if sc['rps'] < sc['rps_clim'] else 'worse'})")
                else:
                    status = "Waiting for the season's data"
                edges = fc["tercile_edges"]
                unit = fc["unit"]
                rows.append(f"<tr><td>{d['season']} {d['target_year']}<br><span class='small muted'>"
                            f"{esc(d['season_months'])}</span></td><td>{VAR_WORD[var]}<br><span class='small muted'>"
                            f"normal: {edges[0]:.1f}–{edges[1]:.1f} {unit}</span></td>"
                            f"<td>{prob_bar(fc['probabilities'], var)}</td><td>{status}</td></tr>")
            if g.get("committed"):
                lock = (f"Locked in commit <a href='{repo_url}/commit/{g['commit']}'><code>{g['commit'][:10]}</code></a> "
                        f"at {esc(g['commit_time'])}"
                        + (" · file unchanged since then ✓" if g.get("unchanged_since_commit") else
                           " · <strong>file has changed since it was committed</strong>"))
            else:
                lock = "Not committed yet (local build)"
            rows.append(f"<tr><td colspan='4' class='small'>{lock}<br>Issued {esc(d['issued_at_utc'])} with data "
                        f"to {esc(d['variables'].get('T', {}).get('data_cutoff', '?'))} · "
                        f"<a href='{repo_url}/blob/main/{esc(lf['file'])}'>forecast file</a> · SHA-256 "
                        f"<span class='mono'>{lf['sha256']}</span></td></tr>")
        out.append("<div class='scroll'><table><thead><tr><th>Season</th><th>What</th><th>Chances</th>"
                   "<th>Result</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
        out.append("<p class='small muted'>Check a fingerprint yourself: download the file and run "
                   "<code>sha256sum</code> (Linux/macOS) or <code>certutil -hashfile FILE SHA256</code> (Windows).</p>")
    else:
        out.append("<p>No locked forecasts yet for this place.</p>")
    if last10:
        h10 = last10
        rows10 = "".join(
            f"<tr><td>{esc(h10['season'])} {r['year']}</td><td>{prob_bar(r['probabilities'], h10['variable'])}</td>"
            f"<td><strong>{r['observed']}</strong> ({r['value']:.1f} {h10['unit']})</td>"
            f"<td>{'✓' if max(r['probabilities'], key=r['probabilities'].get) == r['observed'] else '✗'}</td></tr>"
            for r in h10["rows"])
        out.append(f"<h3>Track record: the last {len(h10['rows'])} {esc(h10['season_words'])} seasons</h3>"
                   f"<p class='small'>The same {VAR_WORD[h10['variable']]} forecast method, re-run for each past season "
                   f"using only the data from before it (hindcasts, not locked). Its most likely category came true "
                   f"in <strong>{h10['hits']} of {len(h10['rows'])}</strong>; skill vs always saying 33/33/33: "
                   f"<strong>{h10['rpss'] * 100:+.0f}%</strong>.</p><div class='scroll'><table><thead><tr><th>Season</th>"
                   f"<th>Forecast</th><th>What happened</th><th>Most likely right?</th></tr></thead><tbody>{rows10}"
                   f"</tbody></table></div>")
    hrows = []
    for var, h in hind.items():
        if not h.get("n"):
            continue
        better = "better than" if h["rpss"] > 0.02 else ("worse than" if h["rpss"] < -0.02 else "no better than")
        hrows.append(f"<tr><td>{esc(season_label(h['season']))} {VAR_WORD[var]}</td><td>{h['first_year']}–{h['last_year']} "
                     f"({h['n']} seasons)</td><td>{h['rpss']:+.2f}</td><td>{pct(h['hit_rate'])}</td>"
                     f"<td>{better} climatology</td></tr>")
    out.append("<h3>How the method did on past seasons (hindcasts)</h3>"
               "<p class='small'>Each past season was forecast using only data from before it. These are "
               "<strong>not</strong> locked forecasts, so they estimate skill but prove nothing about honesty. "
               "Skill score: 1 = perfect, 0 = no better than always saying 33/33/33, below 0 = worse.</p>"
               "<div class='scroll'><table><thead><tr><th>Series</th><th>Seasons</th><th>Skill (RPSS)</th>"
               "<th>Most likely category right</th><th>Verdict</th></tr></thead><tbody>"
               + "".join(hrows) + "</tbody></table></div>")
    return "\n".join(out)


def place_body(place, primary, secondary, ctx, bts, locked, hind, repo_url, power_url, last10=None):
    p_var = primary["variable"]
    return f"""
<p class="muted small" style="margin-top:0">{coords(place)} · judged on {esc(season_label(primary['season']))} {primary['variable_name']}</p>
<h1>{esc(place['name'])}</h1>
<p class="muted">{esc(place['notes'])}</p>
{verdict_block(primary, f"chart-{p_var}.png", f"hist-{p_var}.png")}
<p><a class="cta" href="{esc(check_link('../../', place, p_var, primary['season']))}">Re-run this live, or change the season →</a></p>
<p class="small"><a href="card.png">Share card (PNG)</a> · <a href="data.json">All numbers (JSON)</a></p>
<h2 id="second">{esc(season_label(secondary['season']))} {esc(secondary['variable_name'])}</h2>
{verdict_block(secondary, f"chart-{secondary['variable']}.png", f"hist-{secondary['variable']}.png", big=False)}
{context_block(ctx, primary if p_var == 'T' else secondary)}
{backtest_block(bts, place)}
{forecast_block(locked, hind, repo_url, last10)}
<h2 id="sources">Sources</h2>
<ul>
<li>NASA POWER monthly point data for this place:
<a href="{esc(power_url)}">API request</a> (T2M, PRECTOTCORR; −999 treated as missing). Raw response cached in the repository.</li>
<li><a href="https://data.giss.nasa.gov/gistemp/">NASA GISTEMP v4</a> global and zonal annual means (1951–1980 base).</li>
<li>Event sources are linked in each backtest above.</li>
</ul>
<p class="small muted">What this does not show: a signal means the change is bigger than natural variation can
explain. It does not, on its own, prove the cause. See <a href="../../method/#limits">limitations</a>.</p>
"""


def index_body(cards, fa_rows, n_locked, n_pending, n_scored):
    tiles = "".join(
        f"""<a class="place" href="place/{c['slug']}/"><img src="place/{c['slug']}/card.png" width="1200" height="630" alt="Share card for {esc(c['name'])}" loading="lazy">
<div class="body"><strong>{esc(c['name'])}</strong><div class="v {c['colour']}">{esc(c['verdict'])}</div>
<div class="small muted">{esc(c['what'])} · {esc(c['change'])}</div></div></a>""" for c in cards)
    fa = "".join(f"<tr><td>{esc(r['description'])}</td><td>{r['flagged']} of {r['n_series']}</td>"
                 f"<td><strong>{pct(r['rate'])}</strong></td><td>{pct(r['ci95'][0])}–{pct(r['ci95'][1])}</td></tr>"
                 for r in fa_rows if r["trend_sd_per_decade"] == 0)
    return f"""
<h1>Is it climate change, or just a bad year?</h1>
<p class="lead">Cassandra Signal puts each place's weather record on trial. We build <strong>1,000 imaginary
histories</strong> of what that place's record could have looked like through natural ups and downs alone,
and ask whether the real record stands out from all of them. Then we keep an honest public track record:
we test the method on past droughts and heatwaves, and we lock in forecasts before each season starts.</p>
<p><a class="cta" href="check/">Check any place yourself →</a>
<span class="muted small">Any point on Earth, any season, any year back to 1996. Runs in your browser in a few seconds.</span></p>
<p class="muted">In Greek myth, Cassandra gave true warnings that nobody believed. Warnings get believed when the evidence
can be checked and the predictions were written down first.</p>
<div class="grid">{tiles}</div>
<h2>How to read a card</h2>
<ol>
<li><strong>The verdict</strong> in plain words. <span class="red">Red</span>: natural variation almost certainly can't explain it
(beyond 990 of 1,000 histories). <span class="amber">Amber</span>: probably a real change (beyond 950). <span class="grey">Grey</span>:
not yet distinguishable. We never force a signal.</li>
<li><strong>The chart</strong>: the bold line is the real record; the grey band is where 90% of the 1,000 imaginary histories fall.</li>
<li><strong>The backtest</strong>: would the signal have warned us before a real drought or heatwave, using only the data we had then?</li>
<li><strong>The forecasts</strong>: chances of a below-, near- or above-normal season, published and fingerprinted before it starts.</li>
</ol>
<h2>Is the test itself honest?</h2>
<p>A test that sees climate change everywhere is useless. We fed the method thousands of made-up records that have
<em>no trend at all</em>. A fair test should cry wolf about 5% of the time at the "probably a real change" level.</p>
<div class="scroll"><table><thead><tr><th>Trend-free test series (45 years each)</th><th>Flagged</th><th>False-alarm rate</th>
<th>95% range</th></tr></thead><tbody>{fa}</tbody></table></div>
<p><a href="method/">The full method, its checks and its limits</a>.</p>
<h2>Forecasts on the record</h2>
<p>{n_locked} locked forecast file(s) so far: {n_scored} scored, {n_pending} waiting for their season's data.
Each place page lists them with their commit and SHA-256 fingerprint.</p>
"""


def method_body(fa_rows, n_hist, seed):
    fa = "".join(f"<tr><td>{esc(r['description'])}</td><td>{r['trend_sd_per_decade']:.2f}</td>"
                 f"<td>{r['flagged']} of {r['n_series']}</td><td><strong>{pct(r['rate'])}</strong></td>"
                 f"<td>{pct(r['ci95'][0])}–{pct(r['ci95'][1])}</td></tr>" for r in fa_rows)
    return f"""
<h1>Method, checks and limits</h1>
<p class="lead">Everything here is computed by a public Python pipeline from NASA data. The code is the
specification; this page says what it does in plain words.</p>

<h2>1. Prepare each series</h2>
<p>For each place we download monthly 2 m air temperature (T2M, °C) and bias-corrected precipitation
(PRECTOTCORR, mm/day, turned into monthly totals) from NASA POWER, 1981 to the latest published month.
Values of −999 are treated as missing; seasons with any missing month are skipped.</p>
<ul>
<li><strong>Temperature:</strong> each month minus that calendar month's 1981–2010 average, then averaged over the
season being judged (for example June–August).</li>
<li><strong>Rain:</strong> seasonal totals turned into a standardised precipitation index (SPI): a gamma
distribution is fitted to the 1981–2010 totals (with a separate chance of zero rain) and each total is mapped to the
matching point of a standard normal curve. Charts show the same thing as percent of the 1981–2010 normal. A monthly SPI
(one gamma fit per calendar month) is also computed for reference.</li>
<li>A season that crosses New Year is labelled by its last month: Dec 2026 to Feb 2027 is "DJF 2027".</li>
</ul>

<h2>2. The test statistic</h2>
<p>For both variables we use <strong>Sen's slope</strong>: the median of the slopes between every pair of years. It is
robust to a single freak year. We also report, without testing it, the mean of the last 10 years minus the mean of the
first 20.</p>

<h2>3. The 1,000 imaginary histories</h2>
<p>We remove the straight-line trend from the record. What is left is treated as natural variability, and we fit a
simple model of it: <strong>AR(1) noise</strong>, where each year partly remembers the last (lag-1 correlation) plus fresh
randomness. From that model we draw {n_hist:,} new series of the same length, with a fixed, recorded random seed (base seed
{seed}; each series gets a seed derived from its place, variable and season). None of them contain a trend by construction.</p>
<p>Short records fool simple models. We measured three problems and correct each one: the lag-1 correlation of a
45-year detrended series is biased low by about (2 + 5φ)/n; removing a trend line also removes some genuine slow
wandering, so the variance is too small; and both numbers are uncertain, so each imaginary history draws its own
correlation and variance from their sampling uncertainty instead of reusing one best guess. Without these corrections
the method raised false alarms 7–9% of the time on series with memory instead of 5%.</p>
<p><strong>Robustness checks</strong>, shown on every card: ARMA(p, q) noise with p, q up to 2 chosen by AIC, and IAAFT
surrogates, which shuffle the detrended record while keeping its exact values and almost exactly its power spectrum.</p>

<h2>4. The verdict</h2>
<p>We count how many imaginary histories have a trend at least as large as the real one, in either direction, and
compute p = (count + 1) / (N + 1).</p>
<table><thead><tr><th>Real trend is beyond…</th><th>p</th><th>Verdict</th></tr></thead><tbody>
<tr><td>all 1,000 histories</td><td>&lt; 0.001</td><td class="red">Natural variation has no alibi</td></tr>
<tr><td>990 of them</td><td>&lt; 0.01</td><td class="red">Very unlikely to be natural variation alone</td></tr>
<tr><td>950 of them</td><td>&lt; 0.05</td><td class="amber">Probably a real change</td></tr>
<tr><td>fewer than 950</td><td>≥ 0.05</td><td class="grey">Not yet distinguishable from natural variation</td></tr>
</tbody></table>
<p>We always report the direction (warmer or cooler, wetter or drier) and the size in real units.</p>

<h2 id="false-alarms">5. Checking the generator, not just the record</h2>
<p>We run the whole procedure, from detrending to verdict, on made-up series. Rows with trend 0 have no trend at all,
so anything flagged is a false alarm; a fair test flags about 5%. Rows with a trend show how often a real change of that
size (in noise standard deviations per decade) is caught in 45 years: the test's power.</p>
<div class="scroll"><table><thead><tr><th>Series</th><th>Trend (sd/decade)</th><th>Flagged at p &lt; 0.05</th>
<th>Rate</th><th>95% range</th></tr></thead><tbody>{fa}</tbody></table></div>

<h2>6. Backtests</h2>
<p>For each documented drought or heat event we rerun steps 1–4 with the data cut at the end of the year before the
event (or before the season starts, if that is earlier). The baseline, the fitted noise and the histories are all rebuilt
from that shorter record; an automated test checks that changing any later data changes nothing. "Would it have
warned?" means: before the event, did the record already show a significant change in the event's direction? We also
check whether the event is even visible in the POWER data at that point, and say so when it is not.</p>
<p>A trend test cannot predict a single bad season; it tells you whether the odds had already shifted. The forecast
shown in each backtest is the seasonal method below, run with the same pre-event data.</p>

<h2>7. Locked seasonal forecasts</h2>
<p>Before each season we write <code>forecasts/{{place}}/{{year}}-{{season}}.json</code> with the chances of a below-, near-
or above-normal season (terciles of 1981–2010), the method and the data cut-off. The method slides the climatology
along the Sen's-slope trend line and keeps every category at 2% or more. The file is committed to the public repository
and never overwritten. The page shows the commit that added it, the time of that commit, and the file's SHA-256; the
build re-checks that the file still matches the committed version. A monthly GitHub Action fetches new data, issues the
next season's forecasts before the season starts, and scores finished seasons with the ranked probability score (RPS)
and Brier score against the 33/33/33 climatology, misses included.</p>

<h2 id="live">8. The live checker</h2>
<p>The <a href="../check/">checker</a> runs steps 1–7 in your browser for any point and season, using a JavaScript copy of
the pipeline. An automated test runs it against the Python code for every demo place: trends, anomalies, noise fits,
SPI, forecasts and hindcast skill match, and p-values agree within sampling noise (the random number generators differ).
Its self-check repeats step 5 with the chosen place's own fitted noise.</p>

<h2 id="limits">Limitations</h2>
<ul>
<li><strong>Short records.</strong> NASA POWER starts in 1981, so each test has about 45 seasons. Real but modest
changes can still read "not yet": see the power rows above.</li>
<li><strong>Not a weather station.</strong> POWER is a reanalysis and satellite-based estimate on a grid of roughly
half a degree. Local events can be missed: the grid cell over central Cape Town shows no 2017 drought, which is why that
card uses the dam catchment that actually ran dry, and some backtests are marked "barely shows in this dataset".</li>
<li><strong>Signal is not cause.</strong> A significant trend shows change beyond natural variation as we modelled it. On
its own it does not prove what caused the change; that needs attribution studies.</li>
<li><strong>Rain is noisier than temperature.</strong> Expect many more "not yet" verdicts for rain.</li>
<li><strong>The noise model is a model.</strong> If natural variability has slower swings than AR(1) or ARMA(2,2) can
represent (for example multi-decade ocean cycles), the histories are too calm. The IAAFT check helps but cannot see swings
longer than the record.</li>
<li><strong>Several tests.</strong> With two variables at many places, about 1 test in 20 can be amber by chance alone.</li>
</ul>

<h2 id="ai-use">AI use</h2>
<p>As required by the NASA Space Apps Challenge rules we disclose AI use. The project idea, the method and its
choices, and the review of results are the team's. An AI coding assistant (a large language model) wrote most of the
Python code (data download, statistics, backtests, forecasts, charts and page generation), the JavaScript live checker, the tests, the GitHub
Actions workflows, the README and the wording of these pages, working from the team's written brief. The team ran the
pipeline, read the outputs and checked them against the brief. Charts and share cards are drawn by our code from NASA
data; no image on this site was produced by an image-generating AI.</p>

<h2>Data and citation</h2>
<ul>
<li>NASA POWER (Prediction Of Worldwide Energy Resources), NASA Langley Research Center:
<a href="https://power.larc.nasa.gov/">power.larc.nasa.gov</a>, monthly point API, community AG.</li>
<li>GISTEMP Team: GISS Surface Temperature Analysis (GISTEMP), version 4. NASA Goddard Institute for Space Studies:
<a href="https://data.giss.nasa.gov/gistemp/">data.giss.nasa.gov/gistemp</a>. Lenssen, N., et al. (2019),
Improvements in the GISTEMP uncertainty model, J. Geophys. Res. Atmos., 124, 6307–6326.</li>
</ul>
"""


SEASON_CHOICES = [("ANN", "Whole year"), ("DJF", "Dec–Feb"), ("MAM", "Mar–May"), ("JJA", "Jun–Aug"),
                  ("SON", "Sep–Nov"), ("JJAS", "Jun–Sep (South Asian monsoon)"), ("JAS", "Jul–Sep (Sahel rains)"),
                  ("OND", "Oct–Dec (East African short rains)"), ("AMJJAS", "Apr–Sep (southern winter half)"),
                  ("NDJFM", "Nov–Mar (northern winter half)")]


def check_link(root, place, var, season, cutoff=None):
    from urllib.parse import urlencode
    q = {"lat": f"{place['lat']:.3f}", "lon": f"{place['lon']:.3f}", "name": place["name"], "var": var,
         "season": season}
    if cutoff:
        q["cutoff"] = cutoff
    return f"{root}check/?{urlencode(q)}"


def check_body(max_cut):
    opts = "".join(f'<option value="{k}"{" selected" if k == "JJA" else ""}>{esc(v)}</option>'
                   for k, v in SEASON_CHOICES)
    return f"""
<h1>Check any place yourself</h1>
<p class="lead">Pick any point on Earth and a season. Your browser downloads that point's monthly NASA POWER record
(1981 to now) and puts it on trial with the same method as our cards: it builds 1,000 imaginary histories of
natural ups and downs, ranks the real trend among them and gives a verdict. Nothing here is pre-computed, and
nothing is sent to us.</p>
<form id="checker" class="box" data-root="../" novalidate>
<fieldset><legend>1. Where?</legend>
<div class="row"><input id="q" type="search" placeholder="Search a city, town or region" autocomplete="off" aria-label="Search for a place">
<button type="button" id="geo">Use my location</button></div>
<ul id="results"></ul>
<div id="map" role="application" aria-label="Map: click to choose a point"></div>
<div class="row"><label>Latitude <input id="lat" type="number" step="0.001" min="-90" max="90" inputmode="decimal"></label>
<label>Longitude <input id="lon" type="number" step="0.001" min="-180" max="180" inputmode="decimal"></label></div>
<p class="small">Chosen: <span id="placename" class="muted">nothing yet</span></p>
<p class="small muted">Or start from one of our demo places: <span id="chips"></span></p>
</fieldset>
<fieldset><legend>2. What?</legend>
<div class="row seg" role="radiogroup" aria-label="Variable">
<label><input type="radio" name="var" value="T" checked> Temperature</label>
<label><input type="radio" name="var" value="P"> Rain</label>
<label>Season <select id="season">{opts}</select></label></div>
</fieldset>
<fieldset><legend>3. When? <span class="muted small">(optional: a backtest)</span></legend>
<label class="row"><input type="checkbox" id="usecut"> Pretend it is the end of <output id="cutout">2002</output>
and use only the data that existed then</label>
<input type="range" id="cut" min="1996" max="{max_cut}" value="2002" disabled aria-label="Cut-off year">
<p class="small muted">Everything is rebuilt from that shorter record, baseline included. The chart then shows what
happened next, and the forecast is scored against it.</p>
</fieldset>
<button type="submit" class="primary" id="run">Put it on trial</button>
</form>
<ol id="steps" class="steps" aria-live="polite" hidden></ol>
<div id="out" hidden></div>
<h2>What happens when you press the button</h2>
<ol>
<li>Your browser asks the NASA POWER API for monthly temperature and rain at your point.</li>
<li>Each month is compared with its 1981–2010 average and averaged (or, for rain, totalled) over your season.</li>
<li>The trend is measured with Sen's slope, the median slope between every pair of years.</li>
<li>The trend line is removed and what is left, the natural ups and downs, is modelled. 1,000 new records are made
from that model. None of them contains a trend.</li>
<li>If the real trend is bigger than in 950, 990 or all 1,000 of them, the verdict says so. Otherwise it says
"not yet". A second, different kind of imaginary history (IAAFT) is used as a cross-check.</li>
<li>Optionally, the checker tests itself on your place: fake records with no trend should be flagged only about 5%
of the time.</li>
</ol>
<p><a href="../method/">The full method, its checks and its limits</a>.</p>
"""
