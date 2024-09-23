
import streamlit as st

from csv2gpkg import main as csv2gpkg_main
from gpkg2gs import main as gpkg2gs_main
from sldls import main as sldls_main
from gpkg2txt import main as gpkg2txt_main
from gn2index import main as gn2index_main

csv2gpkg_page = st.Page(csv2gpkg_main, title="CSV to GPKG", icon=":material/dataset:", url_path="csv2gpkg")
gpkg2gs_page = st.Page(gpkg2gs_main, title="GPKG to GeoServer", icon=":material/post_add:", url_path="gpkg2gs")
gpkg2txt_page = st.Page(gpkg2txt_main, title="GPKG to Text", icon=":material/text_snippet:", url_path="gpkg2txt")
sldls_page = st.Page(sldls_main, title="SLD Manager", icon=":material/css:", url_path="sldls")
gn2index_page = st.Page(gn2index_main, title="GeoNetwork Feature Indexing", icon=":material/refresh:", url_path="gn2index")

pg = st.navigation({
    "GeoServer Tools": [csv2gpkg_page, gpkg2gs_page, gpkg2txt_page, sldls_page],
    "GeoNetwork Tools": [gn2index_page]
})
st.set_page_config(page_title="GeoServer Tools", page_icon=":material/handyman:")
pg.run()