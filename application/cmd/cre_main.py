import argparse
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
from application.utils import parsers  # type: ignore
from application.utils import spreadsheet as sheet_utils

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = None


def register_standard(
    standard: defs.Standard, collection: db.Standard_collection
) -> db.Standard:
    """for each link find if either the root standard or the link have a CRE, then map the one who doesn't to the CRE
    if both don't map to anything, just add them in the db as unlinked standards
    """
    linked_standard = collection.add_standard(standard)

    cre_less_standards: List[defs.Standard] = []

    cres_added = []
    # we need to know the cres added in case we encounter a higher level CRE, then we get the higher level CRE to link to these cres
    for link in standard.links:
        if type(link.document).__name__ == defs.Standard.__name__:
            # if a standard links another standard it is likely that a standards writer wants to reference something
            # in that case, find which of the two standards has at least one CRE attached to it and link both to the parent CRE
            cres = collection.find_cres_of_standard(link.document)
            db_link = collection.add_standard(link.document)
            if cres:
                for cre in cres:
                    collection.add_link(
                        cre=cre, standard=linked_standard, type=link.ltype
                    )
                    for unlinked_standard in cre_less_standards:  # if anything in this
                        collection.add_link(
                            cre=cre,
                            standard=db.dbStandardFromStandard(unlinked_standard),
                            type=link.ltype,
                        )
            else:
                cres = collection.find_cres_of_standard(linked_standard)
                if cres:
                    for cre in cres:
                        collection.add_link(cre=cre, standard=db_link, type=link.ltype)
                        for unlinked_standard in cre_less_standards:
                            collection.add_link(
                                cre=cre,
                                standard=db.dbStandardFromStandard(unlinked_standard),
                                type=link.ltype,
                            )
                else:  # if neither the root nor a linked standard has a CRE, add both as unlinked standards
                    cre_less_standards.append(link.document)

            if link.document.links and len(link.document.links) > 0:
                register_standard(standard=link.document, collection=collection)

        elif type(link.document).__name__ == defs.CRE.__name__:
            dbcre = register_cre(link.document, collection)
            collection.add_link(dbcre, linked_standard, type=link.ltype)
            cres_added.append(dbcre)
    return linked_standard


def register_cre(cre: defs.CRE, collection: db.Standard_collection) -> db.CRE:

    dbcre: db.CRE = collection.add_cre(cre)

    for link in cre.links:
        if type(link.document).__name__ == defs.CRE.__name__:
            collection.add_internal_link(
                dbcre, register_cre(link.document, collection), type=link.ltype
            )
        elif type(link.document).__name__ == defs.Standard.__name__:
            collection.add_link(
                cre=dbcre,
                standard=register_standard(
                    standard=link.document, collection=collection
                ),
                type=link.ltype,
            )
    return dbcre


def parse_file(
    filename: str, yamldocs: List[Dict[str, Any]], scollection: db.Standard_collection
) -> Optional[List[defs.Document]]:

    """given yaml from export format deserialise to internal standards format and add standards to db"""

    resulting_objects = []
    for contents in yamldocs:
        links = []

        document: defs.Document
        register_callback: Callable[[Any, Any], Any]

        if not isinstance(
            contents, dict
        ):  # basic object matching, make sure we at least have an object, go has this build in :(
            logger.fatal("Malformed file %s, skipping" % filename)

            return None

        if contents.get("links"):
            links = contents.pop("links")

        if contents.get("doctype") == defs.Credoctypes.CRE.value:
            document = defs.CRE(**contents)
            register_callback = register_cre
        elif contents.get("doctype") == defs.Credoctypes.Standard.value:
            document = defs.Standard(**contents)
            register_callback = register_standard

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
    cre_file: List[Dict[str, Any]], result: db.Standard_collection
) -> None:

    """given a yaml with standards, build a list of standards in the db"""
    hi_lvl_CREs = {}
    cres = {}
    if "CRE Group 1" in cre_file[0].keys():
        hi_lvl_CREs, cres = parsers.parse_v1_standards(cre_file)
    elif "CRE:name" in cre_file[0].keys():
        cres = parsers.parse_export_format(cre_file)
    elif any(key.startswith("CRE hierarchy") for key in cre_file[0].keys()):
        cres = parsers.parse_hierarchical_export_format(cre_file)
    else:
        cres = parsers.parse_v0_standards(cre_file)

    # register groupless cres first
    for _, cre in cres.items():
        register_cre(cre, result)

    # groups
    # TODO :(spyros) merge with register_cre above
    for name, doc in hi_lvl_CREs.items():
        dbgroup = result.add_cre(doc)

        for link in doc.links:
            if type(link.document).__name__ == defs.CRE.__name__:
                dbcre = register_cre(link.document, result)
                result.add_internal_link(group=dbgroup, cre=dbcre, type=link.ltype)

            elif type(link.document).__name__ == defs.Standard.__name__:
                dbstandard = register_standard(link.document, result)
                result.add_link(cre=dbgroup, standard=dbstandard, type=link.ltype)


def get_standards_files_from_disk(cre_loc: str) -> Generator[str, None, None]:

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
        url=spreadsheet_url, cres_loc=cre_loc, alias="new spreadsheet", validate=False
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
    for file in get_standards_files_from_disk(cre_loc):
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
        url=spreadsheet_url, cres_loc=loc, alias="new spreadsheet", validate=False
    )
    for _, contents in spreadsheet.items():
        parse_standards_from_spreadsheeet(contents, database)
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


def review_from_disk(cache: str, cre_file_loc: str, share_with: str) -> None:

    """--review --cre_loc <path>
    copy db to new temp dir,
    import new mappings from yaml files defined in <cre_loc>
    export db to tmp dir
    create new spreadsheet of the new CRE landscape for review
    """
    loc, cache = prepare_for_review(cache)
    database = db_connect(path=cache)
    for file in get_standards_files_from_disk(cre_file_loc):
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


def run(args: argparse.Namespace) -> None:
    script_path = os.path.dirname(os.path.realpath(__file__))
    os.path.join(script_path, "../../../cres")

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


def db_connect(path: str) -> db.Standard_collection:

    global app
    conf = CMDConfig(db_uri=path)
    app = create_app(conf=conf)
    collection = db.Standard_collection()
    app_context = app.app_context()
    app_context.push()

    return collection


def create_spreadsheet(
    collection: db.Standard_collection,
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
