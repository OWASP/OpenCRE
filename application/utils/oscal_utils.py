import random
from trestle.oscal import catalog
from trestle.oscal import common
from datetime import datetime
from application.defs import cre_defs as defs
from uuid import uuid4
from typing import List, Optional, Union


def document_to_oscal(
    document: defs.Document, uuid: Optional[str], last_modified: Optional[str]
) -> str:
    """
    document_to_oscal takes a single document
    which describes a High Level topic and adds controls for each of its links
    """
    hyperlink = ""
    version = "0.0"
    if (
        document.doctype == defs.Credoctypes.Standard
        or document.doctype == defs.Credoctypes.Tool
    ):
        hyperlink = document.hyperlink
        if document.version:
            version = document.version

    else:
        hyperlink = f"https://opencre.org/cre/{document.id}"

    if not last_modified:
        last_modified = datetime.utcnow()
    m = None
    if document.description:
        m = common.Metadata(
            title=document.name,
            last_modified=last_modified,
            oscal_version="1.0.0",
            version=version,
            links=[common.Link(href=hyperlink)],
            remarks=document.description,
        )
    else:
        m = common.Metadata(
            title=document.name,
            last_modified=last_modified,
            oscal_version="1.0.0",
            version=version,
            links=[common.Link(href=hyperlink)],
        )
    if uuid == None or uuid == "":
        uuid = str(uuid4())
    c = catalog.Catalog(metadata=m, uuid=uuid)
    controls: List[catalog.Control] = []

    for link in document.links:
        ctrl = None
        if link.document.doctype == defs.Credoctypes.CRE:
            ctrl = catalog.Control(
                id=f"_{link.document.id}",
                title=link.document.name,
                links=[common.Link(href=f"https://opencre.org/cre/{link.document.id}")],
            )
        elif link.document.doctype == defs.Credoctypes.Standard:
            ctrl = catalog.Control(
                id=f"_{link.document.section}",
                title=link.document.name,
                links=[common.Link(href=link.document.hyperlink)],
            )
        elif link.document.doctype == defs.Credoctypes.Tool:
            ctrl = catalog.Control(
                id=f"_{link.document.sectionID}",
                title=link.document.name,
                links=[common.Link(href=link.document.hyperlink)],
            )
        controls.append(ctrl)
    c.controls = controls
    return c.json()


def list_to_oscal(documents: List[defs.Standard | defs.Tool]) -> str:
    """
    list_to_oscal takes a list of standards or tooling rules
    (they all need to be the same type and the same name)
    and creates a set of controls from them
    """
    version = "0.0"

    m = common.Metadata(
        title=documents[0].name,
        last_modified=datetime.now().astimezone(),
        oscal_version="1.0.0",
        version=version,
    )
    c = catalog.Catalog(metadata=m, uuid=str(uuid4()))
    controls: List[catalog.Control] = []

    if documents[0].doctype == defs.Credoctypes.Standard:
        for doc in documents:
            controls.append(
                catalog.Control(
                    id=f"_{random.getrandbits(1024)}",
                    title=doc.name,
                    props=[common.Property(name="section", value=doc.section)],
                    links=[common.Link(href=doc.hyperlink)],
                )
            )
    elif documents[0].doctype == defs.Credoctypes.Tool:
        for doc in documents:
            from pprint import pprint

            controls.append(
                catalog.Control(
                    id=f"_{random.getrandbits(1024)}",
                    props=[common.Property(name="sectionID", value=doc.sectionID)],
                    title=doc.name,
                    links=[common.Link(href=doc.hyperlink)],
                )
            )
    c.controls = controls
    return c.json()
