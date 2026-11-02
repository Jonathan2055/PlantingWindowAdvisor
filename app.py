"""Planting Window Advisor - NISR 2026 Big Data Hackathon.

Combines NISR Seasonal Agricultural Survey (SAS) 2026 sowing dates and yields with historical and recent
rainfall (Open-Meteo) to show when the rains usually start in each district, how the current season compares,
and when planting has historically met basic rainfall conditions. Decision support, not a yield forecast.
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.planting import (ONSET_WINDOW, PLANT_WINDOW, REF_YEAR, OnsetRule, PlantRule, _ts, advice, best_window,
                          district_series, find_onset, onset_history, onset_stats, ref_date, season_status,
                          suitability)

DATA = Path("data")
RAIN_FILE = DATA / "rainfall_daily.csv.gz"
YIELD_CROP = {"Maize": "Maize", "Beans": "Bean", "Irish potato": "Irish potato"}

st.set_page_config(page_title="Planting Window Advisor - Rwanda", page_icon="🌱", layout="wide")


# data
@st.cache_data
def load_static():
    return (pd.read_csv(DATA / "districts.csv"), pd.read_csv(DATA / "crop_assumptions.csv"),
            pd.read_csv(DATA / "sas_sowing_by_district.csv"), pd.read_csv(DATA / "sas_sowing_by_crop.csv"),
            pd.read_csv(DATA / "sas_yield_by_district.csv"))


@st.cache_data
def load_rain():
    if not RAIN_FILE.exists():
        return None
    df = pd.read_csv(RAIN_FILE, parse_dates=["date"])
    return df


@st.cache_data
def series_for(_df, district):
    return district_series(_df, district)


districts, crops, sow_d, sow_c, yld = load_static()
rain = load_rain()
have_rain = rain is not None

#  sidebar
today = pd.Timestamp.today().normalize()
auto_season = "A" if today.month >= 8 else ("B" if today.month <= 4 else "A")
st.sidebar.title("Planting Window Advisor")
season = st.sidebar.radio("Season", ["A", "B"], index=0 if auto_season == "A" else 1, horizontal=True,
                          help="Season A: Sep-Feb. Season B: Mar-Jun (planting often starts Jan-Feb).")
district = st.sidebar.selectbox("District", districts["district"].tolist(),
                                index=districts["district"].tolist().index("Kayonza"))
crop = st.sidebar.selectbox("Crop", crops["crop"].tolist())
crow = crops[crops["crop"] == crop].iloc[0]
variety = st.sidebar.radio("Variety", ["Standard cycle", "Short cycle"], horizontal=True)
as_of = pd.Timestamp(st.sidebar.date_input("As-of date", value=today.date(),
                                           help="Change this to replay a past season (e.g. for the demo)."))
n_years = st.sidebar.slider("Years of history used", 10, 35, 30)

with st.sidebar.expander("Advanced: thresholds & assumptions"):
    st.caption("These are adjustable assumptions, not official values. Verify with RAB / Meteo Rwanda.")
    wet_mm = st.number_input("Onset: rain in 3 days (mm)", 10, 60, 20)
    dry_spell_max = st.number_input("Onset: max dry spell in next 21 days", 3, 14, 7)
    est_mm = st.number_input("Establishment: rain in first 14 days (mm)", 5, 80, 20)
    dry_max = st.number_input("Max dry spell in first 21 days", 3, 21, 10)
    cycle_days = st.number_input("Crop cycle (days)", 50, 200,
                                 int(crow["cycle_days_short"] if variety == "Short cycle" else crow["cycle_days_standard"]))
    cycle_mm = st.number_input("Min rain over cycle (mm)", 100, 1000, int(crow["min_cycle_rain_mm"]))

onset_rule = OnsetRule(wet_mm=float(wet_mm), dry_spell_max=int(dry_spell_max))
plant_rule = PlantRule(est_mm=float(est_mm), dry_max=int(dry_max), cycle_days=int(cycle_days), cycle_mm=float(cycle_mm))

st.sidebar.caption("Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). "
                   "Survey data: NISR, Seasonal Agricultural Survey 2026.")

st.title(f"When should {district} farmers plant {crop.lower()}?")
st.caption("Decision support from historical rainfall patterns and NISR survey data. It is not a forecast of "
           "yield. Check local advice from your agronomist, cooperative or Meteo Rwanda.")

tab_now, tab_win, tab_map, tab_sas, tab_method = st.tabs(
    ["Advice now", "Planting window", "District map", "Farmer's practice (SAS)", "Method & limits"])

#  shared computations
if have_rain:
    s_full = series_for(rain, district)
    s_asof = s_full.loc[:as_of]
    past_years = [y for y in sorted(set(s_full.index.year)) if y < as_of.year][-n_years:]
    hist = onset_history(s_full, season, onset_rule, years=past_years)
    stats = onset_stats(hist) if len(hist) else None
    curve = suitability(s_full, season, plant_rule, years=past_years)
    win = best_window(curve)
    info = season_status(s_asof, season, as_of, stats, onset_rule)


def show(fig):
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:                       # older Streamlit versions
        st.plotly_chart(fig, use_container_width=True)


def need_rain():
    st.warning("Rainfall data not found. Run `python scripts/fetch_rainfall.py` once (takes in about 10 minutes), then "
               "restart the app. See the README.")


#  tab 1: advice now
with tab_now:
    if not have_rain:
        need_rain()
    elif stats is None:
        st.info("Not enough history to compute onset dates for this district and settings.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Usual rains start (median)", f"{stats['median']:%d %b}")
        c2.metric("Usual range (10th-90th pct)", f"{stats['p10']:%d %b} - {stats['p90']:%d %b}")
        res = info["result"]
        c3.metric("This season", {"confirmed": f"Onset {res.date:%d %b}" if res.date is not None else "",
                                  "provisional": f"Possible onset {res.date:%d %b}" if res.date is not None else "",
                                  "none_yet": "No onset yet", "no_onset": "None found"}[res.status])
        live = as_of >= today - pd.Timedelta(days=2)          # forecast only makes sense for the present
        fut = s_full.loc[as_of + pd.Timedelta(days=1):as_of + pd.Timedelta(days=7)]
        c4.metric("Forecast rain, next 7 days", f"{fut.sum():.0f} mm" if (live and len(fut) == 7) else "n/a")
        kind, msg = advice(info, stats, crop, win)
        getattr(st, {"warning": "warning", "success": "success", "info": "info"}[kind])(msg)

        start_md = ONSET_WINDOW[season][0]
        horizon = 150
        cum = {}
        for y in past_years:
            seg = s_full.loc[_ts(y, start_md):_ts(y, start_md) + pd.Timedelta(days=horizon - 1)]
            if len(seg) == horizon:
                cum[y] = seg.cumsum().values
        fig = go.Figure()
        if cum:
            mat = pd.DataFrame(cum)
            x = pd.Timestamp(REF_YEAR, *start_md) + pd.to_timedelta(range(horizon), unit="D")
            fig.add_trace(go.Scatter(x=x, y=mat.quantile(0.9, axis=1), line=dict(width=0), showlegend=False))
            fig.add_trace(go.Scatter(x=x, y=mat.quantile(0.1, axis=1), fill="tonexty", line=dict(width=0),
                                     name="Past years (10th-90th pct)", fillcolor="rgba(120,160,120,0.30)"))
            fig.add_trace(go.Scatter(x=x, y=mat.median(axis=1), name="Past years (median)",
                                     line=dict(color="green", width=2)))
        cs = _ts(as_of.year, start_md)
        cur = s_full.loc[cs:cs + pd.Timedelta(days=horizon - 1)]
        cur_cum = cur.cumsum()
        obs = cur_cum.loc[:as_of]
        xo = pd.Timestamp(REF_YEAR, *start_md) + (obs.index - cs)
        fig.add_trace(go.Scatter(x=xo, y=obs.values, name=f"{as_of.year} so far", line=dict(color="crimson", width=3)))
        fc = cur_cum.loc[as_of:as_of + pd.Timedelta(days=7)]
        if live and len(fc) > 1:
            fig.add_trace(go.Scatter(x=pd.Timestamp(REF_YEAR, *start_md) + (fc.index - cs), y=fc.values,
                                     name="Next 7 days (forecast)", line=dict(color="crimson", dash="dot", width=3)))
        fig.update_layout(title="Cumulative rainfall since the start of the planting window", yaxis_title="mm",
                          xaxis=dict(tickformat="%d %b"), height=420, margin=dict(t=50, b=10),
                          legend=dict(orientation="h", y=-0.15))
        show(fig)
        st.caption("Recent and forecast days come from a different weather model than the 1991+ history, so small "
                   "differences are expected.")

#  tab 2: planting window
with tab_win:
    if not have_rain:
        need_rain()
    elif curve.empty:
        st.info("Not enough data for this selection.")
    else:
        src = st.radio("Compare with what farmers did (SAS 2026)",
                       ["District (all crops)", f"National ({crop})"], horizontal=True)
        if src.startswith("District"):
            sw = sow_d[(sow_d.season == season) & (sow_d.district == district)]
        else:
            names = str(crow["sas_crops"]).split("|")
            sw = (sow_c[(sow_c.season == season) & (sow_c.crop.isin(names))]
                  .groupby(["period_order", "period", "mid_date"], dropna=False, as_index=False)["pct"].mean())
        bars = sw.dropna(subset=["mid_date"]).copy()
        bars["mid_date"] = pd.to_datetime(bars["mid_date"])
        other = sw[sw["period"] == "Other season"]["pct"].sum()

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=bars["mid_date"], y=bars["pct"], name="% of farmers' sowing (SAS)",
                             marker_color="rgba(230,170,60,0.65)", width=11 * 86400000 if season == "A" else 10 * 86400000,
                             hovertext=bars["period"]), secondary_y=True)
        fig.add_trace(go.Scatter(x=curve["date"], y=100 * curve["p_cycle_rain"], name="Enough rain over crop cycle",
                                 line=dict(color="lightskyblue", dash="dot")), secondary_y=False)
        fig.add_trace(go.Scatter(x=curve["date"], y=100 * curve["p_establish"], name="Rain to establish seedlings",
                                 line=dict(color="steelblue", dash="dot")), secondary_y=False)
        fig.add_trace(go.Scatter(x=curve["date"], y=100 * curve["p_all"], name="All conditions met",
                                 line=dict(color="darkgreen", width=4)), secondary_y=False)
        if win:
            fig.add_vrect(x0=win[0], x1=win[1], fillcolor="green", opacity=0.12, line_width=0,
                          annotation_text="best window", annotation_position="top left")
        if stats:
            fig.add_vrect(x0=stats["p10"], x1=stats["p90"], fillcolor="royalblue", opacity=0.08, line_width=0)
            fig.add_vline(x=stats["median"], line_dash="dash", line_color="royalblue",
                          annotation_text="usual rain onset", annotation_position="bottom right")
        lo = pd.Timestamp(REF_YEAR, *PLANT_WINDOW[season][0]) - pd.Timedelta(days=15)
        hi = pd.Timestamp(REF_YEAR, *PLANT_WINDOW[season][1]) + pd.Timedelta(days=10)
        fig.update_xaxes(range=[lo, hi], tickformat="%d %b")
        fig.update_yaxes(title_text="% of past years meeting rainfall conditions", range=[0, 100], secondary_y=False)
        fig.update_yaxes(title_text="% of farmers' sowing (SAS)", range=[0, max(60, bars["pct"].max() * 1.2)],
                         secondary_y=True)
        fig.update_layout(height=470, margin=dict(t=30, b=10), legend=dict(orientation="h", y=-0.2))
        show(fig)
        if win:
            st.success(f"In {int(curve['n_years'].max())} past years, planting {crop.lower()} between "
                       f"**{win[0]:%d %b} and {win[1]:%d %b}** met all three rainfall conditions in about "
                       f"**{100 * win[2]:.0f}%** of years in {district}.")
        st.caption(f"{other:.0f}% of the sowing reported in SAS falls in 'other season' and is not shown. SAS bars "
                   "sit at the mid-point of each reporting period. 'All conditions met' = enough rain to establish "
                   "seedlings, no long dry spell right after planting, and enough rain across the crop cycle. "
                   "Adjust thresholds in the sidebar.")

#  tab 3: map
with tab_map:
    if not have_rain:
        need_rain()
    else:
        metric = st.radio("Colour districts by",
                          ["This season: days later (+) or earlier (-) than usual onset", "Usual onset date (median)",
                           "Onset variability (days between 10th and 90th percentile)"], horizontal=False)

        @st.cache_data(show_spinner="Computing all districts ...")
        def all_districts(_df, season, as_of, n_years, wet, dry):
            rule = OnsetRule(wet_mm=wet, dry_spell_max=dry)
            rows = []
            for _, r in districts.iterrows():
                s = district_series(_df, r.district)
                yrs = [y for y in sorted(set(s.index.year)) if y < as_of.year][-n_years:]
                h = onset_history(s, season, rule, years=yrs)
                st_ = onset_stats(h) if len(h) else None
                if st_ is None:
                    continue
                inf = season_status(s.loc[:as_of], season, as_of, st_, rule)
                rows.append({"district": r.district, "province": r.province, "lat": r.lat, "lon": r.lon,
                             "median_doy": st_["median"].dayofyear, "median": f"{st_['median']:%d %b}",
                             "spread": (st_["p90"] - st_["p10"]).days, "status": inf["result"].status,
                             "vs_median": inf["days_vs_median"]})
            return pd.DataFrame(rows)

        m = all_districts(rain, season, as_of, n_years, float(wet_mm), int(dry_spell_max))
        label = {"confirmed": "onset confirmed", "provisional": "possible onset", "none_yet": "no onset yet",
                 "no_onset": "no onset found"}
        m["status_txt"] = m["status"].map(label)
        if metric.startswith("This season"):
            mm = m.dropna(subset=["vs_median"]).copy()
            col, scale, mid, title = "vs_median", "RdYlGn_r", 0, "Days vs usual"
            note = "For 'no onset yet' districts the value is a lower bound (days since the usual onset date)."
        elif metric.startswith("Usual"):
            mm, col, scale, mid, title = m, "median_doy", "Viridis", None, "Day of year"
            note = "Darker = earlier usual start of the rains."
        else:
            mm, col, scale, mid, title = m, "spread", "Oranges", None, "Spread (days)"
            note = "Higher = less predictable start of the rains."
        if mm.empty:
            st.info("No districts to show for this selection (the season may not have started yet).")
        else:
            figm = px.scatter_map(mm, lat="lat", lon="lon", color=col, hover_name="district",
                                  hover_data={"median": True, "status_txt": True, "vs_median": True, "lat": False,
                                              "lon": False, col: False},
                                  color_continuous_scale=scale, color_continuous_midpoint=mid, zoom=7.2,
                                  center={"lat": -1.95, "lon": 29.9}, map_style="open-street-map", height=560)
            figm.update_traces(marker=dict(size=20))
            figm.update_layout(margin=dict(t=0, b=0, l=0, r=0), coloraxis_colorbar=dict(title=title))
            show(figm)
            st.caption(note)

#  tab 4: SAS
with tab_sas:
    st.subheader("What the NISR survey says")
    names = str(crow["sas_crops"]).split("|")
    cs = sow_c[(sow_c.season == season) & (sow_c.crop.isin(names))]
    cutoff = 2 if season == "A" else 4
    early = cs[(cs.period_order <= cutoff) & cs.mid_date.notna()].groupby("period_order")["pct"].mean().sum()
    cutoff_txt = "30 Sep" if season == "A" else "28 Feb"
    c1, c2 = st.columns(2)
    c1.metric(f"National {crop.lower()} area sown by {cutoff_txt} (Season {season} 2026)", f"{early:.0f}%",
              help="Average over the SAS crop categories mapped to this crop.")
    ycrop = YIELD_CROP.get(crop)
    yy = yld[(yld.season == season) & (yld.crop == ycrop)]
    yd = yy[yy.district == district]["yield_kg_ha"]
    nat = yy[yy.district == "National"]["yield_kg_ha"]
    if len(yd) and len(nat):
        c2.metric(f"{district} {crop.lower()} yield, Season {season} 2026", f"{yd.iloc[0]:,.0f} kg/ha",
                  f"{yd.iloc[0] - nat.iloc[0]:+,.0f} vs national", delta_color="off")
    dist = yy[~yy.district.isin(["National", "SSF", "LSF"]) & (yy.yield_kg_ha > 0)].sort_values("yield_kg_ha")
    figy = px.bar(dist, x="district", y="yield_kg_ha", color=(dist.district == district).map({True: district, False: "Other districts"}),
                  color_discrete_map={district: "crimson", "Other districts": "lightgray"},
                  labels={"yield_kg_ha": "kg/ha", "color": ""})
    figy.update_layout(title=f"{crop} yield by district, Season {season} 2026 (SAS)", height=380, margin=dict(t=50))
    show(figy)
    st.caption("Source: NISR, Seasonal Agricultural Survey 2026 (Season A and B tables). Yield differences between "
               "districts reflect soil, altitude, varieties and practices as well as rainfall; they are not caused by "
               "planting date alone.")

#  tab 5: method
with tab_method:
    st.markdown(f"""
**Data**
- **NISR SAS 2026** (Seasons A and B): sowing-date distributions by district and by crop, and yields by district.
- **Rainfall**: Open-Meteo daily precipitation, ERA5 reanalysis (~25 km grid) from 1991 plus recent and forecast days.
  Reanalysis is a model estimate, not a rain-gauge record; it can differ from local conditions, especially in the
  highlands, and neighbouring districts may share a grid cell.

**Rainfall onset**: the first day on which the 3-day rainfall is at least {wet_mm} mm and is *not* followed by a dry
spell longer than {dry_spell_max} days within the next 21 days. A day under 1 mm counts as dry.

**Planting suitability**: for each candidate planting date and each past year we check (1) at least {est_mm} mm in the
first 14 days, (2) no dry spell longer than {dry_max} days in the first 21 days, and (3) at least {cycle_mm} mm over a
{cycle_days}-day crop cycle. The curve is the share of past years meeting these conditions.

**Limits**
- Crop cycle length and water need are assumptions, not official values; edit them in the sidebar.
- The tool describes rainfall patterns. It does not predict yield, pests, soil, or market conditions.
- Survey figures are national or district estimates, not individual farms. Large-scale farmers are about 2% of
  cultivated area, so the survey mainly describes smallholders.
- Season windows are approximations (Season A: onset search 15 Aug-30 Nov; Season B: 1 Jan-30 Apr).
""")
