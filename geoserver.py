"""A collection of GeoServer related functions"""

import json
import urllib.parse
from http import HTTPStatus
from io import BytesIO
from typing import List, NamedTuple, Tuple, Union, Optional

import requests
from owslib.wms import WebMapService
from requests import Response


class GeoServerError(Exception):
    def __init__(self, message, response_text=None):
        super().__init__(message)
        self.message = message
        self.response_text = response_text


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


def check_code(r: Response):
    if r.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.ACCEPTED]:
        raise GeoServerError(f"Unexpected status from GeoServer: {r.status_code}", r.text)


def get_wms_url(proto: str, host: str, workspace: str, layer_info: LayerInfo,
                style: Optional[Union[str, List[str]]] = None):
    bounds = layer_info.bounds
    ratio = float(bounds[3] - bounds[1]) / float(bounds[2] - bounds[0])
    width = 512
    height = int(float(width) * ratio)
    bbox = ','.join([str(p) for p in bounds])
    styles = ""
    if style is not None:
        if isinstance(style, str):
            styles = style
        elif isinstance(style, list):
            styles = ",".join(style)

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


class GeoServer:
    def __init__(self, host: str, username: str, password: str, secure: bool, workspace: str, **kwargs):
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"accept": "application/json", "content-type": "application/json"})

        self.host = host
        self.proto = "https" if secure else "http"
        self.workspace = workspace
        self.base_url = f"{self.proto}://{self.host}/geoserver/rest"

        self.wms = WebMapService(f"{self.proto}://{self.host}/geoserver/wms", username=username, password=password)

        self._info = kwargs["info"] if kwargs.get("info") else print
        self._error = kwargs["error"] if kwargs.get("error") else print

    def info(self, *args, **kwargs):
        self._info(*args, **kwargs)

    def error(self, *args, **kwargs):
        self._error(*args, **kwargs)

    def list_styles(self) -> List[Style]:
        r = self.session.get(f"{self.base_url}/styles")
        check_code(r)
        return [Style(style["name"], style["href"]) for style in r.json()["styles"]["style"]]

    def get_layer_default_style(self, layer: Layer) -> Union[Style, None]:
        r = self.session.get(layer.href)
        check_code(r)
        style_info = r.json()["layer"].get("defaultStyle")
        return Style(**style_info) if style_info else None

    def list_layers(self) -> List[Layer]:
        r = self.session.get(f"{self.base_url}/workspaces/{self.workspace}/layers")
        check_code(r)
        return [Layer(layer["name"], layer["href"]) for layer in r.json()["layers"]["layer"]]

    def set_default_style(self, layer_name: str, style: Style) -> None:
        layer_url = f"{self.base_url}/workspaces/{self.workspace}/layers/{layer_name}"
        r = self.session.get(layer_url)
        check_code(r)
        data = r.json()
        data["layer"]["defaultStyle"] = style._asdict()
        rp = self.session.put(layer_url, json.dumps(data))
        check_code(rp)

    def get_layer_info(self, layer) -> LayerInfo:
        info = self.wms[f"{self.workspace}:{layer.name}"]
        return LayerInfo(layer.name, info.boundingBox[0:4], info.boundingBox[4])

    def get_layer_image(self, layer_info: LayerInfo, style: str = None):
        return get_wms_url(self.proto, self.host, self.workspace, layer_info, style)

    def ingest_store(self, name: str, data_type: str, uploaded_file: BytesIO):
        """Coverage data ingest..."""
        ext = "gpkg"
        endpoint = "datastores"
        store_name = name
        if data_type == "tiles":
            # NB: weird "extension" required here...
            ext = "geopackage (mosaic)"
            endpoint = "coveragestores"
            store_name = f"{name}_{data_type}"
        self.info(f"Importing {ext}... {name}")
        url = f"{self.base_url}/workspaces/{self.workspace}/{endpoint}/{store_name}/file.{ext}"
        resp = self.session.put(url, data=uploaded_file, headers={"content-type": "application/x-sqlite3"})
        check_code(resp)

        # Correct datastore metadata...
        if endpoint == "datastores":
            self.fix_store_data(store_name)

    def fix_store_data(self, name: str):
        """Bug GEOS-9769 means that GPKG files uploaded via REST do not have the correct
        file: prefix, although their path on disk is correct. This causes a crash in the
        GeoServer UI. So here we update it to swap the absolute path to the GeoServer data
        dir for the `file:` prefix, which tells GeoServer that it is looking within its
        own data dir."""
        self.info("Fixing datastore metadata...")
        url = f"{self.base_url}/workspaces/{self.workspace}/datastores/{name}"
        get_resp = self.session.get(url)
        check_code(get_resp)

        path_suffix = f"data/{self.workspace}/{name}/{name}.gpkg"
        data = get_resp.json()
        found = False
        try:
            for i, conn_param in enumerate(data["dataStore"]["connectionParameters"]["entry"]):
                if conn_param["@key"] == "database":
                    db_path = str(conn_param["$"])
                    new_db_path = f"file:{path_suffix}"
                    if db_path.endswith(path_suffix):
                        self.info(f"Adding file prefix to datastore path: {new_db_path}")
                        data["dataStore"]["connectionParameters"]["entry"][i]["$"] = new_db_path
                        found = True
                        break
        except KeyError:
            raise GeoServerError("Unable to fetch database connection parameter from datastore metadata")

        if not found:
            raise GeoServerError("Unable to find database connection parameter with expected suffix")

        fix_resp = self.session.put(url, data=json.dumps(data))
        check_code(fix_resp)
