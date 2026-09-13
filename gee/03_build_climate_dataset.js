// Build fire_climate_timeseries.csv from ERA5-Land hourly data.
// Update FIRE_ASSET and field names after uploading NRCan NFDB fire perimeters.

var CONFIG = {
  latitude: 49.05,
  longitude: -76.98,
  radiusKm: 150,
  startYear: 1984,
  endYear: 2025,
  minimumFireAreaHa: 100,
  summerStartMonth: 6,
  summerEndMonth: 8,
  baselineStartYear: 1991,
  baselineEndYear: 2020,
  fireAsset: 'users/your_username/NFDB_poly',
  fireIdField: 'NFDBFIREID',
  fireYearField: 'YEAR',
  fireAreaHaField: 'SIZE_HA'
};

var center = ee.Geometry.Point([CONFIG.longitude, CONFIG.latitude]);
var aoi = center.buffer(CONFIG.radiusKm * 1000);
var years = ee.List.sequence(CONFIG.startYear, CONFIG.endYear);
var baselineYears = ee.List.sequence(CONFIG.baselineStartYear, CONFIG.baselineEndYear);

function cleanFire(feature) {
  var geom = feature.geometry().intersection(aoi, ee.ErrorMargin(30));
  var year = ee.Number.parse(feature.get(CONFIG.fireYearField));
  var sourceArea = ee.Number.parse(feature.get(CONFIG.fireAreaHaField));
  var computedArea = geom.area(30).divide(10000);
  var areaHa = ee.Number(ee.Algorithms.If(sourceArea, sourceArea, computedArea));
  var centroid = geom.centroid(30).coordinates();
  var sourceId = ee.String(ee.Algorithms.If(
    feature.get(CONFIG.fireIdField),
    feature.get(CONFIG.fireIdField),
    feature.id()
  ));

  return ee.Feature(geom, {
    fire_id: sourceId,
    fire_year: year,
    area_ha: areaHa,
    centroid_lon: centroid.get(0),
    centroid_lat: centroid.get(1)
  });
}

var fires = ee.FeatureCollection(CONFIG.fireAsset)
  .filterBounds(aoi)
  .map(cleanFire)
  .filter(ee.Filter.gte('fire_year', CONFIG.startYear))
  .filter(ee.Filter.lte('fire_year', CONFIG.endYear))
  .filter(ee.Filter.gte('area_ha', CONFIG.minimumFireAreaHa));

var era5 = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
  .select(['temperature_2m', 'dewpoint_temperature_2m', 'total_precipitation'])
  .filterBounds(aoi);

function saturationVaporPressureKpa(tempK) {
  var tempC = tempK.subtract(273.15);
  return tempC.expression(
    '0.6108 * exp((17.27 * t) / (t + 237.3))',
    {t: tempC}
  );
}

function addVpd(image) {
  var temp = image.select('temperature_2m');
  var dewpoint = image.select('dewpoint_temperature_2m');
  var es = saturationVaporPressureKpa(temp);
  var ea = saturationVaporPressureKpa(dewpoint);
  var vpd = es.subtract(ea).max(0).rename('vpd_kpa');
  return image.addBands(vpd);
}

function annualClimate(year) {
  year = ee.Number(year);
  var start = ee.Date.fromYMD(year, CONFIG.summerStartMonth, 1);
  var end = ee.Date.fromYMD(year, CONFIG.summerEndMonth, 31).advance(1, 'day');
  var summer = era5.filterDate(start, end).map(addVpd);
  var tempC = summer.select('temperature_2m').mean().subtract(273.15).rename('summer_temp_c');
  var precipMm = summer.select('total_precipitation').sum().multiply(1000).rename('summer_precip_mm');
  var vpdKpa = summer.select('vpd_kpa').mean().rename('summer_vpd_kpa');
  return ee.Image.cat([tempC, precipMm, vpdKpa]).set('observation_year', year);
}

var baseline = ee.ImageCollection(baselineYears.map(annualClimate)).mean().rename([
  'baseline_temp_c',
  'baseline_precip_mm',
  'baseline_vpd_kpa'
]);

function reduceClimateYear(year) {
  year = ee.Number(year);
  var climate = annualClimate(year);
  var anomalies = ee.Image.cat([
    climate.select('summer_temp_c').subtract(baseline.select('baseline_temp_c')).rename('temp_anomaly_c'),
    climate.select('summer_precip_mm').subtract(baseline.select('baseline_precip_mm')).rename('precip_anomaly_mm'),
    climate.select('summer_vpd_kpa').subtract(baseline.select('baseline_vpd_kpa')).rename('vpd_anomaly_kpa')
  ]);

  return climate.addBands(anomalies).reduceRegions({
    collection: fires,
    reducer: ee.Reducer.mean(),
    scale: 11132,
    tileScale: 4
  }).map(function(feature) {
    return feature.set('observation_year', year);
  });
}

var climateRecords = ee.FeatureCollection(years.map(reduceClimateYear)).flatten();

print('Climate records', climateRecords.limit(10));
print('Climate record count', climateRecords.size());

Export.table.toDrive({
  collection: climateRecords.select([
    'fire_id',
    'observation_year',
    'summer_temp_c',
    'summer_precip_mm',
    'summer_vpd_kpa',
    'temp_anomaly_c',
    'precip_anomaly_mm',
    'vpd_anomaly_kpa'
  ]),
  description: 'fire_climate_timeseries',
  fileNamePrefix: 'fire_climate_timeseries',
  fileFormat: 'CSV'
});
