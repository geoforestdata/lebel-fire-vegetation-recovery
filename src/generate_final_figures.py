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
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "outputs" / "tables"
FIGURES = ROOT / "outputs" / "figures"
FIRE_GEOJSON = PROCESSED / "fire_events.geojson"
RECOVERY_METRICS = TABLES / "recovery_metrics.csv"
COHORT_SUMMARY = TABLES / "cohort_summary.csv"
MODEL_TABLE = TABLES / "climate_recovery_models.csv"
CRS_MAP = "EPSG:3978"
CRS_BASEMAP = "EPSG:3857"
NAD83 = "EPSG:4269"
COHORT_ORDER = ["1984-1994", "1995-2004", "2005-2014", "2015-2022", "2023+"]
COHORT_COLORS = {
    "1984-1994": "#3B5F7D",
    "1995-2004": "#5B7493",
    "2005-2014": "#927A4D",
    "2015-2022": "#B56645",
    "2023+": "#7A3F3B",
}
BASEMAP_PROVIDER = "Esri.WorldGrayCanvas"


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


def add_cartodb_positron(ax) -> bool:
    try:
        import contextily as cx

        provider = cx.providers.Esri.WorldGrayCanvas
        cx.add_basemap(
            ax,
            source=provider,
            attribution=False,
            zoom=8,
            alpha=0.92,
        )
        return True
    except Exception as exc:
        print(f"Basemap unavailable; using local fallback background. Reason: {exc}")
        ax.set_facecolor("#F6F6F3")
        return False


def add_scale_bar(ax, length_km: int = 50) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    length_m = length_km * 1000
    x_start = x0 + 0.07 * (x1 - x0)
    y_start = y0 + 0.08 * (y1 - y0)
    ax.plot([x_start, x_start + length_m], [y_start, y_start], color="#222222", linewidth=1.3, solid_capstyle="butt", zorder=10)
    ax.text(x_start + length_m / 2, y_start + 0.018 * (y1 - y0), f"{length_km} km", ha="center", va="bottom", fontsize=8, color="#222222", zorder=10)


def add_locator_inset(fig, ax, center_lon: float, center_lat: float) -> None:
    inset = inset_axes(ax, width="24%", height="24%", loc="upper right", borderpad=1.1)
    inset.set_facecolor("white")
    try:
        url = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces.zip"
        provinces = gpd.read_file(url)
        quebec = provinces.loc[
            (provinces["admin"].eq("Canada")) & (provinces["name_en"].eq("Quebec"))
        ].to_crs(NAD83)
        if quebec.empty:
            raise ValueError("Quebec outline not found in Natural Earth layer")
        quebec.boundary.plot(ax=inset, color="#555555", linewidth=0.6)
        inset.scatter([center_lon], [center_lat], s=16, color="#B56645", zorder=5)
        inset.set_xlim(-81.5, -56.0)
        inset.set_ylim(44.0, 63.5)
        inset.text(-80.5, 62.0, "Quebec", fontsize=7, color="#333333")
    except Exception as exc:
        print(f"Locator boundary unavailable; using schematic locator. Reason: {exc}")
        inset.plot([-80, -57, -57, -80, -80], [45, 45, 63, 63, 45], color="#777777", linewidth=0.7)
        inset.scatter([center_lon], [center_lat], s=16, color="#B56645", zorder=5)
        inset.text(-79.2, 61.2, "Quebec", fontsize=7, color="#333333")
        inset.set_xlim(-84, -54)
        inset.set_ylim(43, 65)
    inset.set_xticks([])
    inset.set_yticks([])
    for spine in inset.spines.values():
        spine.set_color("#BDBDBD")
        spine.set_linewidth(0.6)
    inset.set_title("Location", fontsize=7, pad=2)


def figure_01_map() -> None:
    require(FIRE_GEOJSON)
    fires = gpd.read_file(FIRE_GEOJSON).set_crs(NAD83, allow_override=True).to_crs(CRS_MAP)
    center = gpd.GeoDataFrame(
        {"name": ["Lebel-sur-Quévillon"]},
        geometry=[Point(-76.98, 49.05)],
        crs=NAD83,
    ).to_crs(CRS_MAP)
    aoi = gpd.GeoDataFrame(geometry=center.buffer(150_000), crs=CRS_MAP)
    fires_plot = fires.to_crs(CRS_BASEMAP)
    center_plot = center.to_crs(CRS_BASEMAP)
    aoi_plot = aoi.to_crs(CRS_BASEMAP)

    bounds = aoi_plot.total_bounds
    margin = 24_000
    xlim = (bounds[0] - margin, bounds[2] + margin)
    ylim = (bounds[1] - margin, bounds[3] + margin)

    fig, ax = plt.subplots(figsize=(9.0, 6.8))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    add_cartodb_positron(ax)

    aoi_plot.boundary.plot(ax=ax, color="#2A2A2A", linewidth=0.85, linestyle=(0, (4, 3)), alpha=0.72, zorder=3)
    for cohort in COHORT_ORDER:
        subset = fires_plot.loc[fires_plot["fire_cohort"] == cohort] if "fire_cohort" in fires_plot else fires_plot.loc[fires_plot["fire_year"].apply(cohort_for_year) == cohort]
        if not subset.empty:
            subset.plot(
                ax=ax,
                facecolor=COHORT_COLORS[cohort],
                edgecolor="#FBFBFB",
                linewidth=0.12,
                alpha=0.76,
                zorder=4,
            )
    center_plot.plot(ax=ax, color="#111111", markersize=28, zorder=6)
    x, y = center_plot.geometry.iloc[0].x, center_plot.geometry.iloc[0].y
    ax.annotate(
        "Lebel-sur-Quévillon",
        xy=(x, y),
        xytext=(x - 88_000, y + 40_000),
        fontsize=9,
        ha="left",
        va="center",
        arrowprops={"arrowstyle": "-", "color": "#333333", "linewidth": 0.65},
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 1.5},
        zorder=7,
    )
    ax.text(0.01, 1.055, "39 years of wildfire history around Lebel-sur-Quévillon", transform=ax.transAxes, fontsize=14, fontweight="bold", ha="left", va="bottom")
    ax.text(0.01, 1.018, "78 fires ≥100 ha, 1985–2023", transform=ax.transAxes, fontsize=9.5, ha="left", va="bottom", color="#555555")
    ax.set_axis_off()
    handles = [
        Patch(facecolor=COHORT_COLORS[cohort], edgecolor="none", label=cohort, alpha=0.78)
        for cohort in COHORT_ORDER
    ]
    ax.legend(handles=handles, frameon=True, facecolor="white", edgecolor="#D0D0D0", framealpha=0.88, title="Fire cohort", title_fontsize=8, loc="lower right", borderpad=0.6, labelspacing=0.45, handlelength=1.2)
    add_scale_bar(ax, 50)
    add_locator_inset(fig, ax, -76.98, 49.05)
    ax.set_aspect("equal")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.91, bottom=0.02)
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
