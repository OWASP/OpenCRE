
import json
from copy import copy
from dataclasses import asdict, dataclass, field
from enum import Enum
from pprint import pprint
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
    overload,
)

# used for serialising and deserialising yaml CRE documents


class ExportFormat(Enum):
    separator = ":"
    section = "section"
    subsection = "subsection"
    hyperlink = "hyperlink"
    link_type = "link_type"
    name = "name"
    id = "id"
    description = "description"
    cre_link = "Linked_CRE_"
    cre = "CRE"

    @staticmethod
    def section_key(sname: str) -> str:
        "returns <sname>:section"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.section.value,
        )

    @staticmethod
    def subsection_key(sname: str) -> str:
        "returns <sname>:subsection"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.subsection.value,
        )

    @staticmethod
    def hyperlink_key(sname: str) -> str:
        "returns <sname>:hyperlink"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.hyperlink.value,
        )

    @staticmethod
    def link_type_key(sname: str) -> str:
        "returns <sname>:link_type"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.link_type.value,
        )

    @staticmethod
    def linked_cre_id_key(name: str) -> str:
        "returns Linked_CRE_<name>:id"
        return "%s%s%s%s" % (
            ExportFormat.cre_link.value,
            name,
            ExportFormat.separator.value,
            ExportFormat.id.value,
        )

    @staticmethod
    def linked_cre_name_key(name: str) -> str:
        "returns Linked_CRE_<name>:name"
        return "%s%s%s%s" % (
            ExportFormat.cre_link.value,
            name,
            ExportFormat.separator.value,
            ExportFormat.name.value,
        )

    @staticmethod
    def linked_cre_link_type_key(name: str) -> str:
        "returns Linked_CRE_<name>:link_type"
        return "%s%s%s%s" % (
            ExportFormat.cre_link.value,
            name,
            ExportFormat.separator.value,
            ExportFormat.link_type.value,
        )

    @staticmethod
    def cre_id_key() -> str:
        "returns CRE:id"
        return "%s%s%s" % (
            ExportFormat.cre.value,
            ExportFormat.separator.value,
            ExportFormat.id.value,
        )

    @staticmethod
    def cre_name_key() -> str:
        "returns CRE:name"
        return "%s%s%s" % (
            ExportFormat.cre.value,
            ExportFormat.separator.value,
            ExportFormat.name.value,
        )

    @staticmethod
    def cre_description_key() -> str:
        "returns CRE:description"
        return "%s%s%s" % (
            ExportFormat.cre.value,
            ExportFormat.separator.value,
            ExportFormat.description.value,
        )


class Credoctypes(str, Enum):
    CRE = "CRE"
    Standard = "Standard"
    Tool = "Tool"
    Code = "Code"


class LinkTypes(str, Enum):
    Same = "SAME"
    LinkedTo = "Linked To"  # Any standard entry is by default “linked”
    PartOf = "Is Part Of"  # Hierarchy above: “is part of”
    Contains = "Contains"  # Hierarchy below: “Contains”
    Related = "Related"  # Hierarchy across (other CRE topic or Tag): “related”

    RemediatedBy = "Remediated by"
    Remediates = "Remediates"

    TestedBy = "TestedBy"
    Tests = "Tests"

    @staticmethod
    def from_str(name: str) -> Any:  # it returns LinkTypes but then it won't run
        if name.upper().startswith("SAM"):
            name = "SAME"
        res = [x for x in LinkTypes if x.value == name]
        if not res:
            raise KeyError(f"{name} is not a valid linktype, supported linktypes are {[t for t in LinkTypes]}")
        return res[0]

class ToolTypes(str, Enum):
        Offensive = "Offensive"
        Defensive = "Defensive"
        Unknown = "Unknown"

@dataclass(eq=False)
class Link:
    document: "Document"
    ltype: LinkTypes = LinkTypes.Same
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

        if type(self.ltype) == str:
            self.ltype = LinkTypes.from_str(self.ltype)


    def __hash__(self) -> int:
        return hash(json.dumps(self.todict()))

    def __repr__(self) -> str:
        return json.dumps(self.todict())

    def __eq__(self, other: object) -> bool:
    
        return (
            type(other) is Link
            and self.ltype.value == other.ltype.value
            and self.tags == other.tags
            and self.document.__eq__(other.document)
        )

    def todict(self) -> Dict[str, Union[List[str], str, Dict[Any, Any]]]:
        res: Dict[str, Union[List[str], str, Dict[Any, Any]]] = {}
        if self.document:
            res["document"] = self.document.todict()
        if self.tags and len(self.tags):
            res["tags"] = self.tags

        res["type"] = self.ltype.value
        return res


@dataclass
class Document:
    name: str
    doctype: Credoctypes 
    id: Optional[str] = ""
    description: Optional[str] = ""
    links: List[Link] = field(default_factory=list)
    tags:  List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, type(self))
            and self.id == other.id
            and self.name == other.name
            and self.doctype.value == other.doctype.value
            and self.description == other.description
            and len(self.links) == len(other.links)
            and all(
                [
                    a in other.links and b in self.links
                    for a in self.links
                    for b in other.links
                ]
            )
            and self.tags==other.tags
            and self.metadata == other.metadata
        )

    def __hash__(self) -> int:
        return hash(json.dumps(self.todict()))

    def shallow_copy(self) -> Any:
        """Returns a copy of itself minus the Links,
        useful when creating links between cres"""
        res = copy(self)
        res.links = []
        return res

    def todict(self) -> Dict[str, Union[Dict[str, str], List[Any], Set[str], str]]:
        res = asdict(
            self,
            dict_factory=lambda x: {
                k: v if type(v) == list or type(v) == set or type(v) == dict else str(v)
                for (k, v) in x
                if v not in ["", {}, [], None, set()]
            },
        )
        res["doctype"] = "" + self.doctype.value
        if "tags" in res:
            res["tags"] = list(self.tags)
        return res
    
    def __repr__(self):
        return f"{self.todict()}"

    def add_link(self, link: Link) -> "Document":
        if not self.links:
            self.links = []
        if not isinstance(link,Link):
            raise ValueError("add_link only takes Link() types")

        self.links.append(link)
        return self



@dataclass(eq=False)
class CRE(Document):
    doctype: Credoctypes = Credoctypes.CRE

@dataclass
class Node(Document):
    hyperlink: Optional[str] = ""

    def __eq__(self, other: object) -> bool:
        return (
                isinstance(other, type(self))
                and super().__eq__(other)
                and self.hyperlink == other.hyperlink
            )


@dataclass
class Standard(Node):
    section: str = ""
    doctype: Credoctypes = Credoctypes.Standard
    subsection: Optional[str] = ""
    version: Optional[str] = ""

    def todict(self) -> Dict[Any, Any]:
        res = asdict(
            self,
            dict_factory=lambda x: {
                k: v if type(v) == list or type(v) == set or type(v) == dict else str(v) if not type(v)==Credoctypes else str(v.value)
                for (k, v) in x
                if v not in ["", {}, [], None, set()]
            },
        )
        return res
    def __hash__(self) -> int:
        return hash(json.dumps(self.todict()))


    def __eq__(self, other: object) -> bool:
        return (
                type(other) is Standard
                and super().__eq__(other)
                and self.section == other.section
                and self.subsection == other.subsection
                and self.version == other.version
            )


@dataclass
class Tool(Node):
    toolType: ToolTypes = ToolTypes.Unknown
    doctype:Credoctypes = Credoctypes.Tool
  
    def __eq__(self, other: object) -> bool:
        return (
                type(other) is Tool
                and super().__eq__(other)
                and self.toolType == other.toolType
            )
   
    def todict(self) -> Dict[Any, Any]: # TODO: BUG This needs to also serialise toolType to str properly, same for Code ( very likely we need a ToolBase class)
        res = asdict(
            self,
            dict_factory=lambda x: {
                k: v if type(v) == list or type(v) == set or type(v) == dict else str(v) if not type(v)==Credoctypes else str(v.value)
                for (k, v) in x
                if v not in ["", {}, [], None, set()]
            },
        )
        return res

@dataclass(eq=False)
class Code(Node):
    doctype:Credoctypes = Credoctypes.Code