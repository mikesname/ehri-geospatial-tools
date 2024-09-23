import requests


class GetNetwork:
    def __init__(self, host: str, username: str, password: str, secure: bool, **kwargs):
        self.host = host
        self.username = username
        self.password = password
        self.secure = secure

        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"accept": "application/json", "content-type": "application/json"})

        self.proto = "https" if secure else "http"
        self.base_url = f"{self.proto}://{self.host}/geonetwork"

        self._info = kwargs["info"] if kwargs.get("info") else print
        self._error = kwargs["error"] if kwargs.get("error") else print

    def init_session(self):
        response = self.session.get(f"{self.base_url}/srv/api/me", headers={"Accept": "application/json"})
        response.raise_for_status()
        xsrf_token = self.session.cookies.get("XSRF-TOKEN")
        return xsrf_token

    def list_records(self, xsrf_token: str):
        search_data = {
            "from": 0,
            "size": 1000,
            "query": {
                "match_all": {}
            },
            # "_source": False,
            "fields": ["_id", "title"]
        }

        response = self.session.get(
            f"{self.base_url}/srv/api/search/records/_search",
            headers={
                "Accept": "application/json",
                "X-XSRF-TOKEN": xsrf_token
            },
            auth=(self.username, self.password),
            json=search_data
        )
        response.raise_for_status()
        return response.json()["hits"]["hits"]

    def submit_reindex_task(self, xsrf_token: str, uuid: str, wfsname: str):
        # This is also pretty fragile, assuming the GeoNetwork GeoServer is
        # at the same host as the GeoNetwork instance...
        geoserver_url = f"{self.proto}://{self.host}/geoserver"
        payload = {
            "url": f"{geoserver_url}/ows?SERVICE=wfs&",
            "strategy": "investigator",
            "typeName": wfsname,
            "version": "1.1.0",
            "tokenizedFields": None,
            "treeFields": None,
            "metadataUuid": uuid
        }
        response = self.session.put(
            f"{self.base_url}/srv/api/workers/data/wfs/actions/start",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json;charset=utf-8",
                "X-XSRF-TOKEN": xsrf_token
            },
            auth=(self.username, self.password),
            json=payload
        )
        response.raise_for_status()
        return response.json()

