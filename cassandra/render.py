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

COLOURS = {"red": "#c0392b", "amber": "#d98200", "grey": "#5f6672"}
INK, MUTED, BAND, PAPER = "#1b1f24", "#5f6672", "#9aa1ab", "#fbfaf7"
AI_NOTE = "Code and text AI-assisted; see the AI-use note."
FOOTER_DATA = "Data: NASA POWER, NASA GISTEMP v4"

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#c9ccd1",
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
    ax.axhline(ref, color="#c9ccd1", lw=0.8, zorder=0)
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
    ax.grid(axis="y", color="#eceef1", lw=0.8)
    ax.tick_params(labelsize=9 if compact else 10)
    if not compact:
        ax.legend(loc="upper left", frameon=False, fontsize=9)


def chart_png(res, path: Path):
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=130)
    fig.patch.set_facecolor("white")
    draw_record(ax, res)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def null_hist_png(res, path: Path):
    a = res["_arrays"]
    fig, ax = plt.subplots(figsize=(9, 2.6), dpi=130)
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
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.065, 0.065], color="#d9dbdf", lw=0.8))
    fig.text(0.04, 0.03, f"{FOOTER_DATA}  ·  {AI_NOTE}", fontsize=9.5, color=MUTED)
    fig.text(0.96, 0.03, site_url, fontsize=9.5, color=MUTED, ha="right")
    fig.savefig(path, facecolor=PAPER)
    plt.close(fig)


# ---------------------------------------------------------------- HTML

CSS = """
:root{--ink:#1b1f24;--muted:#5f6672;--line:#e3e5e8;--paper:#fbfaf7;--card:#fff;
--red:#c0392b;--amber:#b86e00;--grey:#5f6672;--link:#1f5fa8}
@media (prefers-color-scheme:dark){:root{--ink:#e9eaec;--muted:#a3a9b2;--line:#30353c;
--paper:#121417;--card:#1a1d21;--red:#ff7a6b;--amber:#f2a93b;--grey:#a3a9b2;--link:#8cbcf5}
img.chart{background:#fff;border-radius:6px}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--link)}main{max-width:960px;margin:0 auto;padding:0 16px 48px}
header.top{max-width:960px;margin:0 auto;padding:18px 16px;display:flex;gap:16px;
flex-wrap:wrap;align-items:baseline;justify-content:space-between}
header.top a.brand{font-weight:700;letter-spacing:.08em;text-decoration:none;color:var(--ink);font-size:14px}
header.top nav a{margin-left:14px;font-size:14px}
h1{font-size:clamp(26px,4vw,38px);line-height:1.15;margin:.4em 0 .1em}
h2{font-size:21px;margin:2em 0 .5em;padding-top:.6em;border-top:1px solid var(--line)}
h3{font-size:17px;margin:1.4em 0 .3em}
.muted{color:var(--muted)}.small{font-size:14px}
.verdict{font-size:clamp(24px,3.6vw,34px);font-weight:750;line-height:1.15;margin:.5em 0 .2em}
.red{color:var(--red)}.amber{color:var(--amber)}.grey{color:var(--grey)}
.pill{display:inline-block;padding:1px 9px;border-radius:99px;font-size:13px;font-weight:600;
border:1px solid currentColor}
img{max-width:100%;height:auto}img.chart{display:block;margin:12px 0;border:1px solid var(--line)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px 18px;
margin:14px 0;padding:0}.facts div{background:var(--card);border:1px solid var(--line);
border-radius:8px;padding:10px 12px}.facts dt{font-size:13px;color:var(--muted)}
.facts dd{margin:2px 0 0;font-weight:600}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted)}.scroll{overflow-x:auto}
code,.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px;word-break:break-all}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin:18px 0}
.grid a.place{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;
overflow:hidden;text-decoration:none;color:var(--ink)}.grid a.place:hover{border-color:var(--muted)}
.grid .body{padding:10px 14px 14px}.grid .v{font-weight:700;margin-top:4px}
.bar{display:flex;height:22px;border-radius:5px;overflow:hidden;font-size:12px;color:#fff;min-width:220px}
.bar span{display:flex;align-items:center;justify-content:center;white-space:nowrap}
.b-below{background:#c27c2c}.b-near{background:#8a929c}.b-above{background:#2f7d6d}
footer{max-width:960px;margin:0 auto;padding:22px 16px 40px;border-top:1px solid var(--line);
color:var(--muted);font-size:14px}
"""


def page(title, body, *, description="", og_image=None, url=None, root="../../"):
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
<link rel="stylesheet" href="{root}style.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='8' cy='8' r='7' fill='%23c0392b'/%3E%3C/svg%3E">
</head><body>
<header class="top"><a class="brand" href="{root}">CASSANDRA SIGNAL</a>
<nav><a href="{root}">All places</a><a href="{root}method/">Method &amp; checks</a></nav></header>
<main>{body}</main>
<footer><p><strong>{FOOTER_DATA}.</strong> Sources:
<a href="https://power.larc.nasa.gov/">NASA POWER</a> (monthly T2M and PRECTOTCORR, 1981 to present) and
<a href="https://data.giss.nasa.gov/gistemp/">NASA GISTEMP v4</a> (GISTEMP Team, NASA Goddard Institute for Space Studies;
Lenssen et al. 2019). This project is not affiliated with or endorsed by NASA.</p>
<p><strong>AI use:</strong> the analysis code, these pages and their wording were written with the help of an
AI coding assistant, then run, checked and tested by the team; the method follows the team's own design.
Charts and cards are drawn by our code from the data; no image on this site is AI-generated.
<a href="{root}method/#ai-use">Details</a>.</p>
<p>No cookies, no tracking, no login. Built {{BUILD_INFO}}.</p></footer>
</body></html>"""
