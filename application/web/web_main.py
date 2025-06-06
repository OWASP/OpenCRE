# type: ignore

# silence mypy for the routes file
import csv
from functools import wraps
import json
import logging
import os
import io
import pathlib
import urllib.parse
from alive_progress import alive_bar
from typing import Any
from application.utils import oscal_utils, redis

from rq import job, exceptions

from application.utils import spreadsheet_parsers
from application.utils import oscal_utils, redis
from application.database import db
from application.cmd import cre_main
from application.defs import cre_defs as defs
from application.defs import cre_exceptions

from application.utils import spreadsheet as sheet_utils
from application.utils import mdutils, redirectors, gap_analysis
from application.prompt_client import prompt_client as prompt_client
from enum import Enum
from flask import json as flask_json
from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    request,
    send_from_directory,
    url_for,
    session,
    send_file,
)
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from application.utils.spreadsheet import write_csv
import oauthlib
import google.auth.transport.requests


ITEMS_PER_PAGE = 20

app = Blueprint(
    "web",
    __name__,
    static_folder=os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "../frontend/www"
    ),
)

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
        lnk = defs.Link(ltype=defs.LinkTypes.Related, document=o)
        if not cre.has_link(lnk) and o.id != cre.id:
            cre.add_link(lnk)
    return cre


def neo4j_not_running_rejection():
    logger.info("Neo4j is disabled functionality will be limited!")
    return (
        jsonify(
            {
                "message": "Backend services connected to this feature are not running at the moment."
            }
        ),
        500,
    )


posthog = None
if os.environ.get("POSTHOG_API_KEY") and os.environ.get("POSTHOG_HOST"):
    from posthog import Posthog

    posthog = Posthog(
        project_api_key=os.environ.get("POSTHOG_API_KEY"),
        host=os.environ.get("POSTHOG_HOST"),
    )


@app.route("/rest/v1/id/<creid>", methods=["GET"])
@app.route("/rest/v1/name/<crename>", methods=["GET"])
def find_cre(creid: str = None, crename: str = None) -> Any:  # refer
    if posthog:
        posthog.capture(f"find_cre", f"id:{creid};name{crename}")
    database = db.Node_collection()
    include_only = request.args.getlist("include_only")
    # opt_osib = request.args.get("osib")
    opt_format = request.args.get("format")
    cres = database.get_CREs(external_id=creid, name=crename, include_only=include_only)
    if cres:
        if len(cres) > 1:
            logger.error("get by id returned more than one results? This looks buggy")
        cre = cres[0]
        result = {"data": cre.todict()}
        # disable until we have a consensus on tag behaviour
        # cre = extend_cre_with_tag_links(cre=cre, collection=database)
        # if opt_osib:
        #     result["osib"] = odefs.cre2osib([cre]).todict()

        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md([cre])}</pre>"

        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.ExportSheet().prepare_spreadsheet(
                docs=[cre], storage=database
            )
            return write_csv(docs=docs).getvalue().encode("utf-8")

        elif opt_format == SupportedFormats.OSCAL.value:
            result = {"data": json.loads(oscal_utils.document_to_oscal(cre))}

        return jsonify(result)
    abort(404, "CRE does not exist")


@app.route("/rest/v1/<ntype>/<name>", methods=["GET"])
@app.route("/rest/v1/standard/<name>", methods=["GET"])
def find_node_by_name(name: str, ntype: str = defs.Credoctypes.Standard.value) -> Any:
    if posthog:
        posthog.capture(f"find_node_by_name", f"hame:{name};nodeType{ntype}")

    database = db.Node_collection()
    opt_section = request.args.get("section")
    opt_sectionID = request.args.get("sectionID")
    # opt_osib = request.args.get("osib")
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
            docs = sheet_utils.ExportSheet().prepare_spreadsheet(
                docs=nodes, storage=database
            )
            return write_csv(docs=docs).getvalue().encode("utf-8")

        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(nodes)))

        # if opt_osib:
        #     result["osib"] = odefs.cre2osib(nodes).todict()

        res = [node.todict() for node in nodes]
        result["standards"] = res

        return jsonify(result)
    else:
        abort(404, "Node does not exist")


# TODO: (spyros) paginate
@app.route("/rest/v1/tags", methods=["GET"])
def find_document_by_tag() -> Any:
    tags = request.args.getlist("tag")
    if posthog:
        posthog.capture(f"find_document_by_tag", f"tags:{tags}")

    database = db.Node_collection()
    # opt_osib = request.args.get("osib")
    opt_format = request.args.get("format")
    documents = database.get_by_tags(tags)
    if documents:
        res = [doc.todict() for doc in documents]
        result = {"data": res}
        # if opt_osib:
        #     result["osib"] = odefs.cre2osib(documents).todict()
        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md(documents)}</pre>"
        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.ExportSheet().prepare_spreadsheet(
                docs=documents, storage=database
            )
            return write_csv(docs=docs).getvalue().encode("utf-8")
        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(documents)))

        return jsonify(result)
    abort(404, "Tag does not exist")


@app.route("/rest/v1/map_analysis", methods=["GET"])
def map_analysis() -> Any:
    standards = request.args.getlist("standard")
    if posthog:
        posthog.capture(f"map_analysis", f"standards:{standards}")

    database = db.Node_collection()
    standards = request.args.getlist("standard")
    gap_analysis_dict = gap_analysis.schedule(standards, database)
    if gap_analysis_dict.get("result"):
        return jsonify(gap_analysis_dict)
    if gap_analysis_dict.get("error"):
        abort(404)
    return jsonify({"job_id": gap_analysis_dict.get("job_id")})


@app.route("/rest/v1/map_analysis_weak_links", methods=["GET"])
def map_analysis_weak_links() -> Any:
    standards = request.args.getlist("standard")
    if posthog:
        posthog.capture(f"map_analysis_weak_links", f"standards:{standards}")

    key = request.args.get("key")
    cache_key = gap_analysis.make_subresources_key(standards=standards, key=key)

    database = db.Node_collection()
    gap_analysis_results = database.get_gap_analysis_result(cache_key=cache_key)
    if gap_analysis_results:
        gap_analysis_dict = json.loads(gap_analysis_results)
        if gap_analysis_dict.get("result"):
            return jsonify({"result": gap_analysis_dict.get("result")})

    # if conn.exists(cache_key):
    #     gap_analysis_results = conn.get(cache_key)
    #     if gap_analysis_results:
    #         gap_analysis_dict = json.loads(gap_analysis_results)
    #         if gap_analysis_dict.get("result"):
    #             return jsonify({"result": gap_analysis_dict.get("result")})
    abort(404, "No such Cache")


@app.route("/rest/v1/ma_job_results", methods=["GET"])
def fetch_job() -> Any:
    logger.debug("fetching job results")
    jobid = request.args.get("id")
    conn = redis.connect()
    try:
        res = job.Job.fetch(id=jobid, connection=conn)
    except exceptions.NoSuchJobError as nje:
        abort(404, "No such job")

    logger.debug("job exists")
    if res.get_status() == job.JobStatus.FAILED:
        abort(500, "background job failed")
    elif res.get_status() == job.JobStatus.STOPPED:
        abort(500, "background job stopped")
    elif res.get_status() == job.JobStatus.CANCELED:
        abort(500, "background job canceled")
    elif (
        res.get_status() == job.JobStatus.STARTED
        or res.get_status() == job.JobStatus.QUEUED
    ):
        logger.debug("but hasn't finished")
        return jsonify({"status": res.get_status()})

    result = res.latest_result()
    logger.debug("and has finished")

    if res.latest_result().type == result.Type.SUCCESSFUL:
        ga_result = result.return_value
        logger.debug("and has results")

        if len(ga_result) > 1:
            standards = ga_result[0]
            standards_hash = gap_analysis.make_resources_key(standards)

            if conn.exists(standards_hash):
                logger.debug("and hash is already in cache")
                # ga = conn.get(standards_hash)
                database = db.Node_collection()
                ga = database.get_gap_analysis_result(standards_hash)
                if ga:
                    # logger.__delattr__("and results in cache")
                    ga = flask_json.loads(ga)
                    if ga.get("result"):
                        return jsonify(ga)
                    else:
                        logger.error(
                            "Finished job does not have a result object, this is a bug!"
                        )
                        abort(500, "this is a bug, please raise a ticket")
        return jsonify({"status": res.get_status()})
    elif res.latest_result().type == result.Type.FAILED:
        logger.error(res.latest_result().exc_string)
        abort(500)
    else:
        logger.warning(f"job stopped? {res.latest_result().type}")
        abort(500)


@app.route("/rest/v1/standards", methods=["GET"])
def standards() -> Any:
    if posthog:
        posthog.capture(f"standards", "")

    database = db.Node_collection()
    standards = database.standards()
    return standards


@app.route("/rest/v1/text_search", methods=["GET"])
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
    if posthog:
        posthog.capture(f"text_search", f"text:{text}")

    opt_format = request.args.get("format")
    documents = database.text_search(text)
    if documents:
        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md(documents)}</pre>"
        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.ExportSheet().prepare_spreadsheet(
                docs=documents, storage=database
            )
            return write_csv(docs=docs).getvalue().encode("utf-8")
        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(documents)))

        res = [doc.todict() for doc in documents]
        return jsonify(res)
    else:
        abort(404, "No object matches the given search terms")


@app.route("/rest/v1/root_cres", methods=["GET"])
def find_root_cres() -> Any:
    """
    Useful for fast browsing the graph from the top

    """
    if posthog:
        posthog.capture(f"find_root_cres", "")

    database = db.Node_collection()
    # opt_osib = request.args.get("osib")
    opt_format = request.args.get("format")
    documents = database.get_root_cres()
    if documents:
        res = [doc.todict() for doc in documents]
        result = {"data": res}
        # if opt_osib:
        #     result["osib"] = odefs.cre2osib(documents).todict()
        if opt_format == SupportedFormats.Markdown.value:
            return f"<pre>{mdutils.cre_to_md(documents)}</pre>"
        elif opt_format == SupportedFormats.CSV.value:
            docs = sheet_utils.ExportSheet().prepare_spreadsheet(
                docs=documents, storage=database
            )
            return write_csv(docs=docs).getvalue().encode("utf-8")
        elif opt_format == SupportedFormats.OSCAL.value:
            return jsonify(json.loads(oscal_utils.list_to_oscal(documents)))

        return jsonify(result)
    abort(404, "No root CREs")


@app.errorhandler(404)
def page_not_found(e) -> Any:
    return "Resource Not found", 404


# If no other routes are matched, serve the react app, or any other static files (like bundle.js)
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def index(path: str) -> Any:
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")


@app.route("/smartlink/<ntype>/<name>/<section>", methods=["GET"])
def smartlink(
    name: str, ntype: str = defs.Credoctypes.Standard.value, section: str = ""
) -> Any:
    """if node is found, show node, else redirect"""
    # ATTENTION: DO NOT MESS WITH THIS FUNCTIONALITY WITHOUT A TICKET AND CORE CONTRIBUTORS APPROVAL!
    # CRITICAL FUNCTIONALITY DEPENDS ON THIS!
    if posthog:
        posthog.capture(f"smartlink", f"name:{name}")

    database = db.Node_collection()
    opt_version = request.args.get("version")
    # match ntype to the credoctypes case-insensitive
    typ = [t.value for t in defs.Credoctypes if t.value.lower() == ntype.lower()]
    doctype = None if not typ else typ[0]

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
    elif doctype == defs.Credoctypes.Standard.value and redirectors.redirect(
        name, section
    ):
        logger.info(
            f"did not find node of type {ntype}, name {name} and section {section}, redirecting to external resource"
        )
        return redirect(redirectors.redirect(name, section))
    else:
        logger.warning(f"not sure what happened, 404")
        return abort(404, "Document does not exist")


@app.route("/rest/v1/deeplink/<ntype>/<name>", methods=["GET"])
@app.route("/rest/v1/deeplink/<name>", methods=["GET"])
@app.route("/deeplink/<ntype>/<name>", methods=["GET"])
@app.route("/deeplink/<name>", methods=["GET"])
@app.route("/deeplink/<name>/section/<section>", methods=["GET"])
@app.route("/deeplink/<name>/section/<section>/sectionid/<section_id>", methods=["GET"])
@app.route("/deeplink/<name>/section/<section>/sectionID/<section_id>", methods=["GET"])
@app.route("/deeplink/<name>/sectionid/<section_id>", methods=["GET"])
@app.route("/deeplink/<name>/sectionID/<section_id>", methods=["GET"])
def deeplink(
    name: str, ntype: str = "", section: str = "", section_id: str = ""
) -> Any:
    database = db.Node_collection()
    opt_section = request.args.get("section")
    opt_sectionID = request.args.get("sectionID")
    opt_sectionid = request.args.get("sectionid")
    opt_version = request.args.get("version")
    opt_subsection = request.args.get("subsection")
    if posthog:
        posthog.capture(f"deeplink", f"name:{name}")

    if opt_section:
        opt_section = urllib.parse.unquote(opt_section)
    elif section:
        opt_section = urllib.parse.unquote(section)

    if opt_sectionID:
        opt_sectionID = urllib.parse.unquote(opt_sectionID)
    elif opt_sectionid:
        opt_sectionID = urllib.parse.unquote(opt_sectionid)
    elif section_id:
        opt_sectionID = urllib.parse.unquote(section_id)

    nodes = None
    nodes = database.get_nodes(
        name=name,
        section=opt_section,
        subsection=opt_subsection,
        version=opt_version,
        sectionID=opt_sectionID,
    )
    for node in nodes:
        if len(node.hyperlink) > 0:
            return redirect(location=node.hyperlink)

    return abort(404)


@app.before_request
def before_request():
    if os.environ.get("INSECURE_REQUESTS"):
        return
    elif not request.is_secure:
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
    if posthog:
        posthog.capture(f"chat_cre", "")

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
                redirect_uri=(
                    request.root_url.rstrip("/") + url_for("web.callback")
                ).replace("http://", "https://"),
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
        flow_instance.flow.fetch_token(
            authorization_response=request.url.replace("http://", "https://")
        )  # cloud run (and others) rewrite https to http at the container
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


@app.route("/rest/v1/all_cres", methods=["GET"])
def all_cres() -> Any:
    database = db.Node_collection()
    if posthog:
        posthog.capture(f"all_cres", "")

    page = 1
    per_page = ITEMS_PER_PAGE
    if request.args.get("page") is not None and int(request.args.get("page")) > 0:
        page = int(request.args.get("page"))

    if (
        request.args.get("per_page") is not None
        and int(request.args.get("per_page")) > 0
    ):
        per_page = int(request.args.get("per_page"))

    documents, page, total_pages = database.all_cres_with_pagination(page, per_page)
    if documents:
        res = [doc.todict() for doc in documents]
        return jsonify({"data": res, "page": page, "total_pages": total_pages})
    abort(404)


# Importing Handlers


@app.route("/rest/v1/cre_csv", methods=["GET"])
def get_cre_csv() -> Any:
    if posthog:
        posthog.capture(f"get_cre_csv", "")

    database = db.Node_collection()
    root_cres = database.get_root_cres()
    if root_cres:
        docs = sheet_utils.generate_mapping_template_file(
            database=database, docs=root_cres
        )
        csvVal = write_csv(docs=docs).getvalue().encode("utf-8")

        # Creating the byteIO object from the StringIO Object
        mem = io.BytesIO()
        mem.write(csvVal)
        mem.seek(0)

        return send_file(
            mem,
            as_attachment=True,
            download_name="CRE-Catalogue.csv",
            mimetype="text/csv",
        )
    abort(404)


@app.route("/rest/v1/cre_csv_import", methods=["POST"])
def import_from_cre_csv() -> Any:
    if not os.environ.get("CRE_ALLOW_IMPORT"):
        abort(
            403,
            "Importing is disabled, set the environment variable CRE_ALLOW_IMPORT to allow this functionality",
        )

    # TODO: (spyros) add optional gap analysis and embeddings calculation
    database = db.Node_collection().with_graph()
    file = request.files.get("cre_csv")
    calculate_embeddings = (
        False if not request.args.get("calculate_embeddings") else True
    )
    calculate_gap_analysis = (
        False if not request.args.get("calculate_gap_analysis") else True
    )

    if file is None:
        abort(400, "No file provided")
    contents = file.read()
    csv_read = csv.DictReader(contents.decode("utf-8").splitlines())
    try:
        documents = spreadsheet_parsers.parse_export_format(list(csv_read))
    except cre_exceptions.DuplicateLinkException as dle:
        abort(500, f"error during parsing of the incoming CSV, err:{dle}")
    cres = documents.pop(defs.Credoctypes.CRE.value)

    standards = documents
    new_cres = []
    for cre in cres:
        new_cre, exists = cre_main.register_cre(cre, database)
        if not exists:
            new_cres.append(new_cre)

    for _, entries in standards.items():
        cre_main.register_standard(
            collection=database,
            standard_entries=list(entries),
            generate_embeddings=calculate_embeddings,
            calculate_gap_analysis=calculate_gap_analysis,
        )
    return jsonify(
        {
            "status": "success",
            "new_cres": [c.external_id for c in new_cres],
            "new_standards": len(standards),
        }
    )


# /End Importing Handlers


# @app.route("/rest/v1/all_nodes", methods=["GET"])
# def all_nodes() -> Any:
#     database = db.Node_collection()
#     page = 1
#     if request.args.get("page") is not None and int(request.args.get("page")) > 0:
#         page = request.args.get("page")
#     items_per_page = request.args.get("items_per_page") or ITEMS_PER_PAGE

#     documents, page, total_pages = database.all_nodes_with_pagination(
#         page, items_per_page
#     )
#     if documents:
#         res = [doc.todict() for doc in documents]
#         return jsonify({"data": res, "page": page, "total_pages": total_pages})
#     abort(404)


if __name__ == "__main__":
    app.run(use_reloader=False, debug=True)
