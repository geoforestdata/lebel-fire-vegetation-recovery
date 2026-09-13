# Post-fire vegetation recovery near Lebel-sur-Quevillon

Compact reproducible analysis of fire-level spectral vegetation recovery and early post-fire climate exposure around Lebel-sur-Quevillon, Quebec.

## Research question

How has post-fire vegetation recovery changed under increasingly warm and dry climate conditions around Lebel-sur-Quevillon since 1984?

## Study area

The study area is a 150 km radius around Lebel-sur-Quevillon. Local preprocessing of the official NRCan Canadian National Fire Database retained 78 wildfire events from 1985-2023 with mapped perimeters intersecting the AOI and reported area of at least 100 ha.

![Study area and fire history](outputs/figures/01_study_area_fire_history.png)

## Approach

```text
Fire perimeters
+
Landsat
+
ERA5-Land
v
age-standardized recovery trajectories
v
climate/recovery comparison
```

Fire perimeters are prepared locally from official NFDB files. Landsat and ERA5-Land extraction is performed through the Earth Engine Python API using the local `fire_events.geojson`; no permanent uploaded fire asset is required.

## Recovery indicators

NBR is the primary recovery indicator. NDVI is retained as a secondary indicator.

```text
dNBR = NBR_pre - NBR_fire

relative_recovery_nbr = (NBR_t - NBR_fire) / (NBR_pre - NBR_fire)
```

`NBR_fire` is the fire-year NBR, and `NBR_pre` is the median of years -3, -2, and -1 before fire. Relative recovery is not capped at 1.0, because vegetation can exceed the pre-fire NBR baseline.

For normalized recovery metrics, this analysis requires `dNBR >= 0.10`. This is an analysis-level minimum disturbance-signal and numerical-stability criterion, not a universal wildfire-severity threshold. Fires with low or negative `dNBR` are excluded from normalized recovery metrics because the denominator is too small or inconsistent with a detectable fire-related NBR decline, making normalized recovery unstable or uninterpretable. Those fires remain in the fire-history and climate summaries.

## Results

![Recovery trajectories](outputs/figures/02_recovery_trajectories.png)

After applying the `dNBR >= 0.10` validity rule, 58 of 78 fire events were valid for normalized recovery. Valid exact-age sample sizes were 43 fires at 3 years, 42 at 5 years, and 38 at 10 years.

![Recovery at common ages](outputs/figures/03_recovery_common_ages.png)

Median 3-year recovery was 0.61 for the 1984-1994 cohort, 0.09 for 1995-2004, 0.47 for 2005-2014, and 0.26 for 2015-2022. The 2023+ cohort has no valid 3-, 5-, or 10-year recovery observations because those ages are not yet available.

![Post-fire climate by cohort](outputs/figures/04_postfire_climate_by_cohort.png)

Median early post-fire VPD anomaly was negative for the 1984-1994, 1995-2004, and 2005-2014 cohorts, and positive for the 2015-2022 and 2023+ cohorts. Climate summaries retain low-`dNBR` fires because they do not depend on normalized recovery validity.

![Climate vs recovery](outputs/figures/05_climate_vs_recovery.png)

Simple 3-year bivariate models were weak: temperature slope = -0.187 with R2 = 0.03, precipitation slope = 0.00003 with R2 = 0.00, and VPD slope = -2.500 with R2 = 0.04. These relationships are associations only and do not establish climate causality.

![Recovery change summary](outputs/figures/06_recovery_change_summary.png)

The summary figure compares median 3-year recovery with median early VPD anomaly by cohort. Recent cohorts show shorter recovery windows, so absence of 10-year values for recent fires is a data-availability constraint rather than an inferred recovery outcome.

## Main findings

- The workflow retained 78 fire events; 58 met the `dNBR >= 0.10` criterion for normalized recovery.
- The low/negative-`dNBR` QA rule removed unstable recovery artifacts, including the previous extreme 3-year recovery value near 75.87.
- Valid exact-age recovery sample sizes are 43, 42, and 38 fires at 3, 5, and 10 years.
- The 3-year climate/recovery bivariate relationships are weak in this fire-level dataset.

## Limitations

- Spectral recovery is not equivalent to structural forest recovery.
- Observational analysis cannot establish climate causality.
- Recent fires have shorter available recovery windows.
- Fire-level aggregation hides within-fire heterogeneity.

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
