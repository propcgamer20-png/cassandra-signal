import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from cassandra import climate as C
from cassandra import forecasts as F
from cassandra.analysis import analyse_variable, backtest, event_cutoff
from cassandra.data import parse_power
from cassandra.falsealarm import false_alarm_check
from cassandra.stats import (empirical_p, fit_ar1, iaaft, null_test, recent_shift, sen_slope,
                             simulate_ar1, verdict_for)


def synthetic_monthly(years=range(1981, 2026), trend=0.0, seed=0):
    """Monthly table with a seasonal cycle, optional warming trend and gamma rain."""
    rng = np.random.default_rng(seed)
    rows = []
    for y in years:
        for m in range(1, 13):
            t = 15 + 8 * np.sin((m - 4) / 12 * 2 * np.pi) + trend * (y - 1981) + rng.normal(0, 1)
            p = rng.gamma(2.0, 30.0) * (1.5 if m in (6, 7, 8) else 1.0)
            rows.append({"year": y, "month": m, "t2m": t, "prec_mm": p})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- data parsing

def test_parse_power_handles_missing_annual_and_units():
    raw = {"properties": {"parameter": {
        "T2M": {"202001": 10.0, "202002": -999, "202013": 12.0},
        "PRECTOTCORR": {"202001": 2.0, "202002": 1.0, "202013": 1.5}}}}
    df = parse_power(raw)
    assert list(df.month) == [1, 2]               # month 13 (annual) dropped
    assert np.isnan(df.t2m.iloc[1])               # -999 is missing
    assert df.prec_mm.iloc[0] == pytest.approx(62.0)   # 2 mm/day * 31 days
    assert df.prec_mm.iloc[1] == pytest.approx(29.0)   # 2020 is a leap year


# ---------------------------------------------------------------- anomaly maths

def test_season_parsing():
    assert C.season_months("JJA") == [6, 7, 8]
    assert C.season_months("DJF") == [12, 1, 2]
    assert C.season_months("AMJJAS") == [4, 5, 6, 7, 8, 9]
    assert C.season_months("OND") == [10, 11, 12]
    assert C.season_months("ANN") == list(range(1, 13))
    assert C.season_start("DJF", 2027) == (2026, 12)
    with pytest.raises(ValueError):
        C.season_months("XYZ")


def test_monthly_anomalies_remove_each_calendar_months_baseline_mean():
    m = synthetic_monthly()
    anom = C.monthly_anomalies(m, "t2m")
    base = m.year.between(1981, 2010)
    per_month = anom[base].groupby(m.month[base]).mean()
    assert np.allclose(per_month, 0, atol=1e-10)
    # a constant shift after the baseline shows up exactly
    m2 = m.copy()
    m2.loc[m2.year > 2010, "t2m"] += 3
    a2 = C.monthly_anomalies(m2, "t2m")
    assert np.allclose(a2[m2.year > 2010] - anom[m.year > 2010], 3)


def test_djf_is_labelled_by_year_of_january_and_needs_all_months():
    m = pd.DataFrame({"year": [2020, 2021, 2021, 2021], "month": [12, 1, 2, 3],
                      "t2m": [1.0, 2.0, 3.0, 9.0], "prec_mm": [10, 20, 30, 40]})
    s = C.seasonal(m, m.t2m, "DJF", "mean")
    assert list(s.index) == [2021] and s.loc[2021] == pytest.approx(2.0)
    tot = C.seasonal(m, m.prec_mm, "DJF", "sum")
    assert tot.loc[2021] == 60
    # drop February: the season is incomplete and must disappear
    assert C.seasonal(m.drop(index=2), m.t2m.drop(index=2), "DJF", "mean").empty


def test_spi_is_standard_normal_for_gamma_data():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.gamma(3.0, 40.0, 3000), index=np.arange(3000) % 30 + 1981)
    fit = C.GammaFit(x.to_numpy())
    z = fit.spi(x.to_numpy())
    assert abs(z.mean()) < 0.05 and abs(z.std() - 1) < 0.05
    # inverse maps back
    assert np.allclose(fit.inverse(fit.spi([50.0, 120.0, 300.0])), [50, 120, 300], rtol=1e-6)


def test_percent_of_normal():
    tot = pd.Series([100.0, 200.0, 300.0], index=[1990, 2000, 2020])
    pct, normal = C.percent_of_normal(tot)
    assert normal == 150 and pct.loc[2020] == 200


# ---------------------------------------------------------------- statistics

def test_sen_slope_matches_scipy_and_handles_many_series():
    rng = np.random.default_rng(2)
    t = np.arange(1981, 2026, dtype=float)
    y = 0.03 * t + rng.normal(0, 1, len(t))
    assert sen_slope(y, t) == pytest.approx(stats.theilslopes(y, t)[0])
    many = rng.normal(size=(5, len(t)))
    assert np.allclose(sen_slope(many, t), [stats.theilslopes(r, t)[0] for r in many])


def test_recent_shift():
    y = np.r_[np.zeros(20), np.ones(15), np.full(10, 2.0)]
    assert recent_shift(y) == 2.0


def test_empirical_p_value_formula():
    null = np.array([-3, -1, 0, 1, 2, 5], float)
    r = empirical_p(2.0, null)        # |null| >= 2: -3, 2, 5
    assert r["count"] == 3 and r["p"] == pytest.approx(4 / 7) and r["outside"] == 3
    r = empirical_p(-10.0, null)      # beyond all of them (two-sided)
    assert r["count"] == 0 and r["p"] == pytest.approx(1 / 7)
    # with 1,000 histories, "outside all" must give the top verdict
    assert verdict_for(1 / 1001)["key"] == "no_alibi"
    assert verdict_for(10 / 1001)["key"] == "very_unlikely"   # beyond 990
    assert verdict_for(50 / 1001)["key"] == "probable"        # beyond 950
    assert verdict_for(51 / 1001)["key"] == "not_yet"


def test_null_test_finds_strong_trend_and_is_reproducible():
    t = np.arange(45, dtype=float)
    y = 0.1 * t + np.random.default_rng(3).normal(0, 1, 45)
    a = null_test(y, t, seed=42)
    assert a["verdict"]["key"] == "no_alibi"
    assert null_test(y, t, seed=42)["p"] == a["p"]          # fixed seed
    for gen in ("arma", "iaaft"):
        assert null_test(y, t, gen, N=300, seed=1)["p"] < 0.01


def test_ar1_fit_recovers_memory():
    rng = np.random.default_rng(4)
    x = simulate_ar1(0.6, 2.0, 2000, 1, rng)[0]
    fit = fit_ar1(x)
    assert fit["phi"] == pytest.approx(0.6, abs=0.06)
    assert fit["sigma"] == pytest.approx(2.0, rel=0.15)


def test_iaaft_keeps_values_exactly():
    rng = np.random.default_rng(5)
    x = rng.gamma(2, 1, 45)
    s = iaaft(x, 20, rng)
    assert np.allclose(np.sort(s, axis=1), np.sort(x))
    amp = np.abs(np.fft.rfft(x))
    rel = np.abs(np.abs(np.fft.rfft(s, axis=1)) - amp).mean() / amp.mean()
    assert rel < 0.15


def test_false_alarm_rate_is_about_five_percent():
    """The generator check: trend-free series must be flagged ~5% of the time."""
    rows = false_alarm_check(M=300, N=400, seed=11)
    flagged = sum(r["flagged"] for r in rows)
    total = sum(r["n_series"] for r in rows)
    assert flagged / total < 0.075, rows
    for r in rows:
        assert r["rate"] < 0.10, r


# ---------------------------------------------------------------- backtests

EVENT = {"slug": "x", "year": 2011, "variable": "T", "season": "JJA", "kind": "heat",
         "name": "test heat", "source": "https://example.org"}


def test_event_cutoff_rules():
    assert event_cutoff(2011, "JJA") == (2010, 12)
    assert event_cutoff(2014, "NDJFM") == (2013, 10)   # season starts Nov 2013
    assert event_cutoff(2020, "DJF") == (2019, 11)


def test_backtest_uses_no_future_data():
    m = synthetic_monthly(trend=0.02)
    a = backtest(m, EVENT)
    # wreck everything after the cut-off except the event season itself
    m2 = m.copy()
    later = (m2.year > 2011) | ((m2.year == 2011) & ~m2.month.isin([6, 7, 8]))
    m2.loc[later, "t2m"] += 50
    m2.loc[later, "prec_mm"] *= 7
    b = backtest(m2, EVENT)
    assert a["result"]["test"]["p"] == b["result"]["test"]["p"]
    assert a["result"]["trend_per_decade"] == b["result"]["trend_per_decade"]
    assert a["forecast_at_the_time"] == b["forecast_at_the_time"]
    assert a["result"]["last_year"] == 2010
    # and the analysis with a cut-off ignores later data completely
    r1 = analyse_variable(m, "P", "JJA", cutoff=(2005, 12), robustness=False)
    r2 = analyse_variable(m2.assign(prec_mm=np.where(m2.year > 2005, 0.0, m2.prec_mm)),
                          "P", "JJA", cutoff=(2005, 12), robustness=False)
    assert r1["test"]["p"] == r2["test"]["p"]


# ---------------------------------------------------------------- forecasts

def test_rps_and_skill():
    perfect = {"below": 0.0, "near": 0.0, "above": 1.0}
    assert F.rps(perfect, "above") == 0
    assert F.rps(perfect, "below") == 1
    assert F.rps(F.CLIMATOLOGY, "near") == pytest.approx((1 / 9 + 1 / 9) / 2)
    assert F.skill([0.1, 0.1], [0.2, 0.2]) == pytest.approx(0.5)


def test_forecast_probabilities_and_lock(tmp_path):
    m = synthetic_monthly(trend=0.05)
    fc = F.forecast_terciles(m, "T", "JJA", 2026)
    assert sum(fc["probabilities"].values()) == pytest.approx(1.0, abs=1e-9)
    assert fc["probabilities"]["above"] > 0.5       # strong warming loads the dice
    assert fc["data_cutoff"] == "2025-12"           # nothing from the season itself
    place = {"slug": "x", "name": "X", "lat": 1.0, "lon": 2.0}
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    p = F.issue(place, m, "DJF", 2027, tmp_path, now=now)
    first = p.read_bytes()
    doc = json.loads(first)
    assert doc["season_starts"] == "2026-12-01" and doc["issued_at_utc"].startswith("2026-11-15")
    # never overwritten
    assert F.issue(place, synthetic_monthly(seed=9), "DJF", 2027, tmp_path, now=now) is None
    assert p.read_bytes() == first
    # too late once the season has begun
    with pytest.raises(F.LateError):
        F.issue(place, m, "MAM", 2026, tmp_path, now=now)


def test_locked_forecast_scoring(tmp_path):
    m = synthetic_monthly(years=range(1981, 2026))
    place = {"slug": "x", "name": "X", "lat": 1.0, "lon": 2.0}
    p = F.issue(place, m[m.year < 2025], "JJA", 2025, tmp_path,
                now=datetime(2025, 5, 1, tzinfo=timezone.utc))
    scored = F.score_locked(p, m)
    assert scored["scores"]["T"]["status"] == "scored"
    assert scored["scores"]["T"]["observed"] in F.CATS
    pending = F.score_locked(p, m[m.year < 2025])
    assert pending["scores"]["T"]["status"] == "pending"


def test_next_season():
    from datetime import date
    assert F.next_season(date(2026, 11, 15)) == ("DJF", 2027)
    assert F.next_season(date(2027, 1, 10)) == ("MAM", 2027)
    assert F.next_season(date(2027, 12, 1)) == ("MAM", 2028)
