import os
import tempfile

import geopandas.io.file
import slugify
import streamlit as st

import gpkg2gs

MAX_LINES = 500


def main():
    st.write("""# GeoServer GeoPackage importer""")

    with st.sidebar:
        st.write("""
        Copy the contents of a GeoPackage file as text.
        
        e.g. for enhancing the record metadata.
        """)

    uploaded_file = st.file_uploader("Choose a GeoPackage file", type=["gpkg"], accept_multiple_files=False)
    if not uploaded_file:
        st.stop()

    # Write the file so we can get metadata from it without depending on Fiona...
    name = slugify.slugify(os.path.splitext(uploaded_file.name)[0],
                           lowercase=False,
                           regex_pattern=gpkg2gs.DISALLOWED_CHARS_PATTERN)

    with tempfile.TemporaryDirectory() as tempdir:
        filename = os.path.join(tempdir, f"{name}.gpkg")
        st.write(f"Filename: `{name}`")

        with open(filename, "wb") as f:
            f.write(uploaded_file.getbuffer())
            uploaded_file.seek(0)

        gdf = geopandas.read_file(filename, engine='pyogrio')
        extract = {}
        # get the column names from the GeoDataFrame
        for col in gdf.columns:
            dtype = gdf[col].dtype
            # ignore non-text columns
            if dtype in ['object', 'string']:
                extract[col] = True

        st.write("### Select text columns to extract:")

        for i, col in enumerate(extract.keys()):
            extract[col] = st.checkbox(col, value=True, key=f"type-col-{i + 1}")

        num_rows = gdf.shape[0]
        max_lines = num_rows
        if num_rows > MAX_LINES:
            # Show an adjustable line limit
            st.write("### Max lines:")
            max_lines = st.slider("Max lines", 0, num_rows, MAX_LINES)

        extract_cols = [col for col, selected in extract.items() if selected]

        st.write("### Extracted text:")
        # get a new dataframe consisting of only the selected columns
        # and the first 500 lines
        new_gdf = gdf[list(extract_cols)].head(max_lines)
        st.code(new_gdf.to_csv(header=False, sep='\t', index=False))


if __name__ == "__main__":
    main()
