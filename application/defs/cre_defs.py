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
            raise KeyError(f'"{name}" is not a valid Link Type')
        return res[0]


@dataclass
class Link:
    ltype: LinkTypes
    tags: Set[str]
    document: "Document"

    def __init__(
        self,
        document: "Document",
        ltype: Union[str, LinkTypes] = LinkTypes.Same,
        tags: Set[str] = set(),
    ) -> None:
        if document is None:
            raise_MandatoryFieldException("Links need to link to a Document")
        self.document = document

        if type(ltype) == str:
            self.ltype = LinkTypes.from_str(ltype) or LinkTypes.Same
        else:
            self.ltype = ltype or LinkTypes.Same  # type: ignore
            # "ltype will always be either str or LinkTypes"

        self.tags = tags if isinstance(tags, set) else set(tags) if tags else set()

    def __hash__(self) -> int:
        return hash(json.dumps(self.todict()))

    def __str__(self) -> str:
        return json.dumps(self.todict())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Link):
            return False
        else:
            return (
                self.ltype.value == other.ltype.value
                and all(
                    [
                        a in other.tags and b in self.tags
                        for a in self.tags
                        for b in other.tags
                    ]
                )
                and self.document.__eq__(other.document)
            )

    def todict(self) -> Dict[str, Union[Set[str], str, Dict[Any, Any]]]:
        res: Dict[str, Union[Set[str], str, Dict[Any, Any]]] = {}
        if self.document:
            res["document"] = self.document.todict()
        if len(self.tags):
            res["tags"] = self.tags

        res["type"] = self.ltype.value
        return res


@dataclass
class Document:
    name: str
    doctype: Credoctypes
    id: Optional[str] = None
    description: Optional[str] = None
    links: List[Link] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    metadata: Optional[Metadata] = field(default_factory=Metadata)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return False
        else:
            return (
                self.id == other.id
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
                and all(
                    [
                        a in other.tags and b in self.tags
                        for a in self.tags
                        for b in other.tags
                    ]
                )
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

    def add_link(self, link: Link) -> Any:  # it returns Document but then it won't run
        if not self.links:
            self.links = []
        if type(link).__name__ != Link.__name__:
            raise ValueError("add_link only takes Link() types")

        self.links.append(link)
        return self

    def __init__(
        self,
        name: str,
        doctype: Optional[Credoctypes] = None,
        id: str = "",
        description: str = "",
        links: List[Link] = [],
        tags: List[str] = [],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = str(description)
        if not name:
            raise_MandatoryFieldException(
                "Document name not defined for document of doctype %s" % doctype
            )
        else:
            self.name = str(name)
        self.links = links or []
        if isinstance(tags, set) and "" in tags:
            tags.remove("")

        self.tags = tags if isinstance(tags, set) else set(tags)
        self.id = id
        self.metadata = metadata

        if not doctype and not self.doctype:
            raise_MandatoryFieldException("You need to set doctype")

        if not self.doctype:
            if isinstance(doctype, str):
                t = [dt for dt in Credoctypes if dt.value == doctype]
                if not t:
                    raise ValueError(f"Unsupported document type {doctype}")
                self.doctype = t[0]
            elif isinstance(doctype, Credoctypes):
                self.doctype = doctype
            else:
                raise ValueError(
                    f"doctype is of unsupported type {type(doctype)} this is most likely a bug"
                )


@dataclass
class CRE(Document):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.doctype = Credoctypes.CRE
        super().__init__(*args, **kwargs)

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CRE):
            return False
        else:
            return super().__eq__(other)


@dataclass
class Node(Document):
    hyperlink: Optional[str] = ""


@dataclass
class Standard(Node):
    section: str = ""
    doctype: Credoctypes = Credoctypes.Standard
    subsection: Optional[str] = ""
    version: Optional[str] = ""

    def todict(self) -> Dict[Any, Any]:
        result: Dict[Any, Any] = super().todict()

        result["section"] = self.section
        result["subsection"] = self.subsection
        result["hyperlink"] = self.hyperlink
        result["version"] = self.version
        return result
    def __hash__(self) -> int:
        return hash(json.dumps(self.todict()))


    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Standard):
            return False
        else:
            return (
                self.section == other.section
                and self.subsection == other.subsection
                and self.hyperlink == other.hyperlink
                and self.version == other.version
                and super().__eq__(other)
            )


@dataclass
class Tool(Node):
    class ToolTypes(Enum):
        Offensive = "Offensive"
        Defensive = "Defensive"
        Code = "Code"
        Unknown = "Unknown"

    doctype = Credoctypes.Tool
    toolType: ToolTypes = ToolTypes.Unknown

    def __init__(
        self, toolType: ToolTypes = ToolTypes.Unknown, *args: Any, **kwargs: Any
    ) -> None:
        self.doctype = Credoctypes.Tool
        self.toolType = toolType
        super().__init__(*args, **kwargs)


@dataclass
class Code(Tool):
    pass


class MandatoryFieldException(Exception):
    pass


def raise_MandatoryFieldException(msg: str = "") -> None:
    raise MandatoryFieldException(msg)
