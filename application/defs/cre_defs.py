import re
import json
from copy import copy
from dataclasses import asdict, dataclass, field
from enum import Enum, EnumMeta
from typing import Any, Dict, List, Optional, Set, Union
from application.defs import cre_exceptions


class ExportFormat(
    Enum
):  # TODO: this can likely be replaced with a method that iterates over an object's vars and formats headers to
    #  <doctype>:<name>:<varname>
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
    tooltype = "ToolType"
    sectionID = "SectionID"

    @staticmethod
    def get_doctype(header: str) -> Optional["Credoctypes"]:
        """Given a header of type
        <doctype>:<name>:<>
        return the doctype
        """
        typ = [t for t in Credoctypes if t in header]
        if not typ:
            return None
        else:
            return typ[0]

    @staticmethod
    def node_name_key(sname: str) -> str:
        """returns :<sname>: used mostly for matching"""
        return "%s%s%s" % (
            ExportFormat.separator.value,
            sname,
            ExportFormat.separator.value,
        )

    @staticmethod
    def tooltype_key(sname: str, doctype: "Credoctypes") -> str:
        "returns <doctype>:<name>:tooltype"
        return "%s%s%s%s%s" % (
            doctype.value,
            ExportFormat.separator.value,
            sname,
            ExportFormat.separator.value,
            ExportFormat.tooltype.value,
        )

    @staticmethod
    def sectionID_key(sname: str, doctype: "Credoctypes") -> str:
        "returns <doctype>:<name>:sectionID"
        return "%s%s%s%s%s" % (
            doctype.value,
            ExportFormat.separator.value,
            sname,
            ExportFormat.separator.value,
            ExportFormat.sectionID.value,
        )

    @staticmethod
    def description_key(sname: str, doctype: "Credoctypes") -> str:
        "returns <doctype>:<name>:description"
        return "%s%s%s%s%s" % (
            doctype.value,
            ExportFormat.separator.value,
            sname,
            ExportFormat.separator.value,
            ExportFormat.description.value,
        )

    @staticmethod
    def section_key(sname: str, doctype: "Credoctypes") -> str:
        "returns <doctype>:<name>:section"
        return "%s%s%s%s%s" % (
            doctype.value,
            ExportFormat.separator.value,
            sname,
            ExportFormat.separator.value,
            ExportFormat.section.value,
        )

    @staticmethod
    def subsection_key(sname: str, doctype: "Credoctypes") -> str:
        "returns <doctype>:<sname>:subsection"
        return "%s%s%s%s%s" % (
            doctype.value,
            ExportFormat.separator.value,
            sname,
            ExportFormat.separator.value,
            ExportFormat.subsection.value,
        )

    @staticmethod
    def hyperlink_key(sname: str, doctype: "Credoctypes") -> str:
        "returns <sname>:hyperlink"
        return "%s%s%s%s%s" % (
            doctype.value,
            ExportFormat.separator.value,
            sname,
            ExportFormat.separator.value,
            ExportFormat.hyperlink.value,
        )

    @staticmethod
    def link_type_key(sname: str, doctype: "Credoctypes") -> str:
        "returns <sname>:link_type"
        return "%s%s%s%s%s" % (
            doctype.value,
            ExportFormat.separator.value,
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


class EnumMetaWithContains(EnumMeta):
    def __contains__(cls: Enum, item: Any) -> bool:
        return item in [v.value for v in cls.__members__.values()]


class Credoctypes(str, Enum, metaclass=EnumMetaWithContains):
    CRE = "CRE"
    Standard = "Standard"
    Tool = "Tool"
    Code = "Code"

    @staticmethod
    def from_str(typ: str) -> "Credoctypes":
        typ = [t for t in Credoctypes if t in typ]
        if not typ:
            return None
        else:
            return typ[0]


class LinkTypes(str, Enum, metaclass=EnumMetaWithContains):
    Same = "SAME"
    LinkedTo = "Linked To"  # Any standard entry is by default “linked”
    PartOf = "Is Part Of"  # Hierarchy above: “is part of”
    Contains = "Contains"  # Hierarchy below: “Contains”
    Related = "Related"  # Hierarchy across (other CRE topic or Tag): “related”

    AutomaticallyLinkedTo = "Automatically linked to"
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
            raise KeyError(
                f"{name} is not a valid linktype, supported linktypes are {[t for t in LinkTypes]}"
            )
        return res[0]

    @classmethod
    def opposite(cls, typ) -> Any:  # it returns the opposite of the type provided
        if typ == cls.Contains:
            return cls.PartOf
        elif typ == cls.PartOf:
            return cls.Contains
        elif typ == cls.LinkedTo:
            return typ
        elif typ == cls.Related:
            return typ
        elif typ == cls.RemediatedBy:
            return cls.Remediates
        elif typ == cls.Remediates:
            return cls.RemediatedBy
        elif typ == cls.TestedBy:
            return cls.Tests
        elif typ == cls.Tests:
            return cls.TestedBy


class ToolTypes(str, Enum, metaclass=EnumMetaWithContains):
    Offensive = "Offensive"
    Defensive = "Defensive"
    Training = "Training"
    Unknown = "Unknown"

    @staticmethod
    def from_str(tooltype: str) -> Optional["ToolTypes"]:
        if tooltype:
            ttype = [t for t in ToolTypes if t.value.lower() == tooltype.lower()]
            if ttype:
                return ttype[0]
        return None


@dataclass
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
        else:
            raise ValueError(
                f"Found Link not containing a document, this is a bug, for debugging, the tags for this Link are {self.tags}"
            )
        self.tags = [x for x in self.tags if x != ""]
        if self.tags and len(self.tags):
            res["tags"] = self.tags

        res["ltype"] = "" + self.ltype.value
        return res


@dataclass(init=True, repr=True, eq=True, order=True)
class Document:
    name: str
    doctype: Credoctypes
    description: Optional[str] = ""
    links: List[Link] = field(default_factory=list)
    embeddings: List[float] = field(default_factory=list)
    embeddings_text: str = ""
    tags: List[str] = field(default_factory=list)
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
            and all(
                [
                    a in other.tags and b in self.tags
                    for a in self.tags
                    for b in other.tags
                ]
            )
            and self.metadata == other.metadata
            and all(
                [
                    a in other.embeddings and b in self.embeddings
                    for a in self.embeddings
                    for b in other.embeddings
                ]
            )
            and self.embeddings_text == other.embeddings_text
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
        res["doctype"] = self.doctype.value + ""
        if "links" in res:
            res["links"] = [l.todict() for l in self.links]
        if "tags" in res:
            res["tags"] = list(self.tags)
        return res

    def __repr__(self):
        return f"{self.todict()}"

    def add_link(self, link: Link) -> "Document":
        if not self.links:
            self.links = []
        if not isinstance(link, Link):
            raise ValueError("add_link only takes Link() types")

        self.links.append(link)
        return self

    def __post_init__(self):
        if not len(self.name) > 1:
            raise cre_exceptions.InvalidDocumentNameException(self)

    @classmethod
    def from_dict(self, input_doc: Dict):
        document = None
        if input_doc.get("doctype") == Credoctypes.CRE:
            document = CRE(**input_doc)
            document.doctype = Credoctypes.CRE
        elif input_doc.get("doctype") == Credoctypes.Standard:
            document = Standard(**input_doc)
            document.doctype = Credoctypes.Standard

        elif input_doc.get("doctype") == Credoctypes.Tool:
            document = Tool(**input_doc)
            document.doctype = Credoctypes.Tool
            document.tooltype = ToolTypes.from_str(document.tooltype)
        links = document.links
        document.links = []
        for link in links:
            doc = Document.from_dict(link["document"])
            l = Link(document=doc, ltype=LinkTypes.from_str(link["ltype"]))
            document.add_link(l)
        return document


@dataclass(eq=False)
class CRE(Document):
    doctype: Credoctypes = Credoctypes.CRE
    id: Optional[str] = ""

    def todict(self) -> Dict[str, Dict[str, str] | List[Any] | Set[str] | str]:
        return super().todict()

    def __post_init__(self):
        if not re.match(r"\d\d\d-\d\d\d", self.id):
            raise cre_exceptions.InvalidCREIDException(self)


@dataclass
class Node(Document):
    id: Optional[str] = ""
    hyperlink: Optional[str] = ""
    version: Optional[str] = ""

    def todict(self):
        res = super().todict()
        if self.hyperlink:
            res["hyperlink"] = self.hyperlink
        return res

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, type(self))
            and super().__eq__(other)
            and self.hyperlink == other.hyperlink
        )


@dataclass
class Standard(Node):
    section: str = ""
    sectionID: str = ""
    doctype: Credoctypes = Credoctypes.Standard
    subsection: Optional[str] = ""

    def __post_init__(self):
        self.id = f"{self.name}"
        if self.sectionID:
            self.id += f":{self.sectionID}"
        if self.section:
            self.id += f":{self.section}"
        if self.subsection:
            self.id += f":{self.subsection}"
        return super().__post_init__()

    def todict(self) -> Dict[Any, Any]:
        res = super().todict()
        res["section"] = self.section
        if self.subsection:
            res["subsection"] = self.subsection
        if self.version:
            res["version"] = self.version
        if self.sectionID:
            res["sectionID"] = self.sectionID
        return res

    def __hash__(self) -> int:
        return hash(json.dumps(self.todict()))

    def __eq__(self, other: object) -> bool:
        return (
            super().__eq__(other)
            and self.section == other.section
            and self.subsection == other.subsection
            and self.version == other.version
            and self.sectionID == other.sectionID
        )


@dataclass
class Tool(Standard):
    tooltype: ToolTypes = ToolTypes.Unknown
    doctype: Credoctypes = Credoctypes.Tool

    def __post_init__(self):
        self.id = f"{self.name}"
        if self.sectionID:
            self.id += f":{self.sectionID}"
        if self.section:
            self.id += f":{self.section}"
        if self.subsection:
            self.id += f":{self.subsection}"
        return super().__post_init__()

    def __eq__(self, other: object) -> bool:
        return super().__eq__(other) and self.tooltype == other.tooltype

    def todict(self) -> Dict[str, Any]:
        res = super().todict()
        res["tooltype"] = self.tooltype.value + ""
        return res

    def __hash__(self) -> int:
        return hash(json.dumps(self.todict()))


@dataclass(eq=False)
class Code(Node):
    doctype: Credoctypes = Credoctypes.Code
