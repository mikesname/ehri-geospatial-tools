
import csv

from gpkg_utils import DataType, csv_to_gdf


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




