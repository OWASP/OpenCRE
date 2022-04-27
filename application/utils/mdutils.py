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
            header.append(doc.name)
        for link in doc.links:
            lnkdoc = link.document
            if lnkdoc.doctype == defs.Credoctypes.CRE:
                name = "CRE"
            else:
                name = lnkdoc.name
            if name not in header:
                header.append(name)
    return header


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

        item = [" "] * len(header)
        item[header.index(doc.name)] = links(doc.hyperlink, f"{doc.name}-{doc.section}")
        for link in doc.links:
            lnkdoc = link.document
            if lnkdoc.doctype == defs.Credoctypes.CRE:
                item[header.index("CRE")] = links(
                    f"https://www.opencre.org/cre/{lnkdoc.id}",
                    f"{lnkdoc.id} {lnkdoc.name}",
                )
            elif lnkdoc.doctype == defs.Credoctypes.Standard:
                item[header.index(lnkdoc.name)] = links(
                    lnkdoc.hyperlink, f"{lnkdoc.name}-{lnkdoc.section}"
                )
            elif lnkdoc.doctype == defs.Credoctypes.Tool:
                item[header.index(lnkdoc.name)] = links(
                    lnkdoc.hyperlink, f"{lnkdoc.name}"
                )
            elif lnkdoc.doctype == defs.Credoctypes.Code:
                item[header.index(lnkdoc.name)] = links(
                    lnkdoc.hyperlink, f"{lnkdoc.name}"
                )
        result.add_item(item)
    return result.render()
