# Planting Window Advisor — Rwanda

**NISR 2026 Big Data Hackathon entry.** A Streamlit app that tells a district-level user *when the rains usually start, how this season compares, and when planting a given crop has historically met basic rainfall conditions*, next to what farmers actually did according to the NISR Seasonal Agricultural Survey (SAS).

## The problem
Rwandan farmers decide when to plant and which variety to choose under rainfall that no longer follows the old calendar. In October 2026 media reported delayed rains across the country, maize planted in September struggling to germinate, and farmers asking for short-cycle varieties suited to dry spells. The SAS 2026 shows how exposed planting is: about **64% of maize area in Season A is sown by 30 September** (national, SAS 2026 Table 19), before the rains are reliably established in many districts. Existing climate services (Meteo Rwanda seasonal forecasts, PICSA training) are valuable but mostly general; this tool turns district rainfall history into crop-specific planting guidance.

## What the app shows

**Advice now** : Usual onset date (median and 10th–90th percentile) for the district, whether this season's rains have started, days later/earlier than usual, 7-day forecast rain, and a plain-language message. 
**Planting window**: For each candidate planting date, the share of past years in which rainfall conditions were met (establishment rain, no long dry spell, enough rain over the crop cycle), overlaid on the SAS distribution of when farmers actually sowed. 
**District map**: All 30 districts coloured by this season's onset lateness, usual onset date, or onset variability. 
**Farmers' practice (SAS)**: Share of crop area sown early, and district yield vs other districts (SAS 2026). 
**Method & limits**: Definitions, assumptions, caveats.

**How to interact:** choose season, district, crop and variety in the sidebar; change the *As-of date* to replay a past season; open *Advanced* to change thresholds and crop assumptions.

## Data
- **NISR SAS 2026, Seasons A and B** (`data/raw/*.xlsx`): sowing dates by district and crop (Tables 16/17 Season B; 18/19 Season A), yield by district (Table 11 Season B; 13 Season A). Cleaned by `scripts/prepare_sas.py` into `data/sas_*.csv`.

- **Rainfall:** daily precipitation from [Open-Meteo](https://open-meteo.com/) (ERA5 reanalysis, ~25 km grid, from 1991 + recent and forecast days), 30 district points listed in `data/districts.csv`. Downloaded by `scripts/fetch_rainfall.py` into `data/rainfall_daily.csv.gz`.

- `data/crop_assumptions.csv`: crop cycle lengths and rainfall needs. **These are assumptions; verify with RAB/FAO and update before submitting.**

Weather data by Open-Meteo.com (CC BY 4.0, free for non-commercial use). Survey data: National Institute of Statistics of Rwanda (NISR).

## Run it
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/prepare_sas.py          
python scripts/fetch_rainfall.py       #writes to data/rainfall_daily.csv.gz
streamlit run app.py
```
The fetch script pauses between districts because Open-Meteo weights long-history requests. If it reports rate limiting, just rerun it later; finished districts are skipped.

## Deployed link
Push to a **public** GitHub repo (commit `data/rainfall_daily.csv.gz`), then deploy on [Streamlit Community Cloud](https://streamlit.io/cloud): New app → pick repo → main file `app.py`. No login is needed, so no credentials to provide.

## Method (short)
- **Rainfall onset:** first day where 3-day rain ≥ 20 mm and no dry spell longer than 7 days (days under 1 mm) in the following 21 days. Adjustable.

- **Planting suitability:** for each candidate date and past year, check ≥ 20 mm in the first 14 days, no dry spell > 10 days in the first 21 days, and enough total rain over the crop cycle. The curve is the share of years meeting all conditions. Best window = dates within 10 points of the maximum.

- The SAS sowing periods are drawn at their mid-points; "other season" sowing is excluded from the bars.

## Limitations (please read)
- Describes rainfall *patterns*; it does not predict yield, pests, soil, or markets. Associations in the SAS are not causal.

- ERA5 reanalysis is a model estimate on a ~25 km grid, so it can differ from local rain-gauge data (especially in the highlands) and neighbouring districts can fall in the same grid cell and show near-identical rainfall. We pin `models=era5` so the 1991+ history is consistent. Recent/forecast days come from a different model than the 1991+ history.

- Crop cycle and water-need values are placeholders until validated.

- District coordinates are approximate centre points (30 points; the grid resolution is coarser than the error).

- Large-scale farmers are ~2% of cultivated area in SAS, so the survey mostly describes smallholders.

## Possible next steps
Kinyarwanda interface, sector-level rainfall, validation against Meteo Rwanda station data, variety recommendations from RAB, linking onset timing to SAS yields across more seasons.

## Repository layout
```
app.py                       Streamlit app
src/planting.py              onset, suitability, advice logic
scripts/prepare_sas.py       SAS Excel -> tidy CSV
scripts/fetch_rainfall.py    Open-Meteo download
data/                        districts, crop assumptions, SAS CSVs, rainfall (after fetch), raw Excel
```

## Submission notes
Entering the competition assigns IP rights in the submitted work to NISR (per the hackathon rules). Declare that all sources are acknowledged: NISR SAS 2026, Open-Meteo, and any articles you cite.
# nisr-planting-window-advisor
