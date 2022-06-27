import csv
import os
from enum import Enum
from io import StringIO

import geopandas
import pandas as pd
import slugify
import streamlit as st
from shapely.geometry import Point


class DataType(Enum):
    TEXT = 0
    INT = 1
    DOUBLE = 2
    BOOLEAN = 3
    DATE = 4
    DATETIME = 5
    LATITUDE = 6
    LONGITUDE = 7


def coerce_value(value: str, dtype: DataType):
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
        return pd.to_datetime(value, format="%Y-%m-%d").dt.date()
    elif dtype == DataType.DATETIME:
        return pd.to_datetime(value, format="%Y-%m-%d %H:%M:%S")
    else:
        raise Exception(f"Unknown data type for col '{key}': {dtype}...")


st.write("""# CSV to GeoPackage converter""")

with st.sidebar:
    st.write("""
    This script allows you to convert a CSV/TSV file containing geospatial point data
    (i.e. points on a map and their attributes) to the GeoPackage format.

    The CSV *must* contain exactly one column assigned to a longitude value and 
    one column assigned to a latitude value. Points are assumed to represent
    WSG84 coordinates.
    
    The CSV *must* contain a header row which will be used to derive the GeoPackage
    database column names.
    
    Date and datetime column values must be in '%Y-%m-%d' and '%Y-%m-%d %H-%M-%S' format
    respectively.
    """)

uploaded_file = st.file_uploader("Choose a CSV file", type=["csv", "tsv"], accept_multiple_files=False)

if not uploaded_file:
    st.stop()

name = slugify.slugify(os.path.splitext(uploaded_file.name)[0], separator="_")
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

headers = reader.fieldnames
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

    init_types[header] = DataType[st.selectbox(header, values, index=selected,
                                               key=f"type-col-{col_idx + 1}")]

lat_cols = [h for h, t in init_types.items() if t == DataType.LATITUDE]
lon_cols = [h for h, t in init_types.items() if t == DataType.LONGITUDE]

if not (lat_cols and lon_cols):
    st.error("No latitude and/or longitude column found")
    st.stop()

if len(lat_cols) > 1:
    st.error("Too many latitude columns assigned")
    st.stop()

if len(lon_cols) > 1:
    st.error("Too many longitude columns assigned")
    st.stop()

lat_col = lat_cols[0]
lon_col = lon_cols[0]
st.write(f"Latitude column: **{lat_col}**, Longitude column: **{lon_col}**")

if st.button("Generate GeoPackage?"):
    data = {"geometry": []}
    for header in headers:
        if header not in [lat_col, lon_col]:
            data[header] = []

    # Put the actual data in the dataframe
    # FIXME: would GeoPandas's own CSV functionality do this better?
    skipped = 0
    for row_num, row in enumerate(reader):
        if not (row[lon_col] and row[lat_col]):
            skipped += 1
            continue

        # Geometry column
        data["geometry"].append(Point(float(row[lon_col]), float(row[lat_col])))

        # Other columns
        for key, value in row.items():
            if key in [lat_col, lon_col]:
                continue
            col_type = init_types[key]
            try:
                data[key].append(coerce_value(value, col_type))
            except ValueError as e:
                print(e)
                st.error(
                    f"Error converting column '{key} value '{value}' to type {col_type.name} at line {row_num + 1}")
                st.stop()

    if skipped:
        st.warning(f"Skipped {skipped} row(s) without latitude/longitude data")

    # Write a dataframe!
    gdf = geopandas.GeoDataFrame(data, crs="EPSG:4326")
    st.write(gdf)
    st.write("---")

    out_name = f"{name}.gpkg"
    gdf.to_file(out_name, layer=name, driver="GPKG")
    with open(out_name, "rb") as f:
        st.download_button(f"Download File: '{out_name}'", f, file_name=out_name, mime="application/x-sqlite3")
