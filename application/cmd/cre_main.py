import time
import argparse
import json
import logging
import os
import shutil
import yaml
import tempfile
import requests

from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
from rq import Queue, job, exceptions
from dacite import from_dict
from dacite.config import Config

from application.utils.external_project_parsers.base_parser import BaseParser
from application import create_app  # type: ignore
from application.config import CMDConfig
from application.database import db
from application.defs import cre_defs as defs
from application.defs import osib_defs as odefs
from application.utils import spreadsheet as sheet_utils
from application.utils import redis
from application.utils import spreadsheet_parsers
from alive_progress import alive_bar
from application.prompt_client import prompt_client as prompt_client
from application.utils import gap_analysis

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = None


def register_node(node: defs.Node, collection: db.Node_collection) -> db.Node:
    """
    for each link find if either the root node or the link have a CRE,
    then map the one who doesn't to the CRE
    if both don't map to anything, just add them in the db as unlinked nodes
    """
    if not node:
        raise ValueError("node is None")

    linked_node = collection.add_node(node)
    if node.embeddings:
        collection.add_embedding(
            linked_node,
            doctype=node.doctype,
            embeddings=node.embeddings,
            embedding_text=node.embeddings_text,
        )
    cre_less_nodes: List[defs.Node] = []

    # we need to know the cres added in case we encounter a higher level CRE,
    # in which case we get the higher level CRE to link to these cres
    cres_added = []

    for link in node.links:
        if type(link.document).__name__ in [
            defs.Standard.__name__,
            defs.Code.__name__,
            defs.Tool.__name__,
        ]:
            # if a node links another node it is likely that a writer wants to reference something
            # in that case, find which of the two nodes has at least one CRE attached to it and link both to the parent CRE
            cres = collection.find_cres_of_node(link.document)
            db_link = collection.add_node(link.document)
            if cres:
                for cre in cres:
                    collection.add_link(cre=cre, node=linked_node, type=link.ltype)
                    for unlinked_standard in cre_less_nodes:  # if anything in this
                        collection.add_link(
                            cre=cre,
                            node=db.dbNodeFromNode(unlinked_standard),
                            type=link.ltype,
                        )
            else:
                cres = collection.find_cres_of_node(linked_node)
                if cres:
                    for cre in cres:
                        collection.add_link(cre=cre, node=db_link, type=link.ltype)
                        for unlinked_node in cre_less_nodes:
                            collection.add_link(
                                cre=cre,
                                node=db.dbNodeFromNode(unlinked_node),
                                type=link.ltype,
                            )
                else:  # if neither the root nor a linked node has a CRE, add both as unlinked nodes
                    cre_less_nodes.append(link.document)

            if link.document.links and len(link.document.links) > 0:
                register_node(node=link.document, collection=collection)

        elif type(link.document).__name__ == defs.CRE.__name__:
            # dbcre,_ = register_cre(link.document, collection) # CREs are idempotent
            c = collection.get_CREs(name=link.document.name)[0]
            dbcre = db.dbCREfromCRE(c)
            collection.add_link(dbcre, linked_node, type=link.ltype)
            cres_added.append(dbcre)
            for unlinked_standard in cre_less_nodes:  # if anything in this
                collection.add_link(
                    cre=dbcre,
                    node=db.dbNodeFromNode(unlinked_standard),
                    type=link.ltype,
                )
            cre_less_nodes = []

    return linked_node


def register_cre(cre: defs.CRE, collection: db.Node_collection) -> Tuple[db.CRE, bool]:
    existing = False
    if collection.get_CREs(name=cre.id):
        existing = True

    dbcre: db.CRE = collection.add_cre(cre)
    for link in cre.links:
        if type(link.document) == defs.CRE:
            logger.info(f"{link.document.id} {link.ltype} {cre.id}")
            lower_cre, _ = register_cre(link.document, collection)
            collection.add_internal_link(
                higher=dbcre,
                lower=lower_cre,
                type=link.ltype,
            )
        else:
            collection.add_link(
                cre=dbcre,
                node=register_node(node=link.document, collection=collection),
                type=link.ltype,
            )
    return dbcre, existing


def parse_file(
    filename: str, yamldocs: List[Dict[str, Any]], scollection: db.Node_collection
) -> Optional[List[defs.Document]]:
    """given yaml from export format deserialise to internal standards format and add standards to db"""

    resulting_objects = []
    for contents in yamldocs:
        links = []

        document: Optional[defs.Document] = None
        register_callback: Optional[Callable[[Any, Any], Any]] = None

        if not isinstance(
            contents, dict
        ):  # basic object matching, make sure we at least have an object, golang has this build in :(
            logger.fatal("Malformed file %s, skipping" % filename)
            return None

        if contents.get("links"):
            links = contents.pop("links")

        if contents.get("doctype") == defs.Credoctypes.CRE.value:
            document = from_dict(
                data_class=defs.CRE,
                data=contents,
                config=Config(cast=[defs.Credoctypes]),
            )
            # document = defs.CRE(**contents)
            register_callback = register_cre
        elif contents.get("doctype") in (
            defs.Credoctypes.Standard.value,
            defs.Credoctypes.Code.value,
            defs.Credoctypes.Tool.value,
        ):
            # document = defs.Standard(**contents)
            doctype = contents.get("doctype")
            data_class = (
                defs.Standard
                if doctype == defs.Credoctypes.Standard.value
                else (
                    defs.Code
                    if doctype == defs.Credoctypes.Code.value
                    else defs.Tool if doctype == defs.Credoctypes.Tool.value else None
                )
            )
            document = from_dict(
                data_class=data_class,
                data=contents,
                config=Config(cast=[defs.Credoctypes]),
            )
            register_callback = register_node

        for link in links:
            doclink = parse_file(
                filename=filename,
                yamldocs=[link.get("document")],
                scollection=scollection,
            )

            if doclink:
                if len(doclink) > 1:
                    logger.fatal(
                        "Parsing single document returned 2 results this is a bug"
                    )
                document.add_link(
                    defs.Link(
                        document=doclink[0],
                        ltype=link.get("type"),
                        tags=link.get("tags"),
                    )
                )
        if register_callback:
            register_callback(document, collection=scollection)  # type: ignore
        else:
            logger.warning("Callback to register Document is None, likely missing data")
        resulting_objects.append(document)
    return resulting_objects


def register_standard(
    standard_entries: List[defs.Standard],
    collection: db.Node_collection = None,
    generate_embeddings=True,
    calculate_gap_analysis=True,
    db_connection_str: str = "",
):
    if os.environ.get("CRE_NO_GEN_EMBEDDINGS"):
        generate_embeddings = False

    if not standard_entries:
        logger.warning("register_standard() called with no standard_entries")
        return

    if collection is None:
        collection = db_connect(path=db_connection_str)

    conn = redis.connect()
    ph = prompt_client.PromptHandler(database=collection)
    importing_name = standard_entries[0].name
    standard_hash = gap_analysis.make_resources_key([importing_name])
    if calculate_gap_analysis and conn.get(standard_hash):
        logger.info(
            f"Standard importing job with info-hash {standard_hash} has already returned, skipping"
        )
        return
    logger.info(
        f"Registering resource {importing_name} of length {len(standard_entries)}"
    )
    for node in standard_entries:
        if not node:
            logger.info(
                f"encountered empty node while importing {standard_entries[0].name}"
            )
            continue
        register_node(node, collection)
        if node.embeddings:
            logger.debug(
                f"node has embeddings populated, skipping generation for resource {importing_name}"
            )
            generate_embeddings = False
    if generate_embeddings and importing_name:
        ph.generate_embeddings_for(importing_name)

    if calculate_gap_analysis and not os.environ.get("CRE_NO_CALCULATE_GAP_ANALYSIS"):
        # calculate gap analysis
        populate_neo4j_db(collection)
        jobs = []
        pending_stadards = collection.standards()
        for standard_name in pending_stadards:
            if standard_name == importing_name:
                continue

            fw_key = gap_analysis.make_resources_key([importing_name, standard_name])
            if not collection.gap_analysis_exists(fw_key):
                fw_job = gap_analysis.schedule(
                    standards=[importing_name, standard_name], database=collection
                )
                forward_job_id = fw_job.get("job_id")
                try:
                    forward_job = job.Job.fetch(id=forward_job_id, connection=conn)
                    jobs.append(forward_job)
                except exceptions.NoSuchJobError as nje:
                    logger.error(
                        f"Could not find gap analysis job for for {importing_name} and {standard_name} putting {standard_name} back in the queue"
                    )
                    pending_stadards.append(standard_name)

            bw_key = gap_analysis.make_resources_key([standard_name, importing_name])
            if not collection.gap_analysis_exists(bw_key):
                bw_job = gap_analysis.schedule(
                    standards=[standard_name, importing_name], database=collection
                )
                backward_job_id = bw_job.get("job_id")
                try:
                    backward_job = job.Job.fetch(id=backward_job_id, connection=conn)
                    jobs.append(backward_job)
                except exceptions.NoSuchJobError as nje:
                    logger.error(
                        f"Could not find gap analysis job for for {importing_name} and {standard_name} putting {standard_name} back in the queue"
                    )
                    pending_stadards.append(standard_name)
        redis.wait_for_jobs(jobs)
        conn.set(standard_hash, value="")


def parse_standards_from_spreadsheeet(
    cre_file: List[Dict[str, Any]],
    cache_location: str,
    prompt_handler: prompt_client.PromptHandler,
) -> None:
    """given a yaml with standards, build a list of standards in the db"""
    collection = db_connect(cache_location)
    if any(key.startswith("CRE hierarchy") for key in cre_file[0].keys()):
        conn = redis.connect()
        collection = collection.with_graph()
        redis.empty_queues(conn)
        q = Queue(connection=conn)
        docs = spreadsheet_parsers.parse_hierarchical_export_format(cre_file)
        total_resources = docs.keys()
        jobs = []
        logger.info(f"Importing {len(docs.get(defs.Credoctypes.CRE.value))} CREs")
        with alive_bar(len(docs.get(defs.Credoctypes.CRE.value))) as bar:
            for cre in docs.pop(defs.Credoctypes.CRE.value):
                register_cre(cre, collection)
                bar()

        populate_neo4j_db(collection)
        if not os.environ.get("CRE_NO_GEN_EMBEDDINGS"):
            prompt_handler.generate_embeddings_for(defs.Credoctypes.CRE.value)
        import_only = []
        if os.environ.get("CRE_ROOT_CSV_IMPORT_ONLY"):
            import_only = json.loads(os.environ.get("CRE_ROOT_CSV_IMPORT_ONLY"))
        database = db_connect(cache_location)
        for standard_name, standard_entries in docs.items():
            if os.environ.get("CRE_NO_REIMPORT_IF_EXISTS") and database.get_nodes(
                name=standard_name
            ):
                logger.info(
                    f"Already know of {standard_name} and CRE_NO_REIMPORT_IF_EXISTS is set, skipping"
                )
                continue
            if import_only and standard_name not in import_only:
                continue
            jobs.append(
                q.enqueue_call(
                    description=standard_name,
                    func=register_standard,
                    kwargs={
                        "standard_entries": standard_entries,
                        "collection": None,
                        "db_connection_str": cache_location,
                    },
                    timeout=gap_analysis.GAP_ANALYSIS_TIMEOUT,
                )
            )
        t0 = time.perf_counter()
        total_standards = len(jobs)
        logger.info(f"Importing {total_standards} Standards")
        with alive_bar(theme="classic", total=total_standards) as bar:
            redis.wait_for_jobs(jobs, bar)
        logger.info(
            f"imported {total_standards} standards in {time.perf_counter()-t0} seconds"
        )
        return total_resources
    else:
        logger.fatal(f"could not find any useful keys { cre_file[0].keys()}")


def get_cre_files_from_disk(cre_loc: str) -> Generator[str, None, None]:
    for root, _, cre_docs in os.walk(cre_loc):
        for name in cre_docs:
            if name.endswith(".yaml") or name.endswith(".yml"):
                yield os.path.join(root, name)


def add_from_spreadsheet(spreadsheet_url: str, cache_loc: str, cre_loc: str) -> None:
    """--add --from_spreadsheet <url>
    use the cre db in this repo
    import new mappings from <url>
    export db to ../../cres/
    """
    database = db_connect(path=cache_loc)
    prompt_handler = ai_client_init(database=database)
    spreadsheet = sheet_utils.read_spreadsheet(
        url=spreadsheet_url, alias="new spreadsheet", validate=False
    )
    for _, contents in spreadsheet.items():
        parse_standards_from_spreadsheeet(contents, cache_loc, prompt_handler)

    logger.info(
        "Db located at %s got updated, files extracted at %s" % (cache_loc, cre_loc)
    )


def add_from_disk(cache_loc: str, cre_loc: str) -> None:
    """--add --cre_loc <path>
    use the cre db in this repo
    import new mappings from <path>
    export db to ../../cres/
    """
    database = db_connect(path=cache_loc)
    for file in get_cre_files_from_disk(cre_loc):
        with open(file, "rb") as standard:
            parse_file(
                filename=file,
                yamldocs=list(yaml.safe_load_all(standard)),
                scollection=database,
            )


def review_from_spreadsheet(cache: str, spreadsheet_url: str, share_with: str) -> None:
    """--review --from_spreadsheet <url>
    copy db to new temp dir,
    import new mappings from spreadsheet
    export db to tmp dir
    create new spreadsheet of the new CRE landscape for review
    """
    loc, cache = prepare_for_review(cache)
    database = db_connect(path=cache)
    prompt_handler = ai_client_init(database=database)
    spreadsheet = sheet_utils.read_spreadsheet(
        url=spreadsheet_url, alias="new spreadsheet", validate=False
    )
    for _, contents in spreadsheet.items():
        parse_standards_from_spreadsheeet(contents, database, prompt_handler)

    logger.info(
        "Stored temporary files and database in %s if you want to use them next time, set cache to the location of the database in that dir"
        % loc
    )
    # logger.info("A spreadsheet view is at %s" % sheet_url)


def donwload_graph_from_upstream(cache: str) -> None:
    imported_cres = {}
    collection = db_connect(path=cache).with_graph()

    def download_cre_from_upstream(creid: str):
        cre_response = requests.get(
            os.environ.get("CRE_UPSTREAM_API_URL", "https://opencre.org/rest/v1")
            + f"/id/{creid}"
        )
        if cre_response.status_code != 200:
            raise RuntimeError(
                f"cannot connect to upstream status code {cre_response.status_code}"
            )
        data = cre_response.json()
        credict = data["data"]
        cre = defs.Document.from_dict(credict)
        if cre.id in imported_cres:
            return
        register_cre(cre, collection)
        imported_cres[cre.id] = ""
        for link in cre.links:
            if link.document.doctype == defs.Credoctypes.CRE:
                download_cre_from_upstream(link.document.id)

    root_cres_response = requests.get(
        os.environ.get("CRE_UPSTREAM_API_URL", "https://opencre.org/rest/v1")
        + "/root_cres"
    )
    if root_cres_response.status_code != 200:
        raise RuntimeError(
            f"cannot connect to upstream status code {root_cres_response.status_code}"
        )
    data = root_cres_response.json()
    for root_cre in data["data"]:
        cre = defs.Document.from_dict(root_cre)
        register_cre(cre, collection)
        imported_cres[cre.id] = ""
        for link in cre.links:
            if link.document.doctype == defs.Credoctypes.CRE:
                download_cre_from_upstream(link.document.id)


# def review_from_disk(cache: str, cre_file_loc: str, share_with: str) -> None:
#     """--review --cre_loc <path>
#     copy db to new temp dir,
#     import new mappings from yaml files defined in <cre_loc>
#     export db to tmp dir
#     create new spreadsheet of the new CRE landscape for review
#     """
#     loc, cache = prepare_for_review(cache)
#     database = db_connect(path=cache)
#     for file in get_cre_files_from_disk(cre_file_loc):
#         with open(file, "rb") as standard:
#             parse_file(
#                 filename=file,
#                 yamldocs=list(yaml.safe_load_all(standard)),
#                 scollection=database,
#             )

#     sheet_url = create_spreadsheet(
#         collection=database,
#         exported_documents=docs,
#         title="cre_review",
#         share_with=[share_with],
#     )
#     logger.info(
#         "Stored temporary files and database in %s if you want to use them next time, set cache to the location of the database in that dir"
#         % loc
#     )
#     logger.info("A spreadsheet view is at %s" % sheet_url)


def run(args: argparse.Namespace) -> None:  # pragma: no cover
    script_path = os.path.dirname(os.path.realpath(__file__))
    os.path.join(script_path, "../cres")

    # if args.review and args.from_spreadsheet:
    #     review_from_spreadsheet(
    #         cache=args.cache_file,
    #         spreadsheet_url=args.from_spreadsheet,
    #         share_with=args.email,
    #     )
    # elif args.review and args.cre_loc:
    #     review_from_disk(
    #         cache=args.cache_file, cre_file_loc=args.cre_loc, share_with=args.email
    #     )
    if args.add and args.from_spreadsheet:
        add_from_spreadsheet(
            spreadsheet_url=args.from_spreadsheet,
            cache_loc=args.cache_file,
            cre_loc=args.cre_loc,
        )
    elif args.add and args.cre_loc and not args.from_spreadsheet:
        add_from_disk(cache_loc=args.cache_file, cre_loc=args.cre_loc)
    elif args.print_graph:
        print_graph()
    # elif args.review and args.osib_in:
    #     review_osib_from_file(
    #         file_loc=args.osib_in, cache=args.cache_file, cre_loc=args.cre_loc
    #     )

    # elif args.add and args.osib_in:
    #     add_osib_from_file(
    #         file_loc=args.osib_in, cache=args.cache_file, cre_loc=args.cre_loc
    #     )

    # elif args.osib_out:
    #     export_to_osib(file_loc=args.osib_out, cache=args.cache_file)

    if args.delete_map_analysis_for:
        cache = db_connect(args.cache_file)
        cache.delete_gapanalysis_results_for(args.delete_map_analysis_for)
    if args.delete_resource:
        cache = db_connect(args.cache_file)
        cache.delete_nodes(args.delete_resource)

    # individual resource importing
    if args.zap_in:
        from application.utils.external_project_parsers.parsers import zap_alerts_parser

        BaseParser().register_resource(
            zap_alerts_parser.ZAP, db_connection_str=args.cache_file
        )
    if args.cheatsheets_in:
        from application.utils.external_project_parsers.parsers import (
            cheatsheets_parser,
        )

        BaseParser().register_resource(
            cheatsheets_parser.Cheatsheets, db_connection_str=args.cache_file
        )
    if args.github_tools_in:
        from application.utils.external_project_parsers.parsers import misc_tools_parser

        BaseParser().register_resource(
            misc_tools_parser.MiscTools, db_connection_str=args.cache_file
        )
    if args.capec_in:
        from application.utils.external_project_parsers.parsers import capec_parser

        BaseParser().register_resource(
            capec_parser.Capec, db_connection_str=args.cache_file
        )
    if args.cwe_in:
        from application.utils.external_project_parsers.parsers import cwe

        BaseParser().register_resource(cwe.CWE, db_connection_str=args.cache_file)
    if args.csa_ccm_v4_in:
        from application.utils.external_project_parsers.parsers import ccmv4

        BaseParser().register_resource(
            ccmv4.CloudControlsMatrix, db_connection_str=args.cache_file
        )
    if args.iso_27001_in:
        from application.utils.external_project_parsers.parsers import iso27001

        BaseParser().register_resource(
            iso27001.ISO27001, db_connection_str=args.cache_file
        )
    if args.owasp_secure_headers_in:
        from application.utils.external_project_parsers.parsers import secure_headers

        BaseParser().register_resource(
            secure_headers.SecureHeaders, db_connection_str=args.cache_file
        )
    if args.pci_dss_4_in:
        from application.utils.external_project_parsers.parsers import pci_dss

        BaseParser().register_resource(
            pci_dss.PciDss, db_connection_str=args.cache_file
        )
    if args.juiceshop_in:
        from application.utils.external_project_parsers.parsers import juiceshop

        BaseParser().register_resource(
            juiceshop.JuiceShop, db_connection_str=args.cache_file
        )
    if args.dsomm_in:
        from application.utils.external_project_parsers.parsers import dsomm

        BaseParser().register_resource(dsomm.DSOMM, db_connection_str=args.cache_file)
    if args.cloud_native_security_controls_in:
        from application.utils.external_project_parsers.parsers import (
            cloud_native_security_controls,
        )

        BaseParser().register_resource(
            cloud_native_security_controls.CloudNativeSecurityControls,
            db_connection_str=args.cache_file,
        )
    # /end individual resource importing

    if args.import_external_projects:
        BaseParser().call_importers(db_connection_str=args.cache_file)

    if args.generate_embeddings:
        generate_embeddings(args.cache_file)
    if args.owasp_proj_meta:
        owasp_metadata_to_cre(args.owasp_proj_meta)
    if args.populate_neo4j_db:
        populate_neo4j_db(args.cache_file)
    if args.start_worker:
        from application.worker import start_worker

        start_worker(args.cache_file)

    if args.preload_map_analysis_target_url:
        gap_analysis.preload(target_url=args.preload_map_analysis_target_url)
    if args.upstream_sync:
        donwload_graph_from_upstream(args.cache_file)


def ai_client_init(database: db.Node_collection):
    return prompt_client.PromptHandler(database=database)


def db_connect(path: str):
    global app
    conf = CMDConfig(db_uri=path)
    app = create_app(conf=conf)
    collection = db.Node_collection()
    app_context = app.app_context()
    app_context.push()

    return collection


def create_spreadsheet(
    collection: db.Node_collection,
    exported_documents: List[Any],
    title: str,
    share_with: List[str],
) -> Any:
    """Reads cre docs exported from a standards_collection.export()
    dumps each doc into a workbook"""
    flat_dicts = sheet_utils.prepare_spreadsheet(docs=exported_documents)
    return sheet_utils.write_spreadsheet(
        title=title, docs=flat_dicts, emails=share_with
    )


def prepare_for_review(cache: str) -> Tuple[str, str]:
    loc = tempfile.mkdtemp()
    cache_filename = os.path.basename(cache)
    if os.path.isfile(cache):
        shutil.copy(cache, loc)
    else:
        logger.fatal("Could not copy database %s this seems like a bug" % cache)
    return loc, os.path.join(loc, cache_filename)


def generate_embeddings(db_url: str) -> None:
    database = db_connect(path=db_url)
    prompt_client.PromptHandler(database, load_all_embeddings=True)


def populate_neo4j_db(cache: str):
    logger.info(f"Populating neo4j DB: Connecting to SQL DB")
    database = db_connect(path=cache)
    logger.info(f"Populating neo4j DB: Populating")
    database.neo_db.populate_DB(database.session)
    logger.info(f"Populating neo4j DB: Complete")
