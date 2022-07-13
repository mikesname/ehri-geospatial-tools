import json
import os
import urllib.parse
from http import HTTPStatus
from typing import NamedTuple, List, Generator, Tuple

import requests
import streamlit as st
from owslib.wms import WebMapService
from rdflib import Graph, SKOS, RDF, URIRef
from requests import Response

VOCAB = "https://raw.githubusercontent.com/michalfrankl/ehri-holocaust-geographies/main/ehri_holocaust_geographies.rdf"


class Term(NamedTuple):
    uri: URIRef
    label: str

    @property
    def tag(self) -> str:
        return os.path.basename(str(self.uri))


class Resource(NamedTuple):
    name: str
    href: str


class Style(Resource):
    pass


class Layer(Resource):
    pass


class LayerInfo(NamedTuple):
    name: str
    bounds: Tuple[float, float, float, float]
    srs: str

class Vocabulary:
    def __init__(self):
        self.g = Graph()
        self.g.load(VOCAB)

    def get_terms(self) -> Generator[Term, None, None]:
        for s in self.g.subjects(RDF.type, SKOS.Concept):
            for _, literal in self.g.preferredLabel(s, lang="en"):
                yield Term(s, str(literal))


def check_code(r: Response):
    if r.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED]:
        st.error(f"Unexpected status from Geoserver: {r.status_code}")
        st.error(r.text)
        st.stop()


def get_wms_url(proto: str, host: str, workspace: str, layer_info: LayerInfo, styles=None):
    bounds = layer_info.bounds
    ratio = float(bounds[3] - bounds[1]) / float(bounds[2] - bounds[0])
    width = 512
    height = int(float(width) * ratio)
    bbox = ','.join([str(p) for p in bounds])
    params = dict(
        request="GetMap",
        layers=f"{workspace}:{layer_info.name}",
        bbox=bbox,
        version="1.1.1",
        service="wms",
        width=width,
        height=height,
        format="image/jpeg",
        styles=styles,
        srs=layer_info.srs
    )
    return f"{proto}://{host}/geoserver/wms?{urllib.parse.urlencode(params)}"


class Geoserver:
    def __init__(self):
        self.session = requests.Session()
        user_ = os.environ["GEOSERVER_USER"]
        pass_ = os.environ["GEOSERVER_PASS"]
        self.session.auth = (user_, pass_)
        self.session.headers.update({"accept": "application/json", "content-type": "application/json"})

        self.host = os.environ["GEOSERVER_HOST"]
        self.proto = "https" if os.environ.get("GEOSERVER_SECURE", 0) else "http"
        self.workspace = os.environ.get("GEOSERVER_WORKSPACE")
        self.base_url = f"{self.proto}://{self.host}/geoserver/rest"

        self.wms = WebMapService(f"{self.proto}://{self.host}/geoserver/wms", username=user_, password=pass_)

    def list_styles(self) -> List[Style]:
        r = self.session.get(f"{self.base_url}/styles")
        check_code(r)
        return [Style(style["name"], style["href"]) for style in r.json()["styles"]["style"]]

    def list_layers(self) -> List[Layer]:
        r = self.session.get(f"{self.base_url}/workspaces/{self.workspace}/layers")
        check_code(r)
        return [Layer(layer["name"], layer["href"]) for layer in r.json()["layers"]["layer"]]

    def set_default_style(self, layer: Layer, style: Style) -> None:
        r = self.session.get(layer.href)
        check_code(r)
        data = r.json()
        data["layer"]["defaultStyle"] = style._asdict()
        rp = self.session.put(layer.href, json.dumps(data))
        check_code(rp)

    def get_layer_info(self, layer) -> LayerInfo:
        info = self.wms[f"{self.workspace}:{layer.name}"]
        return LayerInfo(layer.name, info.boundingBox[0:4], info.boundingBox[4])

    def get_layer_image(self, layer_info: LayerInfo, styles=None):
        return get_wms_url(self.proto, self.host, self.workspace, layer_info, styles)


def main():

    st.set_page_config(layout="wide")
    st.title("Geoserver Styles")
    col1, col2 = st.columns(2)
    sidebar = st.sidebar

    vocab = Vocabulary()
    gs = Geoserver()

    with st.spinner("Loading data"):
        terms = sorted(list(vocab.get_terms()), key=lambda t: t.label)
        layers = gs.list_layers()
        styles = gs.list_styles()

    with sidebar:
        st.write("### Vocabulary terms:")
        for term in terms:
            st.write(f"{term.label} `{term.tag}`")

    with col1:
        st.markdown("### Select a layer:")
        layer_name = st.selectbox("Layer", [""] + [layer.name for layer in layers])

        if layer_name != "":
            st.write(f"Setting title for layer {layer_name}")
            layer = next(layer for layer in layers if layer.name == layer_name)
            info = gs.get_layer_info(layer)

            st.markdown("### Select a style:")
            style_list = [style.name for style in styles]

            if st.checkbox("Limit styles to vocabulary terms"):
                vocab_list = [term.tag for term in terms]
                style_list = [style.name for style in styles if style.name in vocab_list ]
                if not style_list:
                    st.warning("No vocabulary styles found")
                    st.stop()

            style_name = st.selectbox("Style", [""] + style_list)
            if style_name != "":
                st.write(f"Assign layer {layer_name} to {style_name}?")
                style = next(style for style in styles if style.name == style_name)

                if st.button("Assign Default Style", help="Set selected style as layer default"):
                    gs.set_default_style(layer, style)
                    st.success("Done!")

            with col2:
                st.markdown("### Layer preview:")
                with st.spinner("Loading GeoServer layer preview..."):
                    wms_url = gs.get_layer_image(info, style_name)
                    st.write("---")
                    with st.container():
                        st.image(wms_url)
                        if style_name != "":
                            st.caption(f"WMS layer '{layer_name}' preview with style '{style_name}': ([link]({wms_url}))")
                        else:
                            st.caption(f"WMS layer '{layer_name}' preview with default style: ([link]({wms_url}))")



if __name__ == "__main__":
    main()