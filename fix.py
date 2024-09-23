#!/usr/bin/env python

# This script can run various fixes to GeoPackage files for issues that
# cause problems w/ GeoServer and/or GeoNetwork.
#
# - Run St_MakeValid on all invalid geometries in a layer
# - Remove invalid characters from column names

import argparse
import os
import re
import spatialite

from gpkg_utils import get_layer_info, get_column_info


def fix_invalid_geom(filename):
    """Fix invalid geometries in a GeoPackage file."""
    layers = get_layer_info(filename)
    conn = spatialite.connect(filename)
    cur = conn.cursor()
    for layer in layers:
        cur.execute("SELECT EnableGpkgMode();")
        # Replace POINT(nan nan) with POINT EMPTY
        cur.execute(f"""UPDATE "{layer.table_name}" 
                        SET "{layer.geom_col}" = ST_GeomFromText('POINT EMPTY') 
                        WHERE ST_AsText("{layer.geom_col}") = 'POINT(nan nan)'""")
        cur.execute(f"""UPDATE "{layer.table_name}"
                        SET "{layer.geom_col}" = ST_MakeValid("{layer.geom_col}")
                        WHERE NOT ST_IsValid("{layer.geom_col}")""")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fix GeoPackage files for GeoServer import.')
    parser.add_argument('files', type=str, nargs='+',
                        help='one or more .gpkg files')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        default=False, help='show verbose output')

    args = parser.parse_args()
    for filename in args.files:
        if args.verbose:
            print(f"Fixing {filename}...")
        fix_invalid_geom(filename)
        if args.verbose:
            print(f"Done fixing {filename}")