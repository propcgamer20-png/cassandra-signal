"""Charts (matplotlib), the 1200x630 share card, and static HTML pages."""
from __future__ import annotations

import html
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .climate import season_label  # noqa: E402

COLOURS = {"red": "#b4472d", "amber": "#b8801f", "grey": "#667074"}
INK, MUTED, BAND, PAPER = "#1d2b30", "#5c676a", "#a49d90", "#f2ede3"
CHART_BG, GRID, RULE = "#faf7f1", "#e6dfd1", "#d3cab8"
AI_NOTE = "Code and text AI-assisted; see the AI-use note."
FOOTER_DATA = "Data: NASA POWER, NASA GISTEMP v4"

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#cfc6b4",
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED})


def esc(x) -> str:
    return html.escape(str(x), quote=True)


# ---------------------------------------------------------------- formatting

def fmt_signed(v, unit, nd=2):
    return f"{v:+.{nd}f} {unit}".replace("-", "−")


def change_words(res) -> str:
    """'+0.49 °C per decade' or '+7.2 percentage points of normal per decade'."""
    if res["variable"] == "T":
        return fmt_signed(res["trend_per_decade"], "°C per decade")
    return fmt_signed(res["trend_per_decade"], "points of normal rain per decade", 1).replace(
        "points", "percentage points")


def change_short(res) -> str:
    if res["variable"] == "T":
        return fmt_signed(res["trend_per_decade"], "°C/decade")
    return fmt_signed(res["trend_per_decade"], "% of normal/decade", 1).replace(" %", "%")


def headline_sub(res) -> str:
    what = f"{season_label(res['season'])} {res['variable_name']}"
    if res["variable"] == "T":
        trend = "rising" if res["direction"] == "warmer" else "falling"
    else:
        trend = "rising" if res["direction"] == "wetter" else "falling"
    if res["verdict"]["key"] == "not_yet":
        return (f"{what} has a trend of {change_words(res)} since {res['first_year']} "
                f"(pointing {res['direction']}), but natural variation alone can produce a trend that size.")
    return f"{what} is {trend}: {change_words(res)} since {res['first_year']}."


def outside_words(res) -> str:
    t = res["test"]
    return f"Outside {t['outside']:,} of {t['N']:,} imaginary histories"


def p_words(p):
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


# ---------------------------------------------------------------- charts

def draw_record(ax, res, compact=False):
    a = res["_arrays"]
    years, real, band = a["years"], a["plot"], a["band"]
    colour = COLOURS[res["verdict"]["colour"]]
    ax.plot(years, band[:: max(1, len(band) // 400)].T, color=BAND, alpha=0.035, lw=0.6, zorder=1)
    lo, med, hi = np.percentile(band, [5, 50, 95], axis=0)
    ax.fill_between(years, lo, hi, color=BAND, alpha=0.28, lw=0, zorder=2,
                    label="1,000 imaginary histories (5–95%)")
    ax.plot(years, med, color=BAND, lw=1, ls="--", zorder=2)
    ref = 0 if res["variable"] == "T" else 100
    ax.axhline(ref, color=RULE, lw=0.8, zorder=0)
    ax.plot(years, real, color=colour if res["verdict"]["colour"] != "grey" else INK,
            lw=2.8 if not compact else 2.4, zorder=4, label="Real record")
    b = res["trend_per_decade"] / 10
    tt = years.astype(float)
    icpt = np.median(real - b * tt)
    ax.plot(tt, icpt + b * tt, color=INK, lw=1, ls=":", zorder=3, label="Trend (Sen's slope)")
    ax.set_xlim(years[0], years[-1])
    if res["variable"] == "T":
        ax.set_ylabel(f"{season_label(res['season'])} temperature\nvs 1981–2010 (°C)")
    else:
        ax.set_ylabel(f"{season_label(res['season'])} rain\n(% of 1981–2010 normal)")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.tick_params(labelsize=9 if compact else 10)
    if not compact:
        ax.legend(loc="upper left", frameon=False, fontsize=9)


def chart_png(res, path: Path):
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=130)
    fig.patch.set_facecolor(CHART_BG)
    ax.set_facecolor(CHART_BG)
    draw_record(ax, res)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def null_hist_png(res, path: Path):
    a = res["_arrays"]
    fig, ax = plt.subplots(figsize=(9, 2.6), dpi=130)
    fig.patch.set_facecolor(CHART_BG)
    ax.set_facecolor(CHART_BG)
    ax.hist(a["null_stats"], bins=50, color=BAND, alpha=0.8)
    colour = COLOURS[res["verdict"]["colour"]]
    ax.axvline(a["real_stat"], color=colour if res["verdict"]["colour"] != "grey" else INK, lw=2.5)
    ax.axvline(-a["real_stat"], color=MUTED, lw=1, ls=":")
    unit = "°C" if res["variable"] == "T" else "SPI units"
    ax.set_xlabel(f"Trend per decade in each imaginary history ({unit}); bold line = the real trend,"
                  " dotted = its mirror image")
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def card_png(place, res, lines, path: Path, site_url: str):
    """The 1200 x 630 share card."""
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    fig.patch.set_facecolor(PAPER)
    colour = COLOURS[res["verdict"]["colour"]]
    fig.text(0.04, 0.925, "CASSANDRA SIGNAL", fontsize=11, color=MUTED, weight="bold")
    fig.text(0.04, 0.845, place["name"], fontsize=24, color=INK, weight="bold")
    fig.text(0.04, 0.795, f"{abs(place['lat']):.2f}°{'N' if place['lat'] >= 0 else 'S'}, "
             f"{abs(place['lon']):.2f}°{'E' if place['lon'] >= 0 else 'W'} · "
             f"{season_label(res['season'])} {res['variable_name']}, "
             f"{res['first_year']}–{res['last_year']}", fontsize=12, color=MUTED)
    verdict = textwrap.fill(res["verdict"]["text"], 26)
    fig.text(0.04, 0.73, verdict, fontsize=25, color=colour, weight="bold", va="top",
             linespacing=1.1)
    nlines = verdict.count("\n") + 1
    y = 0.73 - 0.085 * nlines - 0.03
    fig.text(0.04, y, outside_words(res), fontsize=13.5, color=INK, va="top")
    fig.text(0.04, y - 0.055, f"Trend: {change_short(res)}  ·  {p_words(res['test']['p'])}",
             fontsize=13.5, color=INK, va="top")
    ax = fig.add_axes([0.50, 0.33, 0.47, 0.56])
    ax.set_facecolor(PAPER)
    draw_record(ax, res, compact=True)
    ax.set_ylabel("°C vs 1981–2010" if res["variable"] == "T" else "% of normal", fontsize=10)
    ax.text(0.01, 0.98, "bold: real record   grey: 1,000 imaginary histories",
            transform=ax.transAxes, fontsize=9, color=MUTED, va="top")
    yy = 0.235
    for label, text in lines:
        fig.text(0.04, yy, label, fontsize=11, color=MUTED, weight="bold", va="top")
        fig.text(0.155, yy, textwrap.shorten(text, 128, placeholder="…"), fontsize=11,
                 color=INK, va="top")
        yy -= 0.05
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.065, 0.065], color=RULE, lw=0.8))
    fig.text(0.04, 0.03, f"{FOOTER_DATA}  ·  {AI_NOTE}", fontsize=9.5, color=MUTED)
    fig.text(0.96, 0.03, site_url, fontsize=9.5, color=MUTED, ha="right")
    fig.savefig(path, facecolor=PAPER)
    plt.close(fig)


# ---------------------------------------------------------------- HTML

CSS = """
:root{color-scheme:light;--paper:#f2ede3;--paper-2:#e9e2d4;--card:#faf7f1;--ink:#1d2b30;--muted:#5c676a;
--line:#ddd4c3;--red:#b4472d;--red-strong:#9c3a23;--amber:#a8741c;--grey:#667074;--link:#25616f;
--band:#a49d90;--grid:#e6dfd1;--tick:#5c676a;--chart-bg:#faf7f1;
--cool:#4f7f95;--warm:#b4472d;--dry:#b8873b;--wet:#3f7f78;--neutral:#a49d90;
--shadow:0 1px 2px rgba(60,40,15,.05),0 8px 22px rgba(60,40,15,.07);--ease:cubic-bezier(.2,.7,.2,1)}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--paper:#13191c;--paper-2:#0f1416;--card:#1b2327;
--ink:#e7e2d7;--muted:#9ba6a8;--line:#2d393d;--red:#e0806a;--red-strong:#c96a54;--amber:#d8a54a;--grey:#a2abad;
--link:#86c0cb;--band:#7f8786;--grid:#263034;--tick:#9ba6a8;--chart-bg:#1b2327;--neutral:#7f8786;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 22px rgba(0,0,0,.25)}}
*{box-sizing:border-box}
html{background:var(--paper)}
body{margin:0;color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
background:radial-gradient(1100px 480px at 90% -8%,rgba(180,71,45,.07),transparent 62%),
radial-gradient(900px 420px at -10% 4%,rgba(37,97,111,.06),transparent 60%),var(--paper);min-height:100vh}
body::before{content:"";position:fixed;top:0;left:0;right:0;height:3px;z-index:10;
background:linear-gradient(90deg,var(--link),var(--amber) 55%,var(--red))}
a{color:var(--link);text-underline-offset:2px;transition:color .18s var(--ease)}a:hover{color:var(--red)}
main{max-width:960px;margin:0 auto;padding:0 16px 48px;animation:rise .5s var(--ease) both}
header.top{max-width:960px;margin:0 auto 8px;padding:18px 16px;display:flex;gap:16px;flex-wrap:wrap;
align-items:baseline;justify-content:space-between;background:var(--paper-2);
box-shadow:0 0 0 100vmax var(--paper-2);clip-path:inset(0 -100vmax);border-bottom:1px solid var(--line)}
header.top a.brand{font-weight:700;letter-spacing:.1em;text-decoration:none;color:var(--ink);font-size:14px}
header.top a.brand::before{content:"";display:inline-block;width:9px;height:9px;border-radius:50%;
background:var(--red);margin-right:8px;vertical-align:1px;box-shadow:0 0 0 3px rgba(180,71,45,.18)}
header.top nav a{margin-left:14px;font-size:14px;text-decoration:none;padding-bottom:2px;border-bottom:2px solid transparent;
transition:border-color .2s var(--ease),color .2s var(--ease)}header.top nav a:hover{border-color:currentColor}
h1{font-size:clamp(26px,4vw,38px);line-height:1.15;margin:.5em 0 .15em;letter-spacing:-.01em}
h2{font-size:21px;margin:2em 0 .5em;padding-top:.7em;border-top:1px solid var(--line)}
h3{font-size:17px;margin:1.4em 0 .3em}
.muted{color:var(--muted)}.small{font-size:14px}.lead{font-size:17px}
.verdict{font-size:clamp(24px,3.6vw,34px);font-weight:750;line-height:1.15;margin:.5em 0 .2em;letter-spacing:-.01em}
.red{color:var(--red)}.amber{color:var(--amber)}.grey{color:var(--grey)}
.pill{display:inline-block;padding:1px 10px;border-radius:99px;font-size:13px;font-weight:600;border:1px solid currentColor;
background:color-mix(in srgb,currentColor 8%,transparent)}
img{max-width:100%;height:auto}
img.chart{display:block;margin:12px 0;border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px 18px;margin:14px 0;padding:0}
.facts div{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:10px 12px;
transition:border-color .2s var(--ease)}.facts div:hover{border-color:var(--band)}
.facts dt{font-size:13px;color:var(--muted)}.facts dd{margin:2px 0 0;font-weight:600}
.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0;box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr{transition:background-color .15s var(--ease)}tbody tr:hover{background:color-mix(in srgb,var(--paper-2) 60%,transparent)}
th{font-weight:600;color:var(--muted)}.scroll{overflow-x:auto}
code,.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px;word-break:break-all}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px;margin:18px 0}
.grid a.place{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;
text-decoration:none;color:var(--ink);box-shadow:var(--shadow);
transition:transform .25s var(--ease),box-shadow .25s var(--ease),border-color .25s var(--ease)}
.grid a.place:hover{transform:translateY(-3px);border-color:var(--band);
box-shadow:0 2px 4px rgba(60,40,15,.06),0 14px 30px rgba(60,40,15,.12)}
.grid a.place img{display:block;transition:opacity .25s var(--ease)}.grid a.place:hover img{opacity:.94}
.grid .body{padding:10px 14px 14px}.grid .v{font-weight:700;margin-top:4px}
.bar{display:flex;height:24px;border-radius:6px;overflow:hidden;font-size:12px;color:#fff;min-width:220px;background:var(--line)}
.bar span{display:flex;align-items:center;justify-content:center;white-space:nowrap}
.b-below{background:var(--cool)}.b-near{background:var(--neutral)}.b-above{background:var(--warm)}
.bar.p .b-below{background:var(--dry)}.bar.p .b-above{background:var(--wet)}
.cta{display:inline-block;background:var(--red);color:#fff;font-weight:700;padding:10px 18px;border-radius:9px;text-decoration:none;
margin:6px 0;box-shadow:0 2px 8px rgba(180,71,45,.25);
transition:background-color .2s var(--ease),transform .2s var(--ease),box-shadow .2s var(--ease)}
.cta:hover{background:var(--red-strong);color:#fff;transform:translateY(-1px);box-shadow:0 6px 16px rgba(180,71,45,.3)}
form#checker fieldset{border:0;padding:0;margin:0 0 18px;min-width:0}select{max-width:100%}
.row label{flex-wrap:wrap;max-width:100%}form#checker legend{font-weight:700;font-size:17px;margin-bottom:8px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0}.row label{display:flex;gap:6px;align-items:center}
input[type=search],input[type=number],select,#sharelink{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;
background:var(--card);color:var(--ink);min-width:0;transition:border-color .18s var(--ease),box-shadow .18s var(--ease)}
input[type=search]:focus,input[type=number]:focus,select:focus,#sharelink:focus{outline:none;border-color:var(--link);
box-shadow:0 0 0 3px color-mix(in srgb,var(--link) 22%,transparent)}
input[type=search]{flex:1 1 220px}input[type=number]{width:120px}#sharelink{flex:1 1 260px;font-size:13px}
input[type=radio],input[type=checkbox],input[type=range]{accent-color:var(--red)}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;
transition:background-color .18s var(--ease),border-color .18s var(--ease),transform .18s var(--ease),box-shadow .18s var(--ease),color .18s var(--ease)}
button:hover{border-color:var(--band);background:var(--paper-2)}button:active{transform:translateY(1px)}
button:disabled{opacity:.55;cursor:wait}
button.primary{background:var(--red);border-color:var(--red);color:#fff;font-weight:700;font-size:17px;padding:11px 22px;
box-shadow:0 2px 8px rgba(180,71,45,.25)}
button.primary:hover{background:var(--red-strong);border-color:var(--red-strong);box-shadow:0 6px 16px rgba(180,71,45,.3)}
.chip{padding:4px 11px;border-radius:99px;font-size:14px;margin:2px}.chip:hover{border-color:var(--link);color:var(--link)}
#results{list-style:none;padding:0;margin:4px 0;border-radius:8px;overflow:hidden}
#results button{width:100%;text-align:left;border-radius:0;border-width:0 0 1px}
#map{height:280px;border-radius:10px;border:1px solid var(--line);margin:8px 0;z-index:0;box-shadow:var(--shadow)}
#placename{font-weight:600}input[type=range]{width:100%;max-width:420px}
.seg label{border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer;background:var(--card);
transition:border-color .18s var(--ease),background-color .18s var(--ease)}.seg label:hover{border-color:var(--band)}
.seg label:has(input:checked){border-color:var(--red);background:color-mix(in srgb,var(--red) 7%,var(--card))}
.steps{padding-left:22px}.steps li{color:var(--muted);margin:3px 0;transition:color .3s var(--ease)}
.steps li.now{color:var(--ink);font-weight:600}.steps li.now::after{content:" …";animation:pulse 1.2s ease-in-out infinite}
.steps li.done{color:var(--ink)}.steps li.done::marker{content:"✓  ";color:var(--wet)}
#out:not([hidden])>*{animation:rise .45s var(--ease) both}
#out>*:nth-child(2){animation-delay:.04s}#out>*:nth-child(3){animation-delay:.08s}#out>*:nth-child(4){animation-delay:.12s}
#out>*:nth-child(5){animation-delay:.16s}#out>*:nth-child(n+6){animation-delay:.2s}
.chartbox{background:var(--chart-bg);border:1px solid var(--line);border-radius:10px;padding:8px;margin:12px 0;box-shadow:var(--shadow)}
.chart-svg{width:100%;height:auto;display:block;font-family:inherit}
.chart-svg .grid{stroke:var(--grid)}.chart-svg .tick{fill:var(--tick);font-size:13px}.chart-svg .ref{stroke:var(--band);opacity:.6}
.chart-svg .band{fill:var(--band);opacity:.3;animation:fade .7s ease-out both}
.chart-svg .hist{fill:none;stroke:var(--band);stroke-width:.7;opacity:.25;animation:fade .9s ease-out both}
.chart-svg .mid{fill:none;stroke:var(--band);stroke-dasharray:5 4}
.chart-svg .trend{fill:none;stroke:var(--ink);stroke-dasharray:2 3;opacity:.8}
.chart-svg .real{fill:none;stroke-width:3;stroke:var(--ink);stroke-linejoin:round;stroke-linecap:round;
stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.3s .35s var(--ease) forwards}
.chart-svg .real.red{stroke:var(--red)}.chart-svg .real.amber{stroke:var(--amber)}
.chart-svg .after{fill:none;stroke:var(--muted);stroke-width:2;stroke-dasharray:6 4;animation:fade .6s 1.5s ease-out both}
.chart-svg .cut{stroke:var(--muted);stroke-dasharray:3 3}
.chart-svg .bar-null{fill:var(--band);opacity:.85}.chart-svg .realline{stroke:var(--ink);stroke-width:3}
.chart-svg .realline.red{stroke:var(--red)}.chart-svg .realline.amber{stroke:var(--amber)}
.chart-svg .mirror{stroke:var(--muted);stroke-dasharray:3 3}
.legend{color:var(--muted);margin:4px 6px}
.key{display:inline-block;width:22px;height:0;border-top:3px solid var(--ink);vertical-align:middle;margin:0 5px 0 12px}
.key.red{border-color:var(--red)}.key.amber{border-color:var(--amber)}.band-key{height:10px;border:0;background:var(--band);opacity:.5}
.trend-key{border-top:2px dotted var(--ink)}.after-key{border-top:2px dashed var(--muted)}
.progress{height:8px;background:var(--line);border-radius:4px;overflow:hidden;max-width:420px}
.progress span{display:block;height:100%;background:linear-gradient(90deg,var(--amber),var(--red));transition:width .25s var(--ease)}
footer{max-width:960px;margin:0 auto;padding:22px 16px 40px;color:var(--muted);font-size:14px;background:var(--paper-2);
box-shadow:0 0 0 100vmax var(--paper-2);clip-path:inset(0 -100vmax);border-top:1px solid var(--line)}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes pulse{50%{opacity:.35}}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}
.chart-svg .real{stroke-dasharray:none;stroke-dashoffset:0}}
"""


def page(title, body, *, description="", og_image=None, url=None, root="../../", head_extra="", scripts=""):
    og = ""
    if og_image:
        og = (f'<meta property="og:type" content="website">'
              f'<meta property="og:title" content="{esc(title)}">'
              f'<meta property="og:description" content="{esc(description)}">'
              f'<meta property="og:image" content="{esc(og_image)}">'
              f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
              f'<meta name="twitter:card" content="summary_large_image">'
              f'<meta name="twitter:image" content="{esc(og_image)}">')
        if url:
            og += f'<meta property="og:url" content="{esc(url)}">'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">{og}
<link rel="stylesheet" href="{root}style.css">{head_extra}
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='8' cy='8' r='7' fill='%23b4472d'/%3E%3C/svg%3E">
</head><body>
<header class="top"><a class="brand" href="{root}">CASSANDRA SIGNAL</a>
<nav><a href="{root}check/"><strong>Check any place</strong></a><a href="{root}">All places</a><a href="{root}method/">Method &amp; checks</a></nav></header>
<main>{body}</main>
<footer><p><strong>{FOOTER_DATA}.</strong> Sources:
<a href="https://power.larc.nasa.gov/">NASA POWER</a> (monthly T2M and PRECTOTCORR, 1981 to present) and
<a href="https://data.giss.nasa.gov/gistemp/">NASA GISTEMP v4</a> (GISTEMP Team, NASA Goddard Institute for Space Studies;
Lenssen et al. 2019). This project is not affiliated with or endorsed by NASA.</p>
<p><strong>AI use:</strong> the analysis code, these pages and their wording were written with the help of an
AI coding assistant, then run, checked and tested by the team; the method follows the team's own design.
Charts and cards are drawn by our code from the data; no image on this site is AI-generated.
<a href="{root}method/#ai-use">Details</a>.</p>
<p>No cookies, no tracking, no login. The live checker runs in your browser: it asks NASA POWER for the data directly, place search uses <a href="https://open-meteo.com/en/docs/geocoding-api">Open-Meteo</a> and the map uses <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> tiles; nothing is sent to us. Built {{BUILD_INFO}}.</p></footer>
{scripts}</body></html>"""
