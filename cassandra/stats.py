"""Test statistics, the null ensemble ("1,000 imaginary histories") and verdicts."""
from __future__ import annotations

import warnings
import zlib

import numpy as np

N_HISTORIES = 1000
BASE_SEED = 1981  # recorded on every card; per-series seeds are derived from it

VERDICTS = [  # (p below, key, plain words, colour)
    (0.001, "no_alibi", "Natural variation has no alibi", "red"),
    (0.01, "very_unlikely", "Very unlikely to be natural variation alone", "red"),
    (0.05, "probable", "Probably a real change", "amber"),
    (1.01, "not_yet", "Not yet distinguishable from natural variation", "grey"),
]


def derive_seed(*parts) -> int:
    """Stable seed for one series: BASE_SEED plus a CRC of its name."""
    return BASE_SEED + zlib.crc32("|".join(map(str, parts)).encode()) % 1_000_000


# ---------------------------------------------------------------- statistics

def sen_slope(y, t=None):
    """Sen's (Theil-Sen) slope: the median of all pairwise slopes.
    Accepts one series (1-D) or many series as rows of a 2-D array."""
    y = np.asarray(y, float)
    single = y.ndim == 1
    Y = np.atleast_2d(y)
    n = Y.shape[1]
    t = np.arange(n, dtype=float) if t is None else np.asarray(t, float)
    i, j = np.triu_indices(n, 1)
    slopes = (Y[:, j] - Y[:, i]) / (t[j] - t[i])
    s = np.median(slopes, axis=1)
    return float(s[0]) if single else s


def sen_line(y, t):
    """Sen slope and the matching intercept (median of y - b t)."""
    y, t = np.asarray(y, float), np.asarray(t, float)
    b = sen_slope(y, t)
    return b, float(np.median(y - b * t))


def recent_shift(y, recent=10, early=20):
    """Mean of the last `recent` values minus the mean of the first `early`."""
    y = np.asarray(y, float)
    if len(y) < recent + early:
        return float("nan")
    return float(y[-recent:].mean() - y[:early].mean())


def detrend(y, t, method="linear", frac=0.5):
    """Return (residuals, trend). Linear least squares or LOWESS."""
    y, t = np.asarray(y, float), np.asarray(t, float)
    if method == "linear":
        b, a = np.polyfit(t, y, 1)
        trend = a + b * t
    elif method == "lowess":
        from statsmodels.nonparametric.smoothers_lowess import lowess
        trend = lowess(y, t, frac=frac, return_sorted=False)
    else:
        raise ValueError(method)
    return y - trend, trend


# ---------------------------------------------------------------- generators

def fit_ar1(resid):
    """Lag-1 autocorrelation and standard deviation of detrended residuals,
    corrected for the shortness of the record.

    Three small-sample problems would otherwise make the imaginary histories
    too calm and the test too eager (we measured 7-9% false alarms instead of
    5% before fixing them):
    1. The lag-1 estimate of a short detrended series is biased low by about
       (2 + 5 phi) / n (measured by simulation for n = 45); we invert that.
    2. Removing a fitted line also removes part of the slow wandering, so the
       residual variance is too small by a factor of about
       1 - 2 (1 + phi) / (n (1 - phi)); we divide it back out.
    3. Both estimates are uncertain. simulate_ar1_uncertain draws each history's
       phi and sigma from their sampling distributions instead of reusing the
       single best guess (n_eff = n (1 - phi) / (1 + phi) for sigma).
    The false-alarm check (falsealarm.py) is what tells us this is good enough.
    """
    r = np.asarray(resid, float)
    r = r - r.mean()
    n = len(r)
    r1 = float(np.sum(r[1:] * r[:-1]) / np.sum(r * r))
    phi = float(np.clip((r1 + 2 / n) / (1 - 5 / n), -0.9, 0.95))
    shrink = max(1 - 2 * (1 + phi) / (n * (1 - phi)), 0.3)
    sigma = float(np.std(r) / np.sqrt(shrink))
    n_eff = float(max(n * (1 - phi) / (1 + phi), 4.0))
    return {"phi": phi, "phi_raw": r1, "sigma": sigma, "n_eff": n_eff, "n": n}


def simulate_ar1(phi, sigma, n, N, rng):
    """N stationary AR(1) series of length n with marginal sd sigma.
    phi and sigma may be scalars or one value per series."""
    phi = np.broadcast_to(np.asarray(phi, float), (N,))
    sigma = np.broadcast_to(np.asarray(sigma, float), (N,))
    x = np.empty((N, n))
    x[:, 0] = rng.standard_normal(N) * sigma
    e = rng.standard_normal((N, n)) * (sigma * np.sqrt(1 - phi ** 2))[:, None]
    for k in range(1, n):
        x[:, k] = phi * x[:, k - 1] + e[:, k]
    return x


def simulate_ar1_uncertain(fit, n, N, rng):
    """AR(1) histories whose phi and sigma are drawn from their uncertainty."""
    se = np.sqrt((1 - fit["phi"] ** 2) / fit["n"])
    phis = np.clip(fit["phi"] + se * rng.standard_normal(N), -0.9, 0.97)
    sigmas = fit["sigma"] * np.sqrt(fit["n_eff"] / rng.chisquare(fit["n_eff"], N))
    return simulate_ar1(phis, sigmas, n, N, rng)


def fit_arma_aic(resid, max_order=2):
    """ARMA(p, q), p, q <= max_order, chosen by AIC."""
    from statsmodels.tsa.arima.model import ARIMA
    r = np.asarray(resid, float) - np.mean(resid)
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in range(max_order + 1):
            for q in range(max_order + 1):
                try:
                    res = ARIMA(r, order=(p, 0, q), trend="n").fit()
                except Exception:  # pragma: no cover - rare optimiser failure
                    continue
                if best is None or res.aic < best["aic"]:
                    best = {"p": p, "q": q, "aic": float(res.aic),
                            "ar": [float(v) for v in res.arparams],
                            "ma": [float(v) for v in res.maparams],
                            "sigma2": float(res.params[-1])}
    return best


def simulate_arma(fit, n, N, rng, burn=200):
    from statsmodels.tsa.arima_process import ArmaProcess
    proc = ArmaProcess(np.r_[1, -np.array(fit["ar"])], np.r_[1, np.array(fit["ma"])])
    x = proc.generate_sample(nsample=(n + burn, N), scale=np.sqrt(fit["sigma2"]),
                             distrvs=rng.standard_normal, axis=0)
    return x[burn:].T


def iaaft(x, N, rng, n_iter=100):
    """Iterative amplitude-adjusted Fourier transform surrogates.
    Each surrogate has exactly the same values as x (re-ordered) and very
    nearly the same power spectrum, but any trend or phase structure is lost."""
    x = np.asarray(x, float)
    n = len(x)
    sorted_x = np.sort(x)
    amp = np.abs(np.fft.rfft(x))
    S = np.array([rng.permutation(x) for _ in range(N)])
    for _ in range(n_iter):
        F = np.fft.rfft(S, axis=1)
        S = np.fft.irfft(amp * np.exp(1j * np.angle(F)), n=n, axis=1)
        S = sorted_x[np.argsort(np.argsort(S, axis=1), axis=1)]
    return S


# ---------------------------------------------------------------- the test

def empirical_p(real, null_stats):
    """Two-sided empirical p-value with the +1 correction.

    count = how many imaginary histories have a trend at least as large (in
    either direction) as the real one; p = (count + 1) / (N + 1).
    """
    null_stats = np.asarray(null_stats, float)
    N = len(null_stats)
    count = int(np.sum(np.abs(null_stats) >= abs(real)))
    return {"count": count, "N": N, "outside": N - count, "p": (count + 1) / (N + 1)}


def verdict_for(p):
    for cut, key, words, colour in VERDICTS:
        if p < cut:
            return {"key": key, "text": words, "colour": colour}
    raise AssertionError


def null_test(y, t, generator="ar1", N=N_HISTORIES, seed=BASE_SEED, keep=False):
    """Rank the real Sen slope among N imaginary histories of natural variation.

    1. Detrend y (linear) - what is left is treated as natural variability.
    2. Fit the generator to the residuals and make N trend-free series.
    3. Compute Sen's slope for each and compare with the real one.
    """
    y, t = np.asarray(y, float), np.asarray(t, float)
    rng = np.random.default_rng(seed)
    real = sen_slope(y, t)
    resid, _ = detrend(y, t)
    if generator == "ar1":
        fit = fit_ar1(resid)
        sims = simulate_ar1_uncertain(fit, len(y), N, rng)
    elif generator == "arma":
        fit = fit_arma_aic(resid)
        sims = simulate_arma(fit, len(y), N, rng)
    elif generator == "iaaft":
        fit = {}
        sims = iaaft(resid, N, rng)
    else:
        raise ValueError(generator)
    nulls = sen_slope(sims, t)
    out = {"generator": generator, "fit": fit, "seed": int(seed), "real": real,
           **empirical_p(real, nulls)}
    out["verdict"] = verdict_for(out["p"])
    if keep:
        out["sims"], out["null_stats"] = sims, nulls
    return out
