from pprint import pprint
import csv
import io
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set
import os
import gspread
import yaml
from application.database import db
from application.defs import cre_defs as defs
from enum import Enum

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


class GspreadAuth(Enum):
    OAuth = "oauth"
    ServiceAccount = "service_account"


def findDups(x):
    seen = set()
    return {val for val in x if (val in seen or seen.add(val))}


def load_csv():
    pass


def read_spreadsheet(
    url: str, alias: str, validate: bool = True, parse_numbered_only=True
) -> Dict[str, Any]:
    """given remote google spreadsheet url,
    reads each workbook into a collection of documents"""
    result = {}
    try:
        if (
            os.environ.get("OpenCRE_gspread_Auth")
            and os.environ.get("OpenCRE_gspread_Auth")
            == GspreadAuth.ServiceAccount.value
        ):
            logger.info("Gspread configured to use a Service Account")
            gc = gspread.service_account()
        else:
            logger.info("Gspread configured to use OAuth")
            gc = gspread.oauth()  # oauth config,
        sh = gc.open_by_url(url)
        logger.info('accessing spreadsheet "%s" : "%s"' % (alias, url))
        result = {}

        for wsh in sh.worksheets():
            if parse_numbered_only and wsh.title[0].isdigit():
                logger.info(
                    "handling worksheet %s  "
                    "(remember, only numbered worksheets"
                    " will be processed by convention)" % wsh.title
                )
                records = wsh.get_all_records(
                    wsh.row_values(1)
                )  # workaround because of https://github.com/burnash/gspread/issues/1007 # this will break if the column names are in any other line
                toyaml = yaml.safe_load(yaml.safe_dump(records))
                result[wsh.title] = toyaml
            elif not parse_numbered_only:
                records = wsh.get_all_records(
                    wsh.row_values(1)
                )  # workaround because of https://github.com/burnash/gspread/issues/1007 # this will break if the column names are in any other line
                toyaml = yaml.safe_load(yaml.safe_dump(records))
                result[wsh.title] = toyaml
    except gspread.exceptions.APIError as ae:
        logger.error('Error opening spreadsheet "%s" : "%s"' % (alias, url))
        logger.error(ae)
        exit(1)
    except gspread.exceptions.GSpreadException as gse:
        logger.error(
            "If this exception says you have a duplicate cell name, the duplicate is",
            findDups(wsh.row_values(1)),
        )

    return result


class ExportSheet:
    processed_ids = []
    body = []
    input_cres = {}

    def __init__(self):
        self.processed_ids = []
        self.body = []
        self.input_cres = {}

    def write_cre_entry(self, cre: defs.CRE, depth: int) -> Dict[str, str]:
        self.processed_ids.append(cre.id)
        return {f"CRE {depth}": f"{cre.id}{defs.ExportFormat.separator}{cre.name}"}

    def write_standard_entry(self, node: defs.Document) -> Dict[str, str]:
        standardEntry = {}
        if node.section:
            standardEntry[f"{defs.ExportFormat.section_key(node.name)}"] = node.section

        if node.sectionID:
            standardEntry[f"{defs.ExportFormat.sectionID_key(node.name)}"] = (
                node.sectionID
            )

        if node.hyperlink:
            standardEntry[f"{defs.ExportFormat.hyperlink_key(node.name)}"] = (
                node.hyperlink
            )

        if node.description:
            standardEntry[f"{defs.ExportFormat.description_key(node.name)}"] = (
                node.description
            )
        return standardEntry

    def process_cre(self, cre: defs.CRE, depth: int):
        if not self.input_cres.get(cre.id):
            return None

        cre_entry = self.write_cre_entry(cre=self.input_cres.pop(cre.id), depth=depth)
        if not cre.links:
            self.body.append(cre_entry)
            return None
        hasStandard = False
        for link in cre.links:
            entry = deepcopy(cre_entry)  # start from the base for every link
            if link.document.doctype != defs.Credoctypes.CRE:
                hasStandard = True
                entry_standard = self.write_standard_entry(link.document)
                entry.update(entry_standard)
                self.body.append(entry)
            elif (
                self.input_cres.get(link.document.id)
                and link.ltype == defs.LinkTypes.Contains
            ):
                if (
                    not hasStandard
                ):  # if we have not written the entry yet (because there have been no standards to write), we write it now as a cre without standards

                    self.body.append(entry)
                self.process_cre(
                    cre=self.input_cres.get(link.document.id), depth=depth + 1
                )

    def inject_cre_in_processed_body(self, cre: defs.CRE, higher_cres: List[defs.CRE]):
        """
        Given a cre to inject and a list of higher_cres to look for in order to inject afterwards, will inject the cre in the body
        """
        lineIndex = 0
        for line in self.body:
            for key in line.keys():
                ancestor_id = line[key].split(defs.ExportFormat.separator)[0]
                if key.startswith("CRE") and ancestor_id in [
                    h.id for h in higher_cres
                ]:  # we found the parent
                    new_depth = len(higher_cres)
                    entry = self.write_cre_entry(cre=cre, depth=new_depth)
                    for link in cre.links:
                        if link.document.doctype != defs.Credoctypes.CRE:
                            new_entry = self.write_standard_entry(link.document)
                            if set(new_entry.keys()).intersection(entry.keys()):
                                # this cre links to the same standard twice so we need to add two lines
                                self.body.insert(
                                    lineIndex + 1, entry
                                )  # write buffer first
                                lineIndex += 1
                                entry = (
                                    entry.copy()
                                )  # we need to copy the entry as we are going to update it and we want to update the values not the reference
                            # update buffer with new standard so we can write in the next line
                            entry.update(new_entry)
                    self.body.insert(lineIndex + 1, entry)
                    return None
        lineIndex += 1

    def prepare_spreadsheet(
        self, docs: List[defs.Document], storage: db.Node_collection
    ) -> List[Dict[str, Any]]:
        """
        Given a list of cre_defs.Document will create a list
        of key,value dict representing the mappings
        """

        # TODO (northdpole): traverses the same docs list multiple times
        # should be optimized

        if not docs:
            return self.body

        non_cre_docs = []

        for doc in docs:
            if doc.doctype == defs.Credoctypes.CRE:
                self.input_cres[doc.id] = doc
                for link in doc.links:
                    if link.document.doctype == defs.Credoctypes.CRE:
                        if not self.input_cres.get(link.document.id):
                            self.input_cres[link.document.id] = link.document
            else:  # flip the link to be CRE -> Node
                newCRE = None
                for link in doc.links:
                    if link.document.doctype == defs.Credoctypes.CRE:
                        newCRE = self.input_cres.get(link.document.id)
                        if not newCRE:
                            newCRE = link.document
                        if not newCRE.link_exists(doc):
                            newCRE.add_link(
                                defs.Link(document=doc.shallow_copy(), ltype=link.ltype)
                            )
                        self.input_cres[newCRE.id] = newCRE
                if not newCRE:
                    non_cre_docs.append(doc)
        cre_id_to_depth = {}
        for cre in self.input_cres.values():
            cre_id_to_depth[cre.id] = storage.get_cre_hierarchy(cre=cre)

        sorted_cres = sorted(
            self.input_cres.values(), key=lambda x: cre_id_to_depth[x.id]
        )

        for cre in sorted_cres:
            processed = False
            depth = cre_id_to_depth[cre.id]
            if depth == 0:
                self.process_cre(cre=cre, depth=depth)
                continue

            # if we have a depth > 0, we need to find the parent
            if not self.input_cres.get(cre.id):
                # happy path first, we already processed this cre
                continue

            # not so happy path second, find if there is a processed cre that has a path to this cre
            for id in self.processed_ids:
                path = storage.get_cre_path(fromID=cre.id, toID=id)
                if path:
                    # we skip the last element as it is the cre we are looking for
                    self.inject_cre_in_processed_body(cre=cre, higher_cres=path[:-1])
                    processed = True
                    break
            if processed:
                continue
            # if we still have the cre, it means it needs a path to a root cre and we need to append it to the body
            # find the root this cre is linked to
            root = storage.get_root_cres()

            for r in root:
                path = storage.get_cre_path(fromID=r.id, toID=cre.id)
                if path:
                    pathIndex = 0
                    for element in path:
                        self.body.append(
                            self.write_cre_entry(cre=element, depth=pathIndex)
                        )
                        pathIndex += 1
                    entry = self.write_cre_entry(cre=cre, depth=pathIndex)
                    for link in cre.links:
                        if link.document.doctype != defs.Credoctypes.CRE:
                            entry.update(self.write_standard_entry(link.document))
                    self.body.append(entry)
                    break

        for doc in non_cre_docs:
            entry = self.write_standard_entry(doc)
            self.body.append(entry)
        return self.body


def write_csv(docs: List[Dict[str, Any]]) -> io.StringIO:
    data = io.StringIO()
    fieldnames = {}
    [fieldnames.update(d) for d in docs]
    writer: csv.DictWriter = csv.DictWriter(data, fieldnames=fieldnames.keys())  # type: ignore
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


def generate_mapping_template_file(
    database: db.Node_collection, docs: List[defs.CRE]
) -> str:
    maxOffset = 0
    related = set()

    def add_offset_cre(
        cre: defs.CRE, database: db.Node_collection, offset: int, visited_cres: Set
    ) -> List[Dict[str, str]]:
        nonlocal maxOffset, related
        maxOffset = max(maxOffset, offset)
        rows = []

        rows.append(
            {f"CRE {offset}": f"{cre.id}{defs.ExportFormat.separator}{cre.name}"}
        )
        visited_cres.add(cre.id)
        dbcre = database.get_CREs(external_id=cre.id)
        if not dbcre:
            raise ValueError(f"CRE with id {cre.id} not found in the database")
        cre = dbcre[0]
        for link in cre.links:
            if (
                link.document.doctype == defs.Credoctypes.CRE
                and link.document.id not in visited_cres
            ):
                if link.ltype == defs.LinkTypes.Contains:
                    rows.extend(
                        add_offset_cre(
                            cre=link.document,
                            database=database,
                            offset=offset + 1,
                            visited_cres=visited_cres,
                        )
                    )
                elif link.ltype == defs.LinkTypes.Related:
                    related.add(link.document.id)
        return rows

    visited_cres = set()
    csv: List[Dict[str, str]] = []

    for cre in docs:
        csv.extend(
            add_offset_cre(
                cre=cre, database=database, offset=0, visited_cres=visited_cres
            )
        )
    result = [{f"CRE {offset}": "" for offset in range(0, maxOffset + 1)}]
    result.extend(csv)

    orphaned_documents = [doc for doc in related if doc not in visited_cres]
    if len(orphaned_documents):
        raise ValueError(
            "found CREs with only related links not provided in the root_cre list, unless you are really sure for this use case, this is a bug"
        )

    return result
