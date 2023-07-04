import logging
import re
from copy import copy
from pprint import pprint
from typing import Any, Dict, List, Optional, Tuple, cast

from application.defs import cre_defs as defs

# collection of methods to parse different versions of spreadsheet standards
# each method returns a list of cre_defs documents


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()


def is_empty(value: Optional[str]) -> bool:
    value = str(value)
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
    )


def recurse_print_links(cre: defs.Document) -> None:
    for link in cre.links:
        pprint(link.document)
        recurse_print_links(link.document)


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
        section = mapping.get(defs.ExportFormat.section_key(name, type))
        subsection = mapping.get(defs.ExportFormat.subsection_key(name, type))
        hyperlink = mapping.get(defs.ExportFormat.hyperlink_key(name, type))
        link_type = mapping.get(defs.ExportFormat.link_type_key(name, type))
        tooltype = defs.ToolTypes.from_str(
            mapping.get(defs.ExportFormat.tooltype_key(name, type))
        )
        sectionID = mapping.get(defs.ExportFormat.sectionID_key(name, type))
        description = mapping.get(defs.ExportFormat.description_key(name, type))
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
            node = defs.Code(description=description, hyperlink=hyperlink, name=name)
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


def update_cre_in_links(
    cres: Dict[str, defs.CRE], cre: defs.CRE
) -> Dict[str, defs.CRE]:
    for k, c in cres.items():
        for link in c.links:
            if link.document.name == cre.name:
                link.document = cre.shallow_copy()
    return cres


def parse_export_format(lfile: List[Dict[str, Any]]) -> Dict[str, defs.Document]:
    """
    Given: a spreadsheet written by prepare_spreadsheet()
    return a list of CRE docs
    cases:
        standard
        standard -> standard
        cre -> other cres
        cre -> standards
        cre -> standards, other cres
    """
    cre: defs.Document
    internal_mapping: defs.Document
    cres: Dict[str, defs.Document] = {}
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
        else:  # cre -> standards, other cres
            name = mapping.pop(defs.ExportFormat.cre_name_key())
            id = mapping.pop(defs.ExportFormat.cre_id_key())
            description = ""
            if defs.ExportFormat.cre_description_key() in mapping:
                description = mapping.pop(defs.ExportFormat.cre_description_key())

            if name not in cres.keys():  # register new cre
                cre = defs.CRE(name=name, id=id, description=description)
            else:  # it's a conflict mapping so we've seen this before,
                # just retrieve so we can add the new info
                cre = cres[name]
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
                name = mapping.pop(defs.ExportFormat.linked_cre_name_key(str(i)))
                if not is_empty(name):
                    id = mapping.pop(defs.ExportFormat.linked_cre_id_key(str(i)))
                    link_type = mapping.pop(
                        defs.ExportFormat.linked_cre_link_type_key(str(i))
                    )
                    if name in cres:
                        internal_mapping = cres[name]
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
                        cres[name] = internal_mapping

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
            cres[cre.name] = cre
    cres.update(lone_nodes)
    return cres


def parse_uknown_key_val_standards_spreadsheet(
    link_file: List[Dict[str, str]]
) -> Dict[str, defs.Standard]:
    """parses a cre-less spreadsheet into a list of Standards documents"""
    standards: Dict[str, defs.Standard] = {}
    standards_registered: List[str] = []
    # get the first Key of the first row, pretty much, choose a standard at random to be the main one
    main_standard_name: str
    for stand in list(link_file[0]):
        if not is_empty(stand):
            main_standard_name = stand
            break

    for mapping in link_file:
        primary_standard: defs.Standard
        linked_standard: defs.Standard
        if not is_empty(mapping[main_standard_name]):
            sname = f"{main_standard_name}-{str(mapping[main_standard_name])}"
            if standards.get(sname):
                # pop is important so that primary standard won't link to itself
                mapping.pop(main_standard_name)
                primary_standard = standards[sname]
            else:
                # pop is important here, if the primary standard is not removed, it will end up linking to itself
                primary_standard = defs.Standard(
                    name=main_standard_name, section=mapping.pop(main_standard_name)
                )

            for key, value in mapping.items():
                if (
                    not is_empty(value)
                    and not is_empty(key)
                    and f"{key}-{value}" not in standards_registered
                ):
                    linked_standard = defs.Standard(name=key, section=value)
                    standards_registered.append(f"{key}-{value}")
                    primary_standard.add_link(defs.Link(document=linked_standard))
            if primary_standard:
                standards[sname] = primary_standard
    return standards


def parse_hierarchical_export_format(
    cre_file: List[Dict[str, str]]
) -> Dict[str, defs.CRE]:
    logger.info("Spreadsheet is hierarchical export format")
    cres: Dict[str, defs.CRE] = {}
    max_hierarchy = len([key for key in cre_file[0].keys() if "CRE hierarchy" in key])
    for mapping in cre_file:
        cre: defs.CRE
        name: str = ""
        current_hierarchy: int = 0
        higher_cre: int = 0
        # a CRE's name is the last hierarchy item which is not blank
        for i in range(max_hierarchy, 0, -1):
            key = [key for key in mapping if key.startswith("CRE hierarchy %s" % i)][0]
            if not is_empty(mapping.get(key)):
                if current_hierarchy == 0:
                    name = mapping.pop(key).strip().replace("\n", " ")
                    current_hierarchy = i
                else:
                    higher_cre = i
                    break
        if is_empty(name):
            logger.warning(
                f'Found entry with ID {mapping.get("CRE ID")}'
                " without a cre name, skipping"
            )
            continue
        if name in cres.keys():
            new_id = mapping.get("CRE ID")
            if cres[name].id != new_id and cres[name].id != "" and new_id != "":
                logger.fatal(
                    f"duplicate entry for cre named {name}, previous id:{cres[name].id}, new id {new_id}"
                )
            cre = cres[name]
        else:
            cre = defs.CRE(name=name)

        if not is_empty(mapping.get("CRE ID")):
            cre.id = mapping.pop("CRE ID")
        else:
            logger.warning(f"empty Id for {name}")

        if not is_empty(mapping.get("CRE Tags")):
            ts = set()
            for x in mapping.pop("CRE Tags").split(","):
                ts.add(x.strip())
            cre.tags = list(ts)

        update_cre_in_links(cres, cre)

        # TODO(spyros): temporary until we agree what we want to do with tags
        mapping[
            "Link to other CRE"
        ] = f'{mapping["Link to other CRE"]},{",".join(cre.tags)}'
        if not is_empty(mapping.get("Link to other CRE")):
            other_cres = list(
                set(
                    [
                        x.strip()
                        for x in mapping.pop("Link to other CRE").split(",")
                        if not is_empty(x.strip())
                    ]
                )
            )
            for other_cre in other_cres:
                if not cres.get(other_cre):
                    logger.warning(
                        "%s linking to not yet existent cre %s" % (cre.name, other_cre)
                    )
                    new_cre = defs.CRE(name=other_cre.strip())
                    cres[new_cre.name] = new_cre
                else:
                    new_cre = cres[other_cre]

                # we only need a shallow copy here
                cre.add_link(
                    defs.Link(
                        ltype=defs.LinkTypes.Related, document=new_cre.shallow_copy()
                    )
                )
        for link in parse_standards(mapping):
            cre.add_link(link)

        # link CRE to a higher level one

        if higher_cre:
            cre_hi: defs.CRE
            name_hi = mapping.pop(f"CRE hierarchy {str(higher_cre)}").strip()
            if cres.get(name_hi):
                cre_hi = cres[name_hi]
            else:
                cre_hi = defs.CRE(name=name_hi)

            existing_link = [
                c
                for c in cre_hi.links
                if c.document.doctype == defs.Credoctypes.CRE
                and c.document.name == cre.name
            ]
            # there is no need to capture the entirety of the cre tree, we just need to register this shallow relation
            # the "cres" dict should contain the rest of the info
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
            cres[cre_hi.name] = cre_hi
        else:
            pass  # add the cre to cres and make the connection
        if cre:
            cres[cre.name] = cre

    return cres


def parse_standards(
    mapping: Dict[str, str], standards_mapping: Dict[str, Dict[str, Any]] = None
) -> List[defs.Link]:
    if not standards_mapping:
        standards_mapping = {
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
                    "separator": "\n",
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

                hyperlinks = mapping.get(struct["hyperlink"], "").split(separator)
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
                subsection = mapping.get(struct["subsection"], "")
                hyperlink = mapping.get(struct["hyperlink"], "")
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
