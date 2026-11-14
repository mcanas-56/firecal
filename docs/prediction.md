# Fire outlook method note (US-16)

All three outlooks beat their climatology baseline on the 2022–2023 test years in both areas, so all three may be shown in the app (US-18). The biggest limit: the cell map only scores places that had burned before. In Canada, 47% of 2022–2023 fire activity fell in cells that had never burned since 2012.

Code: `src/predict.py`. Tests: `tests/test_predict.py`. Rebuild: `python -m src.predict` (after `python -m src.harmonize` and `python -m src.features`).

## Method

**Years.** Fit on 2012–2019, choose settings on 2020–2021, refit on 2012–2021, then score once on 2022–2023. No test-year data is used before that final score.

**The rule (from the roadmap).** A model gets `ship: true` only if it beats the baseline on the test years. Otherwise the app shows the baseline.

| Outlook | What it predicts | Baseline | Model |
|---|---|---|---|
| Cell burn probability | Chance a 0.1° cell has at least one fire cell-day next month | Share of earlier years the cell burned in that calendar month | Logistic regression per area on the US-15 predictors: past burn rate, last month's and last year's cell-days, months since last burn, the 8 neighbouring cells, calendar month. L2 penalty chosen on 2020–2021 |
| Monthly area outlook | Harmonized fire cell-days for an area next month | Mean of that calendar month, 2012–2021 | Nowcast: the baseline scaled by how far last month was above or below its own normal (log anomaly × β) |
| Season timing | The peak month | Peak of the 2012–2021 monthly means | (none: the climatology is the outlook) |

The logistic regression is a small NumPy implementation (Newton's method with step-halving), so the project needs no machine-learning library.

**Which rows are scored.** Cells must have been seen before the scored period (`first_seen_year` ≤ 2021 for the test). The first year (2012) is used only as history. Months with VIIRS gap days are left out of the cell model, because raw VIIRS counts are low there for a technical reason. The monthly outlook keeps them, since the harmonized value already fills those days from MODIS.

## Results on 2022–2023

### Cell burn probability

| Area | Cells scored | Burn rate | AUC baseline → model | Brier baseline → model | L2 |
|---|---|---|---|---|---|
| Argentina | 18,481 | 11.0% | 0.817 → **0.870** | 0.0787 → **0.0698** | 0.1 |
| Canada | 32,088 | 2.2% | 0.717 → **0.852** | 0.0223 → **0.0194** | 1000 |

It holds in each test year: Canada's AUC is 0.852 in 2022 and 0.850 in 2023 (baseline 0.757 and 0.697), and Argentina's is 0.874 and 0.867.

**Calibration.** In Argentina, predicted and observed burn rates agree within about 4 points in every band. In Canada they agree up to 30%. Above that the model is too confident: in the 0.7–1.0 band it predicts 77% and 36% burn, though that band has only 333 cell-months.

**What the model learned** (standardised weights):
- **Months since last burn: strongest, negative in both areas.** Recently burned cells are more likely to burn again. This is the opposite of a fuel-buildup effect at this scale; it reflects fire-prone and farm cells that burn most years. US-17 tests the fire-deficit idea properly.
- **Past burn rate in that calendar month: positive.**
- **Neighbour activity: positive.** This covers last month's fires and how many neighbours burned in the last 12 months.

### Monthly area outlook

| Area | Median \|% error\| climatology → nowcast | Mean \|log error\| | β | Test months inside the 2012–2021 range |
|---|---|---|---|---|
| Argentina | 32.3% → **20.3%** | 0.385 → **0.300** | 0.65 | 83% |
| Canada | 54.3% → **36.6%** | 0.621 → **0.527** | 0.38 | 67% |

β is how much of last month's anomaly carries into the next month. A busy month tends to be followed by another one, more so in Argentina. Canada's 2023 broke the historical range in a third of the test months.

### Season timing

| Area | Climatology peak | 2022 peak | 2023 peak | Fit years within 1 month |
|---|---|---|---|---|
| Argentina | August | September | August | 100% |
| Canada | July | July | August | 80% |

## Outputs

Written to `data/processed/prediction/` (local only):

| File | What it holds |
|---|---|
| `metrics.json` | Every score above, the tuning log loss, reliability bands, model weights and the `ship` flags |
| `cell_test_predictions.parquet` | 2022–2023 cell-months with `burned`, `p_baseline` and `p_model` |
| `monthly_climatology.csv` | Per area and month: mean, median, low and high harmonized cell-days, 2012–2023 (for the app's outlook range) |

## Limits

- **New fire areas are not scored.** The table only holds cells that burned at some point, and scoring needs cells seen before 2022. In Canada, 6,344 cells first burned in 2022–2023 and held 47% of the test fire cell-days (Argentina: 616 cells, 1%). The map says where fire comes back, not where it breaks out somewhere new.
- **One month ahead only.** Both models use last month's activity, so they forecast the next month, not a whole season.
- **No weather.** Nothing here can tell an extreme year in advance. Canada 2023 was outside the historical range in a third of its months.
- **The baseline's log loss is inflated.** A cell that never burned in a calendar month gets probability 0, so any first burn is heavily penalised. Compare models on AUC and Brier score.
- **Canada's top band is over-confident** (above).
- **FIRMS cannot tell wildfires from agricultural or prescribed burns.** Probabilities describe heat detections of any kind.

## Running it

`python -m src.predict` takes about 20 seconds and peaks at about 2.7 GB of memory on 2012–2023.
