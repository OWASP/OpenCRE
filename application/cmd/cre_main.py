import argparse
import json
import logging
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

import yaml
from application import create_app  # type: ignore
from application.config import CMDConfig
from application.database import db
from application.defs import cre_defs as defs
from application.defs import osib_defs as odefs
from application.utils import spreadsheet as sheet_utils
from application.utils import spreadsheet_parsers
from application.utils.external_project_parsers import (
    capec_parser,
    cwe,
    ccmv4,
    cheatsheets_parser,
    misc_tools_parser,
    zap_alerts_parser,
    iso27001,
    secure_headers,
    pci_dss,
    juiceshop,
)
from application.prompt_client import prompt_client as prompt_client
from dacite import from_dict
from dacite.config import Config

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
    linked_node = collection.add_node(node)
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
            dbcre = register_cre(link.document, collection)
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


def register_cre(cre: defs.CRE, collection: db.Node_collection) -> db.CRE:
    dbcre: db.CRE = collection.add_cre(cre)
    for link in cre.links:
        if type(link.document) == defs.CRE:
            collection.add_internal_link(
                dbcre, register_cre(link.document, collection), type=link.ltype
            )
        else:
            collection.add_link(
                cre=dbcre,
                node=register_node(node=link.document, collection=collection),
                type=link.ltype,
            )
    return dbcre


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
                else defs.Code
                if doctype == defs.Credoctypes.Code.value
                else defs.Tool
                if doctype == defs.Credoctypes.Tool.value
                else None
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


def parse_standards_from_spreadsheeet(
    cre_file: List[Dict[str, Any]], result: db.Node_collection
) -> None:
    """given a yaml with standards, build a list of standards in the db"""
    cres = {}
    if "CRE:name" in cre_file[0].keys():
        cres = spreadsheet_parsers.parse_export_format(cre_file)
    elif any(key.startswith("CRE hierarchy") for key in cre_file[0].keys()):
        cres = spreadsheet_parsers.parse_hierarchical_export_format(cre_file)
    else:
        logger.fatal(f"could not find any useful keys { cre_file[0].keys()}")
    # register groupless cres first
    for _, cre in cres.items():
        register_cre(cre, result)


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
    spreadsheet = sheet_utils.readSpreadsheet(
        url=spreadsheet_url, alias="new spreadsheet", validate=False
    )
    for worksheet, contents in spreadsheet.items():
        parse_standards_from_spreadsheeet(contents, database)

    database.export(cre_loc)

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
    docs = database.export(cre_loc)


def review_from_spreadsheet(cache: str, spreadsheet_url: str, share_with: str) -> None:
    """--review --from_spreadsheet <url>
    copy db to new temp dir,
    import new mappings from spreadsheet
    export db to tmp dir
    create new spreadsheet of the new CRE landscape for review
    """
    loc, cache = prepare_for_review(cache)
    database = db_connect(path=cache)
    spreadsheet = sheet_utils.readSpreadsheet(
        url=spreadsheet_url, alias="new spreadsheet", validate=False
    )
    for _, contents in spreadsheet.items():
        parse_standards_from_spreadsheeet(contents, database)
    docs = database.export(loc)

    # sheet_url = create_spreadsheet(
    #     collection=database,
    #     exported_documents=docs,
    #     title="cre_review",
    #     share_with=[share_with],
    # )
    logger.info(
        "Stored temporary files and database in %s if you want to use them next time, set cache to the location of the database in that dir"
        % loc
    )
    # logger.info("A spreadsheet view is at %s" % sheet_url)


def review_from_disk(cache: str, cre_file_loc: str, share_with: str) -> None:
    """--review --cre_loc <path>
    copy db to new temp dir,
    import new mappings from yaml files defined in <cre_loc>
    export db to tmp dir
    create new spreadsheet of the new CRE landscape for review
    """
    loc, cache = prepare_for_review(cache)
    database = db_connect(path=cache)
    for file in get_cre_files_from_disk(cre_file_loc):
        with open(file, "rb") as standard:
            parse_file(
                filename=file,
                yamldocs=list(yaml.safe_load_all(standard)),
                scollection=database,
            )

    docs = database.export(loc)
    sheet_url = create_spreadsheet(
        collection=database,
        exported_documents=docs,
        title="cre_review",
        share_with=[share_with],
    )
    logger.info(
        "Stored temporary files and database in %s if you want to use them next time, set cache to the location of the database in that dir"
        % loc
    )
    logger.info("A spreadsheet view is at %s" % sheet_url)


def print_graph() -> None:
    """export db to single json object, pass to visualise.html so it can be shown in browser"""
    raise NotImplementedError


def run(args: argparse.Namespace) -> None:  # pragma: no cover
    script_path = os.path.dirname(os.path.realpath(__file__))
    os.path.join(script_path, "../cres")

    if args.review and args.from_spreadsheet:
        review_from_spreadsheet(
            cache=args.cache_file,
            spreadsheet_url=args.from_spreadsheet,
            share_with=args.email,
        )
    elif args.review and args.cre_loc:
        review_from_disk(
            cache=args.cache_file, cre_file_loc=args.cre_loc, share_with=args.email
        )
    elif args.add and args.from_spreadsheet:
        add_from_spreadsheet(
            spreadsheet_url=args.from_spreadsheet,
            cache_loc=args.cache_file,
            cre_loc=args.cre_loc,
        )
    elif args.add and args.cre_loc and not args.from_spreadsheet:
        add_from_disk(cache_loc=args.cache_file, cre_loc=args.cre_loc)
    elif args.print_graph:
        print_graph()
    elif args.review and args.osib_in:
        review_osib_from_file(
            file_loc=args.osib_in, cache=args.cache_file, cre_loc=args.cre_loc
        )

    elif args.add and args.osib_in:
        add_osib_from_file(
            file_loc=args.osib_in, cache=args.cache_file, cre_loc=args.cre_loc
        )

    elif args.osib_out:
        export_to_osib(file_loc=args.osib_out, cache=args.cache_file)
    if args.zap_in:
        zap_alerts_parser.parse_zap_alerts(db_connect(args.cache_file))
    if args.cheatsheets_in:
        cheatsheets_parser.parse_cheatsheets(db_connect(args.cache_file))
    if args.github_tools_in:
        for url in misc_tools_parser.tool_urls:
            misc_tools_parser.parse_tool(
                cache=db_connect(args.cache_file), tool_repo=url
            )
    if args.capec_in:
        capec_parser.parse_capec(cache=db_connect(args.cache_file))
    if args.cwe_in:
        cwe.parse_cwe(cache=db_connect(args.cache_file))

    if args.export:
        cache = db_connect(args.cache_file)
        cache.export(args.export)
    if args.csa_ccm_v4_in:
        ccmv4.parse_ccm(
            ccmFile=sheet_utils.readSpreadsheet(
                alias="",
                url="https://docs.google.com/spreadsheets/d/1QDzQy0wt1blGjehyXS3uaHh7k5OOR12AWgAA1DeACyc",
            ),
            cache=db_connect(args.cache_file),
        )
    if args.iso_27001_in:
        iso27001.parse_iso(
            url="https://csrc.nist.gov/CSRC/media/Publications/sp/800-53/rev-5/final/documents/sp800-53r5-to-iso-27001-mapping.docx",
            cache=db_connect(args.cache_file),
        )
    if args.owasp_secure_headers_in:
        secure_headers.parse(
            cache=db_connect(args.cache_file),
        )
    if args.pci_dss_3_2_in:
        pci_dss.parse_3_2(
            pci_file=sheet_utils.readSpreadsheet(
                alias="",
                url="https://docs.google.com/spreadsheets/d/1p-s65MaVrKOnWPEQ_tt7e0fmutCeiJx8EORPNF5TyME",
                parse_numbered_only=False,
            ),
            cache=db_connect(args.cache_file),
        )
    if args.pci_dss_4_in:
        pci_dss.parse_4(
            pci_file=sheet_utils.readSpreadsheet(
                alias="",
                url="https://docs.google.com/spreadsheets/d/18weo-qbik_C7SdYq7FSP2OMgUmsWdWWI1eaXcAfMz8I",
                parse_numbered_only=False,
            ),
            cache=db_connect(args.cache_file),
        )
    if args.juiceshop_in:
        juiceshop.parse(
            cache=db_connect(args.cache_file),
        )
    if args.generate_embeddings:
        generate_embeddings(args.cache_file)
    if args.owasp_proj_meta:
        owasp_metadata_to_cre(args.owasp_proj_meta)
    if args.populate_neo4j_db:
        populate_neo4j_db(args.cache_file)
    if args.start_worker:
        from application.worker import start_worker

        start_worker(args.cache_file)


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
    flat_dicts = sheet_utils.prepare_spreadsheet(
        collection=collection, docs=exported_documents
    )
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


def review_osib_from_file(file_loc: str, cache: str, cre_loc: str) -> None:
    """Given the location of an osib.yaml, parse osib, convert to cres and add to db
    export db to yamls and spreadsheet for review"""
    loc, cache = prepare_for_review(cache)
    database = db_connect(path=cache)
    ymls = odefs.read_osib_yaml(file_loc)
    osibs = odefs.try_from_file(ymls)
    for osib in osibs:
        cres, standards = odefs.osib2cre(osib)
        [register_cre(c, database) for c in cres]
        [register_node(s, database) for s in standards]

    sheet_url = create_spreadsheet(
        collection=database,
        exported_documents=database.export(loc),
        title="osib_review",
        share_with=[],
    )
    logger.info(
        f"Stored temporary files and database in {loc} if you want to use them next time, set cache to the location of the database in that dir"
    )
    logger.info(f"A spreadsheet view is at {sheet_url}")


def add_osib_from_file(file_loc: str, cache: str, cre_loc: str) -> None:
    database = db_connect(path=cache)
    ymls = odefs.read_osib_yaml(file_loc)
    osibs = odefs.try_from_file(ymls)
    for osib in osibs:
        cre, standard = odefs.osib2cre(osib)
        [register_cre(c, database) for c in cre]
        [register_node(s, database) for s in standard]
    database.export(cre_loc)


def export_to_osib(file_loc: str, cache: str) -> None:
    docs = db_connect(path=cache).export(file_loc, dry_run=True)
    tree = odefs.cre2osib(docs)
    with open(file_loc, "x"):
        with open(file_loc, "w") as f:
            f.write(json.dumps(tree.todict()))


def generate_embeddings(db_url: str) -> None:
    database = db_connect(path=db_url)
    prompt = prompt_client.PromptHandler(database)


def owasp_metadata_to_cre(meta_file: str):
    """given a file with entries like below
    parse projects of type "tool" in file into "tool" data.
    {
        "name": "Security Qualitative Metrics",
        "url": "https://owasp.org/www-project-security-qualitative-metrics/",
        "created": "2020-07-20",
        "updated": "2021-04-20",
        "build": "built",
        "title": "OWASP Security Qualitative Metrics",
        "level": "2",
        "type": "documentation",
        "region": "Unknown",
        "pitch": "The OWASP Security Qualitative Metrics is the most detailed list of metrics which evaluate security level of web projects. It shows the level of coverage of OWASP ASVS."
    },
    """
    raise NotImplementedError("someone needs to work on this")


def populate_neo4j_db(cache: str):
    logger.info(f"Populating neo4j DB: Connecting to SQL DB")
    database = db_connect(path=cache)
    logger.info(f"Populating neo4j DB: Populating")
    database.neo_db.populate_DB(database.session)
    logger.info(f"Populating neo4j DB: Complete")
