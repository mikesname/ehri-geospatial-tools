#!/usr/bin/env python


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GeoNetwork administration utilities")
    parser.add_argument("action", choices=["reindex"], help="Action to perform")
    parser.add_argument('-u', '--username', dest='username', type=str, action='store',
                        help='the GeoNetwork username')
    parser.add_argument('-p', '--password', dest='password', type=str, action='store',
                        help='the GeoNetwork password')
    parser.add_argument('-H', '--host', dest='host', type=str, action='store', default='localhost:8080',
                        help='the GeoNetwork host')
    parser.add_argument('-s', '--secure', dest='secure', action='store_true', default=False,
                        help='whether GeoNetwork is using HTTPS')
    args = parser.parse_args()

    if args.action == "reindex":
        from geonetwork import GetNetwork
        gn = GetNetwork(args.host, args.username, args.password, args.secure)
        xsrf_token = gn.init_session()
        records = gn.list_records(xsrf_token)
        for record in records:
            if "_source" in record and "link" in record["_source"]:
                for link in record["_source"]["link"]:
                    if link["protocol"] == "OGC:WFS":
                        print(f"Reindexing {record['_id']} -> ({link['name']})")
                        gn.submit_reindex_task(xsrf_token, record["_id"], link["name"])
            else:
                print(f"No WFS link found for {record['_id']}")
