from typing import Dict, List, Any
from application.utils import import_diff


def change_set_to_graph(changeset: List[import_diff.ChangeSetOp]) -> Dict[str, Any]:
    nodes = {}
    edges = []

    for op in changeset:
        op_type = (
            "added"
            if isinstance(op, import_diff.AddControl)
            else "deleted" if isinstance(op, import_diff.RemoveControl) else "updated"
        )

        doc = getattr(op, "document", getattr(op, "after", {}))

        name = doc.get("name", "")
        section = doc.get("section", "")
        section_id = doc.get("sectionID", "")

        # fallback to op.key if doc lacks info
        if not name and not section and not section_id and hasattr(op, "key"):
            name, section, section_id = op.key

        std_id = f"STD:{name}:{section}:{section_id}"

        nodes[std_id] = {
            "id": std_id,
            "label": f"{name} {section} {section_id}".strip(),
            "type": "Standard",
            "status": op_type,
        }

        # Check linked_cres
        for cre in doc.get("linked_cres", []):
            cre_id = f"CRE:{cre.get('id')}"
            if cre_id not in nodes:
                nodes[cre_id] = {
                    "id": cre_id,
                    "label": cre.get("name", cre_id),
                    "type": "CRE",
                    "status": "unchanged",
                }

            edges.append(
                {
                    "source": std_id,
                    "target": cre_id,
                    "status": op_type,
                }
            )

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }
