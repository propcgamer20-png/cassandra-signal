"""Fetch and cache NASA POWER and NASA GISTEMP v4 data.

Raw responses are stored unchanged in data/raw/ so a build can be repeated
exactly without the network. Pass refresh=True to download again.
"""
from __future__ import annotations

import calendar
import io
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

POWER_URL = (
    "https://power.larc.nasa.gov/api/temporal/monthly/point"
    "?parameters=T2M,PRECTOTCORR&community=AG"
    "&longitude={lon}&latitude={lat}&start=1981&end={year}&format=JSON"
)
GISTEMP_GLOBAL_URL = "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv"
GISTEMP_ZONAL_URL = "https://data.giss.nasa.gov/gistemp/tabledata_v4/ZonAnn.Ts+dSST.csv"

MISSING = -999.0
HEADERS = {"User-Agent": "cassandra-signal/1.0 (open-source climate signal project)"}


def _get(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    return r.text


def power_cache_path(raw_dir: Path, slug: str) -> Path:
    return Path(raw_dir) / f"power_{slug}.json"


def fetch_power(slug: str, lat: float, lon: float, raw_dir: Path, refresh: bool = False,
                end_year: int | None = None) -> dict:
    """Return the raw POWER JSON for a point, from cache when possible."""
    path = power_cache_path(raw_dir, slug)
    if path.exists() and not refresh:
        raw = json.loads(path.read_text(encoding="utf-8"))
        lon_c, lat_c = raw["geometry"]["coordinates"][:2]
        if abs(lon_c - lon) < 0.01 and abs(lat_c - lat) < 0.01:
            return raw
    year = end_year or date.today().year
    last_err = None
    for y in (year, year - 1):  # the current year can be refused early in January
        try:
            text = _get(POWER_URL.format(lat=lat, lon=lon, year=y))
            raw = json.loads(text)
            if "properties" in raw:
                if path.exists():
                    old = json.loads(path.read_text(encoding="utf-8"))
                    if (old.get("properties") == raw["properties"]
                            and old.get("geometry") == raw.get("geometry")):
                        return old  # same data; keep the file so git sees no change
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
                return raw
        except requests.RequestException as e:  # pragma: no cover - network
            last_err = e
    raise RuntimeError(f"POWER request failed for {slug}: {last_err}")


def parse_power(raw: dict) -> pd.DataFrame:
    """Monthly table: year, month, t2m (deg C), prec_mm (monthly total, mm).

    -999 is treated as missing. POWER's month '13' (the annual value) is dropped.
    PRECTOTCORR is a mean rate in mm/day, so it is multiplied by days in month.
    """
    params = raw["properties"]["parameter"]
    rows = {}
    for name, series in params.items():
        for key, val in series.items():
            y, m = int(key[:4]), int(key[4:])
            if m == 13:
                continue
            v = np.nan if val is None or float(val) <= MISSING + 0.5 else float(val)
            rows.setdefault((y, m), {})[name] = v
    df = pd.DataFrame(
        [{"year": y, "month": m, **vals} for (y, m), vals in sorted(rows.items())]
    )
    df["t2m"] = df.get("T2M", np.nan)
    days = np.array([calendar.monthrange(y, m)[1] for y, m in zip(df.year, df.month)])
    df["prec_mm"] = df.get("PRECTOTCORR", np.nan) * days
    out = df[["year", "month", "t2m", "prec_mm"]].copy()
    # drop trailing months that are entirely missing (not yet published)
    ok = out[["t2m", "prec_mm"]].notna().any(axis=1).to_numpy()
    if ok.any():
        out = out.iloc[: np.flatnonzero(ok)[-1] + 1]
    return out.reset_index(drop=True)


def load_power(slug, lat, lon, raw_dir, refresh=False) -> pd.DataFrame:
    return parse_power(fetch_power(slug, lat, lon, raw_dir, refresh=refresh))


# ---------------------------------------------------------------- GISTEMP

def _gistemp_text(url: str, name: str, raw_dir: Path, refresh: bool) -> str:
    path = Path(raw_dir) / name
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")
    text = _get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return text


def load_gistemp(raw_dir: Path, refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Global (annual J-D) and zonal annual anomalies, deg C vs 1951-1980."""
    g = _gistemp_text(GISTEMP_GLOBAL_URL, "gistemp_GLB.Ts+dSST.csv", raw_dir, refresh)
    z = _gistemp_text(GISTEMP_ZONAL_URL, "gistemp_ZonAnn.Ts+dSST.csv", raw_dir, refresh)
    glb = pd.read_csv(io.StringIO(g), skiprows=1, na_values=["***", "****"])
    glb = glb[["Year", "J-D"]].rename(columns={"Year": "year", "J-D": "anom"}).dropna()
    zon = pd.read_csv(io.StringIO(z), na_values=["***", "****"]).rename(columns={"Year": "year"})
    return glb.astype({"year": int}), zon.astype({"year": int})


ZONES = [  # (south edge, north edge, GISTEMP column, label)
    (64, 90, "64N-90N", "64-90°N"), (44, 64, "44N-64N", "44-64°N"),
    (24, 44, "24N-44N", "24-44°N"), (0, 24, "EQU-24N", "0-24°N"),
    (-24, 0, "24S-EQU", "0-24°S"), (-44, -24, "44S-24S", "24-44°S"),
    (-64, -44, "64S-44S", "44-64°S"), (-90, -64, "90S-64S", "64-90°S"),
]


def zone_for_lat(lat: float) -> tuple[str, str]:
    for lo, hi, col, label in ZONES:
        if lo <= lat <= hi:
            return col, label
    raise ValueError(lat)
