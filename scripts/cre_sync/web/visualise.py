from db.db import *
from pprint import pprint
import json


def export_json():
    """exports graph to json object, can be used for javascript visualisation"""
    graph = {"nodes": {"cres": [], "standards": []}, "edges": []}

    collection = Standard_collection(cache=True, cache_file="standards_cache.sqlite")
    cres = collection.session.query(CRE).all()
    for cre in cres:
        graph["nodes"]["cres"].append(
            (
                dict(
                    (name, getattr(cre, name))
                    for name in dir(cre)
                    if not name.startswith("_") and not name == "metadata"
                )
            )
        )

    standards = collection.session.query(Standard).all()
    for standard in standards:
        graph["nodes"]["standards"].append(
            (
                dict(
                    (name, getattr(standard, name))
                    for name in dir(standard)
                    if not name.startswith("_") and not name == "metadata"
                )
            )
        )

    links = collection.session.query(Links).all()
    for link in links:
        graph["edges"].append(
            (
                dict(
                    (name, getattr(link, name))
                    for name in dir(link)
                    if not name.startswith("_") and not name == "metadata"
                )
            )
        )

    # print(json.dumps(nodes))
    # print(json.dumps(edges))
    with open("cre_graph.json", "w+") as cg:
        cg.write("const graph=")
        json.dump(graph, cg)


if __name__ == "__main__":
    export_json()
