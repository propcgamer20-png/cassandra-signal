"""Put one place's record on trial: one variable, one season."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import climate as C
from .stats import N_HISTORIES, derive_seed, null_test, recent_shift, sen_slope

MIN_SEASONS = 15
VAR_NAMES = {"T": "temperature", "P": "precipitation"}


def seasonal_series(monthly: pd.DataFrame, var: str, season: str) -> dict:
    """The series that goes on trial, plus the same series in plain units.

    T: seasonal mean of monthly anomalies (deg C vs each month's 1981-2010 mean).
       Tested and plotted in deg C.
    P: seasonal total (mm). Tested as SPI (gamma fit on 1981-2010 totals),
       plotted as percent of the 1981-2010 normal.
    """
    if var == "T":
        anom = C.monthly_anomalies(monthly, "t2m")
        s = C.seasonal(monthly, anom, season, "mean").dropna()
        absval = C.seasonal(monthly, monthly["t2m"], season, "mean").dropna()
        base = C.baseline_years(absval.index)
        return {"years": s.index.to_numpy(), "stat": s.to_numpy(), "plot": s.to_numpy(),
                "normal": float(absval.loc[base].mean()), "unit": "°C",
                "baseline": [min(base), max(base)], "fit": None}
    if var == "P":
        tot = C.seasonal(monthly, monthly["prec_mm"], season, "sum").dropna()
        spi, fit = C.spi_series(tot)
        pct, normal = C.percent_of_normal(tot)
        base = C.baseline_years(tot.index)
        return {"years": tot.index.to_numpy(), "stat": spi.to_numpy(), "plot": pct.to_numpy(),
                "totals": tot.to_numpy(), "normal": normal, "unit": "% of normal",
                "baseline": [min(base), max(base)], "fit": fit}
    raise ValueError(var)


def _to_plot_units(series_info, var, stat_values):
    if var == "T":
        return stat_values
    fit = series_info["fit"]
    return fit.inverse(stat_values) / series_info["normal"] * 100.0


def analyse_variable(monthly: pd.DataFrame, var: str, season: str, *, slug: str = "",
                     cutoff=None, N: int = N_HISTORIES, robustness: bool = True,
                     keep: bool = False) -> dict:
    """Run steps A-D of the method for one variable and season.

    `cutoff` = (year, month): the data are cut there FIRST, so the baseline,
    the fit and the histories never see anything later.
    """
    monthly = C.truncate(monthly, cutoff)
    info = seasonal_series(monthly, var, season)
    years, y = info["years"], info["stat"]
    out = {"variable": var, "variable_name": VAR_NAMES[var], "season": season,
           "season_label": C.season_label(season), "unit": info["unit"],
           "first_year": int(years[0]) if len(years) else None,
           "last_year": int(years[-1]) if len(years) else None, "n_years": int(len(years)),
           "baseline": info["baseline"], "normal": info["normal"],
           "data_cutoff": f"{int(monthly.year.iloc[-1])}-{int(monthly.month.iloc[-1]):02d}"}
    if len(years) < MIN_SEASONS:
        out["insufficient"] = True
        return out
    seed = derive_seed(slug, var, season, cutoff)
    t = years.astype(float)
    test = null_test(y, t, "ar1", N=N, seed=seed, keep=True)
    sims = test.pop("sims")
    null_stats = test.pop("null_stats")
    out["test"] = test
    out["verdict"] = test["verdict"]

    plot = info["plot"]
    slope_plot = sen_slope(plot, t)  # per year, in plain units
    out["trend_per_decade"] = slope_plot * 10
    out["change_over_record"] = slope_plot * (t[-1] - t[0])
    out["recent_shift"] = recent_shift(plot)
    if var == "T":
        out["direction"] = "warmer" if test["real"] > 0 else "cooler"
    else:
        out["direction"] = "wetter" if test["real"] > 0 else "drier"
        out["normal_mm"] = info["normal"]
        out["spi_trend_per_decade"] = test["real"] * 10

    if robustness:
        rob = {}
        for gen in ("arma", "iaaft"):
            r = null_test(y, t, gen, N=N, seed=seed + 1)
            rob[gen] = {"p": r["p"], "outside": r["outside"], "verdict": r["verdict"]["key"],
                        "fit": r["fit"]}
        out["robustness"] = rob

    if keep:
        base_mask = (years >= info["baseline"][0]) & (years <= info["baseline"][1])
        centre = float(np.mean(y[base_mask]))
        band = _to_plot_units(info, var, sims + centre)
        out["_arrays"] = {"years": years, "plot": plot, "band": band,
                          "null_stats": null_stats * 10, "real_stat": test["real"] * 10}
    return out


# ---------------------------------------------------------------- backtests

def event_cutoff(event_year: int, season: str) -> tuple[int, int]:
    """Last month the backtest may see: the end of the year before the event,
    or the month before the event season starts, whichever is earlier."""
    return min((event_year - 1, 12), C.month_before(C.season_start(season, event_year)))


EXPECTED = {"heat": "warmer", "drought": "drier", "flood": "wetter", "cold": "cooler"}


def backtest(monthly: pd.DataFrame, event: dict, *, slug: str = "", N: int = N_HISTORIES) -> dict:
    """Rerun the trial using only data from before the event (step E)."""
    from .forecasts import forecast_terciles

    var, season, year = event["variable"], event["season"], int(event["year"])
    cut = event_cutoff(year, season)
    past = C.truncate(monthly, cut)
    res = analyse_variable(past, var, season, slug=slug, N=N, robustness=False, keep=True)
    band = res.pop("_arrays")["band"] if "_arrays" in res else None

    # What actually happened, measured against the baseline known at the time.
    then = seasonal_series(past, var, season)
    full_months = C.truncate(monthly, None)
    if var == "T":
        clim = C.monthly_climatology(past, "t2m")
        anom = full_months["t2m"] - full_months["month"].map(clim)
        ev = C.seasonal(full_months, anom, season, "mean")
        observed = {"anomaly": float(ev.loc[year]), "unit": "°C"}
    else:
        tot = C.seasonal(full_months, full_months["prec_mm"], season, "sum")
        v = float(tot.loc[year])
        observed = {"total_mm": v, "pct_of_normal": v / then["normal"] * 100,
                    "spi": float(then["fit"].spi(v))}
    rank_vals = then["plot"] if var == "T" else then["totals"]
    ev_val = observed.get("anomaly", observed.get("total_mm"))
    expected = EXPECTED[event["kind"]]
    # rank 1 = the most extreme in the expected direction of all years before it
    high = expected in ("warmer", "wetter")
    observed["rank_in_record"] = int((np.sum(rank_vals >= ev_val) if high
                                      else np.sum(rank_vals <= ev_val)) + 1)
    observed["record_years"] = int(len(rank_vals))
    # Does the event even show up in this dataset at this point? Measured in
    # standard deviations (temperature) or SPI (rain) in the expected direction.
    z = (observed["anomaly"] / float(np.std(then["plot"], ddof=1)) if var == "T"
         else observed["spi"])
    signed = z if high else -z
    observed["z"] = float(z)
    # How rare was the event itself? Compare it with every year of the 1,000
    # imaginary histories built only from the data before it (plain units).
    if band is not None:
        ev_plot = observed["anomaly"] if var == "T" else observed["pct_of_normal"]
        observed["more_extreme_than_pct"] = float(100 * np.mean(band < ev_plot if high else band > ev_plot))
    observed["visibility"] = ("extreme" if signed >= 1.28 else
                              "unusual" if signed >= 0.43 else "not visible")

    significant = res.get("verdict", {}).get("key", "not_yet") != "not_yet"
    warned = bool(significant and res.get("direction") == expected)
    try:
        fc = forecast_terciles(monthly, var, season, year, cutoff=cut)
    except ValueError as e:
        fc = {"skipped": str(e)}
    return {"event": event, "cutoff": f"{cut[0]}-{cut[1]:02d}", "result": res,
            "observed": observed, "expected_direction": expected, "warned": warned,
            "forecast_at_the_time": fc}
