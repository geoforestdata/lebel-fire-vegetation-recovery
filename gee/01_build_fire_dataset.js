// Build fire_events.csv for a 150 km AOI around Lebel-sur-Quevillon.
// Update FIRE_ASSET and field names after uploading NRCan NFDB fire perimeters.

var CONFIG = {
  studyName: 'Lebel-sur-Quevillon',
  latitude: 49.05,
  longitude: -76.98,
  radiusKm: 150,
  startYear: 1984,
  endYear: 2025,
  minimumFireAreaHa: 100,
  fireAsset: 'users/your_username/NFDB_poly',
  fireIdField: 'NFDBFIREID',
  fireYearField: 'YEAR',
  fireAreaHaField: 'SIZE_HA'
};

var center = ee.Geometry.Point([CONFIG.longitude, CONFIG.latitude]);
var aoi = center.buffer(CONFIG.radiusKm * 1000);
var perimeters = ee.FeatureCollection(CONFIG.fireAsset);

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

var fireEvents = perimeters
  .filterBounds(aoi)
  .map(cleanFire)
  .filter(ee.Filter.gte('fire_year', CONFIG.startYear))
  .filter(ee.Filter.lte('fire_year', CONFIG.endYear))
  .filter(ee.Filter.gte('area_ha', CONFIG.minimumFireAreaHa));

Map.centerObject(aoi, 7);
Map.addLayer(aoi, {color: '333333'}, 'AOI');
Map.addLayer(fireEvents, {color: 'd73027'}, 'Fire events');

print('Fire events', fireEvents.limit(10));
print('Fire event count', fireEvents.size());

Export.table.toDrive({
  collection: fireEvents.select([
    'fire_id',
    'fire_year',
    'area_ha',
    'centroid_lat',
    'centroid_lon'
  ]),
  description: 'fire_events',
  fileNamePrefix: 'fire_events',
  fileFormat: 'CSV'
});
