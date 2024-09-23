"""
Streamlit utility for making GeoNetwork perform
a reindex of all linked dataset features via WFS:
"""
import os

import streamlit as st
from geonetwork import GetNetwork


def main():
    st.write("""# GeoNetwork Feature Indexing""")

    with st.sidebar:
        st.write("""
        Reindex all linked dataset features via WFS.
        """)

    instance = st.selectbox("Choose a server instance", options=["Testing", "Production"])

    # NB: reusing GeoServer credentials, which is not good...
    gn = GetNetwork(
        (os.environ["GEOSERVER_HOST"] if instance == "Production"
         else os.environ["GEOSERVER_TEST_HOST"]),
        os.environ["GEOSERVER_USER"],
        os.environ["GEOSERVER_PASS"],
        bool(int(os.environ.get("GEOSERVER_SECURE", 0))),
        info=st.info,
        error=st.error
    )

    xsrf_token = gn.init_session()
    records = gn.list_records(xsrf_token)

    todo = []
    nope = []
    for record in records:
        if "_source" in record and "link" in record["_source"]:
            for link in record["_source"]["link"]:
                if link["protocol"] == "OGC:WFS":
                    if 'nameObject' in link:
                        todo.append((record["_id"], link["nameObject"]["default"]))
                    elif 'name' in link:
                        todo.append((record["_id"], link["name"]))
                    else:
                        nope.append(record["_id"])
        else:
            nope.append(record["_id"])

    if todo:
        st.info(f"Found {len(todo)} datasets to with WFS links to reindex...")
    if nope:
        st.warning(f"Ignoring {len(nope)} datasets without WFS links...")

    if st.button("Reindex all datasets"):
        def stream_data():
            for record_id, wfs_name in todo:
                st.write(gn.submit_reindex_task(xsrf_token, record_id, wfs_name))
                yield f"Reindexing {record_id} -> ({wfs_name})...\n"

        st.write_stream(stream_data)

        st.success("Done!")



if __name__ == "__main__":
    main()