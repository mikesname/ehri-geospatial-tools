"""A script for importing GeoPackage files into GeoServer"""

import argparse
import sys

from gpkg_utils import get_layer_info, GeoPackageError
from geoserver import GeoServer, GeoServerError, LayerInfo

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Import GeoPackage files into GeoServer.')
    parser.add_argument('files', type=str, nargs='+',
                        help='one or more .gpkg files to import')
    parser.add_argument('-H', '--host', dest='host', type=str, action='store',
                        default="localhost:8080", help='the GeoServer host')
    parser.add_argument('-u', '--username', dest='username', type=str, action='store',
                        default="admin", help='the GeoServer user')
    parser.add_argument('-p', '--password', dest='password', type=str, action='store',
                        default="geoserver", help='the GeoServer password')
    parser.add_argument('-w', '--workspace', dest='workspace', type=str, action='store',
                        required=True, help='the GeoServer host')
    parser.add_argument('-s', '--secure', dest='secure', action='store_true',
                        default=False, help='whether GeoServer is using HTTPS')
    parser.add_argument('--style', dest='style', action='store',
                        help='a style to apply to the layers')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        default=False, help='show verbose output')

    args = parser.parse_args()
    gs = GeoServer(
        host=args.host,
        username=args.username,
        password=args.password,
        secure=args.secure,
        workspace=args.workspace)

    style = None
    if args.style:
        for s in gs.list_styles():
            if s.name == args.style:
                style = s
                break
    if args.style and style is None:
        print(f"Error: no style named '{args.style}' found")
        sys.exit(1)

    try:
        for filename in args.files:
            infos = get_layer_info(filename)
            for info in infos:
                with open(filename, mode='rb') as f:
                    gs.ingest_store(info.table_name, info.data_type, f)
                url = gs.get_layer_image(LayerInfo(info.table_name, info.bounds, info.srs))
                if args.verbose:
                    print(url)
                if style is not None:
                    gs.set_default_style(info.table_name, style)
                    if args.verbose:
                        print(f"Set layer '{info.table_name}' style to '{style.name}'")

    except (GeoPackageError, GeoServerError) as e:
        print(f"Error: {e}", file=sys.stderr)
