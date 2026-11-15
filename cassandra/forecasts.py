"""Locked-in seasonal forecasts (step F) and their honest scoring.

A forecast gives the probability that a season will be below, near or above
normal, where "normal" is the middle third of 1981-2010 seasons. The method is
deliberately simple and says out loud what the project claims: the dice are
loaded. We take the climatology and slide it along the Sen trend line.

Every forecast is written to forecasts/{place}/{year}-{season}.json BEFORE the
season starts and committed to git. The file is never overwritten. The card
shows the commit that added it and its SHA-256, so anyone can check it later.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import climate as C
from .stats import sen_line

CATS = ("below", "near", "above")
STANDARD_SEASONS = ("DJF", "MAM", "JJA", "SON")
CLIMATOLOGY = {"below": 1 / 3, "near": 1 / 3, "above": 1 / 3}
METHOD = ("Trend-shifted climatology: tercile edges from the 1981-2010 seasons; "
          "the season's value is predicted from the Sen's-slope trend line fitted to "
          "all complete seasons before the cut-off, with a normal spread equal to the "
          "scatter around that line (prediction-interval widened). Precipitation is "
          "handled as SPI (gamma fit on 1981-2010). Each category is kept at 2% or more.")


class LateError(RuntimeError):
    """Raised when someone tries to issue a forecast after the season began."""


def _season_values(monthly, var, season):
    if var == "T":
        return C.seasonal(monthly, monthly["t2m"], season, "mean").dropna()
    return C.seasonal(monthly, monthly["prec_mm"], season, "sum").dropna()


def tercile_edges(values: pd.Series):
    base = values.loc[C.baseline_years(values.index)]
    if len(base) < 10:
        raise ValueError("fewer than 10 baseline seasons")
    return [float(v) for v in np.quantile(base.to_numpy(), [1 / 3, 2 / 3])], base


def forecast_terciles(monthly: pd.DataFrame, var: str, season: str, target_year: int,
                      cutoff=None) -> dict:
    start = C.season_start(season, target_year)
    cut = C.month_before(start) if cutoff is None else min(tuple(cutoff), C.month_before(start))
    past = C.truncate(monthly, cut)
    vals = _season_values(past, var, season)
    vals = vals[vals.index < target_year]
    edges, base = tercile_edges(vals)
    unit = "°C" if var == "T" else "mm"
    if var == "P":
        if edges[1] - edges[0] < 1.0 or float(np.median(base)) < 10.0:
            raise ValueError("dry season: normal rainfall is close to zero, terciles are meaningless")
        fit = C.GammaFit(base.to_numpy())
        x, e = fit.spi(vals.to_numpy()), fit.spi(np.array(edges))
    else:
        x, e = vals.to_numpy(), np.array(edges)
    t = vals.index.to_numpy(float)
    b, a = sen_line(x, t)
    resid = x - (a + b * t)
    n = len(x)
    s = float(np.std(resid, ddof=2))
    tbar = t.mean()
    sd = s * np.sqrt(1 + 1 / n + (target_year - tbar) ** 2 / np.sum((t - tbar) ** 2))
    mu = a + b * target_year
    p_below = stats.norm.cdf((e[0] - mu) / sd)
    p_above = 1 - stats.norm.cdf((e[1] - mu) / sd)
    probs = np.clip([p_below, 1 - p_below - p_above, p_above], 0.02, None)
    probs = np.round(probs / probs.sum(), 3)
    probs[1] = round(1 - probs[0] - probs[2], 3)
    centre = float(mu) if var == "T" else float(fit.inverse(mu))
    last = past.iloc[-1]
    return {"variable": var, "season": season, "target_year": int(target_year),
            "probabilities": dict(zip(CATS, [float(p) for p in probs])),
            "tercile_edges": [round(v, 3) for v in edges], "unit": unit,
            "baseline": [int(base.index.min()), int(base.index.max())],
            "trend_centre": round(centre, 3), "seasons_used": int(n),
            "data_cutoff": f"{int(last.year)}-{int(last.month):02d}"}


def category(value: float, edges) -> str:
    if value < edges[0]:
        return "below"
    if value > edges[1]:
        return "above"
    return "near"


def rps(probs: dict, obs: str) -> float:
    """Ranked probability score for three ordered categories (0 = perfect)."""
    f = np.cumsum([probs[c] for c in CATS])[:-1]
    o = np.cumsum([1.0 if c == obs else 0.0 for c in CATS])[:-1]
    return float(np.sum((f - o) ** 2) / (len(CATS) - 1))


def brier(probs: dict, obs: str) -> float:
    """Multi-category Brier score (0 = perfect), averaged over categories."""
    return float(np.mean([(probs[c] - (1.0 if c == obs else 0.0)) ** 2 for c in CATS]))


def skill(rps_f, rps_c) -> float:
    """Skill score vs climatology: 1 is perfect, 0 is no better, < 0 is worse."""
    rps_c = float(np.mean(rps_c))
    return float(1 - np.mean(rps_f) / rps_c) if rps_c > 0 else float("nan")


def observed_value(monthly, var, season, year):
    vals = _season_values(monthly, var, season)
    return float(vals.loc[year]) if year in vals.index else None


def hindcasts(monthly: pd.DataFrame, var: str, season: str, first_year: int = 1996) -> dict:
    """Forecasts for past seasons, each made only with data from before that
    season. NOT locked: this estimates skill, it does not prove honesty."""
    vals = _season_values(monthly, var, season)
    rows = []
    for year in [int(y) for y in vals.index if y >= first_year]:
        try:
            fc = forecast_terciles(monthly, var, season, year)
        except ValueError:
            continue
        obs = category(float(vals.loc[year]), fc["tercile_edges"])
        rows.append({"year": year, "probabilities": fc["probabilities"], "observed": obs,
                     "rps": rps(fc["probabilities"], obs), "rps_clim": rps(CLIMATOLOGY, obs),
                     "brier": brier(fc["probabilities"], obs),
                     "brier_clim": brier(CLIMATOLOGY, obs)})
    if not rows:
        return {"n": 0}
    hit = np.mean([max(r["probabilities"], key=r["probabilities"].get) == r["observed"]
                   for r in rows])
    return {"n": len(rows), "first_year": rows[0]["year"], "last_year": rows[-1]["year"],
            "rpss": skill([r["rps"] for r in rows], [r["rps_clim"] for r in rows]),
            "bss": skill([r["brier"] for r in rows], [r["brier_clim"] for r in rows]),
            "hit_rate": float(hit), "rows": rows}


# ---------------------------------------------------------------- locking

def next_season(today: date) -> tuple[str, int]:
    """The next standard season that has not started yet."""
    best = None
    for year in (today.year, today.year + 1, today.year + 2):
        for s in STANDARD_SEASONS:
            y, m = C.season_start(s, year)
            start = date(y, m, 1)
            if start > today and (best is None or start < best[0]):
                best = (start, s, year)
    return best[1], best[2]


def forecast_path(root: Path, slug: str, season: str, year: int) -> Path:
    return Path(root) / slug / f"{year}-{season}.json"


def issue(place: dict, monthly: pd.DataFrame, season: str, year: int, root: Path,
          now: datetime | None = None) -> Path | None:
    """Write a locked forecast. Returns None if one already exists (never
    overwritten) and raises LateError if the season has already begun."""
    now = now or datetime.now(timezone.utc)
    path = forecast_path(root, place["slug"], season, year)
    if path.exists():
        return None
    sy, sm = C.season_start(season, year)
    if (now.year, now.month) >= (sy, sm):
        raise LateError(f"{season} {year} began {sy}-{sm:02d}; too late to lock a forecast")
    variables = {}
    for var in ("T", "P"):
        try:
            variables[var] = forecast_terciles(monthly, var, season, year)
        except ValueError as e:
            variables[var] = {"variable": var, "not_issued": str(e)}
    doc = {
        "schema": "cassandra-signal/forecast/v1",
        "place": {k: place[k] for k in ("slug", "name", "lat", "lon")},
        "season": season, "season_months": C.season_label(season), "target_year": year,
        "season_starts": f"{sy}-{sm:02d}-01",
        "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "categories": "below / near / above the middle third of 1981-2010 seasons",
        "method": METHOD,
        "data": "NASA POWER monthly T2M and PRECTOTCORR",
        "variables": variables,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_lock_info(path: Path, repo_root: Path) -> dict:
    """The commit that first added the file, and whether the file is still
    byte-for-byte what that commit contains."""
    rel = Path(path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H%x09%cI", "--", rel],
                             cwd=repo_root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"committed": False}
    lines = [ln for ln in out.strip().splitlines() if ln]
    if not lines:
        return {"committed": False}
    sha, when = lines[-1].split("\t")
    blob = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=repo_root,
                          capture_output=True, check=True).stdout
    return {"committed": True, "commit": sha, "commit_time": when,
            "unchanged_since_commit": hashlib.sha256(blob).hexdigest() == sha256_file(path)}


def score_locked(path: Path, monthly: pd.DataFrame) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {"file": Path(path).as_posix(), "doc": doc, "sha256": sha256_file(path), "scores": {}}
    for var, fc in doc["variables"].items():
        if "probabilities" not in fc:
            continue
        v = observed_value(monthly, var, doc["season"], doc["target_year"])
        if v is None:
            out["scores"][var] = {"status": "pending"}
            continue
        obs = category(v, fc["tercile_edges"])
        out["scores"][var] = {"status": "scored", "observed_value": v, "observed": obs,
                              "rps": rps(fc["probabilities"], obs),
                              "rps_clim": rps(CLIMATOLOGY, obs),
                              "brier": brier(fc["probabilities"], obs),
                              "brier_clim": brier(CLIMATOLOGY, obs)}
    return out


def last_seasons(monthly: pd.DataFrame, var: str, season: str, n: int = 10) -> dict | None:
    """Hindcasts for the last n complete seasons, with the observed value,
    for the 'track record' table next to a locked forecast."""
    h = hindcasts(monthly, var, season)
    if not h.get("n"):
        return None
    rows = h["rows"][-n:]
    vals = _season_values(monthly, var, season)
    for r in rows:
        r["value"] = float(vals.loc[r["year"]])
    hits = sum(max(r["probabilities"], key=r["probabilities"].get) == r["observed"] for r in rows)
    return {"variable": var, "season": season, "season_words": C.season_label(season),
            "unit": "°C" if var == "T" else "mm", "rows": rows, "hits": int(hits),
            "rpss": skill([r["rps"] for r in rows], [r["rps_clim"] for r in rows])}
