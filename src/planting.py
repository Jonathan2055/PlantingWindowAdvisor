"""Rainfall-onset and planting-suitability logic (pure functions, no Streamlit).

Everything here describes HISTORICAL RAINFALL PATTERNS. It is decision support, not a yield forecast.
All thresholds are parameters so they can be adjusted (and challenged) in the app.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Window in which we look for the start of the rains / candidate planting dates (month, day).
ONSET_WINDOW = {"A": ((8, 15), (11, 30)), "B": ((1, 1), (4, 30))}
PLANT_WINDOW = {"A": ((8, 15), (11, 30)), "B": ((1, 1), (4, 15))}
REF_YEAR = 2001  # non-leap reference year used to compare dates across years


@dataclass
class OnsetRule:
    wet_mm: float = 20.0       # rain needed over n_days to trigger an onset
    n_days: int = 3
    dry_day_mm: float = 1.0    # a day with less than this is "dry"
    dry_spell_max: int = 7     # longest tolerated dry spell after the trigger ...
    lookahead: int = 21        # ... within this many days


@dataclass
class PlantRule:
    est_days: int = 14         # establishment period after planting
    est_mm: float = 20.0       # minimum rain in the establishment period
    dry_window: int = 21
    dry_max: int = 10          # longest tolerated dry spell in dry_window
    dry_day_mm: float = 1.0
    cycle_mm: float = 450.0    # minimum total rain over the crop cycle
    cycle_days: int = 120


@dataclass
class OnsetResult:
    date: pd.Timestamp | None
    status: str                # confirmed | provisional | none_yet | no_onset


def _ts(year, md):
    m, d = md
    return pd.Timestamp(year, m, min(d, 28) if m == 2 else d)


def ref_date(ts):
    """Map a date to the reference year so different years can be compared on one axis."""
    return pd.Timestamp(REF_YEAR, ts.month, min(ts.day, 28) if ts.month == 2 else ts.day)


def longest_run(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def district_series(df, district):
    s = df.loc[df["district"] == district].set_index("date")["precip_mm"].sort_index()
    s = s[~s.index.duplicated(keep="first")]
    return s.asfreq("D").fillna(0.0)


def find_onset(s, year, season, rule=OnsetRule()):
    """First day whose n-day rainfall >= wet_mm and that is not followed by a long dry spell."""
    start, end = _ts(year, ONSET_WINDOW[season][0]), _ts(year, ONSET_WINDOW[season][1])
    last = s.index.max()
    if last < start:
        return OnsetResult(None, "none_yet")
    r = s.loc[start:min(end + pd.Timedelta(days=rule.n_days), last)]
    v = r.values
    for i in range(len(v) - rule.n_days + 1):
        day = r.index[i]
        if day > end:
            break
        if v[i:i + rule.n_days].sum() >= rule.wet_mm:
            fut = v[i + rule.n_days:i + rule.n_days + rule.lookahead]
            if len(fut) < rule.lookahead:           # not enough days yet to confirm
                return OnsetResult(day, "provisional")
            if longest_run(fut < rule.dry_day_mm) <= rule.dry_spell_max:
                return OnsetResult(day, "confirmed")
    return OnsetResult(None, "none_yet" if last < end else "no_onset")


def onset_history(s, season, rule=OnsetRule(), years=None):
    """Onset date (reference-year) for each complete past year; NaT when no onset was found."""
    last = s.index.max()
    rows = []
    for y in years if years is not None else sorted(set(s.index.year)):
        if _ts(y, ONSET_WINDOW[season][1]) + pd.Timedelta(days=rule.lookahead) > last:
            continue                                 # season not complete in the data
        res = find_onset(s, y, season, rule)
        rows.append({"year": y, "onset": res.date, "onset_ref": ref_date(res.date) if res.date is not None else pd.NaT})
    return pd.DataFrame(rows)


def onset_stats(hist):
    o = hist["onset_ref"].dropna()
    if o.empty:
        return None
    doy = o.dt.dayofyear
    q = lambda p: pd.Timestamp(REF_YEAR, 1, 1) + pd.Timedelta(days=int(round(np.percentile(doy, p))) - 1)
    return {"median": q(50), "p10": q(10), "p90": q(90), "n_years": len(hist),
            "pct_no_onset": 100 * (1 - len(o) / len(hist))}


def suitability(s, season, rule=PlantRule(), step_days=5, years=None):
    """For each candidate planting date: share of past years in which the rainfall conditions were met."""
    last = s.index.max()
    yrs = years if years is not None else sorted(set(s.index.year))
    start_md, end_md = PLANT_WINDOW[season]
    cands = pd.date_range(_ts(REF_YEAR, start_md), _ts(REF_YEAR, end_md), freq=f"{step_days}D")
    out = []
    for c in cands:
        est = dry = cyc = allok = n = 0
        for y in yrs:
            d0 = _ts(y, (c.month, c.day))
            if d0 + pd.Timedelta(days=rule.cycle_days) > last or d0 < s.index.min():
                continue
            n += 1
            e_ok = s.loc[d0:d0 + pd.Timedelta(days=rule.est_days - 1)].sum() >= rule.est_mm
            seg = s.loc[d0:d0 + pd.Timedelta(days=rule.dry_window - 1)].values
            d_ok = longest_run(seg < rule.dry_day_mm) <= rule.dry_max
            c_ok = s.loc[d0:d0 + pd.Timedelta(days=rule.cycle_days - 1)].sum() >= rule.cycle_mm
            est += e_ok; dry += d_ok; cyc += c_ok; allok += (e_ok and d_ok and c_ok)
        if n:
            out.append({"date": c, "p_establish": est / n, "p_no_long_dry": dry / n,
                        "p_cycle_rain": cyc / n, "p_all": allok / n, "n_years": n})
    return pd.DataFrame(out)


def best_window(curve, tol=0.10):
    """Contiguous run of candidate dates within `tol` of the best success share."""
    if curve.empty:
        return None
    best = curve["p_all"].max()
    ok = (curve["p_all"] >= best - tol).values
    i = int(np.argmax(curve["p_all"].values))
    lo = hi = i
    while lo > 0 and ok[lo - 1]:
        lo -= 1
    while hi < len(ok) - 1 and ok[hi + 1]:
        hi += 1
    return curve["date"].iloc[lo], curve["date"].iloc[hi], float(best)


def season_status(s, season, today, stats, rule=OnsetRule()):
    """Where is the CURRENT season compared with the historical onset distribution?"""
    year = today.year
    cur = find_onset(s, year, season, rule)
    in_window = _ts(year, ONSET_WINDOW[season][0]) <= today <= _ts(year, ONSET_WINDOW[season][1]) + pd.Timedelta(days=30)
    past = today > _ts(year, ONSET_WINDOW[season][1]) + pd.Timedelta(days=30)
    info = {"year": year, "result": cur, "in_window": in_window, "past": past, "days_vs_median": None}
    if stats is None:
        return info
    med = stats["median"].replace(year=year) if not (stats["median"].month == 2 and stats["median"].day == 29) else stats["median"]
    if cur.date is not None:
        info["days_vs_median"] = int((cur.date - med).days)
    elif in_window:
        info["days_vs_median"] = int((today - med).days)   # lower bound: no onset yet
    return info


def advice(info, stats, crop, plant_best):
    """Plain-language message. Rule-based and deliberately cautious."""
    res = info["result"]
    if info.get("past") and res.status in ("confirmed", "provisional"):
        return ("info", f"This season has already passed. In {info['year']} the rains started on {res.date:%d %b}. "
                        "Use the Planting window tab to plan the next season.")
    if not info["in_window"] and res.status in ("none_yet", "no_onset"):
        return ("info", "We are outside the usual planting window for this season. Use the Planting window tab to "
                        "plan ahead.")
    med = stats["median"].strftime("%d %b") if stats else "n/a"
    if res.status == "none_yet":
        late = info["days_vs_median"]
        if late is not None and late > 0:
            return ("warning", f"No rainfall onset detected yet. The usual onset in this district is around {med}, "
                               f"so the rains are at least {late} days late. Planting {crop.lower()} now risks poor "
                               "germination if the rain does not follow. Consider waiting for a rain event "
                               f"(~{OnsetRule().wet_mm:.0f} mm in {OnsetRule().n_days} days) or choosing a short-cycle variety.")
        return ("info", f"No onset yet, but it is still within the normal range (usual onset around {med}). "
                        "Prepare land and seed; watch for the first sustained rain.")
    if res.status == "provisional":
        return ("info", f"A rain event that looks like the onset occurred on {res.date:%d %b}, but there are not yet "
                        "enough days to confirm it was followed by no long dry spell. Plant in stages if possible.")
    if res.status == "confirmed":
        dm = info["days_vs_median"]
        rel = "" if dm is None else (f" ({abs(dm)} days {'later' if dm > 0 else 'earlier'} than the usual date)")
        extra = ""
        if plant_best:
            extra = (f" Historically, the best planting dates for {crop.lower()} here are "
                     f"{plant_best[0]:%d %b} to {plant_best[1]:%d %b}.")
        return ("success", f"Rainfall onset confirmed on {res.date:%d %b}{rel}.{extra}")
    return ("info", "No clear onset was found for this season in the data.")
