from pathlib import Path

import numpy as np
import pandas as pd

from climate_metrics import build_climate_metrics
from recovery_metrics import build_recovery_qa_summary


ROOT = Path(__file__).resolve().parents[1]
TABLE_DIR = ROOT / "outputs" / "tables"
RECOVERY_METRICS = TABLE_DIR / "recovery_metrics.csv"
COHORT_SUMMARY = TABLE_DIR / "cohort_summary.csv"
MODEL_TABLE = TABLE_DIR / "climate_recovery_models.csv"
QA_SUMMARY_TABLE = TABLE_DIR / "recovery_qa_summary.csv"

COHORT_ORDER = ["1984-1994", "1995-2004", "2005-2014", "2015-2022", "2023+"]
WINDOWS = {
    3: {
        "response": "recovery_3yr",
        "temp": "temp_anomaly_1_3yr",
        "precip": "precip_anomaly_1_3yr",
        "vpd": "vpd_anomaly_1_3yr",
    },
    5: {
        "response": "recovery_5yr",
        "temp": "temp_anomaly_1_5yr",
        "precip": "precip_anomaly_1_5yr",
        "vpd": "vpd_anomaly_1_5yr",
    },
    10: {
        "response": "recovery_10yr",
        "temp": "temp_anomaly_1_10yr",
        "precip": "precip_anomaly_1_10yr",
        "vpd": "vpd_anomaly_1_10yr",
    },
}


def _count(series: pd.Series) -> int:
    return int(series.notna().sum())


def build_cohort_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cohort in COHORT_ORDER:
        group = metrics.loc[metrics["fire_cohort"] == cohort]
        if group.empty:
            continue

        rows.append(
            {
                "fire_cohort": cohort,
                "n_fires_total": int(group["fire_id"].nunique()),
                "n_recovery_3yr": _count(group["recovery_3yr"]),
                "median_recovery_3yr": group["recovery_3yr"].median(),
                "mean_recovery_3yr": group["recovery_3yr"].mean(),
                "n_recovery_5yr": _count(group["recovery_5yr"]),
                "median_recovery_5yr": group["recovery_5yr"].median(),
                "mean_recovery_5yr": group["recovery_5yr"].mean(),
                "n_recovery_10yr": _count(group["recovery_10yr"]),
                "median_recovery_10yr": group["recovery_10yr"].median(),
                "mean_recovery_10yr": group["recovery_10yr"].mean(),
                "median_rate_0_3yr": group["rate_0_3yr"].median(),
                "median_rate_0_5yr": group["rate_0_5yr"].median(),
                "median_rate_0_10yr": group["rate_0_10yr"].median(),
                "median_years_to_80pct": group["years_to_80pct"].median(),
                "median_dNBR": group["dNBR"].median(),
                "median_temp_anomaly_1_3yr": group["temp_anomaly_1_3yr"].median(),
                "median_precip_anomaly_1_3yr": group["precip_anomaly_1_3yr"].median(),
                "median_vpd_anomaly_1_3yr": group["vpd_anomaly_1_3yr"].median(),
                "median_temp_anomaly_1_5yr": group["temp_anomaly_1_5yr"].median(),
                "median_precip_anomaly_1_5yr": group["precip_anomaly_1_5yr"].median(),
                "median_vpd_anomaly_1_5yr": group["vpd_anomaly_1_5yr"].median(),
            }
        )

    return pd.DataFrame(rows)


def _fit_ols(
    data: pd.DataFrame,
    response: str,
    predictors: list[str],
    window_years: int,
    model_type: str,
) -> list[dict]:
    model_data = data[[response, *predictors]].replace([np.inf, -np.inf], np.nan).dropna()
    n = len(model_data)
    min_n = len(predictors) + 2
    if n < min_n:
        return []

    import statsmodels.api as sm

    y = model_data[response]
    x = sm.add_constant(model_data[predictors], has_constant="add")
    fit = sm.OLS(y, x).fit()

    rows = []
    for predictor in predictors:
        rows.append(
            {
                "response": response,
                "window_years": window_years,
                "model_type": model_type,
                "predictor": predictor,
                "coefficient": fit.params.get(predictor, np.nan),
                "std_error": fit.bse.get(predictor, np.nan),
                "p_value": fit.pvalues.get(predictor, np.nan),
                "n": n,
                "r_squared": fit.rsquared,
            }
        )
    return rows


def build_model_table(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for window_years, columns in WINDOWS.items():
        response = columns["response"]
        rows.extend(
            _fit_ols(
                metrics,
                response,
                [columns["temp"], columns["precip"], columns["vpd"], "dNBR", "fire_year"],
                window_years,
                "multivariable",
            )
        )
        rows.extend(
            _fit_ols(
                metrics,
                response,
                [columns["temp"]],
                window_years,
                "temperature_only",
            )
        )
        rows.extend(
            _fit_ols(
                metrics,
                response,
                [columns["precip"]],
                window_years,
                "precipitation_only",
            )
        )
        rows.extend(
            _fit_ols(
                metrics,
                response,
                [columns["vpd"]],
                window_years,
                "vpd_only",
            )
        )

    columns = [
        "response",
        "window_years",
        "model_type",
        "predictor",
        "coefficient",
        "std_error",
        "p_value",
        "n",
        "r_squared",
    ]
    return pd.DataFrame(rows, columns=columns)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    metrics = build_climate_metrics(write=True)
    cohort_summary = build_cohort_summary(metrics)
    model_table = build_model_table(metrics)
    qa_summary = build_recovery_qa_summary(metrics)

    cohort_summary.to_csv(COHORT_SUMMARY, index=False)
    model_table.to_csv(MODEL_TABLE, index=False)
    qa_summary.to_csv(QA_SUMMARY_TABLE, index=False)

    print(f"Wrote {RECOVERY_METRICS}")
    print(f"Wrote {QA_SUMMARY_TABLE}")
    print(f"Wrote {COHORT_SUMMARY}")
    print(f"Wrote {MODEL_TABLE}")
    print("Recovery sample sizes:")
    for window_years in [3, 5, 10]:
        column = f"recovery_{window_years}yr"
        print(f"- {column}: {int(metrics[column].notna().sum())}")


if __name__ == "__main__":
    main()
