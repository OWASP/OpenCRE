# type: ignore
# silence mypy for the routes file
import os
import urllib.parse
from typing import Any
import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    request,
    send_from_directory,
)

from application import cache
from application.database import db
from application.defs import cre_defs as defs
from application.defs import osib_defs as odefs

ITEMS_PER_PAGE = 20

app = Blueprint("web", __name__, static_folder="../frontend/www")

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def extend_cre_with_tag_links(
    cre: defs.CRE, collection: db.Node_collection
) -> defs.CRE:
    others = []
    # for each tag: get by tag, append results as "RELATED TO" links
    for tag in cre.tags:
        others.extend(collection.get_by_tags([tag]))
    others = list(frozenset(others))
    for o in others:
        o.links = []
        cre.add_link(defs.Link(ltype=defs.LinkTypes.Related, document=o))
    return cre


@app.route("/rest/v1/id/<creid>", methods=["GET"])
@app.route("/rest/v1/name/<crename>", methods=["GET"])
@cache.cached(timeout=50)
def find_cre(creid: str = None, crename: str = None) -> Any:  # refer
    database = db.Node_collection()
    include_only = request.args.getlist("include_only")
    opt_osib = request.args.get("osib")

    cres = database.get_CREs(external_id=creid, name=crename, include_only=include_only)
    if cres:
        if len(cres) > 1:
            logger.error("get by id returned more than one results? This looks buggy")
        cre = cres[0]
        result = {"data": cre.todict()}
        # disable until we have a consensus on tag behaviour
        # cre = extend_cre_with_tag_links(cre=cre, collection=database)
        if opt_osib:
            result["osib"] = odefs.cre2osib([cre]).todict()
        return jsonify(result)
    abort(404)


@app.route("/rest/v1/<ntype>/<name>", methods=["GET"])
@app.route("/rest/v1/standard/<name>", methods=["GET"])
# @cache.cached(timeout=50)
def find_node_by_name(name: str, ntype: str = defs.Credoctypes.Standard.value) -> Any:
    database = db.Node_collection()
    opt_section = request.args.get("section")
    opt_osib = request.args.get("osib")
    opt_version = request.args.get("version")
    if opt_section:
        opt_section = urllib.parse.unquote(opt_section)
    opt_subsection = request.args.get("subsection")
    opt_hyperlink = request.args.get("hyperlink")

    # match ntype to the credoctypes case-insensitive
    typ = [t for t in defs.Credoctypes if t.value.lower() == ntype.lower()]
    if typ:
        ntype = typ[0]

    page = 1
    if request.args.get("page") is not None and int(request.args.get("page")) > 0:
        page = request.args.get("page")
    items_per_page = request.args.get("items_per_page") or ITEMS_PER_PAGE

    include_only = request.args.getlist("include_only")

    total_pages, nodes, _ = database.get_nodes_with_pagination(
        name=name,
        section=opt_section,
        subsection=opt_subsection,
        link=opt_hyperlink,
        page=int(page),
        items_per_page=int(items_per_page),
        include_only=include_only,
        version=opt_version,
        ntype=ntype,
    )
    result = {}
    result["total_pages"] = total_pages
    result["page"] = page
    if nodes:
        if opt_osib:
            result["osib"] = odefs.cre2osib(nodes).todict()
        res = [node.todict() for node in nodes]
        result["standards"] = res
        return jsonify(result)
    else:
        abort(404)


# TODO: (spyros) paginate
@app.route("/rest/v1/tags", methods=["GET"])
def find_document_by_tag() -> Any:
    database = db.Node_collection()
    tags = request.args.getlist("tag")
    opt_osib = request.args.get("osib")
    documents = database.get_by_tags(tags)
    if documents:
        res = [doc.todict() for doc in documents]
        result = {"data": res}
        if opt_osib:
            result["osib"] = odefs.cre2osib(documents).todict()
        return jsonify(result)
    abort(404)


@app.route("/rest/v1/gap_analysis", methods=["GET"])
@cache.cached(timeout=50)
def gap_analysis() -> Any:  # TODO (spyros): add export result to spreadsheet
    database = db.Node_collection()
    standards = request.args.getlist("standard")
    documents = database.gap_analysis(standards=standards)
    if documents:
        res = [doc.todict() for doc in documents]
        return jsonify(res)


@app.route("/rest/v1/text_search", methods=["GET"])
# @cache.cached(timeout=50)
def text_search() -> Any:
    """
    Performs arbitrary text search among all known documents.
    Formats supported:
        * 'CRE:<id>' will search for the <id> in cre ids
        * 'CRE:<name>' will search for the <name> in cre names
        * 'Standard:<name>[:<section>:subsection]' will search for
              all entries of <name> and optionally, section/subsection
        * '\d\d\d-\d\d\d' (two sets of 3 digits) will first try to match
                           CRE ids before it performs a free text search
        Anything else will be a case insensitive LIKE query in the database
    """
    database = db.Node_collection()
    text = request.args.get("text")
    documents = database.text_search(text)
    if documents:
        res = [doc.todict() for doc in documents]
        return jsonify(res)
    else:
        abort(404)


@app.errorhandler(404)
def page_not_found(e) -> Any:
    return "Resource Not found", 404


# If no other routes are matched, serve the react app, or any other static files (like bundle.js)
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
# @cache.cached(timeout=50)
def index(path: str) -> Any:
    if path != "" and os.path.exists(app.static_folder + "/" + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")


@app.before_request
def before_request():
    if current_app.config["ENVIRONMENT"] != "PRODUCTION":
        return

    if not request.is_secure:
        print("https redir")
        url = request.url.replace("http://", "https://", 1)
        code = 301
        return redirect(url, code=code)


@app.after_request
def add_header(response):
    response.cache_control.max_age = 300
    return response


if __name__ == "__main__":
    app.run(use_reloader=False, debug=False)
