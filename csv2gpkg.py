import csv
import os
from io import StringIO
from typing import List

import slugify
import streamlit as st

from gpkg2gs import DISALLOWED_CHARS_PATTERN
from gpkg_utils import DataType, csv_to_gdf


def main():
    st.write("""# CSV to GeoPackage converter""")

    with st.sidebar:
        st.write("""
        This script allows you to convert a CSV/TSV file containing geospatial data
        (i.e. points on a map and their attributes) to the GeoPackage format.

        The CSV *must* contain either:
        
           - one geometry column containing WKT geometry data, or
           - one column assigned to a longitude value and 
             one column assigned to a latitude value. 
            
        Points are assumed to represent WSG84 coordinates.

        The CSV *must* contain a header row which will be used to derive the GeoPackage
        database column names.

        Date and datetime column values must be in '%Y-%m-%d' and '%Y-%m-%d %H-%M-%S' format
        respectively.
        """)

    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv", "tsv"], accept_multiple_files=False)

    crs = st.text_input("CRS (default: EPSG:4326)", "EPSG:4326")

    if not uploaded_file:
        st.stop()

    name = slugify.slugify(os.path.splitext(uploaded_file.name)[0], regex_pattern=DISALLOWED_CHARS_PATTERN, lowercase=False)
    st.write(f"Filename: `{name}`")

    # Try and understand the CSV
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    dialect = csv.Sniffer().sniff(stringio.read(1024))
    if dialect is None:
        st.error("Cannot discern dialect of CSV file. Is this a standard format?")
        st.stop()

    stringio.seek(0)
    reader = csv.DictReader(stringio, dialect=dialect)

    st.write("### Assign column types:")

    headers: List[str] = reader.fieldnames or []
    init_types = dict((header, DataType.TEXT) for header in headers)

    for col_idx, header in enumerate(headers):
        values = [t.name for t in list(DataType)]
        selected = DataType.TEXT.value  # default
        if header.lower().startswith("lat") or header.lower() == "y":
            init_types[header] = DataType.LATITUDE
            selected = DataType.LATITUDE.value
        elif header.lower().startswith("lon") or header.lower() == "x":
            init_types[header] = DataType.LONGITUDE
            selected = DataType.LONGITUDE.value
        elif header.lower().startswith("geom"):
            init_types[header] = DataType.GEOMETRY
            selected = DataType.GEOMETRY.value

        init_types[header] = DataType[st.selectbox(header, values, index=selected,
                                                   key=f"type-col-{col_idx + 1}")]

    lat_cols = [h for h, t in init_types.items() if t == DataType.LATITUDE]
    lon_cols = [h for h, t in init_types.items() if t == DataType.LONGITUDE]
    geom_cols = [h for h, t in init_types.items() if t == DataType.GEOMETRY]

    if not ((lat_cols and lon_cols) or geom_cols):
        st.error("No geometry or latitude/longitude columns found")
        st.stop()

    if len(geom_cols) > 1:
        st.error("Too many geometry columns assigned")
        st.stop()

    if len(lat_cols) > 1:
        st.error("Too many latitude columns assigned")
        st.stop()

    if len(lon_cols) > 1:
        st.error("Too many longitude columns assigned")
        st.stop()

    if geom_cols:
        geom_col = geom_cols[0]
        st.write(f"Geometry column: **{geom_col}**")
    else:
        geom_col = lat_cols[0], lon_cols[0]
        st.write(f"Latitude column: **{geom_col[0]}**, Longitude column: **{geom_col[1]}**")

    if st.button("Generate GeoPackage?"):
        try:
            gdf, skipped = csv_to_gdf(headers, init_types, geom_col, crs, reader)
        except ValueError as e:
            print(e)
            st.error(e)
            st.stop()
        if skipped:
            st.warning(f"Skipped {skipped} row(s) without latitude/longitude data")
        st.write(gdf)
        st.write("---")

        out_name = f"{name}.gpkg"
        gdf.to_file(out_name, layer=name, driver="GPKG")
        with open(out_name, "rb") as f:
            st.download_button(f"Download File: '{out_name}'", f, file_name=out_name, mime="application/x-sqlite3")


if __name__ == "__main__":
    main()