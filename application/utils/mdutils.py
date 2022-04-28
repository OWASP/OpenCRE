from python_markdown_maker import Table, links
from requests import head
from application.defs import cre_defs as defs
from typing import List
from pprint import pprint


def make_header(documents: List[defs.Document]) -> List[str]:
    header = []
    for doc in documents:
        name = ""
        if doc.doctype == defs.Credoctypes.CRE:
            name = "CRE"
        else:
            name = doc.name
        if name not in header:
            header.append(name)
        for link in doc.links:
            lnkdoc = link.document
            if lnkdoc.doctype == defs.Credoctypes.CRE:
                name = "CRE"
            else:
                name = lnkdoc.name
            if name not in header:
                header.append(name)
    return header


def add_entry(doc: defs.Document, header: List[str], item: List[str]) -> List[str]:
    if doc.doctype == defs.Credoctypes.CRE:
        item[header.index("CRE")].append(
            links(f"https://www.opencre.org/cre/{doc.id}", f"{doc.id} {doc.name}")
        )
    elif doc.doctype == defs.Credoctypes.Standard:
        (item[header.index(doc.name)]).append(
            links(doc.hyperlink, f"{doc.name} {doc.section}")
        )
    elif doc.doctype == defs.Credoctypes.Tool:
        item[header.index(doc.name)].append(links(doc.hyperlink, f"{doc.name}"))
    elif doc.doctype == defs.Credoctypes.Code:
        item[header.index(doc.name)].append(links(doc.hyperlink, f"{doc.name}"))
    return item


def cre_to_md(documents: List[defs.Document]) -> str:
    header = make_header(documents)
    result = Table(header)

    for doc in documents:
        name = ""
        if doc.doctype == defs.Credoctypes.CRE:
            name = "CRE"
        else:
            name = doc.name
        if name not in header:
            header.append(doc.name)

        item = [[] for x in range(0, len(header))]
        item = add_entry(doc=doc, header=header, item=item)
        for link in doc.links:
            item = add_entry(doc=link.document, header=header, item=item)
        result.add_item([", ".join(it) for it in item])

    return result.render()
