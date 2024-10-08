import os
import re
import tempfile

import geopandas.io.file
import slugify
import streamlit as st
from geopandas import GeoDataFrame
from streamlit.runtime.uploaded_file_manager import UploadedFile

from gpkg_utils import GPLayerInfo, get_layer_info, GeoPackageError, check_invalid_geometry, get_column_info
from geoserver import GeoServer, LayerInfo


VALID_COL_NAME = r"^[a-zA-Z_][a-zA-Z0-9_-]*$"
DISALLOWED_CHARS_PATTERN = r'[^-a-zA-Z0-9_]+'


def preview_layer(filename: str, layer: GPLayerInfo, uploaded_file: UploadedFile):
    if not layer.data_type == "features":
        st.warning(f"No preview available for data type: {layer.data_type}")
        return

    with st.spinner(f"Loading data for layer \"{layer.identifier}\"..."):
        gdf = load_dataframe(filename, uploaded_file.file_id, layer=layer.table_name)
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


@st.cache_data(show_spinner=False)
def load_dataframe(path: str, *_, **kwargs):
    return geopandas.read_file(path, **kwargs)


@st.cache_data(show_spinner=False)
def clone_with_lat_lon(_gdf: GeoDataFrame) -> GeoDataFrame:
    df = _gdf.copy(deep=True)
    df["lon"] = df.geometry.x
    df["lat"] = df.geometry.y

    # drop empty lat/lon columns
    df.dropna(subset=["lat", "lon"], inplace=True)
    return df


def check_point_geom(gdf) -> bool:
    import numpy as np
    return np.array_equal(np.array(["Point"]), gdf.geom_type.unique())


def main():
    st.write("""# GeoServer GeoPackage importer""")

    with st.sidebar:
        st.write("""
        Import a GeoPackage file into GeoServer, via the REST API.
        
        There's currently a [bug](https://osgeo-org.atlassian.net/browse/GEOS-9769) 
        in GeoServer which means we have to do some fixing up of the package metadata 
        after ingest to avoid a crash when managing the workspace in the GeoServer UI.
        """)

    instance = st.selectbox("Choose a server instance", options=["Testing", "Production"])

    uploaded_file = st.file_uploader("Choose a GeoPackage file", type=["gpkg"], accept_multiple_files=False)
    if not uploaded_file:
        st.stop()

    st.session_state["uploaded_file"] = uploaded_file

    # Write the file so we can get metadata from it without depending on Fiona...
    name = slugify.slugify(os.path.splitext(uploaded_file.name)[0],
                           lowercase=False,
                           regex_pattern=DISALLOWED_CHARS_PATTERN)

    with tempfile.TemporaryDirectory() as tempdir:
        filename = os.path.join(tempdir, f"{name}.gpkg")
        st.write(f"Filename: `{name}`")

        with open(filename, "wb") as f:
            f.write(uploaded_file.getbuffer())
            uploaded_file.seek(0)

        try:
            layers = get_layer_info(filename)
            if not layers:
                st.error("No layers found, exiting...")
                st.stop()
        except GeoPackageError as e:
            st.error(e)
            st.stop()

        st.info(f"Layers found: {', '.join([layer.identifier for layer in layers])}")
        data_types = set([layer.data_type for layer in layers])

        if "features" not in data_types:
            st.warning("No feature layers found, preview will not be available")

        for layer in layers:
            invalid = check_invalid_geometry(filename, layer.table_name)
            if invalid:
                st.error(f"Layer '{layer.identifier}' contains {invalid} invalid {"geometry" if (invalid == 1) else "geometries"}")

        # Check the column names are valid for GeoServer export
        for layer in layers:
            col_names = get_column_info(filename, layer.table_name)
            for col in col_names:
                if not re.match(VALID_COL_NAME, col):
                    st.error(f"Column '{col}' in layer '{layer.identifier}' is not a valid GeoServer column name")

        layer = layers[0]
        if len(layers) > 1:
            layer = st.selectbox("Preview layer:", layers)
        preview_layer(filename, layer, uploaded_file)

    if st.button(f"Import GeoPackage '{name}'"):
            uploaded_file = st.session_state["uploaded_file"]

            gs = GeoServer(
                (os.environ["GEOSERVER_HOST"] if instance == "Production"
                    else os.environ["GEOSERVER_TEST_HOST"]),
                os.environ["GEOSERVER_USER"],
                os.environ["GEOSERVER_PASS"],
                bool(int(os.environ.get("GEOSERVER_SECURE", 0))),
                os.environ["GEOSERVER_WORKSPACE"],
                info=st.info,
                error=st.error
            )

            for data_type in data_types:
                st.info(f"Uploading store for data type: {data_type}")
                gs.ingest_store(name, data_type, uploaded_file)
                uploaded_file.seek(0)

            st.balloons()
            st.success("Done!")

            for layer_info in layers:
                if layer_info.data_type in ["features", "tiles"]:
                    with st.spinner("Loading GeoServer layer preview..."):
                        wms_url = gs.get_layer_image(LayerInfo(layer_info.table_name, layer_info.bounds, layer_info.srs))
                        st.write("---")
                        with st.container():
                            st.markdown(f"WMS layer preview: '{layer_info.identifier}' ([link]({wms_url}))")
                            st.image(wms_url)


if __name__ == "__main__":
    main()
