import json
import os
import sqlite3
import urllib.parse
from http import HTTPStatus
from typing import List, Tuple
from typing import NamedTuple

import geopandas.io.file
import requests
import slugify
import streamlit as st
from geopandas import GeoDataFrame


class LayerInfo(NamedTuple):
    table_name: str
    data_type: str
    identifier: str
    description: str
    bounds: Tuple[float, float, float, float]
    srs: str

    def __str__(self):
        return self.identifier


def get_layer_info(filepath: str) -> List[LayerInfo]:
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
            layers.append(LayerInfo(tn, dt, ident, desc, (min_x, min_y, max_x, max_y), f"{auth}:{srs_id}"))
    except sqlite3.DatabaseError as e:
        st.error(f"Error reading GeoPackage '{filepath}' (is it the right format?) {e}")
        st.stop()
    finally:
        conn.close()
    return layers


def fix_store_data(session: requests.Session, base_url: str, name: str, workspace: str):
    """Bug GEOS-9769 means that GPKG files uploaded via REST do not have the correct
    file: prefix, although their path on disk is correct. This causes a crash in the
    Geoserver UI. So here we update it to swap the absolute path to the Geoserver data
    dir for the `file:` prefix, which tells Geoserver that it is looking within its
    own data dir."""
    st.info("Fixing datastore metadata...")
    url = f"{base_url}/datastores/{name}"
    get_resp = session.get(url)
    if get_resp.status_code not in [HTTPStatus.OK]:
        st.error(f"Unexpected status code retrieving datastore metadata: {get_resp.status_code}")
        st.write(get_resp.text)
        st.stop()

    path_suffix = f"data/{workspace}/{name}/{name}.gpkg"
    data = get_resp.json()
    found = False
    try:
        for i, conn_param in enumerate(data["dataStore"]["connectionParameters"]["entry"]):
            if conn_param["@key"] == "database":
                db_path = str(conn_param["$"])
                new_db_path = f"file:{path_suffix}"
                if db_path.endswith(path_suffix):
                    st.info(f"Adding file prefix to datastore path: {new_db_path}")
                    data["dataStore"]["connectionParameters"]["entry"][i]["$"] = new_db_path
                    found = True
                    break
    except KeyError:
        st.error("Unable to fetch database connection parameter from datastore metadata")
        st.stop()

    if not found:
        st.error("Unable to find database connection parameter with expected suffix")
        st.stop()

    fix_resp = session.put(url, data=json.dumps(data))
    if fix_resp.status_code not in [HTTPStatus.OK]:
        st.error(f"Unexpected status code from ingest fix: {fix_resp.status_code}")
        st.write(fix_resp)
        st.write(fix_resp.text)
        st.stop()


def ingest_store(session: requests.Session, base_url: str, workspace: str, name: str, data_type: str,
                 uploaded_file: str):
    """Coverage data ingest..."""
    ext = "gpkg"
    endpoint = "datastores"
    store_name = name
    if data_type == "tiles":
        # NB: weird "extension" required here...
        ext = "geopackage (mosaic)"
        endpoint = "coveragestores"
        store_name = f"{name}_{data_type}"
    st.info(f"Importing {ext}...")
    url = f"{base_url}/{endpoint}/{store_name}/file.{ext}"
    resp = session.put(url, data=uploaded_file, headers={"content-type": "application/x-sqlite3"})
    if resp.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.ACCEPTED]:
        st.error(f"Unexpected status code from ingest: {resp.status_code}")
        st.write(resp.text)
        st.stop()

    # Correct datastore metadata...
    if endpoint == "datastores":
        fix_store_data(session, base_url, store_name, workspace)


def preview_layer(filename: str, layer: LayerInfo, uploaded_file):
    if not layer.data_type == "features":
        st.warning(f"No preview available for data type: {layer.data_type}")
        return

    with st.spinner(f"Loading data for layer \"{layer.identifier}\"..."):
        gdf = load_dataframe(filename, uploaded_file.id, layer=layer.table_name)
        is_points = check_point_geom(gdf)
        if is_points:
            show = st.radio(f"Preview data for layer \"{layer.identifier}\":", ("Table", "Map"))
            if show == "Table":
                st.write(gdf)
            else:
                st.map(clone_with_lat_lon(gdf))
        else:
            st.write(gdf)
            st.warning("Map preview only available with Point geometry")

        st.write("---")


def get_wms_url(proto: str, host: str, workspace: str, layer_info: LayerInfo):
    bounds = layer_info.bounds
    ratio = float(bounds[3] - bounds[1]) / float(bounds[2] - bounds[0])
    width = 1024
    height = int(float(width) * ratio)
    bbox = ','.join([str(p) for p in bounds])
    params = dict(
        request="GetMap",
        layers=f"{workspace}:{layer_info.table_name}",
        bbox=bbox,
        version="1.1.1",
        service="wms",
        width=width,
        height=height,
        format="image/jpeg",
        srs=layer_info.srs
    )
    return f"{proto}://{host}/geoserver/wms?{urllib.parse.urlencode(params)}"


@st.cache(show_spinner=False)
def load_dataframe(path: str, *_, **kwargs):
    return geopandas.read_file(path, **kwargs)


@st.cache(show_spinner=False)
def clone_with_lat_lon(gdf: GeoDataFrame) -> GeoDataFrame:
    df = gdf.copy(deep=True)
    df["lon"] = df.geometry.x
    df["lat"] = df.geometry.y
    return df


def check_point_geom(gdf) -> bool:
    import numpy as np
    return np.array_equal(np.array(["Point"]), gdf.geom_type.unique())


def main():
    st.write("""# Geoserver GeoPackage importer""")

    with st.sidebar:
        st.write("""
        Import a GeoPackage file into Geoserver, via the REST API.
        
        There's currently a [bug](https://osgeo-org.atlassian.net/browse/GEOS-9769) 
        in Geoserver which means we have to do some fixing up of the package metadata 
        after ingest to avoid a crash when managing the workspace in the Geoserver UI.
        """)

    uploaded_file = st.file_uploader("Choose a GeoPackage file", type=["gpkg"], accept_multiple_files=False)
    if not uploaded_file:
        st.stop()

    # Write the file so we can get metadata from it without depending on Fiona...
    name = slugify.slugify(os.path.splitext(uploaded_file.name)[0], separator="_", lowercase=False)
    filename = f"{name}.gpkg"
    st.write(f"Filename: `{filename}`")

    with open(filename, "wb") as f:
        f.write(uploaded_file.getbuffer())
        uploaded_file.seek(0)

    layers = get_layer_info(filename)
    if not layers:
        st.error("No layers found, exiting...")
        st.stop()

    st.info(f"Layers found: {', '.join([layer.identifier for layer in layers])}")
    data_types = set([layer.data_type for layer in layers])

    if "features" not in data_types:
        st.warning("No feature layers found, preview will not be available")

    layer = layers[0]
    if len(layers) > 1:
        layer = st.selectbox("Preview layer:", layers)
    preview_layer(filename, layer, uploaded_file)

    if st.button(f"Import GeoPackage '{filename}'"):
        session = requests.Session()
        session.auth = (os.environ["GEOSERVER_USER"], os.environ["GEOSERVER_PASS"])
        session.headers.update({"accept": "application/json", "content-type": "application/json"})

        host = os.environ["GEOSERVER_HOST"]
        proto = "https" if os.environ.get("GEOSERVER_SECURE", 0) else "http"
        workspace = os.environ.get("GEOSERVER_WORKSPACE")
        base_url = f"{proto}://{host}/geoserver/rest/workspaces/{workspace}"

        st.info(f"Workspace: `{workspace}`; Base URL: `{base_url}`")
        for data_type in data_types:
            st.info(f"Uploading store for data type: {data_type}")
            ingest_store(session, base_url, workspace, name, data_type, uploaded_file)
            uploaded_file.seek(0)

        st.balloons()
        st.success("Done!")

        for layer_info in layers:
            if layer_info.data_type in ["features", "tiles"]:
                with st.spinner("Loading GeoServer layer preview..."):
                    wms_url = get_wms_url(proto, host, workspace, layer_info)
                    st.write("---")
                    with st.container():
                        st.markdown(f"WMS layer preview: '{layer_info.identifier}' ([link]({wms_url}))")
                        st.image(wms_url)


if __name__ == "__main__":
    main()
