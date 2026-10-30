"""Download daily rainfall for the 30 districts from Open-Meteo (free, no API key).

Run from the repo root:  python scripts/fetch_rainfall.py
Output: data/rainfall_daily.csv.gz  (district, date, precip_mm, source)

 - source=archive  : ERA5 reanalysis, ~25 km grid (archive-api.open-meteo.com), 1991 -> ~6 days ago
 - source=forecast : last 7 days + next 16 days from the forecast API (api.open-meteo.com)
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
START_YEAR = 1991
PAUSE_S = 15           # seconds between districts (keeps us well inside the per-minute limit)
RAW = Path("data/raw_rain")
OUT = Path("data/rainfall_daily.csv.gz")


def get(url, params, tries=5):
    for k in range(tries):
        r = requests.get(url, params=params, timeout=90)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            wait = 65 * (k + 1)
            print(f"  rate limited, waiting {wait}s ...")
            time.sleep(wait)
            continue
        r.raise_for_status()
    raise RuntimeError("Open-Meteo kept refusing the request; try again later (limits reset hourly/daily).")


def to_frame(js, district, source):
    d = js["daily"]
    return pd.DataFrame({"district": district, "date": d["time"], "precip_mm": d["precipitation_sum"],
                         "source": source})


def main():
    districts = pd.read_csv("data/districts.csv")
    RAW.mkdir(parents=True, exist_ok=True)
    end_archive = (date.today() - timedelta(days=6)).isoformat()
    for i, row in districts.iterrows():
        f = RAW / f"{row.district}.csv"
        if f.exists():
            print(f"[{i + 1}/30] {row.district}: already downloaded")
            continue
        print(f"[{i + 1}/30] {row.district}: downloading ...")
        base = {"latitude": row.lat, "longitude": row.lon, "daily": "precipitation_sum",
                "timezone": "Africa/Kigali"}
        # models=era5 pins ONE reanalysis for the whole 1991+ history; Open-Meteo's default blends models
        # (a 9 km model from 2017), which can create artificial shifts in long rainfall records.
        arch = get(ARCHIVE, {**base, "models": "era5", "start_date": f"{START_YEAR}-01-01",
                             "end_date": end_archive})
        fore = get(FORECAST, {**base, "past_days": 7, "forecast_days": 16})
        a = to_frame(arch, row.district, "archive")
        fo = to_frame(fore, row.district, "forecast")
        fo = fo[fo["date"] > a["date"].max()]       # keep only dates the archive does not cover
        pd.concat([a, fo]).to_csv(f, index=False)
        time.sleep(PAUSE_S)
    df = pd.concat([pd.read_csv(RAW / f"{d}.csv") for d in districts.district])
    df["precip_mm"] = df["precip_mm"].round(2)
    df.to_csv(OUT, index=False, compression="gzip")
    print("Wrote", OUT, len(df), "rows; dates", df["date"].min(), "->", df["date"].max())


if __name__ == "__main__":
    sys.exit(main())
