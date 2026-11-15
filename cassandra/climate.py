"""Seasons, anomalies and the standardized precipitation index (SPI).

Conventions
- A season is written as month initials, e.g. "JJA", "DJF", "OND", "AMJJAS",
  or "ANN" for the calendar year.
- A season that crosses the new year is labelled by the year of its last
  month: DJF 2027 = Dec 2026 + Jan 2027 + Feb 2027.
- Only complete seasons (every month present) are used.
- The baseline is 1981-2010, cut short when a backtest has less data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

BASELINE = (1981, 2010)
_LETTERS = "JFMAMJJASOND" * 2
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def season_months(season: str) -> list[int]:
    season = season.upper()
    if season == "ANN":
        return list(range(1, 13))
    start = _LETTERS.find(season)
    if start < 0 or start > 11 or len(season) > 12:
        raise ValueError(f"unknown season {season!r}")
    return [(start + k) % 12 + 1 for k in range(len(season))]


def season_label(season: str) -> str:
    """Human words for a season, e.g. 'Jun-Aug'."""
    if season.upper() == "ANN":
        return "Annual"
    m = season_months(season)
    return f"{MONTH_NAMES[m[0]-1]}-{MONTH_NAMES[m[-1]-1]}"


def season_start(season: str, year: int) -> tuple[int, int]:
    """(year, month) of the first month of the season labelled `year`."""
    m = season_months(season)
    crosses = m[-1] < m[0]
    return (year - 1 if crosses else year, m[0])


def month_before(ym: tuple[int, int]) -> tuple[int, int]:
    y, m = ym
    return (y - 1, 12) if m == 1 else (y, m - 1)


def truncate(monthly: pd.DataFrame, cutoff: tuple[int, int] | None) -> pd.DataFrame:
    """Keep only months on or before cutoff = (year, month). The core of
    'no future data': every later step sees only this table."""
    if cutoff is None:
        return monthly
    key = monthly["year"] * 100 + monthly["month"]
    return monthly[key <= cutoff[0] * 100 + cutoff[1]].reset_index(drop=True)


def baseline_years(years, base=BASELINE) -> list[int]:
    return [y for y in years if base[0] <= y <= base[1]]


def monthly_climatology(monthly: pd.DataFrame, col: str, base=BASELINE) -> pd.Series:
    """Mean of each calendar month over the baseline years available."""
    m = monthly[(monthly.year >= base[0]) & (monthly.year <= base[1])]
    return m.groupby("month")[col].mean()


def monthly_anomalies(monthly: pd.DataFrame, col: str, base=BASELINE) -> pd.Series:
    clim = monthly_climatology(monthly, col, base)
    return monthly[col] - monthly["month"].map(clim)


def seasonal(monthly: pd.DataFrame, values: pd.Series, season: str, how: str) -> pd.Series:
    """Aggregate a monthly series to one value per complete season.

    how = "mean" (temperature) or "sum" (precipitation totals).
    Returns a Series indexed by season-label year.
    """
    months = season_months(season)
    crosses = months[-1] < months[0]
    df = pd.DataFrame({"year": monthly["year"].to_numpy(), "month": monthly["month"].to_numpy(),
                       "v": np.asarray(values, float)})
    df = df[df.month.isin(months)]
    if crosses:
        df.loc[df.month >= months[0], "year"] += 1
    g = df.groupby("year")["v"]
    agg = g.sum(min_count=1) if how == "sum" else g.mean()
    complete = g.count() == len(months)
    out = agg[complete]
    out.index = out.index.astype(int)
    return out.sort_index()


# ---------------------------------------------------------------- SPI

class GammaFit:
    """Mixed gamma distribution for precipitation totals: a probability q of
    zero, and a gamma fit (location 0) to the positive totals."""

    def __init__(self, values):
        v = np.asarray(values, float)
        v = v[np.isfinite(v)]
        if len(v) < 8:
            raise ValueError("need at least 8 values to fit a gamma distribution")
        pos = v[v > 0]
        self.q = 1 - len(pos) / len(v)
        if len(pos) < 5 or np.allclose(pos, pos[0]):
            raise ValueError("too few non-zero totals for a gamma fit (dry season?)")
        self.a, _, self.scale = stats.gamma.fit(pos, floc=0)
        self.mean = float(v.mean())

    def cdf(self, x):
        x = np.asarray(x, float)
        return np.where(x <= 0, self.q, self.q + (1 - self.q) * stats.gamma.cdf(x, self.a, scale=self.scale))

    def spi(self, x):
        p = np.clip(self.cdf(x), 1e-6, 1 - 1e-6)
        # with zeros present, use the mid-probability of the zero mass
        p = np.where(np.asarray(x) <= 0, np.maximum(self.q / 2, 1e-6), p)
        return stats.norm.ppf(p)

    def inverse(self, z):
        """Precipitation total for a given SPI value."""
        p = stats.norm.cdf(np.asarray(z, float))
        pp = np.clip((p - self.q) / (1 - self.q), 0, 1 - 1e-12)
        return np.where(p <= self.q, 0.0, stats.gamma.ppf(pp, self.a, scale=self.scale))


def spi_series(totals: pd.Series, base=BASELINE) -> tuple[pd.Series, GammaFit]:
    """SPI of seasonal totals, gamma fitted on the baseline years present."""
    ref = totals[(totals.index >= base[0]) & (totals.index <= base[1])]
    fit = GammaFit(ref.to_numpy())
    return pd.Series(fit.spi(totals.to_numpy()), index=totals.index), fit


def monthly_spi(monthly: pd.DataFrame, base=BASELINE) -> pd.Series:
    """SPI-1: each month's total against a gamma fit for that calendar month.
    Months that are always dry come back as NaN."""
    out = pd.Series(np.nan, index=monthly.index)
    for m in range(1, 13):
        sel = monthly.month == m
        ref = monthly[sel & (monthly.year >= base[0]) & (monthly.year <= base[1])]["prec_mm"]
        try:
            fit = GammaFit(ref.to_numpy())
        except ValueError:
            continue
        out[sel] = fit.spi(monthly.loc[sel, "prec_mm"].to_numpy())
    return out


def percent_of_normal(totals: pd.Series, base=BASELINE) -> tuple[pd.Series, float]:
    ref = totals[(totals.index >= base[0]) & (totals.index <= base[1])]
    normal = float(ref.mean())
    return totals / normal * 100.0, normal
