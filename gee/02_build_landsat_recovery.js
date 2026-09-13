// Build recovery_timeseries.csv from Landsat Collection 2 Level 2 SR.
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
  fireAsset: 'users/your_username/NFDB_poly',
  fireIdField: 'NFDBFIREID',
  fireYearField: 'YEAR',
  fireAreaHaField: 'SIZE_HA'
};

var center = ee.Geometry.Point([CONFIG.longitude, CONFIG.latitude]);
var aoi = center.buffer(CONFIG.radiusKm * 1000);
var years = ee.List.sequence(CONFIG.startYear, CONFIG.endYear);

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

function maskLandsatC2(image) {
  var qa = image.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(1 << 1).eq(0)  // dilated cloud
    .and(qa.bitwiseAnd(1 << 2).eq(0))      // cirrus
    .and(qa.bitwiseAnd(1 << 3).eq(0))      // cloud
    .and(qa.bitwiseAnd(1 << 4).eq(0))      // cloud shadow
    .and(qa.bitwiseAnd(1 << 5).eq(0));     // snow
  return image.updateMask(clear);
}

function prepTmEtm(image) {
  var sr = image.select(['SR_B3', 'SR_B4', 'SR_B7'], ['RED', 'NIR', 'SWIR2'])
    .multiply(0.0000275)
    .add(-0.2);
  return maskLandsatC2(image).addBands(sr, null, true)
    .select(['RED', 'NIR', 'SWIR2'])
    .copyProperties(image, ['system:time_start']);
}

function prepOli(image) {
  var sr = image.select(['SR_B4', 'SR_B5', 'SR_B7'], ['RED', 'NIR', 'SWIR2'])
    .multiply(0.0000275)
    .add(-0.2);
  return maskLandsatC2(image).addBands(sr, null, true)
    .select(['RED', 'NIR', 'SWIR2'])
    .copyProperties(image, ['system:time_start']);
}

var landsat = ee.ImageCollection('LANDSAT/LT05/C02/T1_L2').map(prepTmEtm)
  .merge(ee.ImageCollection('LANDSAT/LE07/C02/T1_L2').map(prepTmEtm))
  .merge(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').map(prepOli))
  .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2').map(prepOli))
  .filterBounds(aoi);

function annualComposite(year) {
  year = ee.Number(year);
  var start = ee.Date.fromYMD(year, CONFIG.summerStartMonth, 1);
  var end = ee.Date.fromYMD(year, CONFIG.summerEndMonth, 31).advance(1, 'day');
  var image = landsat.filterDate(start, end).median();
  var ndvi = image.normalizedDifference(['NIR', 'RED']).rename('NDVI');
  var nbr = image.normalizedDifference(['NIR', 'SWIR2']).rename('NBR');
  return image.addBands([ndvi, nbr]).select(['NBR', 'NDVI']).set('observation_year', year);
}

function reduceYear(year) {
  year = ee.Number(year);
  var composite = annualComposite(year);
  return composite.reduceRegions({
    collection: fires,
    reducer: ee.Reducer.median(),
    scale: 30,
    tileScale: 4
  }).map(function(feature) {
    var fireYear = ee.Number(feature.get('fire_year'));
    return feature.set({
      observation_year: year,
      years_since_fire: year.subtract(fireYear),
      NBR: feature.get('NBR'),
      NDVI: feature.get('NDVI')
    });
  });
}

var rawRecords = ee.FeatureCollection(years.map(reduceYear)).flatten()
  .filter(ee.Filter.gte('years_since_fire', -3))
  .filter(ee.Filter.lte('years_since_fire', 20));

function addBaselines(record) {
  var fireId = record.get('fire_id');
  var eventRecords = rawRecords.filter(ee.Filter.eq('fire_id', fireId));
  var preRecords = eventRecords
    .filter(ee.Filter.gte('years_since_fire', -3))
    .filter(ee.Filter.lte('years_since_fire', -1));
  var fireYearRecord = eventRecords.filter(ee.Filter.eq('years_since_fire', 0)).first();
  var nbrPre = preRecords.aggregate_median('NBR');
  var ndviPre = preRecords.aggregate_median('NDVI');
  var nbrFire = ee.Feature(fireYearRecord).get('NBR');

  return record.set({
    NBR_pre: nbrPre,
    NDVI_pre: ndviPre,
    dNBR: ee.Number(nbrPre).subtract(ee.Number(nbrFire))
  });
}

var recovery = rawRecords.map(addBaselines);

print('Recovery records', recovery.limit(10));
print('Recovery record count', recovery.size());

Export.table.toDrive({
  collection: recovery.select([
    'fire_id',
    'fire_year',
    'observation_year',
    'years_since_fire',
    'area_ha',
    'centroid_lat',
    'centroid_lon',
    'NBR',
    'NDVI',
    'NBR_pre',
    'NDVI_pre',
    'dNBR'
  ]),
  description: 'recovery_timeseries',
  fileNamePrefix: 'recovery_timeseries',
  fileFormat: 'CSV'
});
