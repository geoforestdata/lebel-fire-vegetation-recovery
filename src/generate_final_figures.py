from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / "tmp" / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "data" / "tmp" / "xdg-cache"))

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from recovery_metrics import add_relative_recovery, load_analysis_dataset


import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "outputs" / "tables"
FIGURES = ROOT / "outputs" / "figures"
FIRE_GEOJSON = PROCESSED / "fire_events.geojson"
RECOVERY_METRICS = TABLES / "recovery_metrics.csv"
COHORT_SUMMARY = TABLES / "cohort_summary.csv"
MODEL_TABLE = TABLES / "climate_recovery_models.csv"
CRS_MAP = "EPSG:3978"
NAD83 = "EPSG:4269"
COHORT_ORDER = ["1984-1994", "1995-2004", "2005-2014", "2015-2022", "2023+"]
COHORT_COLORS = {
    "1984-1994": "#355C7D",
    "1995-2004": "#6C5B7B",
    "2005-2014": "#C06C84",
    "2015-2022": "#F08A5D",
    "2023+": "#2A9D8F",
}


def configure_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "axes.edgecolor": "#666666",
            "axes.linewidth": 0.7,
            "xtick.color": "#333333",
            "ytick.color": "#333333",
            "axes.labelcolor": "#222222",
            "text.color": "#222222",
        }
    )


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")


def save_figure(fig: plt.Figure, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    png = FIGURES / f"{name}.png"
    svg = FIGURES / f"{name}.svg"
    fig.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.04)
    fig.savefig(svg, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    print(f"Wrote {png}")
    print(f"Wrote {svg}")


def clean_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#E5E5E5", linewidth=0.6)


def add_cohort_axis(ax) -> None:
    ax.set_xticks(range(len(COHORT_ORDER)))
    ax.set_xticklabels(COHORT_ORDER, rotation=30, ha="right")


def figure_01_map() -> None:
    require(FIRE_GEOJSON)
    fires = gpd.read_file(FIRE_GEOJSON).set_crs(NAD83, allow_override=True).to_crs(CRS_MAP)
    center = gpd.GeoDataFrame(
        {"name": ["Lebel-sur-Quevillon"]},
        geometry=[Point(-76.98, 49.05)],
        crs=NAD83,
    ).to_crs(CRS_MAP)
    aoi = gpd.GeoDataFrame(geometry=center.buffer(150_000), crs=CRS_MAP)

    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    aoi.boundary.plot(ax=ax, color="#222222", linewidth=0.8, linestyle=(0, (3, 2)))
    for cohort in COHORT_ORDER:
        subset = fires.loc[fires["fire_cohort"] == cohort] if "fire_cohort" in fires else fires.loc[fires["fire_year"].apply(cohort_for_year) == cohort]
        if not subset.empty:
            subset.plot(
                ax=ax,
                facecolor=COHORT_COLORS[cohort],
                edgecolor="white",
                linewidth=0.25,
                alpha=0.78,
            )
    center.plot(ax=ax, color="#111111", markersize=22, zorder=5)
    x, y = center.geometry.iloc[0].x, center.geometry.iloc[0].y
    ax.text(x + 7000, y + 7000, "Lebel-sur-Quevillon", fontsize=8, ha="left", va="bottom")
    ax.set_title("Study area and wildfire history", loc="left", pad=8)
    ax.set_axis_off()
    handles = [
        Patch(facecolor=COHORT_COLORS[cohort], edgecolor="none", label=cohort, alpha=0.78)
        for cohort in COHORT_ORDER
    ]
    ax.legend(handles=handles, frameon=False, title="Fire cohort", title_fontsize=8, loc="lower left")
    ax.set_aspect("equal")
    save_figure(fig, "01_study_area_fire_history")


def cohort_for_year(year) -> str:
    year = int(year)
    if 1984 <= year <= 1994:
        return "1984-1994"
    if 1995 <= year <= 2004:
        return "1995-2004"
    if 2005 <= year <= 2014:
        return "2005-2014"
    if 2015 <= year <= 2022:
        return "2015-2022"
    return "2023+"


def figure_02_trajectories() -> None:
    analysis = add_relative_recovery(load_analysis_dataset())
    data = analysis.loc[analysis["years_since_fire"].between(0, 10)].copy()
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for cohort in COHORT_ORDER:
        subset = data.loc[data["fire_cohort"] == cohort]
        if subset.empty:
            continue
        grouped = subset.groupby("years_since_fire")["relative_recovery_nbr"]
        stats = grouped.agg(["median", "count", lambda x: x.quantile(0.25), lambda x: x.quantile(0.75)])
        stats.columns = ["median", "count", "q25", "q75"]
        stats = stats.loc[stats["count"] > 0]
        if stats.empty:
            continue
        max_n = int(stats["count"].max())
        ax.plot(
            stats.index,
            stats["median"],
            color=COHORT_COLORS[cohort],
            linewidth=1.8,
            label=f"{cohort} (max n={max_n})",
        )
        supported = stats.loc[stats["count"] >= 3]
        if not supported.empty:
            ax.fill_between(
                supported.index.to_numpy(dtype=float),
                supported["q25"].to_numpy(dtype=float),
                supported["q75"].to_numpy(dtype=float),
                color=COHORT_COLORS[cohort],
                alpha=0.12,
                linewidth=0,
            )
    ax.axhline(0.8, color="#777777", linewidth=0.8, linestyle=(0, (3, 3)))
    ax.axhline(1.0, color="#222222", linewidth=0.8, linestyle=(0, (2, 2)))
    ax.text(9.85, 1.0, "pre-fire NBR level", va="center", ha="right", fontsize=8, color="#222222")
    ax.text(9.85, 0.8, "80% recovery threshold", va="center", ha="right", fontsize=8, color="#555555")
    ax.set_xlim(0, 10)
    ax.set_xlabel("Years since fire")
    ax.set_ylabel("Relative NBR recovery")
    ax.set_title("Post-fire recovery trajectories", loc="left", pad=8)
    clean_axes(ax)
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    fig.subplots_adjust(bottom=0.24)
    save_figure(fig, "02_recovery_trajectories")


def scatter_box_panel(ax, metrics: pd.DataFrame, column: str, title: str, ylabel: str | None = None) -> None:
    positions = []
    data = []
    labels = []
    colors = []
    for i, cohort in enumerate(COHORT_ORDER):
        values = metrics.loc[metrics["fire_cohort"] == cohort, column].dropna()
        if values.empty:
            continue
        positions.append(i)
        data.append(values)
        labels.append(f"{cohort}\nn={len(values)}")
        colors.append(COHORT_COLORS[cohort])
    if data:
        box = ax.boxplot(
            data,
            positions=positions,
            widths=0.52,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": "#111111", "linewidth": 1.1},
            boxprops={"linewidth": 0.8, "color": "#555555"},
            whiskerprops={"linewidth": 0.8, "color": "#555555"},
            capprops={"linewidth": 0.8, "color": "#555555"},
        )
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.24)
        rng = np.random.default_rng(42)
        for pos, values, color in zip(positions, data, colors):
            jitter = rng.normal(0, 0.035, len(values))
            ax.scatter(np.full(len(values), pos) + jitter, values, s=12, color=color, alpha=0.65, linewidths=0)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_title(title, loc="left", pad=6)
    if ylabel:
        ax.set_ylabel(ylabel)
    clean_axes(ax)


def figure_03_common_ages(metrics: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.8), sharey=True)
    for ax, year in zip(axes, [3, 5, 10]):
        scatter_box_panel(ax, metrics, f"recovery_{year}yr", f"{year} years")
    axes[0].set_ylabel("Relative NBR recovery")
    fig.suptitle("Recovery at common post-fire ages", x=0.05, y=0.98, ha="left", fontsize=10)
    fig.subplots_adjust(wspace=0.22, top=0.86, bottom=0.28)
    save_figure(fig, "03_recovery_common_ages")


def point_range_panel(ax, metrics: pd.DataFrame, column: str, title: str, ylabel: str | None = None) -> None:
    xs, medians, lows, highs, labels = [], [], [], [], []
    for i, cohort in enumerate(COHORT_ORDER):
        values = metrics.loc[metrics["fire_cohort"] == cohort, column].dropna()
        if values.empty:
            continue
        xs.append(i)
        medians.append(values.median())
        lows.append(values.quantile(0.25))
        highs.append(values.quantile(0.75))
        labels.append(f"{cohort}\nn={len(values)}")
    if xs:
        lower = np.array(medians) - np.array(lows)
        upper = np.array(highs) - np.array(medians)
        ax.errorbar(xs, medians, yerr=[lower, upper], fmt="o", color="#222222", ecolor="#777777", capsize=3, markersize=4)
    ax.axhline(0, color="#888888", linewidth=0.7, linestyle=(0, (2, 2)))
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_title(title, loc="left", pad=6)
    if ylabel:
        ax.set_ylabel(ylabel)
    clean_axes(ax)


def figure_04_climate(metrics: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.8))
    point_range_panel(axes[0], metrics, "temp_anomaly_1_3yr", "Temperature", "Anomaly")
    point_range_panel(axes[1], metrics, "precip_anomaly_1_3yr", "Precipitation")
    point_range_panel(axes[2], metrics, "vpd_anomaly_1_3yr", "VPD")
    fig.suptitle("Early post-fire climate exposure by cohort", x=0.05, y=0.98, ha="left", fontsize=10)
    fig.subplots_adjust(wspace=0.30, top=0.86, bottom=0.28)
    save_figure(fig, "04_postfire_climate_by_cohort")


def fit_annotation(models: pd.DataFrame, model_type: str, predictor: str) -> tuple[float, float, int]:
    row = models.loc[(models["model_type"] == model_type) & (models["predictor"] == predictor)]
    if row.empty:
        return np.nan, np.nan, 0
    first = row.iloc[0]
    return first["coefficient"], first["r_squared"], int(first["n"])


def climate_scatter_panel(ax, metrics: pd.DataFrame, models: pd.DataFrame, xcol: str, model_type: str, predictor: str, xlabel: str) -> None:
    data = metrics[[xcol, "recovery_3yr", "fire_cohort"]].dropna()
    for cohort in COHORT_ORDER:
        subset = data.loc[data["fire_cohort"] == cohort]
        if not subset.empty:
            ax.scatter(subset[xcol], subset["recovery_3yr"], s=18, color=COHORT_COLORS[cohort], alpha=0.72, linewidths=0)
    slope, r2, n = fit_annotation(models, model_type, predictor)
    if len(data) >= 3 and pd.notna(slope):
        x = np.linspace(data[xcol].min(), data[xcol].max(), 100)
        y = slope * (x - data[xcol].mean()) + data["recovery_3yr"].mean()
        ax.plot(x, y, color="#111111", linewidth=1.1)
    ax.text(
        0.03,
        0.97,
        f"n={n}\nslope={slope:.3f}\nR2={r2:.2f}" if n else "n=0",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
    )
    ax.set_xlabel(xlabel)
    clean_axes(ax)


def figure_05_climate_vs_recovery(metrics: pd.DataFrame, models: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.4), sharey=True)
    climate_scatter_panel(axes[0], metrics, models, "temp_anomaly_1_3yr", "temperature_only", "temp_anomaly_1_3yr", "Temp anomaly")
    climate_scatter_panel(axes[1], metrics, models, "precip_anomaly_1_3yr", "precipitation_only", "precip_anomaly_1_3yr", "Precip anomaly")
    climate_scatter_panel(axes[2], metrics, models, "vpd_anomaly_1_3yr", "vpd_only", "vpd_anomaly_1_3yr", "VPD anomaly")
    axes[0].set_ylabel("Recovery at 3 years")
    fig.suptitle("Climate anomalies and early recovery", x=0.05, y=0.98, ha="left", fontsize=10)
    fig.subplots_adjust(wspace=0.18, top=0.84, bottom=0.20)
    save_figure(fig, "05_climate_vs_recovery")


def figure_06_summary(metrics: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.7))
    point_range_panel(axes[0], metrics, "recovery_3yr", "A. Early recovery", "Median and IQR")
    axes[0].axhline(0.8, color="#777777", linewidth=0.7, linestyle=(0, (3, 3)))
    point_range_panel(axes[1], metrics, "vpd_anomaly_1_3yr", "B. Early VPD anomaly")
    fig.suptitle("Early recovery and drying exposure", x=0.05, y=0.98, ha="left", fontsize=10)
    fig.subplots_adjust(wspace=0.28, top=0.84, bottom=0.28)
    save_figure(fig, "06_recovery_change_summary")


def generate_final_figures() -> None:
    configure_style()
    for path in [FIRE_GEOJSON, RECOVERY_METRICS, COHORT_SUMMARY, MODEL_TABLE]:
        require(path)
    metrics = pd.read_csv(RECOVERY_METRICS)
    models = pd.read_csv(MODEL_TABLE)
    figure_01_map()
    figure_02_trajectories()
    figure_03_common_ages(metrics)
    figure_04_climate(metrics)
    figure_05_climate_vs_recovery(metrics, models)
    figure_06_summary(metrics)


if __name__ == "__main__":
    generate_final_figures()
