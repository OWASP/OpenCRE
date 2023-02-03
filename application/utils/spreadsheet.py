import csv
import io
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

import gspread
import yaml
from application.database import db
from application.defs import cre_defs as defs

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


def readSpreadsheet(
    url: str, cres_loc: str, alias: str, validate: bool = True
) -> Dict[str, Any]:
    """given remote google spreadsheet url,
    reads each workbook into a collection of documents"""
    try:
        gc = gspread.oauth()  # oauth config,
        # TODO (northdpole): make this configurable
        # gc = gspread.service_account()
        sh = gc.open_by_url(url)
        logger.info('accessing spreadsheet "%s" : "%s"' % (alias, url))
        result = {}
        for wsh in sh.worksheets():
            if wsh.title[0].isdigit():
                logger.info(
                    "handling worksheet %s  "
                    "(remember, only numbered worksheets"
                    " will be processed by convention)" % wsh.title
                )
                records = wsh.get_all_records()
                toyaml = yaml.safe_load(yaml.safe_dump(records))
                result[wsh.title] = toyaml
    except gspread.exceptions.APIError as ae:
        logger.error('Error opening spreadsheet "%s" : "%s"' % (alias, url))
        logger.error(ae)
    return result


def __add_cre_to_spreadsheet(
    document: defs.Document,
    header: Dict[str, Optional[str]],
    cresheet: List[Dict[str, Any]],
    maxgroups: int,
) -> List[Dict[str, Any]]:
    cresheet.append(header.copy())
    working_array = cresheet[-1]
    conflicts = []
    if document.doctype == defs.Credoctypes.CRE:
        working_array[defs.ExportFormat.cre_name_key()] = document.name
        working_array[defs.ExportFormat.cre_id_key()] = document.id
        working_array[defs.ExportFormat.cre_description_key()] = document.description
    # case where a lone standard is displayed without any CRE links
    elif document.doctype == defs.Credoctypes.Standard:
        working_array[
            defs.ExportFormat.section_key(sname=document.name, doctype=document.doctype)
        ] = document.section  # type: ignore
        working_array[
            defs.ExportFormat.subsection_key(
                sname=document.name, doctype=document.doctype
            )
        ] = document.subsection  # type: ignore
        working_array[
            defs.ExportFormat.hyperlink_key(
                sname=document.name, doctype=document.doctype
            )
        ] = document.hyperlink  # type: ignore

    for link in document.links:
        if (
            link.document.doctype == defs.Credoctypes.Standard
        ):  # linking to normal standard
            # a single CRE can link to multiple subsections of the same
            # standard hence we can have conflicts
            if working_array[
                defs.ExportFormat.section_key(
                    sname=link.document.name, doctype=link.document.doctype
                )
            ]:
                conflicts.append(link)
            else:
                working_array[
                    defs.ExportFormat.section_key(
                        sname=link.document.name, doctype=link.document.doctype
                    )
                ] = link.document.section
                working_array[
                    defs.ExportFormat.subsection_key(
                        sname=link.document.name, doctype=link.document.doctype
                    )
                ] = link.document.subsection
                working_array[
                    defs.ExportFormat.hyperlink_key(
                        sname=link.document.name, doctype=link.document.doctype
                    )
                ] = link.document.hyperlink
                working_array[
                    defs.ExportFormat.link_type_key(
                        sname=link.document.name, doctype=link.document.doctype
                    )
                ] = link.ltype.value
        elif link.document.doctype == defs.Credoctypes.CRE:
            # linking to another CRE
            grp_added = False
            for i in range(0, maxgroups):
                if not working_array[defs.ExportFormat.linked_cre_id_key(str(i))]:
                    grp_added = True
                    working_array[
                        defs.ExportFormat.linked_cre_id_key(str(i))
                    ] = link.document.id
                    working_array[
                        defs.ExportFormat.linked_cre_name_key(str(i))
                    ] = link.document.name
                    working_array[
                        defs.ExportFormat.linked_cre_link_type_key(str(i))
                    ] = link.ltype.value
                    break

            if not grp_added:
                logger.fatal(
                    "Tried to add Group %s but all of the %s group "
                    "slots are filled. This must be a bug"
                    % (link.document.name, maxgroups)
                )

    # conflicts handling
    if len(conflicts):
        new_cre = deepcopy(document)
        new_cre.links = conflicts
        cresheet = __add_cre_to_spreadsheet(
            document=new_cre, header=header, cresheet=cresheet, maxgroups=maxgroups
        )
    return cresheet


def prepare_spreadsheet(
    collection: db.Node_collection, docs: List[defs.Document]
) -> List[Dict[str, Any]]:
    """
    Given a list of cre_defs.Document will create a list
     of key,value dict representing the mappings
    """
    nodes = collection.get_node_names()  # get header from db (cheap enough)
    header: Dict[str, Optional[str]] = {
        defs.ExportFormat.cre_name_key(): None,
        defs.ExportFormat.cre_id_key(): None,
        defs.ExportFormat.cre_description_key(): None,
    }
    if nodes:
        for typ, name in nodes:
            header[
                defs.ExportFormat.section_key(name, defs.Credoctypes.from_str(typ))
            ] = None
            header[
                defs.ExportFormat.subsection_key(name, defs.Credoctypes.from_str(typ))
            ] = None
            header[
                defs.ExportFormat.hyperlink_key(name, defs.Credoctypes.from_str(typ))
            ] = None
            header[
                defs.ExportFormat.link_type_key(name, defs.Credoctypes.from_str(typ))
            ] = None
    maxgroups = collection.get_max_internal_connections()
    for i in range(0, maxgroups):
        header[defs.ExportFormat.linked_cre_id_key(str(i))] = None
        header[defs.ExportFormat.linked_cre_name_key(str(i))] = None
        header[defs.ExportFormat.linked_cre_link_type_key(str(i))] = None

    logger.debug(header)

    flatdict = {}
    result = []
    for cre in docs:
        flatdict[cre.name] = __add_cre_to_spreadsheet(
            document=cre, header=header, cresheet=[], maxgroups=maxgroups
        )
        result.extend(flatdict[cre.name])
    return result


def write_csv(docs: List[Dict[str, Any]]) -> io.StringIO:
    data = io.StringIO()
    fieldnames: List[str] = list(docs[0].keys())
    writer: csv.DictWriter = csv.DictWriter(data, fieldnames=fieldnames)  # type: ignore
    writer.writeheader()
    writer.writerows(docs)
    return data


def write_spreadsheet(title: str, docs: List[Dict[str, Any]], emails: List[str]) -> str:
    """upload local array of flat yamls to url, share with email list"""
    gc = gspread.oauth()  # oauth config,
    # TODO (northdpole): make this configurable
    sh = gc.create("0." + title)
    data = write_csv(docs=docs)
    gc.import_csv(sh.id, data.getvalue().encode("utf-8"))
    for email in emails:
        sh.share(email, perm_type="user", role="writer")
    return "https://docs.google.com/spreadsheets/d/%s" % sh.id
