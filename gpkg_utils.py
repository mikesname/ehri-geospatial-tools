"""GeoPackage-related functions"""
import csv
import sqlite3
from enum import Enum
from typing import NamedTuple, List, Tuple, Dict

import geopandas
import pandas as pd
from geopandas import GeoDataFrame
from shapely import from_wkt, GEOSException
from shapely.geometry import Point


class GeoPackageError(Exception):
    pass


class GPLayerInfo(NamedTuple):
    table_name: str
    data_type: str
    identifier: str
    description: str
    bounds: Tuple[float, float, float, float]
    srs: str

    def __str__(self):
        return self.identifier


class DataType(Enum):
    TEXT = 0
    INT = 1
    DOUBLE = 2
    BOOLEAN = 3
    DATE = 4
    DATETIME = 5
    LATITUDE = 6
    LONGITUDE = 7
    GEOMETRY = 8


def coerce_value(key: str, value: str, dtype: DataType):
    """Convert a string into the correct data type"""
    if dtype == DataType.TEXT:
        return value
    elif dtype == DataType.INT:
        return int(value)
    elif dtype == DataType.DOUBLE:
        return float(value)
    elif dtype == DataType.BOOLEAN:
        return bool(value)
    elif dtype == DataType.DATE:
        return pd.to_datetime(value, format="%Y-%m-%d").date()
    elif dtype == DataType.DATETIME:
        return pd.to_datetime(value, format="%Y-%m-%d %H:%M:%S")
    else:
        raise Exception(f"Unknown data type for col '{key}': {dtype}...")


def get_layer_info(filepath: str) -> List[GPLayerInfo]:
    conn = sqlite3.connect(filepath)
    layers = []
    try:
        cursor = conn.cursor()
        for tn, dt, ident, desc, min_x, min_y, max_x, max_y, srs_id, auth in cursor.execute(
                """SELECT
                    c.table_name,
                    c.data_type,
                    c.identifier,
                    c.description,
                    c.min_x,
                    c.min_y,
                    c.max_x,
                    c.max_y,
                    c.srs_id,
                    s.organization
                    FROM gpkg_contents c
                    JOIN gpkg_spatial_ref_sys s
                    ON c.srs_id = s.srs_id"""):
            layers.append(GPLayerInfo(tn, dt, ident, desc, (min_x, min_y, max_x, max_y), f"{auth}:{srs_id}"))
    except sqlite3.DatabaseError as e:
        raise GeoPackageError(f"Error reading GeoPackage '{filepath}' (is it the right format?) {e}")
    finally:
        conn.close()
    return layers


def csv_to_gdf(
        headers: List[str],
        init_types: Dict[str, DataType],
        geom_col_spec: str | Tuple[str, str],
        crs: str,
        reader: csv.DictReader) -> Tuple[GeoDataFrame, int]:

    if isinstance(geom_col_spec, tuple):
        lat_col, lon_col = geom_col_spec
        geom_col = None
    else:
        lat_col, lon_col = None, None
        geom_col = geom_col_spec

    data = {"geometry": []}
    for header in headers:
        if header not in [lat_col, lon_col, geom_col]:
            data[header] = []
    # Put the actual data in the dataframe
    # FIXME: would GeoPandas's own CSV functionality do this better?
    skipped = 0
    for row_num, row in enumerate(reader):
        # Geometry column
        if geom_col:
            if not row[geom_col]:
                skipped += 1
                continue
            try:
                data["geometry"].append(from_wkt(row[geom_col]))
            except GEOSException:
                raise ValueError(f"Error parsing WKT geometry in row {row_num + 1}: '{row[geom_col]}'")
        else:
            if not (row[lon_col] and row[lat_col]):
                skipped += 1
                continue
            data["geometry"].append(Point(float(row[lon_col]), float(row[lat_col])))

        # Other columns
        for key, value in row.items():
            if key in [lat_col, lon_col, geom_col]:
                continue
            col_type = init_types[key]
            data[key].append(coerce_value(key, value, col_type))
    # Write a dataframe!
    gdf = geopandas.GeoDataFrame(data, crs=crs)
    return gdf, skipped


