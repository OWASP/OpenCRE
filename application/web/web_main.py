# type: ignore
# silence mypy for the routes file
from functools import wraps
import json
import logging
import os
import pathlib
import urllib.parse
from typing import Any
from application.utils import oscal_utils

from application import cache
from application.database import db
from application.defs import cre_defs as defs
from application.defs import osib_defs as odefs
from application.utils import spreadsheet as sheet_utils
from application.utils import mdutils, redirectors
from application.prompt_client import prompt_client as prompt_client
from enum import Enum
from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    request,
    send_from_directory,
    url_for,
    session,
)
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from application.utils.spreadsheet import write_csv
import oauthlib
import google.auth.transport.requests

ITEMS_PER_PAGE = 20

app = Blueprint("web", __name__, static_folder="../frontend/www")

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SupportedFormats(Enum):
    Markdown = "md"
    CSV = "csv"
    JSON = "json"
    YAML = "yaml"
    OSCAL = "oscal"


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
    opt_format = request.args.get("format")
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

        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md([cre])}</pre>"

        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.prepare_spreadsheet(collection=database, docs=[cre])
            return write_csv(docs=docs).getvalue().encode("utf-8")

        elif opt_format == SupportedFormats.OSCAL.value:
            result = {"data": json.loads(oscal_utils.document_to_oscal(cre))}

        return jsonify(result)
    abort(404)


@app.route("/rest/v1/<ntype>/<name>", methods=["GET"])
@app.route("/rest/v1/standard/<name>", methods=["GET"])
# @cache.cached(timeout=50)
def find_node_by_name(name: str, ntype: str = defs.Credoctypes.Standard.value) -> Any:
    database = db.Node_collection()
    opt_section = request.args.get("section")
    opt_sectionID = request.args.get("sectionID")
    opt_osib = request.args.get("osib")
    opt_version = request.args.get("version")
    opt_format = request.args.get("format")
    if opt_section:
        opt_section = urllib.parse.unquote(opt_section)
    if opt_sectionID:
        opt_sectionID = urllib.parse.unquote(opt_sectionID)
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
    total_pages, nodes = None, None
    if not opt_format:
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
            sectionID=opt_sectionID,
        )
    else:
        nodes = database.get_nodes(
            name=name,
            section=opt_section,
            subsection=opt_subsection,
            link=opt_hyperlink,
            include_only=include_only,
            version=opt_version,
            ntype=ntype,
            sectionID=opt_sectionID,
        )
    result = {}
    result["total_pages"] = total_pages
    result["page"] = page
    if nodes:
        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md(nodes)}</pre>"

        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.prepare_spreadsheet(collection=database, docs=nodes)
            return write_csv(docs=docs).getvalue().encode("utf-8")

        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(nodes)))

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
    opt_format = request.args.get("format")
    documents = database.get_by_tags(tags)
    if documents:
        res = [doc.todict() for doc in documents]
        result = {"data": res}
        if opt_osib:
            result["osib"] = odefs.cre2osib(documents).todict()
        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md(documents)}</pre>"
        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.prepare_spreadsheet(collection=database, docs=documents)
            return write_csv(docs=docs).getvalue().encode("utf-8")
        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(documents)))

        return jsonify(result)
    logger.info("tags aborting 404")
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
    opt_format = request.args.get("format")
    documents = database.text_search(text)
    if documents:
        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md(documents)}</pre>"
        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.prepare_spreadsheet(collection=database, docs=documents)
            return write_csv(docs=docs).getvalue().encode("utf-8")
        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(documents)))

        res = [doc.todict() for doc in documents]
        return jsonify(res)
    else:
        abort(404)


@app.route("/rest/v1/root_cres", methods=["GET"])
def find_root_cres() -> Any:
    """Useful for fast browsing the graph from the top"""
    database = db.Node_collection()
    logger.info("got database")
    opt_osib = request.args.get("osib")
    opt_format = request.args.get("format")
    documents = database.get_root_cres()
    logger.info(f"got {len(documents)} cres")

    if documents:
        res = [doc.todict() for doc in documents]
        result = {"data": res}
        if opt_osib:
            result["osib"] = odefs.cre2osib(documents).todict()
        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md(documents)}</pre>"
        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.prepare_spreadsheet(collection=database, docs=documents)
            return write_csv(docs=docs).getvalue().encode("utf-8")
        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(documents)))

        return jsonify(result)
    abort(404)


@app.errorhandler(404)
def page_not_found(e) -> Any:
    return "Resource Not found", 404


# If no other routes are matched, serve the react app, or any other static files (like bundle.js)
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
# @cache.cached(timeout=50)
def index(path: str) -> Any:
    print(1)
    if path != "" and os.path.exists(app.static_folder + "/" + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")


@app.route("/smartlink/<ntype>/<name>/<section>", methods=["GET"])
# @cache.cached(timeout=50)
def smartlink(
    name: str, ntype: str = defs.Credoctypes.Standard.value, section: str = ""
) -> Any:
    """if node is found, show node, else redirect"""
    database = db.Node_collection()
    opt_version = request.args.get("version")
    # match ntype to the credoctypes case-insensitive
    typ = [t for t in defs.Credoctypes if t.value.lower() == ntype.lower()]
    doctype = None
    if typ:
        doctype = typ[0]

    page = 1
    items_per_page = 1
    found_section_id = False
    _, nodes, _ = database.get_nodes_with_pagination(
        name=name,
        section=section,
        page=int(page),
        items_per_page=int(items_per_page),
        version=opt_version,
        ntype=doctype,
    )

    if not nodes or len(nodes) == 0:
        _, nodes, _ = database.get_nodes_with_pagination(
            name=name,
            sectionID=section,
            page=int(page),
            items_per_page=int(items_per_page),
            version=opt_version,
            ntype=doctype,
        )
        found_section_id = True
    if nodes and len(nodes[0].links):
        logger.info(
            f"found node of type {ntype}, name {name} and section {section}, redirecting to opencre"
        )
        if found_section_id:
            return redirect(f"/node/{ntype}/{name}/sectionid/{section}")
        return redirect(f"/node/{ntype}/{name}/section/{section}")
    elif ntype == defs.Credoctypes.Standard.value and redirectors.redirect(
        name, section
    ):
        logger.info(
            f"did not find node of type {ntype}, name {name} and section {section}, redirecting to external resource"
        )
        return redirect(redirectors.redirect(name, section))
    else:
        logger.info(f"not sure what happened, 404")
        return abort(404)


@app.before_request
def before_request():
    if current_app.config["ENVIRONMENT"] != "PRODUCTION":
        return

    if not request.is_secure:
        url = request.url.replace("http://", "https://", 1)
        code = 301
        return redirect(url, code=code)


@app.after_request
def add_header(response):
    response.cache_control.max_age = 300
    return response


def login_required(f):
    @wraps(f)
    def login_r(*args, **kwargs):
        if os.environ.get("NO_LOGIN"):
            return f(*args, **kwargs)
        if "google_id" not in session or "name" not in session:
            allowed_domains = os.environ.get("LOGIN_ALLOWED_DOMAINS")
            abort(
                401,
                description=f"You need an account with one of the following providers to access this functionality {allowed_domains}",
            )
        else:
            return f(*args, **kwargs)

    return login_r


@app.route("/rest/v1/completion", methods=["POST"])
@login_required
def chat_cre() -> Any:
    message = request.get_json(force=True)
    database = db.Node_collection()
    prompt = prompt_client.PromptHandler(database)
    response = prompt.generate_text(message.get("prompt"))
    return jsonify(response)


class CREFlow:
    """ "This class handles authentication with google's oauth"""

    __instance = None
    flow = None

    @classmethod
    def instance(cls):
        if cls.__instance is None:
            cls.__instance = cls.__new__(cls)
            client_secrets_file = os.path.join(
                pathlib.Path(__file__).parent.parent.parent, "gcp_secret.json"
            )
            if not os.path.exists(client_secrets_file):
                if os.environ.get("GOOGLE_SECRET_JSON"):
                    with open(client_secrets_file, "w") as f:
                        f.write(os.environ.get("GOOGLE_SECRET_JSON"))
                else:
                    logger.fatal(
                        "neither file gcp_secret.json nor env GOOGLE_SECRET_JSON have been set"
                    )
            cls.flow = Flow.from_client_secrets_file(
                client_secrets_file=client_secrets_file,
                scopes=[
                    "https://www.googleapis.com/auth/userinfo.profile",
                    "https://www.googleapis.com/auth/userinfo.email",
                    "openid",
                ],
                redirect_uri=request.root_url.rstrip("/") + url_for("web.callback"),
            )
        return cls.__instance

    def __init__(sel):
        raise ValueError("class is a singleton, please call instance() instead")


@app.route("/rest/v1/login")
def login():
    if os.environ.get("NO_LOGIN"):
        session["state"] = {"state": True}
        session["google_id"] = "some dev id"
        session["name"] = "dev user"
        return redirect("/chatbot")
    flow_instance = CREFlow.instance()
    authorization_url, state = flow_instance.flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)


@app.route("/rest/v1/user")
@login_required
def logged_in_user():
    if os.environ.get("NO_LOGIN"):
        return "foobar"
    return session.get("email")


@app.route("/rest/v1/callback")
def callback():
    flow_instance = CREFlow.instance()
    try:
        flow_instance.flow.fetch_token(authorization_response=request.url)
    except oauthlib.oauth2.rfc6749.errors.MismatchingStateError as mse:
        return redirect("/chatbot")
    if not session.get("state") or session.get("state") != request.args["state"]:
        redirect(url_for("web.login"))  # State does not match!
    credentials = flow_instance.flow.credentials
    token_request = google.auth.transport.requests.Request()
    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=os.environ.get("GOOGLE_CLIENT_ID"),
    )

    session["google_id"] = id_info.get("sub")
    session["name"] = id_info.get("name")
    session["email"] = id_info.get("email")
    allowed_domains = os.environ.get("LOGIN_ALLOWED_DOMAINS")
    allowed_domains = allowed_domains.split(",") if allowed_domains else []
    if not allowed_domains:
        abort(
            500,
            "You have not set any domain in the allowed domains list, to ignore this set LOGIN_ALLOWED_DOMAINS to '*'",
        )
    if (
        allowed_domains
        and allowed_domains != ["*"]
        and not any([id_info.get("email").endswith(x) for x in allowed_domains])
    ):
        allowed_domains = os.environ.get("LOGIN_ALLOWED_DOMAINS")
        abort(
            401,
            description=f"You need an account with one of the following providers to access this functionality {allowed_domains}",
        )
    return redirect("/chatbot")


@app.route("/rest/v1/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(use_reloader=False, debug=False)
