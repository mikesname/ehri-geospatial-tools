
import streamlit as st

from csv2gpkg import main as csv2gpkg_main
from gpkg2gs import main as gpkg2gs_main
from sldls import main as sldls_main

csv2gpkg_page = st.Page(csv2gpkg_main, title="CSV to GPKG", icon=":material/dataset:", url_path="csv2gpkg")
gpkg2gs_page = st.Page(gpkg2gs_main, title="GPKG to GeoServer", icon=":material/post_add:", url_path="gpkg2gs")
sldls_page = st.Page(sldls_main, title="SLD Manager", icon=":material/css:", url_path="sldls")

pg = st.navigation([csv2gpkg_page, gpkg2gs_page, sldls_page])
st.set_page_config(page_title="GeoServer Tools", page_icon=":material/handyman:")
pg.run()