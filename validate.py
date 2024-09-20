import argparse
import os
import re

import gpkg2gs
from gpkg_utils import check_invalid_geometry, get_layer_info, get_column_info

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Validate GeoPackage files for GeoServer import.')
    parser.add_argument('files', type=str, nargs='+',
                        help='one or more .gpkg files')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        default=False, help='show verbose output')

    args = parser.parse_args()
    for filename in args.files:
        errors = 0
        if args.verbose:
            print(f"Validating {filename}...")
        layerinfo = get_layer_info(filename)
        for layer in layerinfo:
            if args.verbose:
                print(f"  Validating layer {layer.identifier}...")
            bad = check_invalid_geometry(filename, layer.table_name)
            if bad:
                errors += bad
                print(f"    - Found {bad} invalid geometries in {layer.identifier}")
            columns = get_column_info(filename, layer.table_name)
            for column in columns:
                if not re.match(gpkg2gs.VALID_COL_NAME, column):
                    print(f"    - Column '{column}' in layer '{layer.identifier}' is not a valid GeoServer column name")
                    errors += 1
        if errors:
            print(f"Found {errors} errors in {filename}")
        else:
            if args.verbose:
                print(f"No errors found in {filename}")

