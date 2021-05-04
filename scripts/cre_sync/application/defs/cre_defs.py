from pprint import pprint
from dataclasses import dataclass
from enum import Enum
import json

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
    def section_key(sname: str):
        "returns <sname>:section"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.section.value,
        )

    @staticmethod
    def subsection_key(sname: str):
        "returns <sname>:subsection"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.subsection.value,
        )

    @staticmethod
    def hyperlink_key(sname: str):
        "returns <sname>:hyperlink"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.hyperlink.value,
        )

    @staticmethod
    def link_type_key(sname: str):
        "returns <sname>:link_type"
        return "%s%s%s" % (
            sname,
            ExportFormat.separator.value,
            ExportFormat.link_type.value,
        )

    @staticmethod
    def linked_cre_id_key(name: str):
        "returns Linked_CRE_<name>:id"
        return "%s%s%s%s" % (
            ExportFormat.cre_link.value,
            name,
            ExportFormat.separator.value,
            ExportFormat.id.value,
        )

    @staticmethod
    def linked_cre_name_key(name: str):
        "returns Linked_CRE_<name>:name"
        return "%s%s%s%s" % (
            ExportFormat.cre_link.value,
            name,
            ExportFormat.separator.value,
            ExportFormat.name.value,
        )

    @staticmethod
    def linked_cre_link_type_key(name: str):
        "returns Linked_CRE_<name>:link_type"
        return "%s%s%s%s" % (
            ExportFormat.cre_link.value,
            name,
            ExportFormat.separator.value,
            ExportFormat.link_type.value,
        )

    @staticmethod
    def cre_id_key():
        "returns CRE:id"
        return "%s%s%s" % (
            ExportFormat.cre.value,
            ExportFormat.separator.value,
            ExportFormat.id.value,
        )

    @staticmethod
    def cre_name_key():
        "returns CRE:name"
        return "%s%s%s" % (
            ExportFormat.cre.value,
            ExportFormat.separator.value,
            ExportFormat.name.value,
        )

    @staticmethod
    def cre_description_key():
        "returns CRE:description"
        return "%s%s%s" % (
            ExportFormat.cre.value,
            ExportFormat.separator.value,
            ExportFormat.description.value,
        )


class Credoctypes(Enum):
    CRE = "CRE"
    Standard = "Standard"


class LinkTypes(Enum):
    Same = "SAM"

    @staticmethod
    def from_str(name):
        if name == "SAM":
            return LinkTypes.Same
        raise ValueError('"{}" is not a valid link type'.format(name))


@dataclass
class Metadata:
    labels: {}

    def __init__(self, labels={}):
        self.labels = labels

    def todict(self):
        return self.labels


@dataclass
class Link:
    ltype: LinkTypes
    tags: list
    document = None

    def __init__(self, ltype=LinkTypes.Same, tags=[], document=None):
        if document is None:
            raise_MandatoryFieldException("Links need to link to a Document")
        self.document = document
        if type(ltype) == str:
            self.ltype = LinkTypes.from_str(ltype)
        else:
            self.ltype = ltype
        self.tags = tags

    def __hash__(self):
        return hash(json.dumps(self.todict()))

    def __eq__(self, other):
        return (
            self.ltype == other.ltype
            and self.tags == other.tags
            and self.document == other.document
        )

    def todict(self):
        if isinstance(self.document,list):
            print('wtf?')
            pprint(self.document)
        res = {"type": self.ltype.value}
        if self.document:
            res["document"] = self.document.todict()
        if len(self.tags):
            res["tags"] = self.tags
        return res


@dataclass
class Document:
    doctype: Credoctypes
    id: str
    description: str
    name: str
    links: list
    tags: list
    metadata: Metadata

    def __eq__(self, other):
        return (
            self.id == other.id
            and self.name == other.name
            and self.doctype.value == other.doctype.value
            and self.description == other.description
            and self.links == other.links
            and self.tags == other.tags
            and self.metadata == other.metadata
        )

    def __hash__(self):
        return hash(json.dumps(self.todict()))

    def todict(self):
        result = {
            "doctype": self.doctype.value,
            "name": self.name,
        }
        if self.description:
            result["description"] = self.description
        if self.id:
            result["id"] = self.id
        if self.links:
            result["links"] = []
            for link in self.links:
                result["links"].append(link.todict())
        if self.tags:
            result["tags"] = self.tags
        if self.metadata:
            result["metadata"] = self.metadata.todict()
        return result

    def add_link(self, link: Link):
        if not self.links:
            self.links = []
        if type(link).__name__ != Link.__name__:
            raise ValueError("add_link only takes Link() types")

        self.links.append(link)

    def __init__(
        self,
        name,
        doctype=None,
        id="",
        description="",
        links=[],
        tags=[],
        metadata: Metadata = None,
    ):
        self.description = str(description)
        self.name = str(name) or raise_MandatoryFieldException(
            "Document name not defined for document of doctype %s" % doctype
        )
        self.links = links or []
        if isinstance(tags,list) and "" in tags:
            tags.remove("")
        self.tags = tags
        self.id = id
        self.metadata = metadata
        if not doctype and not self.doctype:
            raise_MandatoryFieldException("You need to set doctype")


@dataclass
class CRE(Document):
    def __init__(self, *args, **kwargs):
        self.doctype = Credoctypes.CRE
        super().__init__(*args, **kwargs)

    def __hash__(self):
        return super().__hash__()
    def __eq__(self, other):
        return (isinstance(other,CRE) and super().__eq__(other))

@dataclass
class Standard(Document):
    doctype = Credoctypes.Standard
    section: str
    subsection: str
    hyperlink: str

    def todict(self):
        result = super().todict()
        result["section"] = self.section
        result["subsection"] = self.subsection
        result["hyperlink"] = self.hyperlink
        return result

    def __hash__(self):
        return super().__hash__()

    def __eq__(self, other):
        return (
            isinstance(other,Standard)
            and super().__eq__(other)
            and self.section == other.section
            and self.subsection == other.subsection
            and self.hyperlink == other.hyperlink
        )

    def __init__(self, section=None, subsection=None, hyperlink=None, *args, **kwargs):
        self.doctype = Credoctypes.Standard
        if section is None or section == "":
            raise MandatoryFieldException(
                "%s:%s is an invalid standard entry,"
                "you can't register an entire standard at once, it needs to have sections"
                % (kwargs.get("name"), section)
            )
        self.section = section
        self.subsection = subsection
        self.hyperlink = hyperlink
        super().__init__(*args, **kwargs)


class MandatoryFieldException(Exception):
    pass


def raise_MandatoryFieldException(msg=""):
    raise MandatoryFieldException(msg)
