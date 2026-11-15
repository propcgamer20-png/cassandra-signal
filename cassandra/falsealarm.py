"""Check the generator, not just the record.

Feed the whole test (detrend, fit AR(1), 1,000 histories, rank) series that
are known to have NO trend. A fair test flags about 5% of them at p < 0.05.
We also feed series with a known trend to show how often a real change is
caught with a record this short (the power of the test).
"""
from __future__ import annotations

import numpy as np
from scipy import stats

from .stats import null_test, simulate_ar1

CASES = [
    # name, description, kind, parameter
    ("white", "White noise (no memory)", "ar1", 0.0),
    ("ar1_03", "AR(1) noise, lag-1 correlation 0.3", "ar1", 0.3),
    ("ar1_06", "AR(1) noise, lag-1 correlation 0.6 (strong memory)", "ar1", 0.6),
    ("skewed", "Skewed noise like rainfall (gamma, shape 2)", "gamma", 2.0),
]


def _series(kind, param, n, M, rng):
    if kind == "ar1":
        return simulate_ar1(param, 1.0, n, M, rng)
    if kind == "gamma":
        g = rng.gamma(param, 1.0, size=(M, n))
        return (g - param) / np.sqrt(param)
    raise ValueError(kind)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def false_alarm_check(M=500, n=45, N=1000, alpha=0.05, seed=2026, cases=CASES,
                      trend_per_decade=(0.0,)):
    """Return one row per (case, trend). Trend is in noise standard deviations
    per decade; trend 0 rows are the false-alarm rates."""
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    rows = []
    for name, desc, kind, param in cases:
        for trend in trend_per_decade:
            ys = _series(kind, param, n, M, rng) + trend / 10 * t
            ps = np.array([null_test(y, t, "ar1", N=N, seed=int(rng.integers(2**31)))["p"]
                           for y in ys])
            k = int(np.sum(ps < alpha))
            lo, hi = wilson(k, M)
            rows.append({"case": name, "description": desc, "trend_sd_per_decade": trend,
                         "n_series": M, "years": n, "flagged": k, "rate": k / M,
                         "ci95": [lo, hi], "alpha": alpha,
                         "binom_p_vs_alpha": float(stats.binomtest(k, M, alpha).pvalue)})
    return rows
