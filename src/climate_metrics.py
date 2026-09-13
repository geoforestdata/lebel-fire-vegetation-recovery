from pathlib import Path

import numpy as np
import pandas as pd

from recovery_metrics import OUTPUT_TABLE, build_recovery_metrics, load_analysis_dataset


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = {
    "1_3yr": {"years": range(1, 4), "minimum": 2},
    "1_5yr": {"years": range(1, 6), "minimum": 3},
    "1_10yr": {"years": range(1, 11), "minimum": 6},
}
CLIMATE_COLUMNS = {
    "temp": "temp_anomaly_c",
    "precip": "precip_anomaly_mm",
    "vpd": "vpd_anomaly_kpa",
}
POSTFIRE_COLUMNS = {
    "mean_temp_postfire_available": "temp_anomaly_c",
    "mean_precip_postfire_available": "precip_anomaly_mm",
    "mean_vpd_postfire_available": "vpd_anomaly_kpa",
}


def _window_mean(group: pd.DataFrame, source_column: str, years: range, minimum: int) -> float:
    values = group.loc[group["years_since_fire"].isin(list(years)), source_column].dropna()
    if len(values) < minimum:
        return np.nan
    return values.mean()


def summarize_climate(fire_id: str, group: pd.DataFrame) -> dict:
    row = {"fire_id": fire_id}

    for window_label, window in WINDOWS.items():
        for prefix, source_column in CLIMATE_COLUMNS.items():
            row[f"{prefix}_anomaly_{window_label}"] = _window_mean(
                group, source_column, window["years"], window["minimum"]
            )

    postfire = group.loc[group["years_since_fire"] >= 1]
    for output_column, source_column in POSTFIRE_COLUMNS.items():
        row[output_column] = postfire[source_column].mean()

    return row


def build_climate_metrics(write: bool = True) -> pd.DataFrame:
    recovery = build_recovery_metrics(write=False)
    analysis = load_analysis_dataset()

    required = ["fire_id", "years_since_fire", *CLIMATE_COLUMNS.values()]
    missing = [column for column in required if column not in analysis.columns]
    if missing:
        raise ValueError(f"{ROOT / 'data' / 'processed' / 'analysis_dataset.csv'} is missing required columns: {missing}")

    rows = [
        summarize_climate(fire_id, group)
        for fire_id, group in analysis.groupby("fire_id", sort=False)
    ]
    climate = pd.DataFrame(rows)

    metrics = recovery.merge(climate, on="fire_id", how="left", validate="one_to_one")
    metrics = metrics.sort_values(["fire_year", "fire_id"]).reset_index(drop=True)

    if write:
        OUTPUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
        metrics.to_csv(OUTPUT_TABLE, index=False)
        print(f"Wrote {OUTPUT_TABLE}")
    return metrics


if __name__ == "__main__":
    build_climate_metrics(write=True)
