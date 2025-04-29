from __future__ import annotations
from requests import Response


class Link:
    """
    Represents a link associated with a CRE.

    Attributes:
    - raw (dict): The raw data of the link.
    - ltype (str): The type of the link.

    Methods:
    - parse_from_cre(cls, cre: CRE) -> list[Link]: Parses links from a CRE object.
    - get_document_class(self): Determines the document class associated with the link's doctype.
    - document(self): Retrieves the associated document instance.
    """
    def __init__(self, raw, ltype):
        self.raw = raw
        self.ltype = ltype

    @classmethod
    def parse_from_cre(cls, cre: CRE) -> list[Link]:
        """
        Parses links from a CRE object.

        Parameters:
        - cre (CRE): The CRE object.

        Returns:
        list[Link]: A list of Link objects parsed from the CRE.
        """
        links_raw = cre.raw.get("links")
        links = [cls(raw=link_raw, ltype=link_raw["ltype"]) for link_raw in links_raw]
        return links

    def get_document_class(self):
        """
        Determines the document class associated with the link's doctype.

        Returns:
        document_class: The class of the associated document.
        """
        document_parent = Document.parse_from_link(link=self)
        doctype = document_parent.doctype
        document_class = None

        if doctype == "Standard":
            document_class = Standard

        if doctype == "CRE":
            document_class = CRELink

        if doctype == "Tool":
            document_class = Tool

        if document_class is None:
            raise NotImplementedError("Not implemented for this doctype")

        return document_class

    @property
    def document(self):
        """
        Retrieves the associated document instance.

        Returns:
        Document: The associated document instance.
        """
        document_class = self.get_document_class()
        document = document_class.parse_from_link(self)
        return document


class CRE:
    """
    Represents a CRE (Common Requirements Enumeration).

    Attributes:
    - raw (dict): The raw data of the CRE.
    - id (str): The identifier of the CRE.
    - name (str): The name of the CRE.
    - doctype (str): The type of the CRE.

    Methods:
    - links(self): Retrieves links associated with the CRE.
    - parse_from_response(cls, response: Response, many: bool = False) -> CRE | list[CRE]: Parses CRE(s) from a response object.
    - __str__(self): Returns a string representation of the CRE.
    """
    def __init__(self, raw, cre_id, name, doctype):
        self.raw = raw
        self.id = cre_id
        self.name = name
        self.doctype = doctype

    @property
    def links(self):
        """
        Retrieves links associated with the CRE.

        Returns:
        list[Link]: A list of Link objects associated with the CRE.
        """
        return Link.parse_from_cre(cre=self)

    @classmethod
    def parse_from_response(cls, response: Response, many: bool = False) -> CRE | list[CRE]:
        """
        Parses CRE(s) from a response object.

        Parameters:
        - response (Response): The response object.
        - many (bool): True if expecting multiple CREs in the response, False otherwise.

        Returns:
        CRE | list[CRE]: A single CRE or a list of CREs parsed from the response.
        """
        cres = []
        data = response.json().get("data")

        if not many:
            data = [data]

        for raw_cre in data:
            cre = cls(
                raw=raw_cre,
                cre_id=raw_cre["id"],
                name=raw_cre["name"],
                doctype=raw_cre["doctype"]
            )
            cres.append(cre)

        if not many:
            return cres[0]

        return cres

    def __str__(self):
        return f'CRE {self.id}'


class Document:
    """
    Represents a document associated with a CRE.

    Attributes:
    - raw (dict): The raw data of the document.
    - doctype (str): The type of the document.
    - name (str): The name of the document.

    Methods:
    - parse_from_link(cls, link: Link) -> Document: Parses a document from a Link object.
    """
    def __init__(self, raw, doctype, name):
        self.raw = raw
        self.doctype = doctype
        self.name = name

    @classmethod
    def parse_from_link(cls, link: Link) -> Document:
        """
        Parses a document from a Link object.

        Parameters:
        - link (Link): The Link object.

        Returns:
        Document: The Document object associated with the Link.
        """
        document_raw = link.raw.get("document")
        document = cls(
            raw=document_raw,
            doctype=document_raw["doctype"],
            name=document_raw["name"]
        )
        return document


class Standard(Document):
    ...


class Tool(Document):
    ...


class CRELink(Document):
    """
    Represents a link to another CRE document associated with a CRE.

    Attributes:
    - id: The identifier of the linked CRE.
    """
    @property
    def id(self):
        return self.raw.get("id")
