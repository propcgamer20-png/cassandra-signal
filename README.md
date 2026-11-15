# Cassandra Signal

**Is the climate really changing where you live, or was that hot summer or dry year just natural variation?**

Cassandra Signal puts each place's weather record on trial. It builds 1,000 imaginary histories of what the record
could have looked like through natural ups and downs alone, and asks whether the real record stands out from all of
them. Then it keeps an honest public track record: it reruns the test on past droughts and heatwaves using only the
data available beforehand, and it locks in seasonal forecasts before each season starts.

In Greek myth, Cassandra gave true warnings that nobody believed. This project tries to make warnings believable by
putting the evidence on trial and publishing predictions before the outcome is known.

- **Live site:** https://cassandra-signal-climate.vercel.app/ (mirror: https://propcgamer20-png.github.io/cassandra-signal/)
- **Check any place yourself (live):** https://cassandra-signal-climate.vercel.app/check/
- **Demo video (30 s):** [demo/cassandra-signal-demo.mp4](demo/cassandra-signal-demo.mp4)
- Built for the NASA Space Apps Challenge. Not affiliated with or endorsed by NASA.

## Current results

| Place | Temperature | Rain | Backtests: would the signal have warned? |
|---|---|---|---|
| Mumbai, India | Mar-May: no alibi (+0.25 °C/decade) | Jun-Sep: probably real (+10.2 points of normal/decade) | 2009 monsoon failure; Mumbai cut water supply: no (barely shows in the data) |
| Latur (Marathwada), India | Annual: not yet (+0.08 °C/decade) | Jun-Sep: not yet (−1.1 points of normal/decade) | 2015 monsoon, before the 2016 Latur water-train crisis: no |
| Cape Town water supply, South Africa | Dec-Feb: not yet (+0.12 °C/decade) | Apr-Sep: not yet (+0.1 points of normal/decade) | 'Day Zero' water crisis, worst in mid-2017 to mid-2018: no |
| Fresno, California, USA | Annual: very unlikely natural (+0.35 °C/decade) | Nov-Mar: not yet (−2.8 points of normal/decade) | 2011-2017 California drought (winter 2013-14): no |
| São Paulo, Brazil | Annual: no alibi (+0.39 °C/decade) | Annual: no alibi (−9.7 points of normal/decade) | São Paulo water crisis, 2014: **warned** |
| Sydney, Australia | Annual: very unlikely natural (+0.31 °C/decade) | Annual: not yet (−5.1 points of normal/decade) | Eastern Australia drought, 2017-2019: no |
| Nairobi, Kenya | Annual: no alibi (+0.26 °C/decade) | Oct-Dec: not yet (−6.1 points of normal/decade) | 2020-2023 Horn of Africa drought (failed Oct-Dec 2021 rains): no |
| London, United Kingdom | Annual: no alibi (+0.39 °C/decade) | Jun-Aug: not yet (+2.1 points of normal/decade) | 2022 UK heatwave, first 40 °C on record: no; 2022 European drought: no |
| Paris, France | Jun-Aug: very unlikely natural (+0.49 °C/decade) | Jun-Aug: not yet (+0.6 points of normal/decade) | 2003 European heat wave: no; 2022 European drought: no |
| Sacramento, California, USA | Jun-Aug: not yet (+0.13 °C/decade) | Nov-Mar: not yet (−3.2 points of normal/decade) | 2011-2017 California drought (winter 2013-14): no |
| Austin, Texas, USA | Jun-Aug: probably real (+0.34 °C/decade) | Annual: not yet (−3.6 points of normal/decade) | 2011 Texas heat wave and drought: no; 2011 Texas drought: no |
| Garissa, Kenya | Annual: probably real (+0.21 °C/decade) | Oct-Dec: not yet (−1.2 points of normal/decade) | 2011 East Africa drought (failed 2011 long rains): no; 2020-2023 Horn of Africa drought (failed Oct-Dec 2021 rains): no (barely shows in the data) |
| Niamey, Niger | Mar-May: no alibi (+0.39 °C/decade) | Jul-Sep: very unlikely natural (+7.2 points of normal/decade) | Sahel heatwave, late March to early April 2024: **warned** |
| Wagga Wagga, Australia | Dec-Feb: not yet (+0.29 °C/decade) | Annual: not yet (−3.7 points of normal/decade) | Millennium drought: 2006, driest year on record for much of Australia: no; Black Summer heat, Dec 2019 to Feb 2020: **warned** |

Results as of the data cut-off of September 2026. The site is rebuilt from the data, so it is the source of truth;
this table is a snapshot. The first eight places are the ones in our demo video. Most backtests say "no": a 20–30 year record is often too short to separate a change from
natural variation before the event, and we report that rather than hide it.

**Is the test honest?** On 1,000 made-up 45-year series with no trend at all, the method flagged 5.6% (white
noise), 4.8% (AR(1), φ = 0.3), 6.0% (AR(1), φ = 0.6) and 1.5% (skewed, rain-like noise) at p < 0.05. A fair test
should flag about 5%. See [the method page](https://cassandra-signal-climate.vercel.app/method/#false-alarms).

## Use it yourself

The [live checker](https://cassandra-signal-climate.vercel.app/check/) runs the whole trial in your browser for any
point on Earth: search a place, click the map or use your location, choose temperature or rain and a season, and
press *Put it on trial*. Your browser fetches the NASA POWER record directly and runs the same method as the cards
(in [cassandra/web/engine.js](cassandra/web/engine.js), in a background worker). You can also:

- **backtest**: tick "pretend it is the end of …" and drag the year. Everything is rebuilt from the shorter record,
  the chart shows what happened next, and the forecast for the following season is scored against reality;
- **check the checker**: run 200 fake records with that place's own natural variability and no trend (a fair test
  flags about 5%), and 200 with a real trend the size of the measured one (how often a change like it is caught);
- **share or keep** the result: every result has a link that reproduces it exactly, plus JSON and CSV downloads.

Every place card and every backtest has a button that opens the checker with its settings filled in.
`tests/test_engine_js.py` runs the JavaScript engine under Node and checks it against the Python pipeline for all
places: identical trends, anomalies, noise fits, SPI, forecasts and hindcast skill, and p-values within sampling noise
(the two use different random number generators).

## The method in plain words

1. **Prepare the record.** Download monthly temperature (T2M) and rain (PRECTOTCORR) for the place from NASA POWER,
   1981 to the latest month. Temperature becomes an anomaly: each month minus that month's 1981–2010 average, then
   averaged over the season being judged. Rain becomes a seasonal total, then a standardised precipitation index
   (SPI, from a gamma distribution fitted to 1981–2010), and is shown as percent of normal.
2. **Measure the trend.** Sen's slope: the median of the slopes between every pair of years, which one freak year
   can't drag around. We also report the last 10 years minus the first 20.
3. **Make 1,000 imaginary histories.** Remove the trend line; treat what is left as natural variability; fit an
   AR(1) model to it (each year partly remembers the last); generate 1,000 trend-free series of the same length with
   a fixed, recorded seed. Short records make the fitted model too calm, so we correct its memory and variance for
   record length and let each history draw its own parameters from their uncertainty. Robustness checks: ARMA(p, q)
   up to order 2 chosen by AIC, and IAAFT surrogates.
4. **Give the verdict.** Count the imaginary histories whose trend is at least as big as the real one, in either
   direction: p = (count + 1) / 1,001. Beyond all 1,000: *natural variation has no alibi*. Beyond 990: *very unlikely
   to be natural variation alone*. Beyond 950: *probably a real change*. Otherwise: *not yet distinguishable from
   natural variation*.
5. **Check the checker.** Run steps 1–4 on thousands of made-up trend-free series. About 5% should be flagged.
6. **Backtest.** For documented droughts and heatwaves ([events.csv](events.csv)), rerun everything with the data cut
   off before the event, baseline included. A test proves no later data are used. We also check whether the event
   even shows in the POWER data at that point.
7. **Lock forecasts.** Before each season, write `forecasts/{place}/{year}-{season}.json` with the chances of a
   below-, near- or above-normal season, commit it, and show the commit and SHA-256 on the card. Score it after the
   season with the ranked probability score and Brier score against a 33/33/33 baseline, misses included.

## Run it

Python 3.11 or newer.

```bash
pip install -r requirements.txt
python build.py --places places.csv          # builds site/ from the cached data in data/raw/
python build.py --places places.csv --refresh  # downloads fresh NASA data first
python -m pytest -q                          # tests: anomaly maths, p-value, no future data, false alarms, forecasts, JS = Python
python forecast.py issue                     # lock forecasts for the next season (never overwrites)
python demo/make_video.py                    # needs: pip install imageio-ffmpeg
```

Open `site/index.html` in a browser. The first build runs the false-alarm check (about 2 minutes); the result is
cached in `data/falsealarm.json` and recomputed whenever the statistics code changes.

### Add a place

Add a row to [places.csv](places.csv):

| column | meaning |
|---|---|
| `slug` | short name used in the URL, e.g. `lima` |
| `name`, `lat`, `lon` | place name and coordinates (decimal degrees) |
| `t_season`, `p_season` | season to judge for temperature and rain: month initials (`JJA`, `DJF`, `OND`, `AMJJAS`) or `ANN` |
| `primary` | `T` or `P`: which variable leads the card |
| `notes` | one or two sentences shown on the page |

Optionally add documented events to [events.csv](events.csv) (`kind` is `heat`, `drought`, `flood` or `cold`, with a
source link). Then run `python build.py --places places.csv` and commit `data/raw/` so the build stays reproducible.

### Deployment

[.github/workflows/site.yml](.github/workflows/site.yml) runs the tests, builds the site and deploys it on every
push: to GitHub Pages directly, and to Vercel by pushing the finished site to the `vercel-site` branch, which is the
Vercel project's production branch ([vercel.json](vercel.json) turns off Vercel deployments of `main`). The site is
always built by the Action, because the forecast proof needs the full git history, which Vercel's own builds don't
have. On the 10th of each month it also refreshes the NASA data, locks the next season's forecasts when
the season starts within 25 days, commits them, and scores any finished seasons. No server, no login, no tracking.

## Data and citations

- **NASA POWER** (Prediction Of Worldwide Energy Resources), NASA Langley Research Center. Monthly point API,
  community AG, parameters T2M and PRECTOTCORR: https://power.larc.nasa.gov/ . Raw responses are cached unchanged in
  `data/raw/`.
- **GISTEMP Team**, GISS Surface Temperature Analysis (GISTEMP), version 4. NASA Goddard Institute for Space Studies:
  https://data.giss.nasa.gov/gistemp/ . Lenssen, N., G. Schmidt, J. Hansen, M. Menne, A. Persin, R. Ruedy and
  D. Zyss (2019), Improvements in the GISTEMP uncertainty model, *J. Geophys. Res. Atmos.*, 124, 6307–6326.
- Event descriptions link to their sources in [events.csv](events.csv).

No NASA logos or branding are used.

## Limitations

- **Short records.** POWER starts in 1981, so each test has about 45 seasons. In our check, a trend of a quarter of a
  standard deviation per decade was caught only 30% of the time; half a standard deviation, 78%. "Not yet" often
  means "not enough data yet", not "no change".
- **Not a weather station.** POWER is a reanalysis and satellite-based estimate on a grid of roughly half a degree.
  The cell over central Cape Town shows no 2017 drought at all, so that card uses the Theewaterskloof Dam catchment
  that actually ran dry. Some backtests are marked "barely shows in this dataset" for the same reason.
- **Signal is not cause.** A significant trend shows a change beyond natural variation as we modelled it. On its own
  it does not prove what caused it.
- **Rain is noisier than temperature**, so expect more "not yet" verdicts for rain.
- **The noise model is a model.** Very slow natural swings (multi-decade ocean cycles) may be longer than the record
  and are not fully represented.
- **Many tests.** With 28 series, one or two could be amber by chance alone.
- **Forecasts are simple** (climatology shifted along the trend). Hindcast skill is positive where there is a strong
  trend and about zero or slightly negative where there isn't; the cards show both.

## AI use

As required by the NASA Space Apps Challenge rules, we disclose AI use. The project idea, the method and its choices,
and the review of the results are the team's. An AI coding assistant (a large language model) wrote most of the code
(`cassandra/` including the browser checker in `cassandra/web/`, `build.py`, `forecast.py`, `demo/make_video.py`), the tests, the GitHub Actions workflow, this README
and the wording of the website, working from the team's written brief. The team ran the pipeline, read the outputs and
checked them against the brief. The charts, share cards and demo video are drawn by our code from NASA data; no image
or video in this project was made by an image- or video-generating AI. The same note appears in the footer of every
page and on every card.

## Licence

Code: MIT (see [LICENSE](LICENSE)). NASA data are used under NASA's open data policy.
