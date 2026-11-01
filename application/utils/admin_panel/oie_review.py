"""Human review of OIE decisions: approve / reject / repoint, and repoint filed links.

Read-write counterpart of the "OIE decisions" admin panel. Rows in
``decision_queue`` that the filer left alone (``review_required``, or ``linked``
below its confidence floor) are reviewed here; links the filer already wrote
(``Automatically linked to``) can be pointed at a different CRE.

Reviewer-set links use ``Linked To`` (a human decided), never
``Automatically linked to``. Every action appends a ``decision_review`` row
holding what was proposed and what the reviewer chose, so it can be explained
and reverted. Nodes are filed through the same ``graph_filer`` helpers.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from pydantic import ValidationError

from application import sqla
from application.database import db
from application.defs import cre_defs as defs
from application.utils.librarian.schemas import LinkProposal, ReviewItem
from application.utils.oie_scheduler import graph_filer

REVIEWED_TAG = graph_filer.REVIEWED_TAG
ACTIONS = ("approve", "reject", "repoint")
_TEXT_LIMIT = 1500
MAX_PAGE_SIZE = 200


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _find_cre(ref: str) -> Optional[Any]:
    """CRE by primary key (Librarian proposals) or external id (``123-456``)."""
    session = sqla.session
    return (
        session.query(db.CRE).filter(db.CRE.id == ref).first()
        or session.query(db.CRE).filter(db.CRE.external_id == ref).first()
    )


def _parse(row: Any) -> Optional[Any]:
    model = LinkProposal if row.status == "linked" else ReviewItem
    try:
        return model.model_validate(row.envelope)
    except ValidationError:
        return None


def _proposed(proposal: Any) -> List[Any]:
    if proposal is None:
        return []
    links = getattr(proposal, "links", None) or getattr(
        proposal, "suggested_links", None
    )
    return list(links or [])


def _review_dict(review: Any) -> Dict[str, Any]:
    return {
        "action": review.action,
        "reviewer": review.reviewer,
        "note": review.note,
        "payload": review.payload,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


def _latest_reviews(target_ids: Sequence[str]) -> Dict[str, Any]:
    if not target_ids:
        return {}
    rows = (
        sqla.session.query(db.DecisionReview)
        .filter(db.DecisionReview.target_id.in_(list(target_ids)))
        .order_by(db.DecisionReview.created_at, db.DecisionReview.id)
        .all()
    )
    return {r.target_id: r for r in rows}  # later rows win


def search_cres(query: str, *, limit: int = 15) -> List[Dict[str, Any]]:
    """Find CREs by id or name for the repoint picker (substring, case-insensitive)."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    limit = max(1, min(int(limit), 50))
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    rows = (
        sqla.session.query(db.CRE)
        .filter(
            sqla.or_(
                db.CRE.external_id.ilike(pattern, escape="\\"),
                db.CRE.name.ilike(pattern, escape="\\"),
            )
        )
        .all()
    )
    low = q.lower()

    def rank(cre: Any) -> tuple:
        ext = (cre.external_id or "").lower()
        name = (cre.name or "").lower()
        return (ext != low, not name.startswith(low), name)

    return [
        {
            "cre_id": cre.external_id,
            "name": cre.name,
            "description": (cre.description or "")[:160],
        }
        for cre in sorted(rows, key=rank)[:limit]
        if cre.external_id
    ]


def _page_args(page: int, page_size: int) -> tuple[int, int]:
    return max(1, int(page)), max(1, min(int(page_size), MAX_PAGE_SIZE))


def list_decisions(
    *,
    status: Optional[str] = None,
    run_id: Optional[str] = None,
    include_consumed: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    page, page_size = _page_args(page, page_size)
    q = sqla.session.query(db.DecisionQueueItem)
    if not include_consumed:
        q = q.filter(db.DecisionQueueItem.consumed_at.is_(None))
    if status:
        q = q.filter(db.DecisionQueueItem.status == status)
    if run_id:
        q = q.filter(db.DecisionQueueItem.pipeline_run_id == run_id)
    total = q.count()
    rows = (
        q.order_by(db.DecisionQueueItem.created_at, db.DecisionQueueItem.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    reviews = _latest_reviews([r.id for r in rows])
    items: List[Dict[str, Any]] = []
    for row in rows:
        proposal = _parse(row)
        item: Dict[str, Any] = {
            "id": row.id,
            "chunk_id": row.chunk_id,
            "status": row.status,
            "reason_code": row.reason_code,
            "confidence": row.confidence,
            "run_id": row.pipeline_run_id,
            "source_label": row.source_label,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "consumed": row.consumed_at is not None,
            "invalid": proposal is None,
            "text": "",
            "source": None,
            "candidates": [],
            "review": _review_dict(reviews[row.id]) if row.id in reviews else None,
        }
        if proposal is not None:
            knowledge = proposal.knowledge
            item["text"] = (knowledge.text or "")[:_TEXT_LIMIT]
            item["source"] = {
                "repo": knowledge.source.repo,
                "path": knowledge.locator.path,
                "title": knowledge.locator.title,
                "hyperlink": graph_filer._hyperlink(proposal),
                "standard_name": graph_filer.standard_name_for_source(proposal),
            }
            for link in _proposed(proposal):
                cre = _find_cre(link.cre_id)
                item["candidates"].append(
                    {
                        "cre_id": cre.external_id if cre else link.cre_id,
                        "cre_name": cre.name if cre else None,
                        "confidence": link.confidence,
                        "rationale": link.rationale,
                    }
                )
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def review_decision(
    decision_id: str,
    action: str,
    *,
    reviewer: Optional[str],
    cre_ids: Optional[Sequence[str]] = None,
    note: Optional[str] = None,
    standard_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Approve / reject / repoint one unconsumed ``decision_queue`` row.

    ``standard_name`` overrides the standard the section is filed under; it is
    required in practice for sources that have no repo and no usable host.
    """
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    session = sqla.session
    row = session.get(db.DecisionQueueItem, decision_id)
    if row is None:
        raise KeyError("no such decision")
    if row.consumed_at is not None:
        raise ValueError("decision was already reviewed or filed")
    proposal = _parse(row)
    proposed_ids = [link.cre_id for link in _proposed(proposal)]
    payload: Dict[str, Any] = {
        "proposed_cre_ids": proposed_ids,
        "final_cre_ids": [],
    }
    links_added = 0

    if action != "reject":
        if proposal is None:
            raise ValueError("decision envelope is invalid and cannot be filed")
        if action == "repoint":
            if not cre_ids:
                raise ValueError("repoint requires at least one cre id")
            refs = list(dict.fromkeys(cre_ids))
        else:
            if not proposed_ids:
                raise ValueError("no proposed CREs; use repoint to choose one")
            refs = list(dict.fromkeys(proposed_ids))
        db_cres = []
        for ref in refs:
            cre = _find_cre(ref)
            if cre is None:
                raise ValueError(f"unknown CRE {ref}")
            db_cres.append(cre)
        node = graph_filer.node_for(proposal, standard_name)
        if node is None:
            raise ValueError(
                "cannot work out a standard name for this source; pass standard_name"
            )
        node.tags = graph_filer.merge_node_tags(
            graph_filer.existing_tags(session, node),
            add=[REVIEWED_TAG, graph_filer.PROVENANCE_TAG],
            drop=[graph_filer.AUTO_FILED_TAG],
        )
        collection = db.Node_collection()
        db_node = collection.add_node(node)
        if db_node is None:
            raise ValueError("node could not be created")
        for cre in db_cres:
            exists = (
                session.query(db.Links)
                .filter(db.Links.cre == cre.id, db.Links.node == db_node.id)
                .first()
            )
            if exists is not None and exists.type == defs.LinkTypes.LinkedTo.value:
                continue
            collection.add_link(cre=cre, node=db_node, ltype=defs.LinkTypes.LinkedTo)
            links_added += 1
        payload["final_cre_ids"] = [c.external_id or c.id for c in db_cres]
        payload["node_id"] = db_node.id
        payload["standard_name"] = node.name

    session.add(
        db.DecisionReview(
            target_id=row.id,
            action=action,
            reviewer=reviewer,
            note=note,
            payload=payload,
        )
    )
    row.consumed_at = _now()
    session.commit()
    logger.info(
        "oie decision reviewed",
        extra={"decision": row.id, "review_action": action, "reviewer": reviewer},
    )
    return {"id": row.id, "action": action, "links_added": links_added}


def _node_dict(node: Any) -> Dict[str, Any]:
    links = []
    for link in sqla.session.query(db.Links).filter(db.Links.node == node.id).all():
        cre = sqla.session.get(db.CRE, link.cre)
        links.append(
            {
                "cre_id": cre.external_id if cre else link.cre,
                "cre_name": cre.name if cre else None,
                "type": link.type,
            }
        )
    return {
        "node_id": node.id,
        "name": node.name,
        "section": node.section,
        "section_id": node.section_id,
        "hyperlink": node.link,
        "tags": node.tags,
        "links": sorted(links, key=lambda x: str(x["cre_id"])),
    }


def list_filed(*, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """Nodes the filer or a reviewer wrote, with their CRE links."""
    page, page_size = _page_args(page, page_size)
    q = sqla.session.query(db.Node).filter(
        sqla.or_(
            db.Node.tags.like(f"%{graph_filer.AUTO_FILED_TAG}%"),
            db.Node.tags.like(f"%{REVIEWED_TAG}%"),
        )
    )
    total = q.count()
    nodes = (
        q.order_by(db.Node.name, db.Node.section_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_node_dict(n) for n in nodes],
    }


def repoint_filed_link(
    node_id: str,
    from_cre_id: str,
    to_cre_id: str,
    *,
    reviewer: Optional[str],
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Replace one CRE link on a filed node, keeping an audit row."""
    session = sqla.session
    node = session.get(db.Node, node_id)
    if node is None:
        raise KeyError("no such node")
    old_cre = _find_cre(from_cre_id)
    new_cre = _find_cre(to_cre_id)
    if new_cre is None:
        raise ValueError(f"unknown CRE {to_cre_id}")
    if old_cre is None:
        raise ValueError(f"unknown CRE {from_cre_id}")
    if old_cre.id == new_cre.id:
        raise ValueError("source and target CRE are the same")
    old_link = (
        session.query(db.Links)
        .filter(db.Links.cre == old_cre.id, db.Links.node == node.id)
        .first()
    )
    if old_link is None:
        raise ValueError("node is not linked to the source CRE")
    already = (
        session.query(db.Links)
        .filter(db.Links.cre == new_cre.id, db.Links.node == node.id)
        .first()
    )
    if already is not None:
        raise ValueError("node is already linked to the target CRE")

    from_type = old_link.type
    session.delete(old_link)
    session.flush()
    db.Node_collection().add_link(cre=new_cre, node=node, ltype=defs.LinkTypes.LinkedTo)
    session.add(
        db.DecisionReview(
            target_id=node.id,
            action="repoint_filed",
            reviewer=reviewer,
            note=note,
            payload={
                "from_cre_id": old_cre.external_id or old_cre.id,
                "to_cre_id": new_cre.external_id or new_cre.id,
                "from_type": from_type,
            },
        )
    )
    session.commit()
    logger.info(
        "oie filed link repointed",
        extra={"node": node.id, "reviewer": reviewer},
    )
    return {"node_id": node.id, "from": from_cre_id, "to": to_cre_id}
