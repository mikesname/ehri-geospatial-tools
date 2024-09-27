import csv
import os
import tempfile

import geopandas.io.file
import slugify
import streamlit as st

import gpkg2gs

MAX_LINES = 500


def check_invalid_characters(text):
    # Define ranges of valid characters
    valid_ranges = [
        (0x9, 0xA),       # Tab, Newline
        (0xD, 0xD),       # Carriage Return
        (0x20, 0xD7FF),   # Basic Multilingual Plane without surrogates
        (0xE000, 0xFFFD), # Private Use Area
        (0x10000, 0x10FFFF) # Supplementary Planes
    ]

    invalid_chars = []
    if text is not None:
        for i, char in enumerate(text):
            code_point = ord(char)
            if not any(start <= code_point <= end for start, end in valid_ranges):
                invalid_chars.append((i, char, code_point))

    return invalid_chars


def main():
    st.write("""# GeoPackage Text Exporter""")

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
            extract[col] = st.checkbox(col, value=False, key=f"type-col-{i + 1}")

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

        # for column in new_gdf.select_dtypes(include=['object', 'string']):
        #     invalid_chars = new_gdf[column].apply(check_invalid_characters)
        #     for idx, chars in invalid_chars[invalid_chars.apply(bool)].items():
        #         # print(f"Row {idx}:")
        #         for pos, char, code_point in chars:
        #             st.error(f"  Position {pos}: Character '{char}' (U+{code_point:04X}, Decimal {code_point})")

        txt = new_gdf.to_csv(header=False, sep='\t', quoting=csv.QUOTE_NONE, index=False)
        txt_size = len(txt.encode('utf-8')) / 1024
        if txt_size < 32:
            st.info("Text size: {:.1f}kB".format(txt_size))
        else:
            st.error("Text size exceeds 32kB limit")
        st.code(txt, language='text')


if __name__ == "__main__":
    main()
