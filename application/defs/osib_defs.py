import networkx as nx
from pprint import pprint
import logging
import os
import re
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Collection, Dict, List, Mapping, NewType, Optional, Tuple, Union

from networkx.algorithms.simple_paths import all_simple_paths
from application.defs import cre_defs as defs

import semver
import yaml
from dacite import (
    Config,
    ForwardReferenceError,
    StrictUnionMatchError,
    UnexpectedDataError,
    from_dict,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# used for serialising and deserialising yaml OSIB documents

# default language is 'en'
default_lang = "en"

# Osib_id is an int or a string
Osib_id = NewType("Osib_id", str)

# Lang is a string, e.g. 'en', 'pt_BR')
Lang = NewType("Lang", str)


@dataclass
class _Osib_base:
    def todict(self) -> Dict[str, Any]:
        return asdict(
            self,
            dict_factory=lambda x: {
                k: v for (k, v) in x if v not in ["", {}, [], None]
            },
        )


@dataclass
class _Status(_Osib_base):
    """Status attributes decribing OSIB attributes and list items"""

    status: str = field(compare=False, default="")
    reviewed: Optional[int] = field(compare=False, default=None)
    change: str = field(compare=False, default="")


@dataclass
class _Link(_Status):
    """Basic attributes used by `link`s-list items"""

    link: str = field(default="")  # osib id (=osib path to an object)
    type: Optional[str] = field(default=None)


@dataclass
class _Source(_Status):
    """Basic attributes used by i18n sources-directory items"""

    source: Optional[str] = field(default=None)  # url
    name: str = field(compare=False, default="")
    description: Optional[str] = field(compare=False, default=None)
    section: Optional[str] = field(default=None)
    subsection: Optional[str] = field(default=None)
    sectionID: Optional[str] = field(default=None)


@dataclass
class Node_attributes(_Status):
    """Attributes decribing an OSIB object"""

    source_id: Optional[str] = field(
        default=""
    )  # Unique id name by source, e.g. document
    links: List[_Link] = field(compare=False, default_factory=list)
    categories: Optional[List[str]] = field(compare=False, default=None)
    maturity: Optional[str] = field(compare=False, default=None)
    sources_i18n: Dict[Union[str, Lang], Optional[_Source]] = field(
        compare=False, default_factory=dict
    )


@dataclass
class Osib_node(_Osib_base):
    """Object-Node for building the OSIB tree"""

    aliases: Optional[List[Osib_id]] = field(compare=False, default=None)
    attributes: Optional[Node_attributes] = field(compare=False, default=None)
    children: Optional[Dict[str, "Osib_node"]] = field(compare=False, default=None)


@dataclass
class Osib_tree(Osib_node):
    """Root-Object for building the OSIB tree"""

    doctype: str = field(compare=False, default="OSIB")
    schema: Optional[str] = field(
        compare=False, default=str(semver.VersionInfo(major=0, minor=0, patch=0))
    )
    # Date, when the tree has been comiled as int: YYYYMMDD
    date: Optional[str] = field(compare=False, default=None)


def read_osib_yaml(yaml_file: str = "") -> List[Dict[str, Any]]:
    with open(yaml_file, "r") as fin:
        osib_yaml = yaml.safe_load_all(fin)
        return [y for y in osib_yaml]


def try_from_file(data: List[Dict[str, Any]] = []) -> List[Osib_tree]:
    result = []
    for dat in data:
        result.append(
            from_dict(data_class=Osib_tree, data=dat, config=Config(check_types=False))
        )  # check_Types=False on purpose as everything is a str
    return result


def resolve_path(
    osib_link: Optional[_Link] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if osib_link and osib_link.link:
        reg = r"\w+\.\w+\.(?P<name>\w+)(\.(?P<section>.+$))?"
        match = re.search(reg, osib_link.link)
        if match:
            return (match["name"], match["section"])
    return None, None


# TODO: get this to return tools and code depending on type
def find_doc(link: Optional[_Link] = None) -> Optional[defs.Document]:
    # TODO (spyros): given a list of existing docs, find if the link exists in the list, otherwise create a new doc and return1.
    docname, docsection = resolve_path(link)
    if docname and docsection:
        return defs.Standard(section=docsection, name=docname)
    return None


def _parse_node(
    orgname: Optional[str] = None,
    root: str = "OSIB",
    name: Optional[str] = None,
    osib: Optional[Osib_node] = None,
    current_path: str = "",
    node_type: Optional[defs.Credoctypes] = None,
) -> List[Union[defs.Document, defs.CRE, defs.Standard]]:
    result: List[Union[defs.Document, defs.CRE, defs.Standard]] = []
    if not osib:
        return result

    if (
        osib is not None
        and osib.attributes is not None
        and (
            "children" not in vars(osib)
            or not osib.children
            or osib.children in ({}, None)
        )
        and current_path not in (None, "")
    ):
        res: defs.Document
        "register the standard with the current path as subsection"
        english_attrs = osib.attributes.sources_i18n.get("en")
        if english_attrs:
            if node_type == defs.Credoctypes.Standard:
                res = defs.Standard(
                    name=name,
                    section=current_path.replace(f"{root}.{orgname}.", ""),
                    hyperlink=english_attrs.source if english_attrs.source else "",
                )
            elif node_type == defs.Credoctypes.Code:
                res = defs.Code(
                    name=name,
                    description=english_attrs.description,
                    hyperlink=english_attrs.source if english_attrs.source else "",
                )
            elif node_type == defs.Credoctypes.Tool:
                ttype = [
                    t
                    for t in defs.ToolTypes
                    if "categories" in vars(osib.attributes)
                    and osib.attributes.categories
                    and t in osib.attributes.categories
                ]
                if ttype:
                    ttype = ttype[0]
                    osib.attributes.categories.remove(ttype)
                    osib.attributes.categories.remove(node_type)
                res = defs.Tool(
                    name=name,
                    description=english_attrs.description,
                    hyperlink=english_attrs.source if english_attrs.source else "",
                    tooltype=ttype if ttype else defs.ToolTypes.Unknown,
                    section=english_attrs.section if english_attrs.section else "",
                    sectionID=(
                        english_attrs.sectionID if english_attrs.sectionID else ""
                    ),
                )

            elif node_type == defs.Credoctypes.CRE:
                res = defs.CRE(
                    name=name,
                    description=english_attrs.description,
                    hyperlink=english_attrs.source if english_attrs.source else "",
                )
            else:
                raise ValueError("OSIB node type unknown")

            res.metadata = {}
            if osib.aliases:
                res.metadata["alias"] = [x for x in osib.aliases]
            if osib.attributes.source_id:
                res.metadata["source_id"] = osib.attributes.source_id
            if osib.attributes.maturity:
                res.metadata["maturity"] = osib.attributes.maturity
            if osib.attributes.categories:
                res.metadata["categories"] = [x for x in osib.attributes.categories]

            for olink in osib.attributes.links:
                linked_doc = find_doc(olink)
                if olink.type:
                    if olink.type.lower() == "parent":
                        res.add_link(
                            link=defs.Link(
                                document=linked_doc, ltype=defs.LinkTypes.PartOf
                            )
                        )
                    elif olink.type.lower() == "child":
                        res.add_link(
                            link=defs.Link(
                                document=linked_doc, ltype=defs.LinkTypes.Contains
                            )
                        )
                    elif olink.type.lower() == "related":
                        res.add_link(
                            link=defs.Link(
                                document=linked_doc, ltype=defs.LinkTypes.Related
                            )
                        )
            return [res]
        else:
            logger.warning("OSIB has no english attributes, parsing skipped")

    elif osib.children:
        for section, child in osib.children.items():
            cpath = current_path.replace(f"{root}.{orgname}.", "")
            result.extend(
                _parse_node(
                    orgname=orgname,
                    root=root,
                    name=name,
                    osib=child,
                    current_path=f"{cpath}.{section}" if len(cpath) else f"{section}",
                    node_type=node_type,
                )
            )
    else:
        logger.error(
            "OSIB doesn't have children but leaf branch not followed this is a bug"
        )
        raise Exception(
            "OSIB doesn't have children but leaf branch not followed this is a bug"
        )
    return result


def osib2cre(tree: Osib_tree) -> Tuple[List[defs.CRE], List[defs.Standard]]:
    tree_aliases = tree.aliases
    attrs = tree.attributes
    standards: List[defs.Standard] = []
    cres = []
    root = tree.doctype
    if not tree.children:
        return [], []
    for orgname, org in tree.children.items():
        if org.children:
            for pname, project in org.children.items():
                if str(pname).lower() != "cre":
                    node_type = None
                    if project and project.attributes and project.attributes.categories:
                        t = [
                            c
                            for c in defs.Credoctypes
                            if c in project.attributes.categories
                        ]
                        if t:
                            node_type = t[0]
                    standards.extend(
                        _parse_node(  # type: ignore  # I know what i'm doing just this once
                            root=root,
                            orgname=str(orgname),
                            name=str(pname),
                            osib=project,
                            node_type=node_type,
                            current_path=f"{root}.{orgname}",
                        )
                    )
                else:
                    cres.extend(
                        [
                            defs.CRE(d)
                            for d in _parse_node(
                                root=root,
                                orgname=str(orgname),
                                osib=project,
                                node_type=defs.Credoctypes.CRE,
                                current_path=f"{root}.{orgname}",
                            )
                        ]
                    )
    return (cres, standards)


def update_paths(
    paths: Optional[nx.DiGraph], pid: str, cid: str, rel_type: defs.LinkTypes
) -> nx.DiGraph:
    if not paths:
        paths = nx.DiGraph()
    paths.add_edge(pid, cid)
    return paths


def paths_to_osib(
    osib_paths: List[str],
    cres: Mapping[str, defs.Document],
    related_nodes: List[Tuple[str, str]],
) -> Osib_tree:
    # TODO: this doesn't add links (although, the child/parent structure IS the link)
    # TODO: this doesn't account for non CRE paths, cres needs to become "documents" and we need to figure this out based on paths of standards or code or whatevs
    result: Dict[str, Osib_node] = {}
    osibs = {}
    owasp = Osib_node(
        attributes=Node_attributes(
            sources_i18n={
                Lang("en"): _Source(
                    name="Open Web Application Security Project",
                    source="https://owasp.org",
                )
            }
        )
    )
    root = Osib_node(
        attributes=Node_attributes(
            sources_i18n={
                Lang("en"): _Source(
                    name="Common Requirements Enumeration",
                    source="https://www.opencre.org",
                )
            }
        )
    )
    # transform everything to Osib Nodes
    for id, cre in cres.items():
        o = Osib_node(
            children={},
            attributes=Node_attributes(
                source_id=cre.id,
                categories=[cre.doctype],
                sources_i18n={
                    Lang("en"): _Source(
                        description=cre.description,
                        name=cre.name,
                        source="",  # todo: make source point to opencre.org deeplink
                    )
                },
                links=[],
            ),
        )
        osibs[id] = o
    # Add links to nodes potentially not in the tree first
    for r in related_nodes:
        l0 = [p for p in osib_paths if f"{r[0]}." in p]
        l1 = [p for p in osib_paths if f"{r[1]}." in p]
        path = ""
        if l0:
            path = f"OSIB.OWASP.CRE.{l0[0].split(r[0])[0]}.{r[0]}"
        else:
            path = f"OSIB.OWASP.CRE.{r[0]}"
            result[r[0]] = osibs[r[0]]

        osibs[r[0]].attributes.links.append(_Link(link=path, type="Related"))

        path = ""
        if l1:
            path = f"OSIB.OWASP.CRE.{l1[0].split(r[1])[0]}.{r[1]}"
        else:
            path = f"OSIB.OWASP.CRE.{r[1]}"
            result[r[1]] = osibs[r[1]]
        osibs[r[1]].attributes.links.append(_Link(link=path, type="Related"))

    # build the child-tree structure
    for osib_path in sorted(osib_paths, key=len):
        pwo = None
        for oid in osib_path.split("."):
            if pwo is not None:
                if oid not in pwo.children:
                    pwo.children[oid] = osibs[oid]
            else:
                result[oid] = osibs[oid]
            pwo = osibs[oid]
    root.children = result
    owasp.children = {"CRE": root}
    return Osib_tree(children={"OWASP": owasp})


def cre2osib(docs: List[defs.Document]) -> Osib_tree:
    # TODO: This only works with a link depth of 1, this is the general assumption for CREs but would be nice to make it work recursively
    osib_paths: List[str] = []
    related_nodes: List[Tuple[str, str]] = []
    cres = {}
    root = "OSIB"
    org = "OWASP"
    project = "CRE"
    base_path = f"{root}.{org}.{project}"
    osib_graph = nx.DiGraph()

    # TODO: get this to update paths attaching the TYPE of document that is in this path somehow, maybe as part of node attrs(?)
    for doc in docs:
        cres[doc.id] = doc
        for link in doc.links:
            cres[link.document.id] = link.document
            if link.ltype == defs.LinkTypes.PartOf:
                osib_paths = update_paths(
                    paths=osib_graph,
                    pid=link.document.id,
                    cid=doc.id,
                    rel_type=link.ltype,
                )
            elif link.ltype == defs.LinkTypes.Contains:
                osib_paths = update_paths(
                    paths=osib_graph,
                    pid=doc.id,
                    cid=link.document.id,
                    rel_type=link.ltype,
                )
            elif link.ltype == defs.LinkTypes.Related:
                related_nodes.append((doc.id, link.document.id))
            elif link.ltype == defs.LinkTypes.LinkedTo:
                related_nodes.append((doc.id, link.document.id))

    return paths_to_osib(
        osib_paths=[".".join(p) for p in osib_paths],
        cres=cres,
        related_nodes=related_nodes,
    )
