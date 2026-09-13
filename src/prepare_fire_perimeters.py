from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen, Request
import re
import zipfile

import geopandas as gpd
import pandas as pd
import yaml
from shapely import force_2d


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "config.yml"
RAW_DIR = ROOT / "data" / "raw" / "nfdb_fire_poly"
PROCESSED = ROOT / "data" / "processed"
NFDB_URL = "https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_poly/current_version/"
LOCAL_NFDB_DIRS = [
    Path("/Users/jano/Downloads/NFDB_poly"),
]
NAD83 = "EPSG:4269"


def load_config() -> dict:
    with CONFIG.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_nfdb_zip_url() -> str:
    request = Request(NFDB_URL, headers={"User-Agent": "lebel-fire-recovery/1.0"})
    html = urlopen(request, timeout=60).read().decode("utf-8", errors="replace")
    matches = re.findall(r'href="([^"]*NFDB_poly[^"]*\.zip)"', html, flags=re.I)
    if not matches:
        matches = re.findall(r'href="([^"]*\.zip)"', html, flags=re.I)
    if not matches:
        raise RuntimeError(f"No NFDB ZIP archive found at {NFDB_URL}")
    return urljoin(NFDB_URL, matches[0])


def download_zip(url: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / Path(url).name
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path

    request = Request(url, headers={"User-Agent": "lebel-fire-recovery/1.0"})
    with urlopen(request, timeout=120) as response, zip_path.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    return zip_path


def extract_zip(zip_path: Path) -> Path:
    extract_dir = RAW_DIR / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    return extract_dir


def find_vector_files(search_dir: Path) -> list[Path]:
    files = []
    for pattern in ("*.gpkg", "*.shp"):
        files.extend(sorted(search_dir.rglob(pattern)))
    return files


def find_local_vector_files() -> list[Path]:
    for directory in LOCAL_NFDB_DIRS:
        if directory.exists():
            files = find_vector_files(directory)
            if files:
                return files
    return []


def read_nfdb_vectors() -> tuple[gpd.GeoDataFrame, list[Path], str]:
    vector_files = find_local_vector_files()
    source = "local"
    if not vector_files:
        zip_url = find_nfdb_zip_url()
        zip_path = download_zip(zip_url)
        vector_files = find_vector_files(extract_zip(zip_path))
        source = f"downloaded archive: {zip_path}"
    if not vector_files:
        raise RuntimeError("No GeoPackage or shapefile found for NFDB fire perimeters")

    frames = []
    for path in vector_files:
        frame = gpd.read_file(path)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise ValueError(f"NFDB vector files are empty: {vector_files}")

    crs = frames[0].crs
    for i, frame in enumerate(frames):
        if frame.crs is None:
            raise ValueError(f"NFDB vector file has no CRS: {vector_files[i]}")
        if frame.crs != crs:
            frames[i] = frame.to_crs(crs)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs), vector_files, source


def choose_field(columns: list[str], candidates: list[str], contains: list[str] | None = None) -> str:
    upper_lookup = {col.upper(): col for col in columns}
    for candidate in candidates:
        if candidate.upper() in upper_lookup:
            return upper_lookup[candidate.upper()]
    if contains:
        for col in columns:
            name = col.upper()
            if all(token.upper() in name for token in contains):
                return col
    raise ValueError(f"Could not identify field from candidates {candidates}")


def fire_cohort(year: int) -> str:
    if 1984 <= year <= 1994:
        return "1984-1994"
    if 1995 <= year <= 2004:
        return "1995-2004"
    if 2005 <= year <= 2014:
        return "2005-2014"
    if 2015 <= year <= 2022:
        return "2015-2022"
    return "2023+"


def prepare_fire_events() -> tuple[pd.DataFrame, Path]:
    config = load_config()
    study = config["study_area"]
    analysis = config["analysis"]

    fires, vector_paths, source = read_nfdb_vectors()
    if fires.empty:
        raise ValueError(f"NFDB vector files are empty: {vector_paths}")
    if fires.crs is None:
        raise ValueError(f"NFDB vector files have no CRS: {vector_paths}")

    fire_id_field = choose_field(
        list(fires.columns),
        ["NFDBFIREID", "FIRE_ID", "FIREID", "ID"],
        contains=["FIRE", "ID"],
    )
    fire_year_field = choose_field(
        list(fires.columns),
        ["YEAR", "FIRE_YEAR", "REP_YEAR", "YEAR_", "YR"],
        contains=["YEAR"],
    )
    area_field = choose_field(
        list(fires.columns),
        ["SIZE_HA", "AREA_HA", "POLY_HA", "GIS_HA", "HECTARES", "HA"],
        contains=["HA"],
    )

    fires = fires[[fire_id_field, fire_year_field, area_field, "geometry"]].copy()
    fires = fires.rename(
        columns={
            fire_id_field: "fire_id",
            fire_year_field: "fire_year",
            area_field: "source_area_ha",
        }
    )
    fires["fire_year"] = pd.to_numeric(fires["fire_year"], errors="coerce")
    fires["source_area_ha"] = pd.to_numeric(fires["source_area_ha"], errors="coerce")
    fires = fires.dropna(subset=["fire_id", "fire_year", "geometry"])
    fires["fire_year"] = fires["fire_year"].astype(int)

    source_crs = fires.crs
    center = gpd.GeoSeries(
        gpd.points_from_xy([study["longitude"]], [study["latitude"]]),
        crs=NAD83,
    ).to_crs(source_crs)
    aoi = center.buffer(float(study["radius_km"]) * 1000).iloc[0]

    fires_eq = fires.copy()
    intersects = fires_eq.geometry.intersects(aoi)
    fires_eq = fires_eq.loc[intersects].copy()
    fires_eq["geometry"] = fires_eq.geometry.intersection(aoi)
    fires_eq = fires_eq.loc[~fires_eq.geometry.is_empty & fires_eq.geometry.notna()].copy()
    fires_eq["geometry"] = fires_eq.geometry.simplify(60, preserve_topology=True)
    fires_eq["area_ha"] = fires_eq.geometry.area / 10000
    fires_eq.loc[fires_eq["source_area_ha"].notna(), "area_ha"] = fires_eq["source_area_ha"]

    fires_eq = fires_eq.loc[
        (fires_eq["fire_year"] >= int(analysis["start_year"]))
        & (fires_eq["area_ha"] >= float(analysis["minimum_fire_area_ha"]))
    ].copy()

    centroids = fires_eq.geometry.centroid
    centroid_wgs = gpd.GeoSeries(centroids, crs=source_crs).to_crs(NAD83)
    fires_eq["centroid_lon"] = centroid_wgs.x
    fires_eq["centroid_lat"] = centroid_wgs.y
    fires_eq["fire_cohort"] = fires_eq["fire_year"].apply(fire_cohort)

    out = fires_eq[["fire_id", "fire_year", "fire_cohort", "area_ha", "centroid_lat", "centroid_lon", "geometry"]]
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=source_crs).to_crs(NAD83)
    out["fire_id"] = out["fire_id"].astype(str)
    out = out.sort_values(["fire_year", "fire_id"]).reset_index(drop=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    csv_path = PROCESSED / "fire_events.csv"
    geojson_path = PROCESSED / "fire_events.geojson"
    out.drop(columns=["geometry", "fire_cohort"]).to_csv(csv_path, index=False)
    # Earth Engine requires 2D WGS84 GeoJSON geometries.
    out["geometry"] = out.geometry.apply(force_2d)
    out = out.to_crs("EPSG:4326")
    out.to_file(geojson_path, driver="GeoJSON")

    print(f"NFDB source: {source}")
    print(f"NFDB vector files: {', '.join(str(path) for path in vector_paths)}")
    print(f"Detected fields: fire_id={fire_id_field}, fire_year={fire_year_field}, area_ha={area_field}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {geojson_path}")
    print(f"Fire events retained: {len(out)}")
    return out.drop(columns="geometry"), geojson_path


if __name__ == "__main__":
    prepare_fire_events()
