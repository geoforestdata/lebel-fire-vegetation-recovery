from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DATASET = ROOT / "data" / "processed" / "analysis_dataset.csv"
OUTPUT_TABLE = ROOT / "outputs" / "tables" / "recovery_metrics.csv"
QA_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "recovery_qa_summary.csv"
TRAJECTORY_YEARS = list(range(0, 21))
REQUIRED_TARGET_YEARS = [1, 2, 3, 5, 10]
DENOMINATOR_TOLERANCE = 1e-6
MIN_VALID_DNBR = 0.10


REQUIRED_COLUMNS = [
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
]


def load_analysis_dataset() -> pd.DataFrame:
    if not ANALYSIS_DATASET.exists():
        raise FileNotFoundError(f"Missing required input: {ANALYSIS_DATASET}")

    df = pd.read_csv(ANALYSIS_DATASET)
    if df.empty:
        raise ValueError(f"Input is empty: {ANALYSIS_DATASET}")

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{ANALYSIS_DATASET} is missing required columns: {missing}")

    if df["fire_id"].isna().any():
        raise ValueError(f"{ANALYSIS_DATASET} contains missing fire_id values")
    if df["years_since_fire"].isna().any():
        raise ValueError(f"{ANALYSIS_DATASET} contains missing years_since_fire values")
    if df.duplicated(["fire_id", "observation_year"]).any():
        count = int(df.duplicated(["fire_id", "observation_year"]).sum())
        raise ValueError(
            f"{ANALYSIS_DATASET} has {count} duplicate fire_id + observation_year rows"
        )

    return df


def _relative_recovery(value: float, pre: float, fire_value: float) -> float:
    denominator = pre - fire_value
    if pd.isna(value) or pd.isna(pre) or pd.isna(fire_value):
        return np.nan
    if abs(denominator) < DENOMINATOR_TOLERANCE:
        return np.nan
    return (value - fire_value) / denominator


def add_relative_recovery(df: pd.DataFrame) -> pd.DataFrame:
    fire_year_rows = df.loc[df["years_since_fire"] == 0, ["fire_id", "NBR", "NDVI"]]
    fire_year_rows = fire_year_rows.rename(columns={"NBR": "NBR_fire", "NDVI": "NDVI_fire"})

    if fire_year_rows.duplicated("fire_id").any():
        count = int(fire_year_rows.duplicated("fire_id").sum())
        raise ValueError(f"{ANALYSIS_DATASET} has {count} duplicate fire-year rows")

    out = df.merge(fire_year_rows, on="fire_id", how="left", validate="many_to_one")
    out["relative_recovery_nbr"] = out.apply(
        lambda row: _relative_recovery(row["NBR"], row["NBR_pre"], row["NBR_fire"]),
        axis=1,
    )
    out["relative_recovery_ndvi"] = out.apply(
        lambda row: _relative_recovery(row["NDVI"], row["NDVI_pre"], row["NDVI_fire"]),
        axis=1,
    )
    out["recovery_metric_valid"] = out["dNBR"] >= MIN_VALID_DNBR
    out.loc[~out["recovery_metric_valid"], ["relative_recovery_nbr", "relative_recovery_ndvi"]] = np.nan
    return out


def _first_non_null(series: pd.Series) -> float:
    values = series.dropna()
    return values.iloc[0] if not values.empty else np.nan


def _value_at_year(group: pd.DataFrame, column: str, years_since_fire: int) -> float:
    values = group.loc[group["years_since_fire"] == years_since_fire, column].dropna()
    return values.iloc[0] if not values.empty else np.nan


def summarize_fire(fire_id: str, group: pd.DataFrame) -> dict:
    group = group.sort_values("years_since_fire")
    recovery_0yr = _value_at_year(group, "relative_recovery_nbr", 0)
    recovery = {
        f"recovery_{year}yr": _value_at_year(group, "relative_recovery_nbr", year)
        for year in TRAJECTORY_YEARS
    }
    recovery_ndvi = {
        f"recovery_ndvi_{year}yr": _value_at_year(group, "relative_recovery_ndvi", year)
        for year in TRAJECTORY_YEARS
    }

    postfire = group.loc[group["years_since_fire"] >= 1]
    reached_80 = postfire.loc[postfire["relative_recovery_nbr"] >= 0.80, "years_since_fire"]

    row = {
        "fire_id": fire_id,
        "fire_year": _first_non_null(group["fire_year"]),
        "fire_cohort": _first_non_null(group["fire_cohort"]),
        "area_ha": _first_non_null(group["area_ha"]),
        "centroid_lat": _first_non_null(group["centroid_lat"]),
        "centroid_lon": _first_non_null(group["centroid_lon"]),
        "dNBR": _first_non_null(group["dNBR"]),
        "recovery_metric_valid": bool(_first_non_null(group["recovery_metric_valid"])),
        "recovery_exclusion_reason": ""
        if bool(_first_non_null(group["recovery_metric_valid"]))
        else "low_or_negative_dnbr",
        "NBR_pre": _first_non_null(group["NBR_pre"]),
        "NBR_fire": _value_at_year(group, "NBR", 0),
        "NDVI_pre": _first_non_null(group["NDVI_pre"]),
        "NDVI_fire": _value_at_year(group, "NDVI", 0),
        **recovery,
        **recovery_ndvi,
        "rate_0_3yr": (recovery["recovery_3yr"] - recovery_0yr) / 3
        if pd.notna(recovery["recovery_3yr"]) and pd.notna(recovery_0yr)
        else np.nan,
        "rate_0_5yr": (recovery["recovery_5yr"] - recovery_0yr) / 5
        if pd.notna(recovery["recovery_5yr"]) and pd.notna(recovery_0yr)
        else np.nan,
        "rate_0_10yr": (recovery["recovery_10yr"] - recovery_0yr) / 10
        if pd.notna(recovery["recovery_10yr"]) and pd.notna(recovery_0yr)
        else np.nan,
        "years_to_80pct": reached_80.min() if not reached_80.empty else np.nan,
        "n_postfire_observations": int(postfire["relative_recovery_nbr"].notna().sum()),
    }
    return row


def build_recovery_qa_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    total = len(metrics)
    valid = int(metrics["recovery_metric_valid"].sum())
    excluded = total - valid
    return pd.DataFrame(
        [
            {
                "total_fire_events": total,
                "valid_recovery_fire_events": valid,
                "excluded_low_dnbr": excluded,
                "valid_percentage": (valid / total * 100) if total else np.nan,
                "valid_n_recovery_3yr": int(metrics["recovery_3yr"].notna().sum()),
                "valid_n_recovery_5yr": int(metrics["recovery_5yr"].notna().sum()),
                "valid_n_recovery_10yr": int(metrics["recovery_10yr"].notna().sum()),
            }
        ]
    )


def build_recovery_metrics(write: bool = True) -> pd.DataFrame:
    analysis = add_relative_recovery(load_analysis_dataset())
    rows = [
        summarize_fire(fire_id, group)
        for fire_id, group in analysis.groupby("fire_id", sort=False)
    ]
    metrics = pd.DataFrame(rows)

    metrics = metrics.sort_values(["fire_year", "fire_id"]).reset_index(drop=True)
    if write:
        OUTPUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
        metrics.to_csv(OUTPUT_TABLE, index=False)
        build_recovery_qa_summary(metrics).to_csv(QA_SUMMARY_TABLE, index=False)
        print(f"Wrote {OUTPUT_TABLE}")
        print(f"Wrote {QA_SUMMARY_TABLE}")
    return metrics


if __name__ == "__main__":
    build_recovery_metrics(write=True)
