"""Issue locked seasonal forecasts.

    python forecast.py issue                      # the next season, every place
    python forecast.py issue --season DJF --year 2027
    python forecast.py issue --within-days 25     # only if the next season starts soon (used by CI)

A forecast file is never overwritten, and cannot be issued once its season has
started. Commit the new files straight away: the commit time is the lock.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from build import ROOT, read_places
from cassandra import climate as C
from cassandra import forecasts as F
from cassandra.data import load_power


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    iss = sub.add_parser("issue")
    iss.add_argument("--places", default="places.csv")
    iss.add_argument("--raw", default="data/raw")
    iss.add_argument("--out", default="forecasts")
    iss.add_argument("--season", choices=F.STANDARD_SEASONS)
    iss.add_argument("--year", type=int)
    iss.add_argument("--within-days", type=int, default=None,
                     help="do nothing unless the season starts within this many days")
    args = ap.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    season, year = (args.season, args.year) if args.season and args.year else F.next_season(today)
    sy, sm = C.season_start(season, year)
    days = (date(sy, sm, 1) - today).days
    print(f"Next season: {season} {year} ({C.season_label(season)}), starts {sy}-{sm:02d}-01, in {days} days")
    if args.within_days is not None and days > args.within_days:
        print("Not within the issuing window; nothing to do.")
        return
    for place in read_places(ROOT / args.places):
        m = load_power(place["slug"], place["lat"], place["lon"], ROOT / args.raw)
        path = F.issue(place, m, season, year, ROOT / args.out)
        print(f"  {place['slug']:14s} {'written ' + str(Path(path).relative_to(ROOT)) if path else 'already locked, left unchanged'}")


if __name__ == "__main__":
    main()
