import logging
from typing import Any, Dict, List, Optional

from application.defs import cre_defs as defs

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def is_empty(value: Optional[str]) -> bool:
    value = str(value).strip()
    return (
        value is None
        or value == "None"
        or value == ""
        or "n/a" in value.lower()
        or value == "nan"
        or value.lower() == "no"
        or value.lower() == "tbd"
        or value.lower() == "see higher level topic"
        or value.lower() == "tbd"
        or value.lower() == "0"
    )


def parse_export_format(lfile: List[Dict[str, Any]]) -> Dict[str, List[defs.Document]]:
    """
    Given a spreadsheet written by prepare_spreadsheet(), return CRE + standards docs.
    """
    cres: Dict[str, defs.CRE] = {}
    standards: Dict[str, Dict[str, defs.Standard]] = {}
    documents: Dict[str, List[defs.Document]] = {}

    if not lfile:
        return documents

    max_internal_cre_links = len(
        set([k for k in lfile[0].keys() if k.startswith("CRE")])
    )
    standard_names = set(
        [k.split("|")[0] for k in lfile[0].keys() if not k.startswith("CRE")]
    )
    logger.info(f"Found standards with names: {standard_names}")

    highest_cre = None
    highest_index = max_internal_cre_links + 1

    previous_cre = None
    previous_index = max_internal_cre_links + 1

    for mapping_line in lfile:
        working_cre = None
        working_standard = None
        # get highest numbered CRE entry (lowest in hierarchy)
        for i in range(max_internal_cre_links - 1, -1, -1):
            if not is_empty(mapping_line.get(f"CRE {i}")):
                entry = mapping_line.get(f"CRE {i}").split(defs.ExportFormat.separator)
                if not entry or len(entry) < 2:
                    line = mapping_line.get(f"CRE {i}")
                    raise ValueError(
                        f"mapping line contents: {line}, key: CRE {i} is not formatted correctly, missing separator {defs.ExportFormat.separator}"
                    )
                working_cre = defs.CRE(name=entry[1], id=entry[0])
                if cres.get(working_cre.id):
                    working_cre = cres[working_cre.id]

                if previous_index < i:  # we found a higher hierarchy CRE
                    previous_index = i
                    highest_cre = previous_cre
                    cres[highest_cre.id] = highest_cre.add_link(
                        defs.Link(
                            document=working_cre.shallow_copy(),
                            ltype=defs.LinkTypes.Contains,
                        )
                    )
                elif highest_index < i:  # we found a higher hierarchy CRE
                    lnk = defs.Link(
                        document=working_cre.shallow_copy(),
                        ltype=defs.LinkTypes.Contains,
                    )
                    if not highest_cre.has_link(lnk):
                        cres[highest_cre.id] = highest_cre.add_link(lnk)
                    else:
                        logger.warning(
                            f"Link between {highest_cre.name} and {working_cre.name} already exists"
                        )
                elif highest_cre == None:
                    highest_cre = working_cre
                    highest_index = i

                previous_index = i
                previous_cre = working_cre
                break

        for s in standard_names:
            if not is_empty(mapping_line.get(f"{s}{defs.ExportFormat.separator}name")):
                working_standard = defs.Standard(
                    name=s,
                    sectionID=mapping_line.get(f"{s}{defs.ExportFormat.separator}id"),
                    section=mapping_line.get(f"{s}{defs.ExportFormat.separator}name"),
                    hyperlink=mapping_line.get(
                        f"{s}{defs.ExportFormat.separator}hyperlink", ""
                    ),
                    description=mapping_line.get(
                        f"{s}{defs.ExportFormat.separator}description", ""
                    ),
                )
                if standards.get(working_standard.name) and standards.get(
                    working_standard.name
                ).get(working_standard.id):
                    working_standard = standards[working_standard.name][
                        working_standard.id
                    ]

                if working_cre:
                    working_cre.add_link(
                        defs.Link(
                            document=working_standard.shallow_copy(),
                            ltype=defs.LinkTypes.LinkedTo,
                        )
                    )
                    working_standard.add_link(
                        defs.Link(
                            document=working_cre.shallow_copy(),
                            ltype=defs.LinkTypes.LinkedTo,
                        )
                    )

                if working_standard.name not in standards:
                    standards[working_standard.name] = {}

                standards[working_standard.name][working_standard.id] = working_standard

        if working_cre:
            cres[working_cre.id] = working_cre
    documents[defs.Credoctypes.CRE] = list(cres.values())

    for standard_name, standard_entries in standards.items():
        logger.info(f"Adding {len(standard_entries)} entries for {standard_name}")
        documents[standard_name] = list(standard_entries.values())
    return documents
