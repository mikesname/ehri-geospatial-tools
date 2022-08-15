import os
from typing import NamedTuple, Generator

import streamlit as st
from rdflib import Graph, SKOS, RDF, URIRef

from geoserver import GeoServer, Layer, GeoServerError

VOCAB = "https://raw.githubusercontent.com/michalfrankl/ehri-holocaust-geographies/main/ehri_holocaust_geographies.rdf"


class Term(NamedTuple):
    uri: URIRef
    label: str

    @property
    def tag(self) -> str:
        return os.path.basename(str(self.uri))


class Vocabulary:
    def __init__(self):
        self.g = Graph()
        self.g.load(VOCAB)

    def get_terms(self) -> Generator[Term, None, None]:
        for s in self.g.subjects(RDF.type, SKOS.Concept):
            for _, literal in self.g.preferredLabel(s, lang="en"):
                yield Term(s, str(literal))


def main():

    st.set_page_config(layout="wide")
    st.title("GeoServer Styles")
    col1, col2 = st.columns(2)
    sidebar = st.sidebar

    vocab = Vocabulary()

    gs = GeoServer(
        os.environ["GEOSERVER_HOST"],
        os.environ["GEOSERVER_USER"],
        os.environ["GEOSERVER_PASS"],
        bool(int(os.environ.get("GEOSERVER_SECURE", 0))),
        os.environ["GEOSERVER_WORKSPACE"],
        info = st.info,
        error = st.error
    )

    try:
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

            # This box has to update when we reload the data
            style_info = st.empty()

            def show_style_info(layer: Layer):
                default_style = gs.get_layer_default_style(layer)
                if default_style:
                    style_info.info(f"Layer '{layer_name}' default style: **{default_style.name}**")
                else:
                    style_info.warning(f"Layer '{layer_name}' has no default style")

            if layer_name == "":
                st.stop()

            layer = next(layer for layer in layers if layer.name == layer_name)
            show_style_info(layer)

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
                    gs.set_default_style(layer.name, style)
                    st.success("Done!")
                    show_style_info(layer)

            with col2:
                st.markdown("### Layer preview:")
                with st.spinner("Loading GeoServer layer preview..."):
                    wms_url = gs.get_layer_image(gs.get_layer_info(layer), style_name)
                    st.write("---")
                    with st.container():
                        st.image(wms_url)
                        if style_name:
                            st.caption(f"WMS layer '{layer_name}' preview with style '{style_name}': ([link]({wms_url}))")
                        else:
                            st.caption(f"WMS layer '{layer_name}' preview with default style: ([link]({wms_url}))")

    except GeoServerError as e:
        st.error(e.message)
        st.error(e.response_text)
        st.stop()


if __name__ == "__main__":
    main()
