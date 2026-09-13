# Data Sources

## Fire perimeters

- Dataset name: Canadian National Fire Database fire perimeter polygons
- Provider: Natural Resources Canada, Canadian Forest Service
- Temporal coverage used: 1984-2024 from the local official NFDB perimeter shapefiles dated 2025-06-30
- Spatial resolution: vector fire perimeter polygons
- Source URL: `https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_poly/current_version/`
- Local source files used during execution:
  - `/Users/jano/Downloads/NFDB_poly/NFDB_poly_1972to2020_20250630.shp`
  - `/Users/jano/Downloads/NFDB_poly/NFDB_poly_2021to2024_20250630.shp`
- Detected fields used:
  - fire identifier: `FIRE_ID`
  - fire year: `YEAR`
  - fire area: `SIZE_HA`
- Derived outputs:
  - `data/processed/fire_events.csv`
  - `data/processed/fire_events.geojson`
- Reason for use: authoritative Canadian wildfire perimeter source suitable for event-level post-fire recovery analysis.

## Landsat Surface Reflectance

- Dataset name: Landsat Collection 2 Level 2 Surface Reflectance
- Provider: USGS/NASA
- Temporal coverage: Landsat 5 from 1984, Landsat 7 from 1999, Landsat 8 from 2013, Landsat 9 from 2021
- Spatial resolution: 30 m
- Earth Engine collection IDs:
  - `LANDSAT/LT05/C02/T1_L2`
  - `LANDSAT/LE07/C02/T1_L2`
  - `LANDSAT/LC08/C02/T1_L2`
  - `LANDSAT/LC09/C02/T1_L2`
- Variables used: surface reflectance red, near infrared, shortwave infrared 2, and `QA_PIXEL`
- Derived indicators: annual summer NBR and NDVI by fire polygon.
- Reason for use: long, consistent multisensor record for annual summer vegetation recovery metrics since 1984.

## Climate

- Dataset name: ERA5-Land hourly
- Provider: ECMWF Copernicus Climate Data Store
- Temporal coverage: 1950 to near present
- Spatial resolution: about 11 km
- Earth Engine collection ID: `ECMWF/ERA5_LAND/HOURLY`
- Variables used: `temperature_2m`, `dewpoint_temperature_2m`, `total_precipitation`
- Derived indicators: mean summer air temperature, total summer precipitation, mean summer vapor pressure deficit, and 1991-2020 anomaly fields.
- Reason for use: consistent long-term reanalysis suitable for polygon-level summer climate summaries.

## Climatic Water Deficit

CWD is not included in this version. A defensible CWD field would require either a dedicated product or a separate water-balance calculation beyond this compact pipeline.
