from python_markdown_maker import Table, links
from application.defs import cre_defs as defs
from typing import List


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


def make_node_entry(doc: defs.Node) -> str:
    if doc.doctype == defs.Credoctypes.Standard:
        return f"{doc.name} {doc.section}"
    elif doc.doctype == defs.Credoctypes.Tool:
        return f"{doc.name}-{doc.sectionID}"
    elif doc.doctype == defs.Credoctypes.CRE:
        return f"{doc.name}-{doc.id}"
    else:
        return f"{doc.name}"


def add_entry(doc: defs.Document, header: List[str], item: List[str]) -> List[str]:
    if doc.doctype == defs.Credoctypes.CRE:
        item[header.index("CRE")].append(
            links(f"https://www.opencre.org/cre/{doc.id}", f"{doc.id} {doc.name}")
        )
    else:
        item[header.index(doc.name)].append(links(doc.hyperlink, make_node_entry(doc)))
    return item


def cre_to_md(documents: List[defs.Document]) -> str:
    header = make_header(documents)
    result = Table(header)
    entries = {}
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
        entries[make_node_entry(doc)] = {}
        for (
            link
        ) in (
            doc.links
        ):  # since doc is probably a standard, it's links should only be CRE, this loop builds the Standard to multiple CREs mapping
            item = add_entry(doc=link.document, header=header, item=item)
        entries[make_node_entry(doc)]["item"] = item

    entry_keys_sorted = list(entries.keys())
    entry_keys_sorted.sort()
    sorted_entries = [entries[itm] for itm in entry_keys_sorted]

    for e in sorted_entries:
        result.add_item([",".join(it) for it in e["item"]])

    return result.render()
