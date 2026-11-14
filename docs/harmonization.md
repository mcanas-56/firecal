# Harmonization method note (US-02)

FireCal joins two satellite fire records, MODIS (2000–present) and VIIRS (2012–present), into one monthly number per area that means the same thing before and after 2012. VIIRS sees far more hotspots than MODIS (smaller pixels, more sensitive), so joining them unadjusted creates a false jump in fire activity when VIIRS arrives. This note records every choice so it can be defended.

Code: `src/harmonize.py`. Tests: `tests/test_harmonize.py`. Rebuild: `python -m src.harmonize data/*.csv`.

## Method

1. **Match the satellites.** MODIS on Aqua and VIIRS on Suomi-NPP cross the equator around 13:30 and 01:30, so they observe the same fires at the same time of day. MODIS Terra (10:30) is left out by default; `--include-terra` adds it.
2. **Count fire cell-days, not pixels.** A VIIRS pixel is 375 m and a MODIS pixel about 1 km, so VIIRS reports one fire as many more detections. Each detection is snapped to a 0.1° grid (`--grid` changes it) and each cell counts at most once per day per sensor. One active cell on one day = one fire cell-day.
3. **Aggregate by month.** Fire cell-days are summed per area, sensor, year and month. Every month of every year with data gets a row; a month with no fires is 0. A month a sensor has no data for (for example VIIRS before 2012) is left empty, not 0.
4. **Find satellite gaps.** A satellite sometimes stops recording for days (safe mode, maintenance). A day is a gap for one sensor when it has no detections in any area it covers while the other sensor saw fires in at least one of them that day. VIIRS sees more fires than MODIS, so a whole day of MODIS fires with no VIIRS detections at all means VIIRS was off, not that the fires stopped. A day both sensors record as empty is a real quiet day, not a gap.
5. **Calibrate on the overlap.** For each area, over the months where both sensors have data, one factor is fitted: VIIRS cell-days ≈ factor × MODIS cell-days (least squares through the origin). Gap days of either sensor are left out of both sensors' counts for the fit, so an outage does not drag the factor.
6. **Build the harmonized series.** Where VIIRS exists, the harmonized value is the VIIRS count, plus MODIS × factor for any VIIRS gap days that month. Before VIIRS, it is MODIS × factor. The `source` column says which was used.

Input is the cleaned output of US-01 (`load_hotspots`): vegetation fires only (`type` 0), MODIS confidence ≥ 30, VIIRS nominal or high confidence.

## Output

`data/processed/harmonized_monthly.csv` (local only, never committed), one row per area-month:

| Column | Meaning |
|---|---|
| area, year, month | Where and when |
| modis_cell_days | MODIS Aqua fire cell-days (empty if no MODIS data) |
| viirs_cell_days | VIIRS Suomi-NPP fire cell-days (empty if no VIIRS data) |
| modis_scaled | modis_cell_days × factor |
| harmonized | The calendar value: VIIRS if present (gap days filled with MODIS × factor), else modis_scaled |
| source | `viirs`, `viirs+modis_gap_fill`, `modis_scaled` or `none` |
| factor | The area's calibration factor |
| viirs_gap_days | Days that month VIIRS was not recording (filled from MODIS) |

`modis_cell_days` and `viirs_cell_days` stay the raw counts, gaps included, so US-07's raw view shows what each satellite actually recorded.

The raw per-sensor columns let US-07 show raw vs harmonized.

## Satellite gaps in the practice set

| Sensor | Days not recording | What happened |
|---|---|---|
| VIIRS Suomi-NPP | 27 Jul – 10 Aug 2022 (15 days), 26 Jul 2023 | Suomi NPP was offline: MODIS saw fires in Canada and Argentina, VIIRS recorded nothing in either |
| MODIS Aqua | 31 Mar – 16 Apr 2022 (17 days), 23 Mar and 1 May 2022 | MODIS Aqua recorded nothing while VIIRS saw fires |

Without step 4 the VIIRS outage made July and August 2022 look up to about 20% quieter than they were (Argentina, July 2022: 3,550 recorded vs 4,409 filled), and both outages pulled the factor fit. Filling adds, for example, 1,476 cell-days to Argentina's August 2022 (9,268 → 10,744) and 310 to Canada's (2,879 → 3,189). The daily calendar on the page shows gap days as "no data".

## Results on the practice set (2022–2023, 24 overlap months per area)

Gap days left out of the fit (step 5):

| Area | Factor | R² | Pearson r | Median \|% diff\| | Activity-weighted \|% diff\| | Scaled MODIS total vs VIIRS |
|---|---|---|---|---|---|---|
| Argentina | 2.95 | 0.94 | 0.99 | 13.6% | 12.8% | −6% |
| Canada | 2.32 | 0.99 | 0.99 | 50.9% | 13.6% | −7% |

Before the gap handling (2026-11-14 review): Argentina 2.86, R² 0.90, r 0.97, median 18.6%; Canada 2.30, R² 0.99, r 0.99, median 51.2%. Leaving gaps out mainly helps Argentina, whose fire season overlaps the VIIRS outage.

The charter's target (harmonized MODIS and VIIRS agree with r ≥ 0.8) is met in both areas. With Terra included, the factors drop to 2.16 (Argentina) and 1.69 (Canada), with similar fit.

**Where it fits and where it doesn't.** The factor is driven by the big fire months, and there it is accurate: Canada's May–September 2023 are within −6% to +27%, and July–September within 6%. In quiet months VIIRS records 4–10 times more cell-days than MODIS (for example Canada, March 2023: MODIS 26, VIIRS 290), so MODIS × factor is 50–85% too low. That is why Canada's median % difference is high while its R² is 0.99: half the months are quiet winter months. VIIRS picks up small, cool fires and low-level burning that MODIS misses; quiet months are mostly that kind of activity.

**What this means for the calendar.** Fire-season timing and peak size before 2012 are reliable. Off-season months before 2012 will look quieter than the same months after 2012. The calendar should not be read as showing a real increase in winter fire activity in 2012.

## Results on 2012–2023 (US-14, 144 overlap months per area)

Data: 48 FIRMS country files (MODIS and VIIRS Suomi-NPP, Canada and Argentina, 2012–2023), downloaded with `python3 scripts/get_data.py --years 2012-2023`. Detections kept by US-01's cleaning:

| Year | Canada VIIRS | Canada MODIS | Argentina VIIRS | Argentina MODIS |
|---|---|---|---|---|
| 2012 | 170,046 | 34,739 | 169,182 | 58,289 |
| 2013 | 311,138 | 56,234 | 210,337 | 63,106 |
| 2014 | 460,528 | 62,407 | 108,470 | 34,538 |
| 2015 | 301,445 | 64,872 | 136,392 | 42,498 |
| 2016 | 101,567 | 23,525 | 162,934 | 52,693 |
| 2017 | 426,242 | 81,141 | 180,476 | 57,317 |
| 2018 | 302,827 | 56,795 | 165,584 | 49,992 |
| 2019 | 170,859 | 35,686 | 143,367 | 45,668 |
| 2020 | 37,262 | 11,033 | 400,953 | 113,716 |
| 2021 | 430,732 | 83,292 | 170,504 | 51,590 |
| 2022 | 151,415 | 29,337 | 271,393 | 71,024 |
| 2023 | 1,641,678 | 280,489 | 147,160 | 44,095 |

VIIRS Suomi-NPP data starts on 20 January 2012. Step 4 flags 1–19 January 2012 as VIIRS gap days, so January 2012 is VIIRS plus MODIS × factor for those days (Argentina 1,651 recorded → 5,067; Canada 148 → 271).

**Fit (single factor, gap days left out):**

| Area | Factor | R² | Pearson r | Median \|% diff\| | Activity-weighted \|% diff\| |
|---|---|---|---|---|---|
| Argentina | 2.83 | 0.96 | 0.99 | 16.8% | 13.7% |
| Canada | 2.46 | 0.96 | 0.99 | 40.2% | 21.1% |

The charter's target (r ≥ 0.8) is still met. Gap days found: 36 for VIIRS (all filled from MODIS), 30 for MODIS (left out of the fit). Because VIIRS covers every month from 2012, the harmonized value is VIIRS in 278 of 288 area-months and VIIRS plus a MODIS gap fill in the other 10. The factor now matters only for gap days and for any MODIS-only back record before 2012.

**Is one factor per area stable?** Not very. Fitted on each year alone:

| Area | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Argentina | 2.89 | 2.83 | 3.15 | 3.15 | 2.70 | 2.76 | 2.82 | 2.95 | 2.70 | 2.92 | 2.96 | 2.94 |
| Canada | 2.89 | 2.84 | 3.41 | 2.63 | 3.26 | 2.55 | 2.36 | 2.81 | 3.14 | 2.29 | 2.87 | 2.30 |

Argentina stays within 2.70–3.15. Canada ranges from 2.29 to 3.41. Canada's all-years factor (2.46) sits below most single years because least squares is driven by the biggest months, and 2023 alone holds about a third of Canada's VIIRS detections. Quiet Canadian years (2016, 2020) have high ratios, the same pattern as quiet months.

**Single factor vs power law** (VIIRS = a × MODIS^b, fitted in log space on months with both counts above 0; quiet = months below the area's median VIIRS):

| Area | Method | Parameters | Median \|% diff\| | Quiet months | Busy months | Activity-weighted |
|---|---|---|---|---|---|---|
| Argentina | Single factor | 2.83 | 16.8% | 27.8% | 9.9% | 13.7% |
| Argentina | Power law | a 10.37, b 0.84 | 7.6% | 11.6% | 6.0% | 7.5% |
| Canada | Single factor | 2.46 | 40.2% | 56.4% | 24.0% | 21.1% |
| Canada | Power law | a 22.81, b 0.71 | 12.0% | 16.7% | 8.9% | 15.0% |

The power law is better on every measure in both areas, most of all in quiet months (Canada 56% → 17%). `python -m src.harmonize` prints both tables and writes them to `data/processed/harmonized_monthly_factors_by_year.csv` and `harmonized_monthly_methods.csv`.

**Running it on a laptop.** The command line reads one CSV at a time into daily cell-days (with detection and night-detection counts, and highest and summed FRP, which US-15 uses) and caches them as Parquet in `data/processed/cells/` (about 8 MB for 2012–2023). Peak memory for the full rebuild fell from 4.2 GB to 1.7 GB on the first run and 0.5 GB on later runs (2 seconds instead of 14), and the output is identical to loading everything at once.

## Limits

- Gap detection needs the other sensor: before 2012 (MODIS only) an Aqua outage cannot be told apart from a quiet spell. One sensor having zero detections everywhere while the other has only a handful could occasionally be a real difference rather than an outage; filling it with MODIS × factor is still the better estimate.

- Each factor now comes from 144 months (2012–2023), but the ratio varies from year to year (Canada 2.29–3.41). Applying one factor back to 2001 assumes a stability the overlap does not show; read any pre-2012 MODIS-only year with that range in mind.
- One constant factor per area cannot capture the different ratio in quiet and busy months (above).
- The 0.1° grid is a choice. Larger cells reduce the gap between sensors but blur location; this has not been tuned.
- Results depend on US-01's cleaning thresholds (MODIS confidence ≥ 30, VIIRS nominal/high).

## Decision

**Keep the single factor per area** (decided 2026-11-14 at US-02 review). It matches the fire season, which is what the calendar is for, and it is easy to explain to judges. The quiet-month underestimate above is a known, documented limit.

**To revisit (US-14):** on 2012–2023 the power law beats the single factor everywhere (table above). For the current series this changes only the 36 VIIRS gap days, so the decision matters mainly if a MODIS-only back record before 2012 is added. The team decides; until then the published series keeps the single factor.

## Enhancement (not planned for the hackathon)

**Power-law calibration for quiet months.** Fit VIIRS = a × MODIS^b per area instead of one constant factor. Done in US-14: `compare_methods` in `src/harmonize.py` fits it and compares it with the single factor on the same overlap months (results above). Still open before it can drive the published series:

- add it as an option (for example `--method power`), keeping the single factor as the default until the team decides;
- decide how to fill VIIRS gap days with it: the curve is fitted on monthly totals, so it cannot scale a few days of MODIS the way the factor does;
- decide how to handle months where MODIS is 0 (the power law gives 0; VIIRS usually is not).
