
import os
import yaml
import logging
import gspread
import cre_defs as defs
from pprint import pprint
import db
from copy import deepcopy
import io
import csv

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


def readSpreadsheet(url: str, cres_loc: str, alias: str, validate=True):
    """given remote google spreadsheet url,
     reads each workbook into a collection of documents"""
    changes_present = False
    try:
        gc = gspread.oauth()  # oauth config, TODO (northdpole): make this configurable
        # gc = gspread.service_account()
        sh = gc.open_by_url(url)
        logger.info("accessing spreadsheet \"%s\" : \"%s\"" % (alias, url))
        result = {}
        for wsh in sh.worksheets():
            if wsh.title[0].isdigit():
                logger.info(
                    "handling worksheet %s  (remember, only numbered worksheets will be processed by convention)" % wsh.title)
                records = wsh.get_all_records()
                toyaml = yaml.safe_load(yaml.safe_dump(records))
                result[wsh.title] = toyaml
    except gspread.exceptions.APIError as ae:
        logger.error("Error opening spreadsheet \"%s\" : \"%s\"" %
                     (alias, url))
        logger.error(ae)
    return result


def __add_cre_to_spreadsheet(document: defs.Document, header: dict, cresheet: list, maxgroups: int):
    cresheet.append(header.copy())
    working_array = cresheet[-1]
    conflicts = []
    if document.doctype == defs.Credoctypes.CRE:
        working_array[defs.ExportFormat.cre_name_key()] = document.name
        working_array[defs.ExportFormat.cre_id_key()] = document.id
        working_array[defs.ExportFormat.cre_description_key()] = document.description
    # case where a lone standard is displayed without any CRE links
    elif document.doctype == defs.Credoctypes.Standard:
        working_array[defs.ExportFormat.section_key(document.name)] = document.section
        working_array[defs.ExportFormat.subsection_key(document.name)] = document.subsection
        working_array[defs.ExportFormat.hyperlink_key(document.name)] = document.hyperlink

    for link in document.links:
        if link.document.doctype == defs.Credoctypes.Standard:  # linking to normal standard
            # a single CRE can link to multiple standards hence we can have conflicts
            if working_array[defs.ExportFormat.section_key(link.document.name)]:
                conflicts.append(link)
            else:
                working_array[defs.ExportFormat.section_key(link.document.name)] = link.document.section
                working_array[defs.ExportFormat.subsection_key(link.document.name)] = link.document.subsection
                working_array[defs.ExportFormat.hyperlink_key(link.document.name)] = link.document.hyperlink
                working_array[defs.ExportFormat.link_type_key(link.document.name)] = link.ltype.value
        elif link.document.doctype == defs.Credoctypes.CRE:  # linking to another CRE
            grp_added = False
            for i in range(0, maxgroups):
                if not working_array[defs.ExportFormat.linked_cre_id_key(i)]:
                    grp_added = True
                    working_array[defs.ExportFormat.linked_cre_id_key(i)] = link.document.id
                    working_array[defs.ExportFormat.linked_cre_name_key(i)] = link.document.name
                    working_array[defs.ExportFormat.linked_cre_link_type_key(i)] = link.ltype.value
                    break
            if not grp_added:
                logger.fatal("Tried to add Group %s but all of the %s group slots are filled. This must be a bug" % (
                    link.document.name, maxgroups))

    # conflicts handling
    if len(conflicts):
        new_cre = deepcopy(document)
        new_cre.links = conflicts
        cresheet = __add_cre_to_spreadsheet(
            new_cre, header, cresheet, maxgroups)
    return cresheet


def prepare_spreadsheet(collection: db.Standard_collection, docs: list) -> str:
    """ 
        Given a list of cre_defs.Document will create a list of key,value dict representing the mappings
    """
    standard_names = collection.get_standards_names()  # get header from db (cheap enough)
    header = {defs.ExportFormat.cre_name_key(): None, defs.ExportFormat.cre_id_key(): None, defs.ExportFormat.cre_description_key(): None}
    groups = {}
    for name in standard_names:
        header[defs.ExportFormat.section_key(name)] = None
        header[defs.ExportFormat.subsection_key(name)] = None
        header[defs.ExportFormat.hyperlink_key(name)] = None
        header[defs.ExportFormat.link_type_key(name)] = None
    maxgroups = collection.get_max_internal_connections()
    for i in range(0, maxgroups):
        header[defs.ExportFormat.linked_cre_id_key(i)] = None
        header[defs.ExportFormat.linked_cre_name_key(i)] = None
        header[defs.ExportFormat.linked_cre_link_type_key(i)] = None

    logger.debug(header)

    flatdict = {}
    result = []
    for cre in docs:
        flatdict[cre.name] = __add_cre_to_spreadsheet(
            document=cre, header=header, cresheet=[], maxgroups=maxgroups)
        result.extend(flatdict[cre.name])
    return result


def write_spreadsheet(title: str, docs: list, emails: list):
    """ upload local array of flat yamls to url, share with email list"""
    gc = gspread.oauth()  # oauth config, TODO (northdpole): make this configurable
    sh = gc.create("0."+title)
    data = io.StringIO()
    fieldnames = docs[0].keys()
    writer = csv.DictWriter(data, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(docs)
    gc.import_csv(sh.id, data.getvalue().encode('utf-8'))
    for email in emails:
        sh.share(email, perm_type='user', role='writer')
    return "https://docs.google.com/spreadsheets/d/%s" % sh.id
