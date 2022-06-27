import json
import os
import sqlite3
from http import HTTPStatus

import geopandas.io.file
import requests
import slugify
import streamlit as st


def get_layer_info(filepath: str) -> (str, str, str, str):
    conn = sqlite3.connect(filepath)
    layers = []
    try:
        cursor = conn.cursor()
        for row in cursor.execute("SELECT * FROM gpkg_contents"):
            layers.append(row)
    except sqlite3.DatabaseError:
        st.error(f"Error reading GeoPackage '{filepath}' (is it the right format?)")
        st.stop()
    finally:
        conn.close()

    return layers


def create_or_update_layer(session: requests.Session, base_url: str, workspace: str, store: str, layerdata):
    identifier, dtype, title, description, *_ = layerdata
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
    if identifier in layers:
        url = f"{base_url}/datastores/{store}/featuretypes/{identifier}"
        method = "PUT"

    data = dict(
        featureType=dict(
            name=identifier,
            nativeName=identifier,
            namespace=dict(
                name=workspace,
                href=f"{base_url}.json"
            ),
            title=title,
            description=description,
            keywords=dict(string=[dtype])
        )
    )

    r = session.request(method, url, data=json.dumps(data))
    if r.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED]:
        st.error(f"Unexpected import status code: {r.status_code} ({method} {url})")
        st.stop()
    return identifier in layers


def fix_store_data(session, base_url, name, workspace):
    fix_payload = dict(
        dataStore=dict(
            name=name,
            type="GeoPackage",
            enabled=True,
            workspace=dict(
                name=workspace,
                href=f"{base_url}.json"
            ),
            connectionParameters=dict(
                entry=[
                    {"@key": "database", "$": f"file:data/{workspace}/{name}/{name}.gpkg"},
                    {"@key": "dbtype", "$": "geopkg"},
                ]
            )
        )
    )
    fix_url = f"{base_url}/datastores/{name}"
    fix_resp = session.put(fix_url, data=json.dumps(fix_payload), headers={"content-type": "application/json"})
    if fix_resp.status_code not in [HTTPStatus.OK]:
        st.error(f"Unexpected status code from ingest fix: {fix_resp.status_code}")
        st.write(fix_resp.text)
        st.stop()


def ingest_store(session, base_url, name, uploaded_file):
    # Initial data ingest: this requires fixing later...
    ingest_url = f"{base_url}/datastores/{name}/file.gpkg"
    ingest_resp = session.put(ingest_url, data=uploaded_file, headers={"content-type": "application/x-sqlite3"})
    if ingest_resp.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.ACCEPTED]:
        st.error(f"Unexpected status code from ingest: {ingest_resp.status_code}")
        st.write(ingest_resp.text)
        st.stop()


def main():
    st.write("""# Geoserver GeoPackage importer""")

    with st.sidebar:
        st.write("""
        Import a GeoPackage file into Geoserver, via the REST API.
        
        There's currently a [bug](https://osgeo-org.atlassian.net/browse/GEOS-9769) 
        in Geoserver which means we have to do some fixing up of the package metadata 
        after ingest to avoid a crash when managing the workspace in the Geoserver UI.
        """)

    uploaded_file = st.file_uploader("Choose a GPKG file", type=["gpkg"], accept_multiple_files=False)

    if not uploaded_file:
        st.stop()

    # Write the file so we can get metadata from it without depending on Fiona...

    name = slugify.slugify(os.path.splitext(uploaded_file.name)[0], separator="_")
    filename = f"{name}.gpkg"
    st.write(f"Filename: `{filename}`")

    with open(filename, "wb") as f:
        f.write(uploaded_file.getbuffer())
        uploaded_file.seek(0)

    layers = get_layer_info(filename)
    if not layers:
        st.error("No layers found, exiting...")
        st.stop()

    st.write(f"Layers found: {len(layers)}")

    gdf = geopandas.read_file(filename)
    st.write(gdf)

    workspace = os.environ.get("GEOSERVER_WORKSPACE")
    st.write(f"Importing into workspace: `{workspace}`")

    session = requests.Session()
    session.auth = (os.environ["GEOSERVER_USER"], os.environ["GEOSERVER_PASS"])
    session.headers.update({"accept": "application/json", "content-type": "application/json"})

    host = os.environ["GEOSERVER_HOST"]
    proto = "https" if os.environ.get("GEOSERVER_SECURE", 0) else "http"
    base_url = f"{proto}://{host}/geoserver/rest/workspaces/{workspace}"

    st.write(f"Base URL: `{base_url}`")

    if st.button("Ingest GeoPackage?"):
        progress = st.progress(0)

        ingest_store(session, base_url, name, uploaded_file)
        progress.progress(33)

        fix_store_data(session, base_url, name, workspace)
        progress.progress(60)

        for layer_info in layers:
            st.write(f"Importing layer: {layer_info[0]}")
            create_or_update_layer(session, base_url, workspace, name, layer_info)
            progress.progress(60 + int(40.0 / float(len(layers))))

        st.balloons()
        st.success("Done!")


if __name__ == "__main__":
    main()