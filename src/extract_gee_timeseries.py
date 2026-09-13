from pathlib import Path
import json

import geopandas as gpd
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "config.yml"
PROCESSED = ROOT / "data" / "processed"
FIRE_GEOJSON = PROCESSED / "fire_events.geojson"
RECOVERY_CSV = PROCESSED / "recovery_timeseries.csv"
CLIMATE_CSV = PROCESSED / "fire_climate_timeseries.csv"
BATCH_SIZE = 5


def load_config() -> dict:
    with CONFIG.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def initialize_earth_engine(config: dict) -> None:
    try:
        import ee
    except ImportError as exc:
        raise ImportError(
            "Missing dependency earthengine-api. Install requirements.txt before running."
        ) from exc

    project_id = config.get("gee", {}).get("project_id")
    kwargs = {"project": project_id} if project_id else {}
    try:
        ee.Initialize(**kwargs)
    except Exception as first_error:
        message = str(first_error)
        if "Not signed up for Earth Engine" in message or "project is not registered" in message:
            raise RuntimeError(
                "Earth Engine credentials exist, but the active account/project is not registered. "
                "Register Earth Engine access or set gee.project_id in config/config.yml to a registered project."
            ) from first_error
        ee.Authenticate()
        try:
            ee.Initialize(**kwargs)
        except Exception as second_error:
            message = str(second_error)
            if "Not signed up for Earth Engine" in message or "project is not registered" in message:
                raise RuntimeError(
                    "Earth Engine authentication completed or credentials exist, but the active account/project is not registered. "
                    "Register Earth Engine access or set gee.project_id in config/config.yml to a registered project."
                ) from second_error
            raise


def geojson_to_ee_features(batch: gpd.GeoDataFrame):
    import ee

    features = []
    for item in json.loads(batch.to_json())["features"]:
        props = item["properties"]
        geom = ee.Geometry(item["geometry"])
        features.append(ee.Feature(geom, props))
    return ee.FeatureCollection(features)


def mask_landsat_c2(image):
    import ee

    qa = image.select("QA_PIXEL")
    clear = (
        qa.bitwiseAnd(1 << 1).eq(0)
        .And(qa.bitwiseAnd(1 << 2).eq(0))
        .And(qa.bitwiseAnd(1 << 3).eq(0))
        .And(qa.bitwiseAnd(1 << 4).eq(0))
        .And(qa.bitwiseAnd(1 << 5).eq(0))
    )
    return image.updateMask(clear)


def prep_tm_etm(image):
    sr = image.select(["SR_B3", "SR_B4", "SR_B7"], ["RED", "NIR", "SWIR2"]).multiply(
        0.0000275
    ).add(-0.2)
    return mask_landsat_c2(image).addBands(sr, None, True).select(["RED", "NIR", "SWIR2"])


def prep_oli(image):
    sr = image.select(["SR_B4", "SR_B5", "SR_B7"], ["RED", "NIR", "SWIR2"]).multiply(
        0.0000275
    ).add(-0.2)
    return mask_landsat_c2(image).addBands(sr, None, True).select(["RED", "NIR", "SWIR2"])


def annual_landsat_composite(year: int, config: dict):
    import ee

    start = ee.Date.fromYMD(year, config["analysis"]["summer_start_month"], 1)
    end = ee.Date.fromYMD(year, config["analysis"]["summer_end_month"], 31).advance(1, "day")
    aoi = ee.Geometry.Point(
        [config["study_area"]["longitude"], config["study_area"]["latitude"]]
    ).buffer(config["study_area"]["radius_km"] * 1000)

    collection = (
        ee.ImageCollection("LANDSAT/LT05/C02/T1_L2")
        .map(prep_tm_etm)
        .merge(ee.ImageCollection("LANDSAT/LE07/C02/T1_L2").map(prep_tm_etm))
        .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").map(prep_oli))
        .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").map(prep_oli))
        .filterBounds(aoi)
        .filterDate(start, end)
    )
    image = collection.median()
    ndvi = image.normalizedDifference(["NIR", "RED"]).rename("NDVI")
    nbr = image.normalizedDifference(["NIR", "SWIR2"]).rename("NBR")
    return image.addBands([nbr, ndvi]).select(["NBR", "NDVI"])


def extract_recovery_batch(fires_fc, config: dict) -> list[dict]:
    records = []
    start_year = int(config["analysis"]["start_year"])
    end_year = int(config["analysis"]["end_year"])

    for year in range(start_year, end_year + 1):
        image = annual_landsat_composite(year, config)
        reduced = image.reduceRegions(
            collection=fires_fc,
            reducer=__import__("ee").Reducer.median(),
            scale=30,
            tileScale=4,
        )
        for feature in reduced.getInfo()["features"]:
            props = feature["properties"]
            fire_year = int(props["fire_year"])
            years_since_fire = year - fire_year
            if -3 <= years_since_fire <= 20:
                records.append(
                    {
                        "fire_id": str(props["fire_id"]),
                        "fire_year": fire_year,
                        "observation_year": year,
                        "years_since_fire": years_since_fire,
                        "area_ha": props.get("area_ha"),
                        "centroid_lat": props.get("centroid_lat"),
                        "centroid_lon": props.get("centroid_lon"),
                        "NBR": props.get("NBR"),
                        "NDVI": props.get("NDVI"),
                    }
                )
    return records


def add_recovery_baselines(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, group in df.groupby("fire_id", sort=False):
        group = group.copy()
        pre = group.loc[group["years_since_fire"].isin([-3, -2, -1])]
        fire = group.loc[group["years_since_fire"] == 0]
        nbr_pre = pre["NBR"].median(skipna=True)
        ndvi_pre = pre["NDVI"].median(skipna=True)
        nbr_fire = fire["NBR"].dropna().iloc[0] if not fire["NBR"].dropna().empty else pd.NA
        group["NBR_pre"] = nbr_pre
        group["NDVI_pre"] = ndvi_pre
        group["dNBR"] = nbr_pre - nbr_fire if pd.notna(nbr_pre) and pd.notna(nbr_fire) else pd.NA
        rows.append(group)
    return pd.concat(rows, ignore_index=True)


def saturation_vapor_pressure_kpa(temp_k):
    temp_c = temp_k.subtract(273.15)
    return temp_c.expression("0.6108 * exp((17.27 * t) / (t + 237.3))", {"t": temp_c})


def annual_climate_image(year: int, config: dict):
    import ee

    start = ee.Date.fromYMD(year, config["analysis"]["summer_start_month"], 1)
    end = ee.Date.fromYMD(year, config["analysis"]["summer_end_month"], 31).advance(1, "day")
    collection = (
        ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
        .select(["temperature_2m", "dewpoint_temperature_2m", "total_precipitation"])
        .filterDate(start, end)
    )

    def add_vpd(image):
        es = saturation_vapor_pressure_kpa(image.select("temperature_2m"))
        ea = saturation_vapor_pressure_kpa(image.select("dewpoint_temperature_2m"))
        return image.addBands(es.subtract(ea).max(0).rename("vpd_kpa"))

    summer = collection.map(add_vpd)
    temp = summer.select("temperature_2m").mean().subtract(273.15).rename("summer_temp_c")
    precip = summer.select("total_precipitation").sum().multiply(1000).rename("summer_precip_mm")
    vpd = summer.select("vpd_kpa").mean().rename("summer_vpd_kpa")
    return temp.addBands([precip, vpd])


def extract_climate_batch(fires_fc, config: dict) -> list[dict]:
    import ee

    baseline_years = range(
        int(config["analysis"]["climate_baseline_start_year"]),
        int(config["analysis"]["climate_baseline_end_year"]) + 1,
    )
    baseline = ee.ImageCollection([annual_climate_image(year, config) for year in baseline_years]).mean()
    records = []

    for year in range(int(config["analysis"]["start_year"]), int(config["analysis"]["end_year"]) + 1):
        image = annual_climate_image(year, config)
        anomalies = ee.Image.cat(
            [
                image.select("summer_temp_c").subtract(baseline.select("summer_temp_c")).rename("temp_anomaly_c"),
                image.select("summer_precip_mm").subtract(baseline.select("summer_precip_mm")).rename("precip_anomaly_mm"),
                image.select("summer_vpd_kpa").subtract(baseline.select("summer_vpd_kpa")).rename("vpd_anomaly_kpa"),
            ]
        )
        reduced = image.addBands(anomalies).reduceRegions(
            collection=fires_fc,
            reducer=ee.Reducer.mean(),
            scale=11132,
            tileScale=4,
        )
        for feature in reduced.getInfo()["features"]:
            props = feature["properties"]
            records.append(
                {
                    "fire_id": str(props["fire_id"]),
                    "observation_year": year,
                    "summer_temp_c": props.get("summer_temp_c"),
                    "summer_precip_mm": props.get("summer_precip_mm"),
                    "summer_vpd_kpa": props.get("summer_vpd_kpa"),
                    "temp_anomaly_c": props.get("temp_anomaly_c"),
                    "precip_anomaly_mm": props.get("precip_anomaly_mm"),
                    "vpd_anomaly_kpa": props.get("vpd_anomaly_kpa"),
                }
            )
    return records


def extract_gee_timeseries() -> tuple[Path, Path]:
    if not FIRE_GEOJSON.exists():
        raise FileNotFoundError(f"Missing required input: {FIRE_GEOJSON}")

    config = load_config()
    initialize_earth_engine(config)
    fires = gpd.read_file(FIRE_GEOJSON).to_crs("EPSG:4326")
    if fires.empty:
        raise ValueError(f"Input is empty: {FIRE_GEOJSON}")

    recovery_records = []
    climate_records = []
    for start in range(0, len(fires), BATCH_SIZE):
        batch = fires.iloc[start : start + BATCH_SIZE].copy()
        fires_fc = geojson_to_ee_features(batch)
        recovery_records.extend(extract_recovery_batch(fires_fc, config))
        climate_records.extend(extract_climate_batch(fires_fc, config))
        print(f"Processed fire batch {start + 1}-{min(start + BATCH_SIZE, len(fires))} of {len(fires)}")

    recovery = add_recovery_baselines(pd.DataFrame(recovery_records))
    climate = pd.DataFrame(climate_records)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    recovery.to_csv(RECOVERY_CSV, index=False)
    climate.to_csv(CLIMATE_CSV, index=False)
    print(f"Wrote {RECOVERY_CSV}")
    print(f"Wrote {CLIMATE_CSV}")
    return RECOVERY_CSV, CLIMATE_CSV


if __name__ == "__main__":
    extract_gee_timeseries()
