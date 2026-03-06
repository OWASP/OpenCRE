from pprint import pprint
import csv
import io
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set
import os
import gspread
from gspread.exceptions import GSpreadException
import yaml
from yaml import YAMLError
from google.auth.exceptions import DefaultCredentialsError
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
            gc = gspread.oauth()

        sh = gc.open_by_url(url)

        logger.info('accessing spreadsheet "%s" : "%s"' % (alias, url))

        for wsh in sh.worksheets():
            if parse_numbered_only and wsh.title[0].isdigit():
                logger.info(
                    "handling worksheet %s  "
                    "(remember, only numbered worksheets"
                    " will be processed by convention)" % wsh.title
                )

                records = wsh.get_all_records(
                    head=1,
                    numericise_ignore=list(range(1, wsh.col_count)),
                )

                toyaml = yaml.safe_load(yaml.safe_dump(records))

                result[wsh.title] = toyaml

            elif not parse_numbered_only:
                records = wsh.get_all_records(
                    head=1,
                    numericise_ignore=list(range(1, wsh.col_count)),
                )

                toyaml = yaml.safe_load(yaml.safe_dump(records))

                result[wsh.title] = toyaml

    except (GSpreadException, DefaultCredentialsError, OSError, YAMLError) as e:
        logger.warning(
            'Spreadsheet read skipped "%s" : "%s"',
            alias,
            str(e),
        )

        return {}

    return result


class ExportSheet:
    processed_ids: List[Optional[str]] = []
    body: List[Dict[str, str]] = []
    input_cres: Dict[str, defs.CRE] = {}

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
            standardEntry[
                f"{defs.ExportFormat.sectionID_key(node.name)}"
            ] = node.sectionID

        if node.hyperlink:
            standardEntry[
                f"{defs.ExportFormat.hyperlink_key(node.name)}"
            ] = node.hyperlink

        if node.description:
            standardEntry[
                f"{defs.ExportFormat.description_key(node.name)}"
            ] = node.description

        return standardEntry

    @staticmethod
    def _row_key(row: Dict[str, str]) -> tuple:
        return tuple(sorted(row.items()))

    def process_cre(
        self,
        cre: defs.CRE,
        depth: int,
        rows: List[Dict[str, str]],
        seen_rows: Set[tuple],
        processed_standards: Set[int],
    ) -> None:
        """Emit CSV rows for one CRE.

        Behavior matches previous export semantics:
        - emit one row per linked non-CRE document
        - emit CRE-only row when no linked standards/tools/codes exist
        """
        std_links = [
            l
            for l in getattr(cre, "links", [])
            if getattr(l.document, "doctype", None) != defs.Credoctypes.CRE
        ]
        if std_links:
            for l in std_links:
                row = self.write_cre_entry(cre, depth)
                row.update(self.write_standard_entry(l.document))
                key = self._row_key(row)
                if key not in seen_rows:
                    rows.append(row)
                    seen_rows.add(key)
                processed_standards.add(id(l.document))
            return

        row = self.write_cre_entry(cre, depth)
        key = self._row_key(row)
        if key not in seen_rows:
            rows.append(row)
            seen_rows.add(key)

    def process_standard(
        self,
        doc: defs.Document,
        cre_depth: Any,
        rows: List[Dict[str, str]],
        seen_rows: Set[tuple],
        processed_standards: Set[int],
    ) -> None:
        """Emit CSV rows for one non-CRE document."""
        cre_links = [
            l
            for l in getattr(doc, "links", [])
            if getattr(l.document, "doctype", None) == defs.Credoctypes.CRE
        ]
        if cre_links:
            if id(doc) in processed_standards:
                return
            for l in cre_links:
                cre = l.document
                depth = cre_depth(cre)
                row = self.write_cre_entry(cre, depth)
                row.update(self.write_standard_entry(doc))
                key = self._row_key(row)
                if key not in seen_rows:
                    rows.append(row)
                    seen_rows.add(key)
            return

        row = self.write_standard_entry(doc)
        key = self._row_key(row)
        if key not in seen_rows:
            rows.append(row)
            seen_rows.add(key)

    def prepare_spreadsheet(self, docs=None, storage=None):
        """
        Compatibility wrapper expected by tests.

        Produces a list of dict rows suitable for CSV writing. When a
        `storage` (Node_collection) is provided we use it to calculate
        CRE hierarchy depth. The function is intentionally tolerant to
        receiving both CRE and Standard documents in `docs` and will
        produce one row per CRE/standard relationship.  Standards that
        are not linked to any CRE are emitted as standalone rows.
        """

        if docs is None:
            docs = []

        # Empty case expected by tests
        if not docs:
            return []

        rows: List[Dict[str, str]] = []
        # keep track of row content we've already added so we can avoid
        # duplicates (order of dict entries does not matter)
        seen_rows: Set[tuple] = set()
        # track which standard objects we've already attached (best effort,
        # mostly for object identity but not relied on for duplicating)
        processed_standards: Set[int] = set()
        cre_docs: Dict[str, defs.CRE] = {
            d.id: d
            for d in docs
            if getattr(d, "doctype", None) == defs.Credoctypes.CRE
            and isinstance(d, defs.CRE)
            and d.id
        }
        parent_by_child: Dict[str, str] = {}
        for cre_obj in cre_docs.values():
            for link in getattr(cre_obj, "links", []):
                if (
                    getattr(link.document, "doctype", None) == defs.Credoctypes.CRE
                    and link.ltype == defs.LinkTypes.Contains
                    and isinstance(link.document, defs.CRE)
                    and link.document.id
                    and cre_obj.id
                ):
                    parent_by_child[link.document.id] = cre_obj.id

        def cre_depth(cre_obj):
            if getattr(cre_obj, "id", None) in cre_docs:
                depth = 0
                current = cre_obj.id
                seen: Set[str] = set()
                while current in parent_by_child and current not in seen:
                    seen.add(current)
                    depth += 1
                    current = parent_by_child[current]
                return depth

            if storage:
                return storage.get_cre_hierarchy(cre_obj)
            return 0

        # first pass: iterate through the original docs order
        for doc in docs:
            if getattr(doc, "doctype", None) == defs.Credoctypes.CRE:
                depth = cre_depth(doc)
                self.process_cre(doc, depth, rows, seen_rows, processed_standards)
            else:
                self.process_standard(
                    doc, cre_depth, rows, seen_rows, processed_standards
                )

        return rows


def write_csv(docs: List[Dict[str, Any]]) -> io.StringIO:
    data = io.StringIO()

    fieldnames = {}

    [fieldnames.update(d) for d in docs]

    writer: csv.DictWriter = csv.DictWriter(data, fieldnames=fieldnames.keys())

    writer.writeheader()

    writer.writerows(docs)

    return data


def write_spreadsheet(title: str, docs: List[Dict[str, Any]], emails: List[str]) -> str:
    gc = gspread.oauth()

    sh = gc.create("0." + title)

    data = write_csv(docs=docs)

    gc.import_csv(sh.id, data.getvalue().encode("utf-8"))

    for email in emails:
        sh.share(email, perm_type="user", role="writer")

    return "https://docs.google.com/spreadsheets/d/%s" % sh.id


def generate_mapping_template_file(
    database: db.Node_collection, docs: List[defs.CRE]
) -> List[Dict[str, str]]:
    """
    Generate a simple mapping template CSV structure used by the
    `/rest/v1/cre_csv` endpoint. Produces a list of row dictionaries
    where the first entry is an empty header/template row followed by
    CRE rows traversed depth-first starting from the provided roots.
    """

    processed: Set[str] = set()
    cre_rows: List[Dict[str, str]] = []
    max_depth = 0
    linked_standard_names: Set[str] = set()

    def resolve_cre(cre_obj: defs.CRE) -> defs.CRE:
        full = database.get_CREs(external_id=cre_obj.id)
        if full and isinstance(full[0], defs.CRE):
            return full[0]
        return cre_obj

    def visit(cre_obj: defs.CRE, depth: int) -> None:
        nonlocal max_depth
        if not cre_obj.id or cre_obj.id in processed:
            return

        row = {f"CRE {depth}": f"{cre_obj.id}|{cre_obj.name}"}
        cre_rows.append(row)
        processed.add(cre_obj.id)
        if depth > max_depth:
            max_depth = depth

        full = resolve_cre(cre_obj)
        child_cres: List[defs.CRE] = []
        for link in getattr(full, "links", []):
            if (
                getattr(link.document, "doctype", None) == defs.Credoctypes.CRE
                and link.ltype == defs.LinkTypes.Contains
                and isinstance(link.document, defs.CRE)
            ):
                child_cres.append(link.document)
            elif getattr(link.document, "doctype", None) != defs.Credoctypes.CRE:
                if getattr(link.document, "name", None):
                    linked_standard_names.add(link.document.name)

        for child in sorted(child_cres, key=lambda cre: (cre.id or "", cre.name or "")):
            visit(child, depth + 1)

    for root in docs:
        visit(root, 0)

    header: Dict[str, str] = {f"CRE {i}": "" for i in range(max_depth + 1)}
    # Build template columns dynamically so output adapts to available mappings.
    # Keep generic standard columns as the baseline import template.
    template_name = "standard"
    header[defs.ExportFormat.section_key(template_name)] = ""
    header[defs.ExportFormat.sectionID_key(template_name)] = ""
    header[defs.ExportFormat.hyperlink_key(template_name)] = ""

    for standard_name in sorted(linked_standard_names):
        header[defs.ExportFormat.section_key(standard_name)] = ""
        header[defs.ExportFormat.sectionID_key(standard_name)] = ""
        header[defs.ExportFormat.hyperlink_key(standard_name)] = ""

    rows: List[Dict[str, str]] = []
    rows.append(header)
    rows.extend(cre_rows)

    return rows
