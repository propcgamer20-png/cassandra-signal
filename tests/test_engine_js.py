"""The browser engine (cassandra/web/engine.js) must agree with the Python pipeline.

Deterministic quantities (trend, anomalies, AR(1) fit, SPI, forecasts) must match
closely. p-values come from different random number generators, so they may
differ by sampling noise only.
"""
import json
import math
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from scipy import stats

from cassandra import climate as C
from cassandra.analysis import analyse_variable
from cassandra.data import parse_power
from cassandra.forecasts import forecast_terciles, hindcasts

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
PLACES = pd.read_csv(ROOT / "places.csv").to_dict("records")


def run_js(slug, jobs, tmp_path):
    jf = tmp_path / f"jobs_{slug}.json"
    jf.write_text(json.dumps(jobs))
    out = subprocess.run([NODE, str(ROOT / "tests" / "engine_harness.js"),
                          str(ROOT / "data" / "raw" / f"power_{slug}.json"), str(jf)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def monthly(slug):
    return parse_power(json.loads((ROOT / "data" / "raw" / f"power_{slug}.json").read_text()))


def p_close(a, b):
    p = max(a, b)
    return abs(a - b) <= 4.5 * math.sqrt(p * (1 - p) / 1000) + 0.004


@pytest.mark.parametrize("place", PLACES, ids=[p["slug"] for p in PLACES])
def test_js_engine_matches_python(place, tmp_path):
    m = monthly(place["slug"])
    jobs, py = [], []
    for var, season in (("T", place["t_season"]), ("P", place["p_season"])):
        for cutoff in (None, [2005, 12]):
            jobs.append({"kind": "analyse", "variable": var, "season": season, "cutoff": cutoff})
            py.append(analyse_variable(m, var, season, cutoff=tuple(cutoff) if cutoff else None,
                                       robustness=False))
    js = run_js(place["slug"], jobs, tmp_path)
    for j, p in zip(js, py):
        t = p["test"]
        assert j["n"] == p["n_years"] and j["last"] == p["last_year"]
        assert j["real"] == pytest.approx(t["real"], rel=1e-6, abs=1e-9)
        assert j["trend"] == pytest.approx(p["trend_per_decade"], rel=1e-6, abs=1e-9)
        assert j["phi"] == pytest.approx(t["fit"]["phi"], rel=1e-6, abs=1e-8)
        assert j["sigma"] == pytest.approx(t["fit"]["sigma"], rel=1e-6)
        assert j["normal"] == pytest.approx(p["normal"], rel=1e-9)
        assert p_close(j["p"], t["p"]), (place["slug"], j, t["p"])


@pytest.mark.parametrize("place", PLACES, ids=[p["slug"] for p in PLACES])
def test_js_forecasts_match_python(place, tmp_path):
    m = monthly(place["slug"])
    jobs = [{"kind": "forecast", "variable": v, "season": "DJF", "year": 2027, "cutoff": None} for v in "TP"]
    jobs += [{"kind": "forecast", "variable": "T", "season": place["t_season"], "year": 2010, "cutoff": [2009, 12]}]
    jobs += [{"kind": "hindcast", "variable": "T", "season": place["t_season"]}]
    js = run_js(place["slug"], jobs, tmp_path)
    for j, job in zip(js[:3], jobs[:3]):
        try:
            p = forecast_terciles(m, job["variable"], job["season"], job["year"],
                                  cutoff=tuple(job["cutoff"]) if job["cutoff"] else None)
        except ValueError:
            assert "error" in j
            continue
        for c in ("below", "near", "above"):
            assert j["probabilities"][c] == pytest.approx(p["probabilities"][c], abs=0.0015)
        assert j["tercile_edges"] == pytest.approx(p["tercile_edges"], abs=1e-3)
        assert j["data_cutoff"] == p["data_cutoff"]
    h = hindcasts(m, "T", place["t_season"])
    assert js[3]["n"] == h["n"] and js[3]["rpss"] == pytest.approx(h["rpss"], abs=0.01)


def test_js_spi_matches_scipy(tmp_path):
    m = monthly("cape-town")
    js = run_js("cape-town", [{"kind": "gamma", "season": "AMJJAS"}], tmp_path)[0]
    tot = C.seasonal(m, m["prec_mm"], "AMJJAS", "sum").dropna()
    spi, fit = C.spi_series(tot)
    assert js["a"] == pytest.approx(fit.a, rel=1e-4) and js["scale"] == pytest.approx(fit.scale, rel=1e-4)
    assert js["spi"] == pytest.approx(list(spi), abs=1e-4)
    assert js["inv"] == pytest.approx(float(fit.inverse(0.7)), rel=1e-4)
