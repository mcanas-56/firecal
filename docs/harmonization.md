# Harmonization method note (US-02)

FireCal joins two satellite fire records, MODIS (2000–present) and VIIRS (2012–present), into one monthly number per area that means the same thing before and after 2012. VIIRS sees far more hotspots than MODIS (smaller pixels, more sensitive), so joining them unadjusted creates a false jump in fire activity when VIIRS arrives. This note records every choice so it can be defended.

Code: `src/harmonize.py`. Tests: `tests/test_harmonize.py`. Rebuild: `python -m src.harmonize data/*.csv`.

## Method

1. **Match the satellites.** MODIS on Aqua and VIIRS on Suomi-NPP cross the equator around 13:30 and 01:30, so they observe the same fires at the same time of day. MODIS Terra (10:30) is left out by default; `--include-terra` adds it.
2. **Count fire cell-days, not pixels.** A VIIRS pixel is 375 m and a MODIS pixel about 1 km, so VIIRS reports one fire as many more detections. Each detection is snapped to a 0.1° grid (`--grid` changes it) and each cell counts at most once per day per sensor. One active cell on one day = one fire cell-day.
3. **Aggregate by month.** Fire cell-days are summed per area, sensor, year and month. Every month of every year with data gets a row; a month with no fires is 0. A month a sensor has no data for (for example VIIRS before 2012) is left empty, not 0.
4. **Calibrate on the overlap.** For each area, over the months where both sensors have data, one factor is fitted: VIIRS cell-days ≈ factor × MODIS cell-days (least squares through the origin).
5. **Build the harmonized series.** Where VIIRS exists, the harmonized value is the VIIRS count. Before VIIRS, it is MODIS × factor. The `source` column says which was used.

Input is the cleaned output of US-01 (`load_hotspots`): vegetation fires only (`type` 0), MODIS confidence ≥ 30, VIIRS nominal or high confidence.

## Output

`data/processed/harmonized_monthly.csv` (local only, never committed), one row per area-month:

| Column | Meaning |
|---|---|
| area, year, month | Where and when |
| modis_cell_days | MODIS Aqua fire cell-days (empty if no MODIS data) |
| viirs_cell_days | VIIRS Suomi-NPP fire cell-days (empty if no VIIRS data) |
| modis_scaled | modis_cell_days × factor |
| harmonized | The calendar value: VIIRS if present, else modis_scaled |
| source | `viirs`, `modis_scaled` or `none` |
| factor | The area's calibration factor |

The raw per-sensor columns let US-07 show raw vs harmonized.

## Results on the practice set (2022–2023, 24 overlap months per area)

| Area | Factor | R² | Pearson r | Median \|% diff\| | Activity-weighted \|% diff\| | Scaled MODIS total vs VIIRS |
|---|---|---|---|---|---|---|
| Argentina | 2.86 | 0.90 | 0.97 | 18.6% | 15.6% | −8% |
| Canada | 2.30 | 0.99 | 0.99 | 51.2% | 13.3% | −7% |

The charter's target (harmonized MODIS and VIIRS agree with r ≥ 0.8) is met in both areas. With Terra included, the factors drop to 2.11 (Argentina) and 1.68 (Canada), with similar fit.

**Where it fits and where it doesn't.** The factor is driven by the big fire months, and there it is accurate: Canada's May–September 2023 are within −6% to +27%, and July–September within 6%. In quiet months VIIRS records 4–10 times more cell-days than MODIS (for example Canada, April 2022: MODIS 21, VIIRS 322), so MODIS × factor is 50–85% too low. That is why Canada's median % difference is high while its R² is 0.99: half the months are quiet winter months. VIIRS picks up small, cool fires and low-level burning that MODIS misses; quiet months are mostly that kind of activity.

**What this means for the calendar.** Fire-season timing and peak size before 2012 are reliable. Off-season months before 2012 will look quieter than the same months after 2012. The calendar should not be read as showing a real increase in winter fire activity in 2012.

## Limits

- The practice set covers only 2022–2023, so each factor comes from 24 months. Applying it back to 2001 assumes the MODIS–VIIRS relationship is stable over time. Download the full overlap with `python3 scripts/get_data.py --years 2012-2023` (and MODIS from 2001 for the back record) before trusting the long series.
- One constant factor per area cannot capture the different ratio in quiet and busy months (above).
- The 0.1° grid is a choice. Larger cells reduce the gap between sensors but blur location; this has not been tuned.
- Results depend on US-01's cleaning thresholds (MODIS confidence ≥ 30, VIIRS nominal/high).

## Decision

**Keep the single factor per area** (decided 2026-11-14 at US-02 review). It matches the fire season, which is what the calendar is for, and it is easy to explain to judges. The quiet-month underestimate above is a known, documented limit.

## Enhancement (not planned for the hackathon)

**Power-law calibration for quiet months.** Fit VIIRS = a × MODIS^b per area, in log space on overlap months with both counts above 0, instead of one constant factor. With b < 1 the curve scales quiet months up more than busy ones, which should shrink the 50–85% quiet-month gap while keeping the fire-season fit. To do it:

- add the fit next to `fit_factors` in `src/harmonize.py` behind an option (for example `--method power`), keeping the single factor as the default;
- compare both methods on the same overlap months (median and activity-weighted % difference, quiet vs busy months) and report them here;
- decide how to handle months where MODIS is 0 (the power law gives 0; VIIRS usually is not).

Worth doing once the full 2012–2023 overlap is downloaded, so the curve is fitted on more than 24 months.
