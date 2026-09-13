from pathlib import Path

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.yml"
PROCESSED = ROOT / "data" / "processed"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_csv(name: str) -> pd.DataFrame:
    path = PROCESSED / name
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"Input is empty: {path}")
    return df


def require_columns(df: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def check_duplicate_keys(df: pd.DataFrame, keys: list[str], name: str) -> None:
    duplicate_count = int(df.duplicated(keys).sum())
    if duplicate_count:
        raise ValueError(f"{name} has {duplicate_count} duplicate rows for keys {keys}")


def assign_fire_cohort(fire_year: pd.Series) -> pd.Series:
    conditions = [
        fire_year.between(1984, 1994),
        fire_year.between(1995, 2004),
        fire_year.between(2005, 2014),
        fire_year.between(2015, 2022),
        fire_year.ge(2023),
    ]
    labels = ["1984-1994", "1995-2004", "2005-2014", "2015-2022", "2023+"]
    return pd.Series(np.select(conditions, labels, default=pd.NA), index=fire_year.index)


def main() -> None:
    config = load_config()
    start_year = int(config["analysis"]["start_year"])
    end_year = int(config["analysis"]["end_year"])

    fire_events = read_csv("fire_events.csv")
    recovery = read_csv("recovery_timeseries.csv")
    climate = read_csv("fire_climate_timeseries.csv")

    require_columns(
        fire_events,
        ["fire_id", "fire_year", "area_ha", "centroid_lat", "centroid_lon"],
        "fire_events.csv",
    )
    require_columns(
        recovery,
        [
            "fire_id",
            "fire_year",
            "observation_year",
            "years_since_fire",
            "area_ha",
            "centroid_lat",
            "centroid_lon",
            "NBR",
            "NDVI",
            "NBR_pre",
            "NDVI_pre",
            "dNBR",
        ],
        "recovery_timeseries.csv",
    )
    require_columns(
        climate,
        [
            "fire_id",
            "observation_year",
            "summer_temp_c",
            "summer_precip_mm",
            "summer_vpd_kpa",
            "temp_anomaly_c",
            "precip_anomaly_mm",
            "vpd_anomaly_kpa",
        ],
        "fire_climate_timeseries.csv",
    )

    for name, df in {
        "fire_events.csv": fire_events,
        "recovery_timeseries.csv": recovery,
        "fire_climate_timeseries.csv": climate,
    }.items():
        require_columns(df, ["fire_id"], name)
        if df["fire_id"].isna().any():
            raise ValueError(f"{name} contains missing fire_id values")

    for name, df in {
        "recovery_timeseries.csv": recovery,
        "fire_climate_timeseries.csv": climate,
    }.items():
        if df["observation_year"].isna().any():
            raise ValueError(f"{name} contains missing observation_year values")
        bad_years = ~df["observation_year"].between(start_year - 3, end_year + 20)
        if bad_years.any():
            raise ValueError(f"{name} contains impossible observation_year values")
        check_duplicate_keys(df, ["fire_id", "observation_year"], name)

    if fire_events["fire_year"].isna().any():
        raise ValueError("fire_events.csv contains missing fire_year values")
    if (~fire_events["fire_year"].between(start_year, end_year)).any():
        raise ValueError("fire_events.csv contains fire_year values outside configured range")
    check_duplicate_keys(fire_events, ["fire_id"], "fire_events.csv")

    climate_columns = [
        "fire_id",
        "observation_year",
        "summer_temp_c",
        "summer_precip_mm",
        "summer_vpd_kpa",
        "temp_anomaly_c",
        "precip_anomaly_mm",
        "vpd_anomaly_kpa",
    ]
    optional_cwd = [
        col
        for col in ["summer_cwd_mm", "cwd_anomaly_mm"]
        if col in climate.columns
    ]

    analysis = recovery.merge(
        climate[climate_columns + optional_cwd],
        on=["fire_id", "observation_year"],
        how="left",
        validate="one_to_one",
    )

    if analysis[climate_columns[2:]].isna().all(axis=1).any():
        missing = int(analysis[climate_columns[2:]].isna().all(axis=1).sum())
        raise ValueError(f"{missing} recovery rows did not match climate records")

    analysis["fire_cohort"] = assign_fire_cohort(analysis["fire_year"])
    if analysis["fire_cohort"].isna().any():
        raise ValueError("Unable to assign fire_cohort for one or more rows")

    output_columns = [
        "fire_id",
        "fire_year",
        "observation_year",
        "years_since_fire",
        "fire_cohort",
        "area_ha",
        "centroid_lat",
        "centroid_lon",
        "NBR",
        "NDVI",
        "NBR_pre",
        "NDVI_pre",
        "dNBR",
        "summer_temp_c",
        "summer_precip_mm",
        "summer_vpd_kpa",
        "temp_anomaly_c",
        "precip_anomaly_mm",
        "vpd_anomaly_kpa",
    ] + optional_cwd

    analysis = analysis[output_columns].sort_values(
        ["fire_year", "fire_id", "observation_year"]
    )

    output_path = PROCESSED / "analysis_dataset.csv"
    analysis.to_csv(output_path, index=False)
    print(f"Wrote {output_path}")
    print(f"Rows: {len(analysis)}")
    print("Schema:")
    for column in analysis.columns:
        print(f"- {column}")


if __name__ == "__main__":
    main()
