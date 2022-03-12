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
        description = mapping.get(defs.ExportFormat.description_key(name, type))
        node = None
        if type == defs.Credoctypes.Standard:
            node = defs.Standard(
                name=name, section=section, subsection=subsection, hyperlink=hyperlink
            )
        elif type == defs.Credoctypes.Code:
            node = defs.Code(description=description, hyperlink=hyperlink, name=name)
        elif type == defs.Credoctypes.Tool:
            node = defs.Tool(
                tooltype=tooltype,
                name=name,
                description=description,
                hyperlink=hyperlink,
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
    """Given: a spreadsheet written by prepare_spreadsheet()
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

        else:  # cre -> standards, other cres
            name = mapping.pop(defs.ExportFormat.cre_name_key())
            id = mapping.pop(defs.ExportFormat.cre_id_key())
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


def parse_v1_standards(
    cre_file: List[Dict[str, str]]
) -> Tuple[Dict[str, defs.CRE], Dict[str, defs.CRE]]:
    cre: defs.CRE
    linked_standard: defs.Standard
    cres: Dict[str, defs.CRE] = {}
    groupless_cres: Dict[str, defs.CRE] = {}
    groups: Dict[str, defs.CRE] = {}
    for cre_mapping in cre_file:
        name = cre_mapping.pop("Core-CRE (high-level description/summary)")
        id = cre_mapping.pop("CORE-CRE-ID").strip()
        if name in cres.keys():
            cre = cres[name]
            # if name is not None and id != cre.id:
            #     raise EnvironmentError(
            #         "same cre name %s different id? %s %s" % (cre.name, cre.id, id))
        else:
            cre = defs.CRE(description=cre_mapping.pop("Description"), name=name, id=id)
        asvs_tags = []
        if cre_mapping.pop("ASVS-L1") == "X":
            asvs_tags.append("L1")
        if cre_mapping.pop("ASVS-L2") == "X":
            asvs_tags.append("L2")
        if cre_mapping.pop("ASVS-L3") == "X":
            asvs_tags.append("L3")

        if not is_empty(cre_mapping.get("ID-taxonomy-lookup-from-ASVS-mapping")):
            cre.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name="ASVS",
                        section=cre_mapping.pop("ASVS Item"),
                        subsection=cre_mapping.pop(
                            "ID-taxonomy-lookup-from-ASVS-mapping"
                        ),
                        tags=asvs_tags,
                    ),
                )
            )
        if not is_empty(cre_mapping.get("CWE")):
            cre.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(name="CWE", section=cre_mapping.pop("CWE")),
                )
            )

        if not is_empty(cre_mapping.get("Cheat Sheet")) and not is_empty(
            cre_mapping.get("cheat_sheets")
        ):
            cre.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name="Cheatsheet",
                        section=cre_mapping.pop("Cheat Sheet"),
                        hyperlink=cre_mapping.pop("cheat_sheets"),
                    ),
                )
            )

        nist_items = cre_mapping.pop("NIST 800-53 - IS RELATED TO")
        if not is_empty(nist_items):
            if "\n" in nist_items:
                for element in nist_items.split("\n"):
                    if element:
                        cre.add_link(
                            defs.Link(
                                ltype=defs.LinkTypes.LinkedTo,
                                document=defs.Standard(
                                    name="NIST 800-53",
                                    section=element,
                                    tags=["is related to"],
                                ),
                            )
                        )
            else:
                cre.add_link(
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="NIST 800-53",
                            section=nist_items,
                            tags=["is related to"],
                        ),
                    )
                )
        if not is_empty(cre_mapping.get("NIST 800-63")):
            cre.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name="NIST 800-63", section=cre_mapping.pop("NIST 800-63")
                    ),
                )
            )

        if not is_empty(cre_mapping.get("OPC")):
            cre.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(name="OPC", section=cre_mapping.pop("OPC")),
                )
            )

        if not is_empty(cre_mapping.get("Top10 2017")):
            cre.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name="TOP10", section=cre_mapping.pop("Top10 2017")
                    ),
                )
            )
        if not is_empty(cre_mapping.get("WSTG")):
            if "\n" in cre_mapping.get("WSTG", ""):
                for element in cre_mapping.get("WSTG", "").split("\n"):
                    if not is_empty(element):
                        cre.add_link(
                            defs.Link(
                                ltype=defs.LinkTypes.LinkedTo,
                                document=defs.Standard(name="WSTG", section=element),
                            )
                        )
            else:
                cre.add_link(
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="WSTG", section=cre_mapping.pop("WSTG")
                        ),
                    )
                )
        if not is_empty(cre_mapping.get("SIG ISO 25010")):
            cre.add_link(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name="SIG ISO 25010", section=cre_mapping.pop("SIG ISO 25010")
                    ),
                )
            )
        cres[cre.name] = cre
        # group mapping
        is_in_group = False
        for i in range(1, 8):

            group: defs.CRE
            gname = cre_mapping.pop("CRE Group %s" % i)
            gid = cre_mapping.pop("CRE Group %s Lookup" % i)
            if not is_empty(gname):

                if gname not in groups.keys():
                    group = defs.CRE(name=gname, id=gid)

                elif groups.get(name) and id != groups[name].id and groups.get("name"):
                    raise ValueError(
                        "Group %s has two different ids %s and %s"
                        % (name, id, groups.get("name"))
                    )
                else:

                    group = groups[gname]

                is_in_group = True
                group.add_link(defs.Link(ltype=defs.LinkTypes.Contains, document=cre))
                groups[group.name] = group
        if not is_in_group:
            groupless_cres[cre.name] = cre
    return (groups, groupless_cres)


def parse_v0_standards(cre_file: List[Dict[str, str]]) -> Dict[str, defs.CRE]:
    """given a yaml with standards, build a list of standards"""
    cres: Dict[str, defs.CRE] = {}
    for cre_mapping in cre_file:
        cre: defs.CRE
        linked_standard: defs.Standard
        if not is_empty(cre_mapping.get("CRE-ID-lookup-from-taxonomy-table")):
            existing = cres.get(cre_mapping["CRE-ID-lookup-from-taxonomy-table"])
            if existing:
                cre = existing
                name = cre_mapping.get("name")
                if name is not None and name != cre.name:
                    raise EnvironmentError(
                        "same cre different name? %s %s" % (cre.name, name)
                    )
            else:
                cre = defs.CRE(
                    description=cre_mapping.pop("Description"),
                    name=cre_mapping.pop("CRE-ID-lookup-from-taxonomy-table"),
                )

        # parse ASVS, the v0 docs have a human-friendly but non-standard way of doing asvs
        if cre_mapping.get("ID-taxonomy-lookup-from-ASVS-mapping"):
            linked_standard = defs.Standard(
                name="ASVS",
                section=cre_mapping.pop("ID-taxonomy-lookup-from-ASVS-mapping"),
                subsection=cre_mapping.pop("Item"),
            )
            cre.add_link(
                defs.Link(ltype=defs.LinkTypes.LinkedTo, document=linked_standard)
            )

        for key, value in cre_mapping.items():
            if not is_empty(value) and not is_empty(key):
                linked_standard = defs.Standard(name=key, section=value)
                cre.add_link(
                    defs.Link(ltype=defs.LinkTypes.LinkedTo, document=linked_standard)
                )
        if cre:
            cres[cre.name] = cre
    return cres


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

        [cre.add_link(link) for link in parse_standards(mapping)]

        # link CRE to a higher level one

        if higher_cre:
            cre_hi: defs.CRE
            if cres.get(mapping[f"CRE hierarchy {str(higher_cre)}"]):
                cre_hi = cres[mapping.pop(f"CRE hierarchy {str(higher_cre)}").strip()]
            else:
                cre_hi = defs.CRE(
                    name=mapping.pop(f"CRE hierarchy {str(higher_cre)}").strip()
                )

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
                cre_hi.add_link(
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
                    "section": "Standard ASVS Item",
                    "subsection": "",
                    "hyperlink": "Standard ASVS Hyperlink",
                },
                "OWASP Proactive Controls": {
                    "section": "Standard OPC (ASVS source)",
                    "subsection": "",
                    "hyperlink": "Standard OPC (ASVS source)-hyperlink",
                },
                "CWE": {
                    "section": "Standard CWE (from ASVS)",
                    "subsection": "",
                    "hyperlink": "Standard CWE (from ASVS)-hyperlink",
                },
                "NIST 800-53 v5": {
                    "section": "Standard NIST 800-53 v5",
                    "subsection": "",
                    "hyperlink": "Standard NIST 800-53 v5-hyperlink",
                    "separator": "\n",
                },
                "(WSTG) Web Security Testing Guide": {
                    "section": "Standard WSTG",
                    "subsection": "",
                    "hyperlink": "Standard WSTG-Hyperlink",
                    "separator": "\n",
                },
                "Cheat_sheets": {
                    "section": "Standard Cheat_sheets",
                    "subsection": "",
                    "hyperlink": "Standard Cheat_sheets-Hyperlink",
                    "separator": ";",
                },
                "NIST 800-63": {
                    "section": "Standard NIST-800-63 (from ASVS)",
                    "subsection": "",
                    "hyperlink": "",
                    "separator": "/",
                },
                "OWASP Top 10 2021": {
                    "section": "OWASP Top 10 2021",
                    "subsection": "",
                    "hyperlink": "OWASP Top 10 hyperlink",
                },
                "Top10 2017": {
                    "section": "Standard Top10 2017",
                    "subsection": "",
                    "hyperlink": "Standard Top10 Hyperlink",
                },
            },
        }
    links: List[defs.Link] = []
    for name, struct in standards_mapping.get("Standards", {}).items():
        if not is_empty(mapping.get(struct["section"])):
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

                if "Top" in name:
                    pprint("found top 10")

                for section, subsection, link in zip(sections, subsections, hyperlinks):
                    if not is_empty(section):
                        links.append(
                            defs.Link(
                                ltype=defs.LinkTypes.LinkedTo,
                                document=defs.Standard(
                                    name=name,
                                    section=section.strip(),
                                    hyperlink=link.strip(),
                                    subsection=subsection.strip(),
                                ),
                            )
                        )
            else:
                section = str(mapping.pop(struct["section"]))
                subsection = mapping.get(struct["subsection"], "")
                hyperlink = mapping.get(struct["hyperlink"], "")
                links.append(
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name=name,
                            section=section.strip(),
                            subsection=subsection.strip(),
                            hyperlink=hyperlink.strip(),
                        ),
                    )
                )
    return links
