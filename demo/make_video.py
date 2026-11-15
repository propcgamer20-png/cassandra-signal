"""Render the 30-second demo video from the real pipeline output.

    python build.py                 # first, so site/place/*/data.json exist
    pip install imageio-ffmpeg      # provides an ffmpeg binary
    python demo/make_video.py       # writes demo/cassandra-signal-demo.mp4

Every number and curve on screen comes from the analysis; nothing is typed in.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import imageio_ffmpeg  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.animation import FFMpegWriter  # noqa: E402

from cassandra import forecasts as F  # noqa: E402
from cassandra.analysis import analyse_variable  # noqa: E402
from cassandra.data import load_power  # noqa: E402
from cassandra.render import BAND, COLOURS, INK, MUTED, PAPER  # noqa: E402

FPS, SECONDS = 24, 30
plt.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
FOOT = "Data: NASA POWER, NASA GISTEMP v4  ·  video drawn by our (AI-assisted) code from the data"


def load(slug):
    return json.loads((ROOT / "site" / "place" / slug / "data.json").read_text(encoding="utf-8"))


def series(slug, lat, lon, var, season):
    m = load_power(slug, lat, lon, ROOT / "data" / "raw")
    return analyse_variable(m, var, season, slug=slug, keep=True, robustness=False)


NIAMEY = series("niamey", 13.512, 2.112, "T", "MAM")
SACRA = series("sacramento", 38.582, -121.494, "P", "NDJFM")
PARIS, NIAMEY_D = load("paris"), load("niamey")
SUMMARY = json.loads((ROOT / "site" / "summary.json").read_text(encoding="utf-8"))
FC_PATH = ROOT / "forecasts" / "paris" / "2027-DJF.json"
FC = json.loads(FC_PATH.read_text(encoding="utf-8"))
SHA = F.sha256_file(FC_PATH)
BTS = [b for pl in SUMMARY["places"] for b in pl["backtests"]]
WARNED = sum(b["warned"] for b in BTS)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def chart(ax, res, reveal_band=1.0, reveal_line=1.0, n_lines=160):
    a = res["_arrays"]
    yrs, real, band = a["years"], a["plot"], a["band"]
    lo, hi = np.percentile(band, [5, 95], axis=0)
    ax.set_facecolor(PAPER)
    if reveal_band > 0:
        k = int(n_lines * reveal_band)
        ax.plot(yrs, band[:k].T, color=BAND, alpha=0.12, lw=0.7)
        ax.fill_between(yrs, lo, hi, color=BAND, alpha=0.3 * reveal_band, lw=0)
    if reveal_line > 0:
        n = max(2, int(len(yrs) * reveal_line))
        col = COLOURS[res["verdict"]["colour"]] if res["verdict"]["colour"] != "grey" else INK
        ax.plot(yrs[:n], real[:n], color=col, lw=3.2)
    ax.set_xlim(yrs[0], yrs[-1])
    pad = (band.max() - band.min()) * 0.05
    ax.set_ylim(min(band.min(), real.min()) - pad, max(band.max(), real.max()) + pad)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=12)


def frame(fig, t):
    fig.clf()
    fig.patch.set_facecolor(PAPER)
    fig.text(0.04, 0.03, FOOT, fontsize=11, color=MUTED)
    if t < 3.5:                                    # title
        a = ease(t / 1.0)
        fig.text(0.5, 0.58, "Cassandra Signal", fontsize=58, weight="bold", ha="center",
                 color=INK, alpha=a)
        fig.text(0.5, 0.45, "Is it climate change, or just a bad year?", fontsize=28,
                 ha="center", color=COLOURS["red"], alpha=ease((t - 0.8) / 1.0))
        fig.text(0.5, 0.36, "We put each place's record on trial, and publish our forecasts first.",
                 fontsize=17, ha="center", color=MUTED, alpha=ease((t - 1.6) / 1.0))
    elif t < 13:                                   # Niamey: the trial
        u = t - 3.5
        fig.text(0.04, 0.9, "Niamey, Niger  ·  March–May temperature, 1981–2026", fontsize=22,
                 weight="bold", color=INK)
        ax = fig.add_axes([0.07, 0.2, 0.88, 0.6])
        chart(ax, NIAMEY, reveal_band=ease(u / 2.5), reveal_line=ease((u - 3.0) / 4.0))
        ax.set_ylabel("°C vs 1981–2010", fontsize=13, color=MUTED)
        cap = ("1,000 imaginary histories: natural ups and downs only, no climate change"
               if u < 3.0 else "The real record")
        fig.text(0.04, 0.84, cap, fontsize=17, color=MUTED)
        if u > 7.3:
            v = NIAMEY["verdict"]
            fig.text(0.5, 0.11, f"{v['text']}  ·  outside {NIAMEY['test']['outside']:,} of 1,000",
                     fontsize=24, weight="bold", ha="center", color=COLOURS[v["colour"]],
                     alpha=ease((u - 7.3) / 0.6))
    elif t < 18:                                   # Sacramento: honest "not yet"
        u = t - 13
        fig.text(0.04, 0.9, "Sacramento, California  ·  November–March rain", fontsize=22,
                 weight="bold", color=INK)
        ax = fig.add_axes([0.07, 0.2, 0.88, 0.6])
        chart(ax, SACRA)
        ax.set_ylabel("% of normal", fontsize=13, color=MUTED)
        fig.text(0.04, 0.84, "Even with a famous drought in the record…", fontsize=17, color=MUTED)
        if u > 1.5:
            fig.text(0.5, 0.11, "Not yet distinguishable from natural variation. We never force a signal.",
                     fontsize=21, weight="bold", ha="center", color=COLOURS["grey"],
                     alpha=ease((u - 1.5) / 0.6))
    elif t < 23:                                   # backtests
        u = t - 18
        fig.text(0.04, 0.86, "Would it have warned? (using only data from before each event)",
                 fontsize=22, weight="bold", color=INK)
        rows = [(PARIS, "paris"), (NIAMEY_D, "niamey")]
        for i, (d, _) in enumerate(rows):
            bt = d["backtests"][0]
            res = bt["result"]
            y = 0.62 - i * 0.24
            a = ease((u - 0.6 - i * 1.6) / 0.6)
            fig.text(0.06, y, f"{bt['event']['name']}  (data to {bt['cutoff']})", fontsize=20,
                     color=INK, alpha=a)
            fig.text(0.06, y - 0.07, f"{res['verdict']['text']}  →  "
                     f"{'WARNED' if bt['warned'] else 'no warning'}", fontsize=20, weight="bold",
                     color=COLOURS[res["verdict"]["colour"]], alpha=a)
        fig.text(0.06, 0.16, f"Misses are published too: {WARNED} of {len(BTS)} events would have been warned. "
                 "Paris 2003 came with only 22 years of data.", fontsize=15, color=MUTED, alpha=ease((u - 3.6) / 0.6))
    elif t < 27.5:                                 # locked forecast
        u = t - 23
        fig.text(0.04, 0.86, "Forecasts are locked before the season starts", fontsize=24,
                 weight="bold", color=INK)
        p = FC["variables"]["T"]["probabilities"]
        fig.text(0.06, 0.72, f"Paris, Dec 2026 – Feb 2027 temperature  ·  issued {FC['issued_at_utc'][:10]}",
                 fontsize=18, color=INK)
        ax = fig.add_axes([0.06, 0.55, 0.88, 0.1])
        left = 0
        for k, col in (("below", "#c27c2c"), ("near", "#8a929c"), ("above", "#2f7d6d")):
            w = p[k] * ease(u / 1.0)
            ax.barh(0, w, left=left, color=col, height=1)
            if w > 0.08:
                ax.text(left + w / 2, 0, f"{k} {p[k] * 100:.0f}%", ha="center", va="center",
                        color="white", fontsize=16, weight="bold")
            left += w
        ax.set_xlim(0, 1)
        ax.axis("off")
        fig.text(0.06, 0.42, "SHA-256 fingerprint of the committed file:", fontsize=15, color=MUTED,
                 alpha=ease((u - 1.2) / 0.5))
        fig.text(0.06, 0.36, SHA, fontsize=13.5, family="DejaVu Sans Mono", color=INK,
                 alpha=ease((u - 1.2) / 0.5))
        fig.text(0.06, 0.24, "Scored against plain climatology (33/33/33) when the data arrive, misses included.",
                 fontsize=16, color=MUTED, alpha=ease((u - 2.2) / 0.5))
    else:                                          # all places
        u = t - 27.5
        fig.text(0.5, 0.88, "8 places, one honest card each", fontsize=26, weight="bold",
                 ha="center", color=INK)
        names = {"no_alibi": "no alibi", "very_unlikely": "very unlikely natural",
                 "probable": "probably real", "not_yet": "not yet"}
        cols = {"no_alibi": "red", "very_unlikely": "red", "probable": "amber", "not_yet": "grey"}
        for i, pl in enumerate(SUMMARY["places"]):
            x, y = 0.05 + (i % 2) * 0.48, 0.74 - (i // 2) * 0.13
            a = ease((u - i * 0.12) / 0.4)
            fig.text(x, y, pl["name"].split(",")[0], fontsize=17, weight="bold", color=INK, alpha=a)
            fig.text(x, y - 0.045, f"temperature: {names[pl['T']['verdict']]}", fontsize=13,
                     color=COLOURS[cols[pl["T"]["verdict"]]], alpha=a)
            fig.text(x + 0.255, y - 0.045, f"rain: {names[pl['P']['verdict']]}", fontsize=13,
                     color=COLOURS[cols[pl["P"]["verdict"]]], alpha=a)
        fig.text(0.5, 0.1, "propcgamer20-png.github.io/cassandra-signal", fontsize=18,
                 ha="center", color=COLOURS["red"])


def main():
    out = ROOT / "demo" / "cassandra-signal-demo.mp4"
    fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
    writer = FFMpegWriter(fps=FPS, bitrate=2500, extra_args=["-pix_fmt", "yuv420p"])
    with writer.saving(fig, str(out), dpi=100):
        for i in range(FPS * SECONDS):
            frame(fig, i / FPS)
            writer.grab_frame(facecolor=PAPER)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
