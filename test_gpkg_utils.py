
import csv

from gpkg_utils import DataType, csv_to_gdf, check_invalid_geometry


def test_geom_col_csv_to_gpkg():
    with open('test/test_geom_col.csv', 'r') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        types = {
            'geom': DataType.GEOMETRY,
            'col1': DataType.TEXT,
            'col2': DataType.TEXT,
        }
        gdf, _ = csv_to_gdf(headers, types, 'geom', 'EPSG:4326', reader)
        assert gdf is not None
        assert gdf.shape[1] == 3 # 3 columns
        assert gdf.shape[0] == 7 # 7 rows


def test_latlon_col_csv_to_gpkg():
    with open('test/test_latlon_cols.csv', 'r') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        types = {
            'lat': DataType.LATITUDE,
            'lon': DataType.LONGITUDE,
            'col1': DataType.TEXT,
            'col2': DataType.TEXT,
        }
        gdf, _ = csv_to_gdf(headers, types, ('lat', 'lon'), 'EPSG:4326', reader)
        assert gdf is not None
        assert gdf.shape[1] == 3 # 3 columns
        assert gdf.shape[0] == 7 # 7 rows


def test_date_col_csv_to_gpkg():
    with open('test/test_date_col.csv', 'r') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        types = {
            'geom': DataType.GEOMETRY,
            'col1': DataType.TEXT,
            'date': DataType.DATE,
            'datetime': DataType.DATETIME,
        }
        gdf, _ = csv_to_gdf(headers, types, 'geom', 'EPSG:4326', reader)
        assert gdf is not None
        assert gdf.shape[1] == 4 # 4 columns
        assert gdf.shape[0] == 7 # 7 rows


def test_check_invalid_geometry():
    bad = check_invalid_geometry('test/invalid_geom.gpkg','invalid_geom')
    assert bad == 2


def test_get_layer_info():
    from gpkg_utils import get_layer_info
    layers = get_layer_info('test/invalid_geom.gpkg')
    assert len(layers) == 1
    assert layers[0].table_name == 'invalid_geom'
    assert layers[0].data_type == 'features'
    assert layers[0].identifier == 'invalid_geom'
    assert layers[0].description == ''
    assert layers[0].geom_col == 'geom'
    assert layers[0].srs == 'EPSG:4326'