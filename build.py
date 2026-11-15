"""Cassandra Signal: fetch, analyse, and write the static site.

    python build.py --places places.csv            # build site/ from cached data
    python build.py --places places.csv --refresh  # download fresh data first
    python build.py --fetch-only --refresh         # just update data/raw/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from cassandra import forecasts as F
from cassandra import render as R
from cassandra import site as S
from cassandra.analysis import analyse_variable, backtest
from cassandra.climate import season_label
from cassandra.data import POWER_URL, load_gistemp, load_power, zone_for_lat
from cassandra.falsealarm import false_alarm_check
from cassandra.stats import BASE_SEED, N_HISTORIES, sen_slope

ROOT = Path(__file__).resolve().parent
DEFAULT_BASE = "https://propcgamer20-png.github.io/cassandra-signal/"
DEFAULT_REPO = "https://github.com/propcgamer20-png/cassandra-signal"


def read_places(path):
    df = pd.read_csv(path)
    need = {"slug", "name", "lat", "lon", "notes"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"{path} is missing columns: {sorted(missing)}")
    df["t_season"] = df.get("t_season", "ANN")
    df["p_season"] = df.get("p_season", "ANN")
    df["primary"] = df.get("primary", "T")
    df = df.fillna({"t_season": "ANN", "p_season": "ANN", "primary": "T", "notes": ""})
    return df.to_dict("records")


def jsonable(o):
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 6)
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    return o


def gistemp_context(glb, zon, lat, first_year):
    g = glb[glb.year >= first_year]
    col, label = zone_for_lat(lat)
    z = zon[zon.year >= first_year][["year", col]].dropna()
    return {"first": int(g.year.min()), "last": int(g.year.max()),
            "global_trend": sen_slope(g.anom.to_numpy(), g.year.to_numpy()) * 10,
            "zone": col, "zone_label": label,
            "zone_trend": sen_slope(z[col].to_numpy(), z.year.to_numpy()) * 10,
            "latest": float(g.anom.iloc[-1])}


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def false_alarms(cache: Path, quick: bool):
    """The false-alarm and power check, cached on the hash of the statistics code."""
    code = b"".join((ROOT / "cassandra" / f).read_bytes() for f in ("stats.py", "falsealarm.py"))
    key = hashlib.sha256(code).hexdigest()[:16] + ("-quick" if quick else "")
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved.get("key") == key:
            return saved["rows"]
    t0 = time.time()
    M = 100 if quick else 1000
    rows = false_alarm_check(M=M, N=N_HISTORIES, trend_per_decade=(0.0,))
    from cassandra.falsealarm import CASES
    rows += false_alarm_check(M=M // 2, N=N_HISTORIES, cases=[CASES[1]],
                              trend_per_decade=(0.25, 0.5), seed=2027)
    print(f"  false-alarm check: {time.time() - t0:.0f}s")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": key, "rows": jsonable(rows)}, indent=1) + "\n",
                     encoding="utf-8", newline="\n")
    return rows


def card_lines(primary, ctx, res_t, bts, locked, hind):
    lines = [("Planet", f"Here {season_label(res_t['season'])} temperature {R.change_short(res_t)}; "
                        f"whole planet {ctx['global_trend']:+.2f} °C/decade (GISTEMP, "
                        f"{ctx['first']}–{ctx['last']})")]
    if bts:
        bt = bts[0]
        ev, res = bt["event"], bt["result"]
        lines.append(("Backtest", f"{ev['name']}: {'WARNED' if bt['warned'] else 'no warning'} "
                                  f"using data to {bt['cutoff']} ({S.SHORT_VERDICT[res['verdict']['key']]})"))
    scored = [s for lf in locked for s in lf["scores"].values() if s.get("status") == "scored"]
    pending = [s for lf in locked for s in lf["scores"].values() if s.get("status") == "pending"]
    h = hind.get(primary["variable"], {})
    skill = f"; hindcast skill {h['rpss']:+.2f} over {h['n']} seasons" if h.get("n") else ""
    if scored:
        txt = f"{len(scored)} locked forecasts scored, {len(pending)} pending{skill}"
    elif locked:
        d = locked[-1]["doc"]
        p = d["variables"].get(primary["variable"], {}).get("probabilities") or \
            next((v["probabilities"] for v in d["variables"].values() if "probabilities" in v), None)
        txt = (f"{d['season']} {d['target_year']} locked before it began"
               + (f": above normal {p['above'] * 100:.0f}%, below {p['below'] * 100:.0f}%" if p else "")
               + skill)
    else:
        txt = "No locked forecasts yet" + skill
    lines.append(("Forecast", txt))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--places", default="places.csv")
    ap.add_argument("--events", default="events.csv")
    ap.add_argument("--out", default="site")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--forecasts", default="forecasts")
    ap.add_argument("--refresh", action="store_true", help="download fresh data")
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--quick", action="store_true", help="fewer false-alarm series (for testing)")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--repo-url", default=DEFAULT_REPO)
    args = ap.parse_args(argv)

    places = read_places(ROOT / args.places)
    events = pd.read_csv(ROOT / args.events).to_dict("records") if (ROOT / args.events).exists() else []
    raw = ROOT / args.raw
    print(f"Fetching data for {len(places)} places ({'refresh' if args.refresh else 'cache'})")
    monthly = {p["slug"]: load_power(p["slug"], p["lat"], p["lon"], raw, refresh=args.refresh)
               for p in places}
    glb, zon = load_gistemp(raw, refresh=args.refresh)
    if args.fetch_only:
        return

    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "method").mkdir(parents=True)
    (out / "style.css").write_text(R.CSS.strip() + "\n", encoding="utf-8", newline="\n")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    base = args.base_url.rstrip("/") + "/"
    head = git("rev-parse", "--short", "HEAD")
    build_info = (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                  + (f' from commit <a href="{args.repo_url}/commit/{head}">{head}</a>' if head else "")
                  + f' · <a href="{args.repo_url}">source code</a>')

    print("False-alarm check")
    fa_rows = false_alarms(ROOT / "data" / "falsealarm.json", args.quick)

    cards, summary = [], []
    n_locked = n_pending = n_scored = 0
    for place in places:
        slug = place["slug"]
        t0 = time.time()
        m = monthly[slug]
        res = {"T": analyse_variable(m, "T", place["t_season"], slug=slug, keep=True),
               "P": analyse_variable(m, "P", place["p_season"], slug=slug, keep=True)}
        primary, secondary = res[place["primary"]], res["P" if place["primary"] == "T" else "T"]
        ctx = gistemp_context(glb, zon, place["lat"], res["T"]["first_year"])
        bts = [backtest(m, ev, slug=slug) for ev in events if ev["slug"] == slug]
        hind = {}
        for var, season in (("T", place["t_season"]), ("P", place["p_season"])):
            hind[var] = F.hindcasts(m, var, season)
            hind[var]["season"] = season
        locked = []
        for path in sorted((ROOT / args.forecasts / slug).glob("*.json")):
            lf = F.score_locked(path, m)
            lf["file"] = path.relative_to(ROOT).as_posix()
            lf["git"] = F.git_lock_info(path, ROOT)
            locked.append(lf)
            for s in lf["scores"].values():
                n_locked += 1
                n_pending += s["status"] == "pending"
                n_scored += s["status"] == "scored"

        pdir = out / "place" / slug
        pdir.mkdir(parents=True)
        for var, r in res.items():
            R.chart_png(r, pdir / f"chart-{var}.png")
            R.null_hist_png(r, pdir / f"hist-{var}.png")
        url = f"{base}place/{slug}/"
        R.card_png(place, primary, card_lines(primary, ctx, res["T"], bts, locked, hind),
                   pdir / "card.png", url.replace("https://", "").rstrip("/"))
        power_url = POWER_URL.format(lat=place["lat"], lon=place["lon"], year=m.year.max())
        body = S.place_body(place, primary, secondary, ctx, bts, locked, hind, args.repo_url, power_url)
        desc = f"{primary['verdict']['text']}. {R.headline_sub(primary)} {R.outside_words(primary)}."
        html = R.page(f"{place['name']}: Cassandra Signal", body, description=desc,
                      og_image=url + "card.png", url=url).replace("{BUILD_INFO}", build_info)
        (pdir / "index.html").write_text(html, encoding="utf-8", newline="\n")
        data = {"place": place, "primary": place["primary"], "results": res, "gistemp": ctx,
                "backtests": bts, "hindcasts": hind,
                "locked_forecasts": [{k: v for k, v in lf.items()} for lf in locked],
                "seed_base": BASE_SEED, "histories": N_HISTORIES}
        (pdir / "data.json").write_text(json.dumps(jsonable(data), indent=1, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")
        cards.append({"slug": slug, "name": place["name"], "verdict": primary["verdict"]["text"],
                      "colour": primary["verdict"]["colour"],
                      "what": f"{season_label(primary['season'])} {primary['variable_name']}",
                      "change": R.change_short(primary)})
        summary.append({"slug": slug, "name": place["name"],
                        **{v: {"verdict": r["verdict"]["key"], "p": r["test"]["p"],
                               "trend_per_decade": r["trend_per_decade"], "season": r["season"]}
                           for v, r in res.items()},
                        "backtests": [{"event": b["event"]["name"], "warned": b["warned"],
                                       "visibility": b["observed"]["visibility"]} for b in bts]})
        print(f"  {slug:14s} T {res['T']['verdict']['key']:13s} P {res['P']['verdict']['key']:13s}"
              f" backtests warned {sum(b['warned'] for b in bts)}/{len(bts)}  ({time.time() - t0:.1f}s)")

    idx = R.page("Cassandra Signal: is it climate change, or just a bad year?",
                 S.index_body(cards, fa_rows, n_locked, n_pending, n_scored),
                 description="Place by place, we test whether the climate is really changing or a hot summer "
                             "or dry year is just natural variation, and keep an honest public track record.",
                 og_image=f"{base}place/{cards[0]['slug']}/card.png", url=base, root="")
    (out / "index.html").write_text(idx.replace("{BUILD_INFO}", build_info), encoding="utf-8", newline="\n")
    meth = R.page("Method, checks and limits: Cassandra Signal",
                  S.method_body(fa_rows, N_HISTORIES, BASE_SEED),
                  description="How Cassandra Signal decides whether a change is real.", root="../")
    (out / "method" / "index.html").write_text(meth.replace("{BUILD_INFO}", build_info),
                                               encoding="utf-8", newline="\n")
    (out / "summary.json").write_text(json.dumps(jsonable({"places": summary, "false_alarm": fa_rows}),
                                                 indent=1, ensure_ascii=False) + "\n",
                                      encoding="utf-8", newline="\n")
    print(f"Wrote {out} ({len(places)} places)")


if __name__ == "__main__":
    main()
