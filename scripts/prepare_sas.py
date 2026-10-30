"""Turn the NISR SAS 2026 Excel tables into tidy CSVs used by the app.

Run from the repo root:  python scripts/prepare_sas.py
Input : data/raw/Tables_2026_Season_A.xlsx, data/raw/Tables_2026_Season_B.xlsx
Output: data/sas_sowing_by_district.csv, data/sas_sowing_by_crop.csv, data/sas_yield_by_district.csv

Source: National Institute of Statistics of Rwanda (NISR), Seasonal Agricultural Survey 2026.
"""
import re
from pathlib import Path
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data")

# Representative mid-point date of each sowing period (reference year 2001; the
# "Before January" period of Season B is placed in Dec 2000). These are an
# approximation used only to draw the survey bars on a date axis.
MID = {
    "A": ["2001-08-25", "2001-09-08", "2001-09-23", "2001-10-08", "2001-10-24", "2001-11-10"],
    "B": ["2000-12-20", "2001-01-08", "2001-01-24", "2001-02-08", "2001-02-22", "2001-03-08",
          "2001-03-24", "2001-04-10"],
}
LABEL = {
    "A": ["Before 1 Sep", "1-15 Sep", "16-30 Sep", "1-15 Oct", "16-31 Oct", "After 31 Oct"],
    "B": ["Before Jan", "1-15 Jan", "16-31 Jan", "1-15 Feb", "16-28 Feb", "1-15 Mar",
          "16-31 Mar", "After 31 Mar"],
}
CROPS_YIELD = {"Maize": "Maize", "Bean": "Bean", "Irish potato": "Irish potato"}


def sheet_by_title(xl, pattern):
    for name, d in xl.items():
        d = d.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        title = " ".join(str(v) for v in d.iloc[0].dropna().tolist())
        if re.search(pattern, title, re.I):
            return d
    raise ValueError(f"No sheet matching {pattern}")


def sowing(d, season, key):
    n = len(LABEL[season])
    body = d.iloc[2:].copy()
    body = body[body.iloc[:, 0].notna() & ~body.iloc[:, 0].astype(str).str.startswith("Source")]
    rows = []
    for _, r in body.iterrows():
        name = str(r.iloc[0]).strip()
        vals = pd.to_numeric(r.iloc[1:], errors="coerce").tolist()
        for i in range(n):
            rows.append({"season": season, key: name, "period_order": i, "period": LABEL[season][i],
                         "mid_date": MID[season][i], "pct": vals[i]})
        rows.append({"season": season, key: name, "period_order": n, "period": "Other season",
                     "mid_date": None, "pct": vals[n]})
    return pd.DataFrame(rows)


def yields(d, season):
    hdr = list(d.iloc[1])
    body = d.iloc[2:].copy()
    body.columns = [str(h).strip() for h in hdr]
    body = body[body["District"].notna()]
    out = []
    for _, r in body.iterrows():
        for c in CROPS_YIELD:
            if c in body.columns:
                out.append({"season": season, "district": str(r["District"]).strip(), "crop": c,
                            "yield_kg_ha": pd.to_numeric(r[c], errors="coerce")})
    return pd.DataFrame(out)


def main():
    sd, sc, yd = [], [], []
    for season in ("A", "B"):
        xl = pd.read_excel(RAW / f"Tables_2026_Season_{season}.xlsx", sheet_name=None, header=None)
        sd.append(sowing(sheet_by_title(xl, r"sowing dates? by district"), season, "district"))
        sc.append(sowing(sheet_by_title(xl, r"sowing dates? by crops?"), season, "crop"))
        yd.append(yields(sheet_by_title(xl, r"^Table \d+:\s+Season . 2026_Average yield by crop type and district"
                                        if season == "A" else
                                        r"^Table \d+:\s+Season B 2026_Average yield by crop type and district"),
                         season))
    pd.concat(sd).to_csv(OUT / "sas_sowing_by_district.csv", index=False)
    pd.concat(sc).to_csv(OUT / "sas_sowing_by_crop.csv", index=False)
    pd.concat(yd).to_csv(OUT / "sas_yield_by_district.csv", index=False)
    print("Wrote 3 CSVs to", OUT)


if __name__ == "__main__":
    main()
