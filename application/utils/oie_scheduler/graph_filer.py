"""File Librarian-confident links into the CRE graph.

The last write step of the expansion path: ``decision_queue`` rows with status
``linked`` become a ``Standard`` node (one per source section) plus
``Automatically linked to`` edges to the CREs the Librarian chose.

Policy (decided with the maintainers): if the Librarian is sure, file it; if not,
drop it for now -- a later version routes the unsure ones to Module D. "Sure" is
a confidence floor above the Librarian's own link threshold, and a kill switch
can disable filing outright. Rows that are not filed are left **unconsumed**, so
nothing is lost and a later version (or a lower floor) can still pick them up.

Idempotent: node upsert is by identity, an existing link is never overwritten
(so a curated edge is never downgraded to an automatic one), and a filed row is
stamped ``consumed_at`` so it is not read again.
"""

from __future__ import annotations

from cre_logging import get_logger

logger = get_logger(__name__)

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Collection, Dict, List, Optional

import sqlalchemy as sa
from pydantic import ValidationError

from application.database import db
from application.defs import cre_defs as defs
from application.utils.librarian.schemas import LinkProposal
from application.utils.oie_scheduler.run_log import naive_utc, utcnow

#: Tag on auto-filed nodes so they are recognisable (and removable) in the graph.
AUTO_FILED_TAG = "oie-auto-filed"


@dataclass
class FilerResult:
    enabled: bool = True
    dry_run: bool = False
    floor: float = 0.0
    considered: int = 0
    filed: int = 0
    below_floor: int = 0
    skipped_standard_repo: int = 0
    unknown_cre: int = 0
    invalid: int = 0
    nodes_touched: int = 0
    links_added: int = 0
    links_already_present: int = 0
    standards: List[str] = field(default_factory=list)

    @property
    def graph_changed(self) -> bool:
        return self.links_added > 0

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["graph_changed"] = self.graph_changed
        return out


def auto_filed_nodes_without_embeddings(session: Any) -> List[str]:
    """Ids of auto-filed nodes that have no embedding row yet.

    Derived from the graph rather than from one run's filer result, so a node
    whose embedding failed (or whose run crashed) is picked up by the next run.
    """
    rows = (
        session.query(db.Node.id, db.Node.tags)
        .filter(db.Node.tags.like(f"%{AUTO_FILED_TAG}%"))
        .filter(~sqla_exists_embedding())
        .order_by(db.Node.id)
        .all()
    )
    return [
        node_id
        for node_id, tags in rows
        if AUTO_FILED_TAG in [t.strip() for t in (tags or "").split(",")]
    ]


def sqla_exists_embedding() -> Any:
    return (
        sa.select(db.Embeddings.id).where(db.Embeddings.node_id == db.Node.id).exists()
    )


def standard_name_for_repo(repo: str) -> str:
    return repo if "/" in repo else f"OWASP/{repo}"


def _hyperlink(proposal: LinkProposal) -> str:
    locator = proposal.knowledge.locator
    if locator.url:
        return str(locator.url)
    source = proposal.knowledge.source
    if source.repo and source.commit_sha and locator.path:
        return (
            f"https://github.com/{source.repo}/blob/{source.commit_sha}/{locator.path}"
        )
    return ""


def _node_for(proposal: LinkProposal) -> Optional[defs.Standard]:
    source = proposal.knowledge.source
    locator = proposal.knowledge.locator
    if not source.repo:
        return None
    section_id = locator.path or locator.id
    return defs.Standard(
        name=standard_name_for_repo(source.repo),
        section=locator.title or section_id,
        sectionID=section_id,
        hyperlink=_hyperlink(proposal),
        description=(proposal.knowledge.security_summary or "")[:1000],
        tags=[AUTO_FILED_TAG],
    )


def file_linked_decisions(
    collection: Any,
    *,
    floor: float,
    enabled: bool = True,
    dry_run: bool = False,
    skip_repos: Optional[Collection[str]] = None,
    now: Optional[datetime] = None,
) -> FilerResult:
    """File every unconsumed ``linked`` decision whose confidence clears ``floor``.

    ``skip_repos`` are source repos (``OWASP/ASVS``) whose standards already have
    a dedicated importer; filing chunk-level nodes under them would duplicate it.
    """
    result = FilerResult(enabled=enabled, dry_run=dry_run, floor=floor)
    if not enabled:
        logger.info("graph filing disabled (kill switch); decisions left unconsumed")
        return result

    session = collection.session
    skip = {r.casefold() for r in (skip_repos or ())}
    rows = (
        session.query(db.DecisionQueueItem)
        .filter(
            db.DecisionQueueItem.status == "linked",
            db.DecisionQueueItem.consumed_at.is_(None),
        )
        .order_by(db.DecisionQueueItem.created_at, db.DecisionQueueItem.id)
        .all()
    )
    standards: set[str] = set()
    touched_nodes: set[Any] = set()
    filed_rows: List[Any] = []

    for row in rows:
        result.considered += 1
        try:
            proposal = LinkProposal.model_validate(row.envelope)
        except ValidationError:
            result.invalid += 1
            logger.warning("decision %s has an invalid LinkProposal envelope", row.id)
            continue

        repo = proposal.knowledge.source.repo or ""
        if repo.casefold() in skip:
            result.skipped_standard_repo += 1
            continue

        sure = [link for link in proposal.links if link.confidence >= floor]
        if not sure:
            result.below_floor += 1
            continue

        node = _node_for(proposal)
        if node is None:
            result.invalid += 1
            continue

        db_cres = []
        for link in sure:
            db_cre = (
                session.query(db.CRE).filter(db.CRE.external_id == link.cre_id).first()
            )
            if db_cre is None:
                result.unknown_cre += 1
                logger.warning(
                    "decision %s links unknown CRE %s; not filed", row.id, link.cre_id
                )
                continue
            db_cres.append(db_cre)
        if not db_cres:
            continue

        if dry_run:
            result.filed += 1
            standards.add(node.name)
            continue

        db_node = collection.add_node(node)
        if db_node is None:
            result.invalid += 1
            continue
        touched_nodes.add(db_node.id)
        standards.add(node.name)
        for db_cre in db_cres:
            exists = (
                session.query(db.Links)
                .filter(db.Links.cre == db_cre.id, db.Links.node == db_node.id)
                .first()
            )
            if exists is not None:
                result.links_already_present += 1
                continue
            collection.add_link(
                cre=db_cre, node=db_node, ltype=defs.LinkTypes.AutomaticallyLinkedTo
            )
            result.links_added += 1
        result.filed += 1
        filed_rows.append(row)

    if filed_rows:
        stamp = naive_utc(now or utcnow())
        for row in filed_rows:
            row.consumed_at = stamp
        session.commit()

    result.nodes_touched = len(touched_nodes)
    result.standards = sorted(standards)
    logger.info("graph filing complete", extra={"filer": result.to_dict()})
    return result
