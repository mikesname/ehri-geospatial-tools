"""GeoPackage-related functions"""
import sqlite3
from typing import NamedTuple, List, Tuple


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


