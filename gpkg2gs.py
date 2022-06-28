import json
import os
import sqlite3
import urllib.parse
from collections import namedtuple
from http import HTTPStatus
from typing import List

import geopandas.io.file
import requests
import slugify
import streamlit as st
from geopandas import GeoDataFrame

LayerInfo = namedtuple("LayerInfo", ["table_name", "data_type", "identifier", "description"])


def get_layer_info(filepath: str) -> List[LayerInfo]:
    conn = sqlite3.connect(filepath)
    layers = []
    try:
        cursor = conn.cursor()
        for tn, dt, ident, desc in cursor.execute(
                "SELECT table_name, data_type, identifier, description FROM gpkg_contents"):
            layers.append(LayerInfo(tn, dt, ident, desc))
    except sqlite3.DatabaseError:
        st.error(f"Error reading GeoPackage '{filepath}' (is it the right format?)")
        st.stop()
    finally:
        conn.close()
    return layers


def create_or_update_layer(session: requests.Session, base_url: str, workspace: str, store: str,
                           layer: LayerInfo) -> bool:
    """Create a new layer from the GPKG-derived layer data"""
    st.info(f"Importing layer '{layer.identifier}'")
    list_url = f"{base_url}/datastores/{store}/featuretypes"
    r = session.get(list_url)
    layers = []
    try:
        layers = [data["name"] for data in r.json().get("featureTypes", {}).get("featureType", [])]
    except AttributeError:
        # no layers
        pass

    url = list_url
    method = "POST"
    if layer.identifier in layers:
        url = f"{base_url}/datastores/{store}/featuretypes/{layer.identifier}"
        method = "PUT"

    data = dict(
        featureType=dict(
            name=layer.identifier,
            nativeName=layer.table_name,
            namespace=dict(
                name=workspace,
                href=f"{base_url}.json"
            ),
            title=layer.identifier,
            description=layer.description,
            keywords=dict(string=[layer.data_type])
        )
    )

    r = session.request(method, url, data=json.dumps(data))
    if r.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED]:
        st.error(f"Unexpected import status code: {r.status_code} ({method} {url})")
        st.stop()
    return layer.identifier in layers


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


def ingest_store(session: requests.Session, base_url: str, name: str, uploaded_file: str):
    """Initial data ingest: this requires fixing later..."""
    st.info("Importing GeoPackage...")
    ingest_url = f"{base_url}/datastores/{name}/file.gpkg"
    ingest_resp = session.put(ingest_url, data=uploaded_file, headers={"content-type": "application/x-sqlite3"})
    if ingest_resp.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.ACCEPTED]:
        st.error(f"Unexpected status code from ingest: {ingest_resp.status_code}")
        st.write(ingest_resp.text)
        st.stop()


def get_wms_url(gdf, proto, host, workspace, name):
    bounds = gdf.total_bounds
    ratio = float(bounds[3] - bounds[1]) / float(bounds[2] - bounds[0])
    width = 1024
    height = int(float(width) * ratio)
    bbox = ','.join([str(p) for p in bounds])
    params = dict(
        request="GetMap",
        layers=f"{workspace}:{name}",
        bbox=bbox,
        version="1.1.1",
        service="wms",
        width=width,
        height=height,
        format="image/jpeg",
        srs=gdf.crs.srs
    )
    return f"{proto}://{host}/geoserver/wms?{urllib.parse.urlencode(params)}"


@st.cache(show_spinner=False)
def load_dataframe(path: str, *_):
    return geopandas.read_file(path)


@st.cache(show_spinner=False)
def clone_with_lat_lon(gdf: GeoDataFrame) -> GeoDataFrame:
    df = gdf.copy(deep=True)
    df['lon'] = df.geometry.x
    df['lat'] = df.geometry.y
    return df


def check_point_geom(gdf) -> bool:
    import numpy as np
    return np.array_equal(np.array(['Point']), gdf.geom_type.unique())


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

    st.info(f"Layers found: {len(layers)}")

    with st.spinner("Loading data..."):
        gdf = load_dataframe(filename, uploaded_file.id)
        is_points = check_point_geom(gdf)
        if is_points:
            show = st.radio("Preview data:", ('Table', 'Map'))
            if show == 'Table':
                st.write(gdf)
            else:
                st.map(clone_with_lat_lon(gdf))
        else:
            st.write(gdf)
            st.warning("Map preview only available with Point geometry")

        st.write("---")

    if st.button(f"Import GeoPackage '{filename}'"):
        session = requests.Session()
        session.auth = (os.environ["GEOSERVER_USER"], os.environ["GEOSERVER_PASS"])
        session.headers.update({"accept": "application/json", "content-type": "application/json"})

        host = os.environ["GEOSERVER_HOST"]
        proto = "https" if os.environ.get("GEOSERVER_SECURE", 0) else "http"
        workspace = os.environ.get("GEOSERVER_WORKSPACE")
        base_url = f"{proto}://{host}/geoserver/rest/workspaces/{workspace}"

        st.info(f"Workspace: `{workspace}`; Base URL: `{base_url}`")

        progress = st.progress(0)
        num_ops = 0
        inc_progress = 100 / (2 + len(layers))

        ingest_store(session, base_url, name, uploaded_file)
        num_ops += 1
        progress.progress(int(inc_progress * num_ops))

        fix_store_data(session, base_url, name, workspace)
        num_ops += 1
        progress.progress(int(inc_progress * num_ops))

        for layer_info in layers:
            create_or_update_layer(session, base_url, workspace, name, layer_info)
            num_ops += 1
            progress.progress(int(inc_progress * num_ops))

        st.balloons()
        st.success("Done!")

        with st.spinner("Loading layer preview..."):
            for layer_info in layers:
                wms_url = get_wms_url(gdf, proto, host, workspace, layer_info.identifier)
                with st.container():
                    st.markdown(f"WMS layer preview: '{layer_info.identifier}' ([link]({wms_url}))")
                    st.image(wms_url)


if __name__ == "__main__":
    main()
