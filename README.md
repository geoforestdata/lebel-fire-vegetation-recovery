# Post-fire vegetation recovery near Lebel-sur-Quévillon

Wildfires burning today in Québec's boreal forest are beginning their recovery under a different climate than fires that burned four decades ago. But are forests actually recovering differently?

This repository follows 78 wildfire events from 1985-2023 within 150 km of Lebel-sur-Quévillon, Québec, using Landsat vegetation indices and ERA5-Land summer climate anomalies. It compares fire cohorts at the same post-fire ages so that older and newer fires are not mixed across unequal recovery windows.

**The post-fire climate signal has changed more clearly than the recovery signal.**

## Research question

How has post-fire vegetation recovery changed under increasingly warm and dry climate conditions around Lebel-sur-Quévillon since 1984?

## 39 years of fire history

![Study area and fire history](outputs/figures/01_study_area_fire_history.png)

The study area is a 150 km radius around Lebel-sur-Quévillon. The analysis retains wildfire perimeters from the official Canadian National Fire Database where fires intersect the study area, occurred from 1985-2023, and were at least 100 ha.

The fire cohorts provide a long-term natural comparison: fires from the 1980s and 1990s can be compared with more recent events, while still respecting the fact that recent fires have had less time to recover.

## How did vegetation recover?

![Recovery trajectories](outputs/figures/02_recovery_trajectories.png)

Vegetation recovery is measured with relative NBR recovery. A value of 0 represents the fire-year NBR condition, while 1 represents return to the pre-fire NBR baseline. Values above 1 are possible and are not capped, because post-fire vegetation can exceed the pre-fire spectral baseline.

![Recovery at common ages](outputs/figures/03_recovery_common_ages.png)

At three years after fire, median relative NBR recovery was:

- 1984-1994: 0.61
- 1995-2004: 0.09
- 2005-2014: 0.47
- 2015-2022: 0.26
- 2023+: unavailable because sufficient recovery time has not elapsed

These values do not show a simple monotonic temporal pattern. In this dataset, comparable-age spectral recovery varies substantially among fire cohorts, but it does not support a claim that recent forests are progressively recovering worse.

## The post-fire climate changed

![Post-fire climate by cohort](outputs/figures/04_postfire_climate_by_cohort.png)

The atmospheric context during early recovery changed more clearly than the recovery trajectories themselves. Median early post-fire VPD anomaly is negative for the 1984-1994, 1995-2004, and 2005-2014 cohorts, but positive for the two most recent cohorts: 2015-2022 and 2023+.

That shift matters because vapor pressure deficit links temperature, atmospheric dryness, and plant water stress. Recent fires are beginning recovery under a different early post-fire climate envelope than many older fires in the record.

## But climate alone does not explain recovery

![Climate vs recovery](outputs/figures/05_climate_vs_recovery.png)

Simple bivariate relationships between three-year recovery and early post-fire climate anomalies explain little of the observed between-fire variability:

- Temperature anomaly: slope = -0.187, R² = 0.03
- Precipitation anomaly: slope = 0.00003, R² = 0.00
- VPD anomaly: slope = -2.500, R² = 0.04

These are associations only. The climatic context clearly changed, but variation in recovery among fires cannot be reduced to a simple one-variable climate response.

## Synthesis

![Recovery change summary](outputs/figures/06_recovery_change_summary.png)

Recent fires are beginning recovery in a different atmospheric environment, especially with respect to VPD and temperature. Comparable-age spectral recovery, however, does not show a corresponding simple or monotonic decline through time.

Detecting a changing post-fire climate is easier here than attributing fire-level recovery trajectories to climate alone.

## Quality control

Normalized recovery requires a detectable fire-related NBR decline. The disturbance signal is:

```text
dNBR = NBR_pre - NBR_fire
```

Relative recovery is:

```text
relative_recovery_nbr = (NBR_t - NBR_fire) / (NBR_pre - NBR_fire)
```

This analysis requires `dNBR >= 0.10` for normalized recovery metrics. This is an analysis-level minimum disturbance-signal and numerical-stability criterion, not a universal wildfire-severity threshold.

Fires with low or negative `dNBR` are excluded from normalized recovery because the denominator is too small or inconsistent with a detectable fire-related NBR decline, making normalized recovery unstable or uninterpretable. Of the 78 fire events, 58 pass this criterion. Excluded fires remain in the fire-history and climate analyses. Normalized recovery is not capped at 1.0.

## Methods and workflow

```text
NFDB fire perimeters
+
Landsat Collection 2
+
ERA5-Land
v
age-standardized recovery metrics
v
climate/recovery comparisons
```

NBR is the primary recovery indicator, and NDVI is retained as a secondary indicator. The pre-fire baseline is the median of years -3, -2, and -1 before fire. Recovery comparisons use exact post-fire ages of 3, 5, and 10 years; missing ages are not interpolated or substituted.

Fire perimeters are prepared locally as a compact GeoJSON and passed to the Earth Engine Python API. The workflow does not require a permanent uploaded Earth Engine fire asset.

## Limitations

- Spectral recovery is not equivalent to structural forest recovery.
- Observational analysis cannot establish climate causality.
- Recent fires have shorter recovery windows.
- Fire-level aggregation hides within-fire heterogeneity.
- The `dNBR >= 0.10` criterion means normalized recovery inference applies to fires with a detectable NBR decline.

## Reproduce

Install dependencies and run the full pipeline:

```bash
python3 -m pip install -r requirements.txt
python3 src/run_pipeline.py
```

To rerun only the corrected downstream QA, metrics, models, and figures from existing extracted tables:

```bash
python3 src/build_analysis_dataset.py
python3 src/analyze_recovery.py
python3 src/generate_final_figures.py
```

Earth Engine must be authenticated with a registered Earth Engine project/account before the full Landsat and ERA5-Land extraction can be rerun.

## Data sources

- NRCan Canadian National Fire Database fire perimeter polygons
- USGS Landsat Collection 2 Level 2 Surface Reflectance
- ECMWF ERA5-Land hourly reanalysis
