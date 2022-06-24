from io import StringIO

import os
import geopandas
import streamlit as st
from shapely.geometry import Point

import csv

st.write("""# Csv to GeoPackage converter
Select your CSV file
""")

types = dict(
    text="TEXT",
    int="INT",
    double="DOUBLE",
    lat="LATITUDE",
    lon="LONGITUDE"
)

uploaded_file = st.file_uploader("Choose a CSV file", accept_multiple_files=False)

if uploaded_file:
    name = os.path.splitext(uploaded_file.name)[0]
    st.write("filename:", name)

    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    reader = csv.DictReader(stringio)

    headers = reader.fieldnames
    init_types = {}

    col = 1
    for header in headers:
        values = list(types.values())
        selected = 0
        if header.lower().startswith("lat"):
            init_types[header] = types["lat"]
            selected = values.index(types["lat"])
        elif header.lower().startswith("lon"):
            init_types[header] = types["lon"]
            selected = values.index(types["lon"])
        else:
            init_types[header] = types["text"]
        with st.container():
            st.text(header)
            init_types[header] = st.selectbox(f"Column {col} type", values, index=selected, key = f"type-col-{col}")
        col += 1

    st.write("Types: ", init_types)

    lat_col = [h for h, t in init_types.items() if t == "LATITUDE"][0]
    lon_col = [h for h, t in init_types.items() if t == "LONGITUDE"][0]

    st.write(f"Lat col: {lat_col}, Lon col: {lon_col}")

    if st.button("Generate GeoPackage?"):
        data = {"geometry": []}
        for header in headers:
            if not header in [lat_col, lon_col]:
                data[header] = []

        for row in reader:
            data["geometry"].append(Point(float(row[lon_col]), float(row[lat_col])))
            for col, value in row.items():
                if not col in [lat_col, lon_col]:
                    coltype = init_types[col]
                    if coltype == "TEXT":
                        data[col].append(value)
                    elif coltype == "INT":
                        data[col].append(int(value))
                    else:
                        data[col].append(float(value))

        gdf = geopandas.GeoDataFrame(data, crs="EPSG:4326")
        st.write(gdf)

        outname = f"{name}.gpkg"
        gdf.to_file(outname, layer=name, driver="GPKG")
        with open(outname, "rb") as f:
            st.download_button(f"Download File: '{outname}'", f, file_name=outname, mime="application/x-sqlite3")