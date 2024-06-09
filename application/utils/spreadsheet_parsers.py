import logging
import re
from copy import copy
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from application.defs import cre_defs as defs

# collection of methods to parse different versions of spreadsheet standards
# each method returns a list of cre_defs documents


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


# the supported resources from the main CSV
supported_resource_mapping = {
    "CRE": {
        "id": "CRE ID",
        "name": "CRE hierarchy",
        "tags": "CRE Tags",
        "links": "Link to other CRE",
        "description": "",
    },
    "Standards": {
        "ASVS": {
            "section": "Standard ASVS 4.0.3 description",
            "sectionID": "Standard ASVS 4.0.3 Item",
            "subsection": "",
            "hyperlink": "Standard ASVS 4.0.3 Hyperlink",
        },
        "OWASP Proactive Controls": {
            "section": "Standard OPC (ASVS source)",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard OPC (ASVS source)-hyperlink",
            "separator": ";",
        },
        "CWE": {
            "section": "",
            "sectionID": "Standard CWE (from ASVS)",
            "subsection": "",
            "hyperlink": "Standard CWE (from ASVS)-hyperlink",
        },
        "NIST 800-53 v5": {
            "section": "Standard NIST 800-53 v5",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard NIST 800-53 v5-hyperlink",
            "separator": "\n",
        },
        "OWASP Web Security Testing Guide (WSTG)": {
            "section": "Standard WSTG-item",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard WSTG-Hyperlink",
            "separator": ";",
        },
        "OWASP Cheat Sheets": {
            "section": "Standard Cheat_sheets",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard Cheat_sheets-Hyperlink",
            "separator": ";",
        },
        "NIST 800-63": {
            "section": "Standard NIST-800-63 (from ASVS)",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "",
            "separator": "/",
        },
        "OWASP Top 10 2021": {
            "section": "OWASP Top 10 2021 item",
            "sectionID": "OWASP Top 10 2021 item ID",
            "subsection": "",
            "hyperlink": "OWASP Top 10 2021 hyperlink",
        },
        "OWASP Top 10 2017": {
            "section": "Standard Top 10 2017 item",
            "sectionID": "",
            "subsection": "",
            "hyperlink": "Standard Top 10 2017 Hyperlink",
        },
        "Cloud Controls Matrix": {
            "section": "Source-CCM-Control Title",
            "sectionID": "Source-CCM ID",
            "subsection": "",
            "hyperlink": "",
            "separator": "\n",
        },
        "ISO 27001": {
            "section": "Standard 27001/2:2022",
            "sectionID": "Standard 27001/2:2022 Section ID",
            "subsection": "",
            "hyperlink": "",
            "separator": "\n",
        },
        "SAMM": {
            "section": "Standard SAMM v2",
            "sectionID": "Standard SAMM v2 ID",
            "subsection": "",
            "hyperlink": "Standard SAMM v2 hyperlink",
            # "version":"v2",
            "separator": "\n",
        },
        "NIST SSDF": {
            "section": "Standard NIST SSDF",
            "sectionID": "Standard NIST SSDF ID",
            "subsection": "",
            "hyperlink": "",
            # "version":"v2",
            "separator": "\n",
        },
    },
}


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


def parse_export_format(lfile: List[Dict[str, Any]]) -> Dict[str, defs.Document]:
    """
    Given: a spreadsheet written by prepare_spreadsheet()
    return a list of CRE docs
    cases:
        standard
        standard -> standard
        cre -> other documents
        cre -> standards
        cre -> standards, other documents
    """

    def get_linked_nodes(mapping: Dict[str, str]) -> List[defs.Link]:
        nodes = []
        names = set(
            [
                k.split(defs.ExportFormat.separator.value)[1]
                for k, v in mapping.items()
                if not is_empty(v)
                and "CRE" not in k.upper()
                and len(k.split(defs.ExportFormat.separator.value)) >= 3
            ]
        )
        for name in names:
            type = defs.ExportFormat.get_doctype(
                [m for m in mapping.keys() if name in m][0]
            )
            if not type:
                raise ValueError(
                    f"Mapping of {name} not in format of <type>:{name}:<attribute>"
                )
            section = str(mapping.get(defs.ExportFormat.section_key(name, type)))
            subsection = str(mapping.get(defs.ExportFormat.subsection_key(name, type)))
            hyperlink = str(mapping.get(defs.ExportFormat.hyperlink_key(name, type)))
            link_type = str(mapping.get(defs.ExportFormat.link_type_key(name, type)))
            tooltype = defs.ToolTypes.from_str(
                str(mapping.get(defs.ExportFormat.tooltype_key(name, type)))
            )
            sectionID = str(mapping.get(defs.ExportFormat.sectionID_key(name, type)))
            description = str(
                mapping.get(defs.ExportFormat.description_key(name, type))
            )
            node = None
            if type == defs.Credoctypes.Standard:
                node = defs.Standard(
                    name=name,
                    section=section,
                    subsection=subsection,
                    hyperlink=hyperlink,
                    sectionID=sectionID,
                )
            elif type == defs.Credoctypes.Code:
                node = defs.Code(
                    description=description, hyperlink=hyperlink, name=name
                )
            elif type == defs.Credoctypes.Tool:
                node = defs.Tool(
                    tooltype=tooltype,
                    name=name,
                    description=description,
                    hyperlink=hyperlink,
                    section=section,
                    sectionID=sectionID,
                )

            lt: defs.LinkTypes
            if not is_empty(link_type):
                lt = defs.LinkTypes.from_str(link_type)
            else:
                lt = defs.LinkTypes.LinkedTo
            nodes.append(defs.Link(document=node, ltype=lt))
        return nodes

    cre: defs.Document
    internal_mapping: defs.Document
    documents: Dict[str, defs.Document] = {}
    lone_nodes: Dict[str, defs.Node] = {}
    link_types_regexp = re.compile(defs.ExportFormat.linked_cre_name_key("(\d+)"))
    max_internal_cre_links = len(
        set([k for k, v in lfile[0].items() if link_types_regexp.match(k)])
    )
    for mapping in lfile:
        # if the line does not register a CRE
        if not mapping.get(defs.ExportFormat.cre_name_key()):
            # standard -> nothing | standard
            for st in get_linked_nodes(mapping):
                lone_nodes[
                    f"{st.document.doctype}:{st.document.name}:{st.document.section}"
                ] = st.document
                logger.info(
                    f"adding node: {st.document.doctype}:{st.document.name}:{st.document.section}"
                )
        else:  # cre -> standards, other documents
            name = str(mapping.pop(defs.ExportFormat.cre_name_key()))
            id = str(mapping.pop(defs.ExportFormat.cre_id_key()))
            description = ""
            if defs.ExportFormat.cre_description_key() in mapping:
                description = mapping.pop(defs.ExportFormat.cre_description_key())

            if name not in documents.keys():  # register new cre
                cre = defs.CRE(name=name, id=id, description=description)
            else:  # it's a conflict mapping so we've seen this before,
                # just retrieve so we can add the new info
                cre = documents[name]
                if cre.id != id:
                    if is_empty(id):
                        id = cre.id
                    else:
                        logger.fatal(
                            "id from sheet %s does not match already parsed id %s for cre %s, this looks like a bug"
                            % (id, cre.id, name)
                        )
                        continue
                if is_empty(cre.description) and not is_empty(description):
                    # might have seen the particular name/id as an internal
                    # mapping, in which case just update the description and continue
                    cre.description = description

            # register the standards part
            for standard in get_linked_nodes(mapping):
                cre.add_link(standard)

            # add the CRE links
            for i in range(0, max_internal_cre_links):
                name = str(mapping.pop(defs.ExportFormat.linked_cre_name_key(str(i))))
                if not is_empty(name):
                    id = str(mapping.pop(defs.ExportFormat.linked_cre_id_key(str(i))))
                    link_type = str(
                        mapping.pop(defs.ExportFormat.linked_cre_link_type_key(str(i)))
                    )
                    if name in documents:
                        internal_mapping = documents[name]
                        if internal_mapping.id != id:
                            if is_empty(id):
                                id = internal_mapping.id
                            else:
                                logger.fatal(
                                    "id from sheet %s does not match already parsed id %s for cre/group %s, this looks like a bug"
                                    % (id, internal_mapping.id, name)
                                )
                                continue
                    else:
                        internal_mapping = defs.CRE(name=name, id=id)
                        lt = defs.LinkTypes.from_str(link_type)
                        sub_lt: defs.LinkTypes
                        if lt == defs.LinkTypes.Contains:
                            sub_lt = defs.LinkTypes.PartOf
                        internal_mapping.add_link(
                            defs.Link(
                                document=defs.CRE(  # add a link to the original without the links
                                    name=cre.name,
                                    id=cre.id,
                                    description=cre.description,
                                ),
                                ltype=sub_lt,
                            )
                        )
                        documents[name] = internal_mapping

                    if name not in [l.document.name for l in cre.links]:
                        cre.add_link(
                            defs.Link(
                                document=defs.CRE(
                                    name=internal_mapping.name,
                                    id=internal_mapping.id,
                                    description=internal_mapping.description,
                                ),
                                ltype=defs.LinkTypes.from_str(link_type),
                            )
                        )
            documents[cre.name] = cre
    documents.update(lone_nodes)
    return documents


@dataclass
class UninitializedMapping:
    complete_cre: defs.CRE
    other_cre_name: str
    relationship: defs.LinkTypes  # Relationship is complete_cre->other_cre_name


def get_supported_resources_from_main_csv() -> List[str]:
    return supported_resource_mapping["Standards"].keys()


def add_standard_to_documents_array(
    standard: defs.Standard, documents: Dict[str, List[defs.Document]]
) -> Dict[defs.Credoctypes, Dict[str, List[defs.Document]]]:
    if standard.name not in documents.keys():
        documents[standard.name] = []
    found = False
    index = 0
    docs = documents[standard.name]
    for doc in documents[standard.name]:
        if (
            doc.name == standard.name
            and doc.section == standard.section
            and doc.subsection == standard.subsection
            and doc.sectionID == standard.sectionID
            and doc.version == standard.version
        ):
            for lnk in standard.links:
                if lnk.document.id not in list([l.document.id for l in doc.links]):
                    doc = doc.add_link(lnk)
            docs[index] = doc

            found = True
        index += 1
    documents[standard.name] = docs
    if not found:
        documents[standard.name].append(standard)
    return documents


def reconcile_uninitializedMappings(
    cres: Dict[str, defs.CRE], u_mappings: List[UninitializedMapping]
) -> Dict[str, defs.CRE]:
    for mapping in u_mappings:
        other_cre = cres.get(mapping.other_cre_name)
        if not other_cre:
            raise ValueError(
                f"CRE named: '{mapping.other_cre_name}' does not have an id in the sheet"
            )
        cre = cres[mapping.complete_cre.name]
        cres[cre.name] = cre.add_link(
            defs.Link(ltype=mapping.relationship, document=other_cre.shallow_copy())
        )
    return cres


def get_highest_cre_name(
    mapping: Dict[str, str], highest_hierarchy: int = 5
) -> tuple[int, str]:
    """
    given a line of the root CSV, returns the highest hierarchy CRE and a number from 1 to 5 based on where in the hierarchy it found the CRE
    """
    for i in range(highest_hierarchy, 0, -1):
        if not is_empty(mapping.get(f"CRE hierarchy {i}")):
            return i, mapping.get(f"CRE hierarchy {i}").strip()
    return -1, None


def update_cre_in_links(
    documents: Dict[str, defs.CRE], cre: defs.CRE
) -> List[defs.CRE]:
    for c in documents.values():
        for link in c.links:
            if link.document.name == cre.name:
                link.document = cre.shallow_copy()
    return documents


def parse_hierarchical_export_format(
    cre_file: List[Dict[str, str]]
) -> Dict[str, List[defs.Document]]:
    """parses the main OpenCRE csv and creates a list of standards in it

    Args:
        cre_file (List[Dict[str, str]]): the Dict representation of the spreadsheet, entries in the dict are {<Header-Entry>:<Value-Entry>}

    Returns:
        Dict[str,List[defs.Document]]] a dictionary of
        {
            <Name of resource>:[<resource documents>]
            }

        for example:
        {
            "CRE":[<list of cre docs>],
            "ASVS":[<list of ASVS docs>]
        }
    """

    logger.info("Spreadsheet is hierarchical export format")
    documents: Dict[str, List[defs.Document]] = {defs.Credoctypes.CRE.value: []}
    cre_dict = {}
    uninitialized_cre_mappings: List[UninitializedMapping] = (
        []
    )  # the csv has a column "Link to Other CRE", this column linksa complete CRE entry to another CRE by name.
    # The other CRE might not have been initialized yet at the time of linking so it cannot be part of our main document collection yet
    max_hierarchy = len([key for key in cre_file[0].keys() if "CRE hierarchy" in key])
    for mapping in cre_file:
        cre: defs.CRE
        name: str = ""
        current_hierarchy: int = 0
        higher_cre: int = 0

        current_hierarchy, name = get_highest_cre_name(
            mapping=mapping, highest_hierarchy=max_hierarchy
        )
        if name == None:  # skip empty lines
            continue

        if current_hierarchy > 0:  # find the previous higher CRE so we can link
            higher_cre = 0
            for i in range(current_hierarchy - 1, 0, -1):
                if not is_empty(mapping.get(f"CRE hierarchy {str(i)}")):
                    higher_cre = i
                    break

        if is_empty(name):
            raise ValueError(
                f'Found entry with ID \'{mapping.get("CRE ID")}\' hierarchy {current_hierarchy} without a cre name'
            )

        if name in cre_dict.keys():
            curr_id = str(mapping.get("CRE ID")).strip()
            if (
                cre_dict[name].id != curr_id
                and cre_dict[name].id != ""
                and curr_id != ""
            ):
                err_msg = f"duplicate entry for cre named {name}, previous id:{cre_dict[name].id}, new id {curr_id}"
                raise ValueError(err_msg)
            cre = cre_dict[name]
        elif not is_empty(str(mapping.get("CRE ID")).strip()):
            cre = defs.CRE(name=name, id=str(mapping.pop("CRE ID")))
        else:
            logger.warning(f"empty Id for {name}")

        if not is_empty(str(mapping.get("CRE Tags")).strip()):
            ts = set()
            for x in str(mapping.pop("CRE Tags")).split(","):
                ts.add(x.strip())
            cre.tags = list(ts)
        if cre:
            cre_dict = update_cre_in_links(cre_dict, cre)

        mapping["Link to other CRE"] = (
            f'{mapping["Link to other CRE"]},{",".join(cre.tags)}'
        )

        if not is_empty(str(mapping.get("Link to other CRE")).strip()):
            other_cres = list(
                set(
                    [
                        x.strip()
                        for x in str(mapping.pop("Link to other CRE")).split(",")
                        if not is_empty(x.strip())
                    ]
                )
            )
            for other_cre in other_cres:
                logger.info(f"{cre.id}: Found 'other cre' {other_cre}")
                if not cre_dict.get(other_cre):
                    logger.info(
                        f"{cre.id}: We don't know yet of 'other cre' {other_cre}, adding to uninitialized mappings"
                    )
                    uninitialized_cre_mappings.append(
                        UninitializedMapping(
                            complete_cre=cre,
                            other_cre_name=other_cre.strip(),
                            relationship=defs.LinkTypes.Related,
                        )
                    )
                else:
                    logger.info(
                        f"{cre.id}: We knew yet 'other cre' {other_cre}, adding regular link"
                    )
                    new_cre = cre_dict[other_cre.strip()]
                    # we only need a shallow copy here
                    cre = cre.add_link(
                        defs.Link(
                            ltype=defs.LinkTypes.Related,
                            document=new_cre.shallow_copy(),
                        )
                    )

        for link in parse_standards(mapping):
            doc = link.document
            doc = doc.add_link(
                defs.Link(document=cre.shallow_copy(), ltype=defs.LinkTypes.LinkedTo)
            )
            documents = add_standard_to_documents_array(doc, documents)

        # link CRE to a higher level one
        if higher_cre and not is_empty(
            str(mapping.get(f"CRE hierarchy {str(higher_cre)}")).strip()
        ):
            name_hi = str(mapping.pop(f"CRE hierarchy {str(higher_cre)}")).strip()
            cre_hi = cre_dict.get(name_hi)
            if not cre_hi:
                uninitialized_cre_mappings.append(
                    UninitializedMapping(
                        complete_cre=cre,
                        other_cre_name=name_hi,
                        relationship=defs.LinkTypes.PartOf,
                    )
                )
            else:
                existing_link = [
                    c
                    for c in cre_hi.links
                    if c.document.doctype == defs.Credoctypes.CRE
                    and c.document.name == cre.name
                ]
                # there is no need to capture the entirety of the cre tree, we just need to register this shallow relation
                # the "documents" dict should contain the rest of the info
                if existing_link:
                    cre_hi.links[
                        cre_hi.links.index(existing_link[0])
                        # ugliest way ever to write "update the object in that pointer"
                    ].document = cre.shallow_copy()
                else:
                    cre_hi = cre_hi.add_link(
                        defs.Link(
                            ltype=defs.LinkTypes.Contains, document=cre.shallow_copy()
                        )
                    )
                cre_dict[cre_hi.name] = cre_hi
        else:
            pass  # add the cre to documents and make the connection
        if cre:
            cre_dict[cre.name] = cre

    cre_dict = reconcile_uninitializedMappings(cre_dict, uninitialized_cre_mappings)
    documents[defs.Credoctypes.CRE.value] = list(cre_dict.values())
    return documents


def parse_standards(
    mapping: Dict[str, str], standards_mapping: Dict[str, Dict[str, Any]] = None
) -> List[defs.Link]:
    if not standards_mapping:
        standards_mapping = supported_resource_mapping

    links: List[defs.Link] = []
    for name, struct in standards_mapping.get("Standards", {}).items():
        if not is_empty(mapping.get(struct["section"])) or not is_empty(
            mapping.get(struct["sectionID"])
        ):
            if "separator" in struct:
                separator = struct["separator"]
                sections = str(mapping.pop(struct["section"])).split(separator)
                subsections = str(mapping.get(struct["subsection"], "")).split(
                    separator
                )

                hyperlinks = str(mapping.get(struct["hyperlink"], "")).split(separator)
                if len(sections) > len(subsections):
                    subsections.extend([""] * (len(sections) - len(subsections)))
                if len(sections) > len(hyperlinks):
                    hyperlinks.extend([""] * (len(sections) - len(hyperlinks)))

                sectionIDs = [""] * len(sections)
                if struct["sectionID"] in mapping:
                    sectionIDs = str(mapping.pop(struct["sectionID"])).split(separator)

                if len(sections) == 0:
                    sections = [""] * len(sectionIDs)

                for section, subsection, link, sectionID in zip(
                    sections, subsections, hyperlinks, sectionIDs
                ):
                    if not is_empty(section):
                        links.append(
                            defs.Link(
                                ltype=defs.LinkTypes.LinkedTo,
                                document=defs.Standard(
                                    name=name,
                                    section=section.strip(),
                                    hyperlink=link.strip(),
                                    subsection=subsection.strip(),
                                    sectionID=sectionID.strip(),
                                ),
                            )
                        )
            else:
                section = str(mapping.get(struct["section"], ""))
                subsection = str(mapping.get(struct["subsection"], ""))
                hyperlink = str(mapping.get(struct["hyperlink"], ""))
                sectionID = str(mapping.get(struct["sectionID"], ""))

                links.append(
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name=name,
                            section=section.strip(),
                            sectionID=sectionID.strip(),
                            subsection=subsection.strip(),
                            hyperlink=hyperlink.strip(),
                        ),
                    )
                )
    return links
