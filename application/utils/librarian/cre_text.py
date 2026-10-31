"""CRE embedding / cross-encoder pair text.

CRE hub vectors are built from name + empty description. Linked Standard
``embeddings_content`` is the prose we already paid to embed — use it as the
CRE match description (C.2, optional C.1 re-embed). Skip junk chrome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple

from application.utils.librarian.embedding_quality import usable_embedding_text

_STUB_MAX_CHARS = 200
# MiniLM C.2 truncates ~512 tokens; keep CE pair text in that neighborhood.
CE_PROSE_CHARS = 1800
# Gemini/OpenAI embeddings accept much more; used when re-embedding CREs.
EMBED_PROSE_CHARS = 12000


@dataclass(frozen=True)
class LinkedStandardRef:
    standard: str
    section_id: str
    title: str
    prose: str = ""

    def line(self) -> str:
        parts = [self.standard.strip(), self.section_id.strip(), self.title.strip()]
        return " ".join(p for p in parts if p)

    def match_text(self) -> str:
        """Prefer stored embeddings_content; fall back to the title line."""
        body = usable_embedding_text(self.prose)
        if body:
            return body
        return self.line()


def _linked_excerpt(ref: LinkedStandardRef, remaining: int) -> str:
    """One linked standard's match text, clipped to the leftover budget."""
    if remaining <= 0:
        return ""
    piece = ref.match_text()
    if not piece:
        return ""
    if len(piece) <= remaining:
        return piece
    return piece[:remaining].rstrip()


def build_cre_embedding_text(
    *,
    name: str,
    description: str,
    cre_id: str,
    linked: Sequence[LinkedStandardRef] = (),
    include_linked_titles: bool = False,
    max_linked_chars: int = 800,
    doctype: str = "CRE",
) -> str:
    """Stable CRE blob. Linked match text is opt-in and length-capped."""
    linked_blob = ""
    if include_linked_titles and linked:
        chunks: list[str] = []
        used = 0
        for ref in linked:
            remaining = max_linked_chars - used - (2 if chunks else 0)
            piece = _linked_excerpt(ref, remaining)
            if not piece:
                continue
            extra = (2 if chunks else 0) + len(piece)
            if used + extra > max_linked_chars:
                break
            chunks.append(piece)
            used += extra
        if chunks:
            linked_blob = "; ".join(chunks)
    desc = (description or "").strip()
    if linked_blob and not desc:
        desc = linked_blob
        linked_blob = ""
    lines = [
        doctype,
        f" name:{name}",
        f" description:{desc}",
        f" id:{cre_id}",
    ]
    if linked_blob:
        lines.append(" linked: " + linked_blob)
    return "\n".join(lines)


def enrich_cre_contents(
    contents: Mapping[str, str],
    linked_by_cre: Mapping[str, Sequence[LinkedStandardRef]],
    names: Optional[Mapping[str, str]] = None,
    *,
    max_linked_chars: int = CE_PROSE_CHARS,
) -> Dict[str, str]:
    """Append linked Standard embeddings_content to stub CRE pair text."""
    names = names or {}
    out: Dict[str, str] = {}
    for cre_id, text in contents.items():
        refs = linked_by_cre.get(cre_id) or ()
        if not refs or len(text or "") > _STUB_MAX_CHARS:
            out[cre_id] = text
            continue
        out[cre_id] = build_cre_embedding_text(
            name=names.get(cre_id, ""),
            description="",
            cre_id=cre_id,
            linked=refs,
            include_linked_titles=True,
            max_linked_chars=max_linked_chars,
        )
    return out


def load_linked_standard_refs(
    database: object,
) -> Dict[str, Tuple[LinkedStandardRef, ...]]:
    """``cre.id`` → linked standards with stored ``embeddings_content``."""
    session = getattr(database, "session", None)
    if session is None:
        return {}
    try:
        from application.database.db import Embeddings, Links, Node
    except Exception:  # noqa: BLE001
        return {}

    grouped: Dict[str, Dict[Tuple[str, str, str], LinkedStandardRef]] = {}
    rows = (
        session.query(
            Links.cre,
            Node.name,
            Node.section_id,
            Node.section,
            Embeddings.embeddings_content,
        )
        .join(Node, Node.id == Links.node)
        .outerjoin(Embeddings, Embeddings.node_id == Node.id)
        .all()
    )
    for cre_id, std_name, section_id, section, content in rows:
        if not cre_id:
            continue
        ref = LinkedStandardRef(
            standard=str(std_name or ""),
            section_id=str(section_id or ""),
            title=str(section or ""),
            prose=str(content or ""),
        )
        slot = grouped.setdefault(str(cre_id), {})
        key = (ref.standard, ref.section_id, ref.title)
        prev = slot.get(key)
        if prev is None or len(ref.prose) > len(prev.prose):
            slot[key] = ref
    return {k: tuple(v.values()) for k, v in grouped.items()}


__all__ = [
    "CE_PROSE_CHARS",
    "EMBED_PROSE_CHARS",
    "LinkedStandardRef",
    "build_cre_embedding_text",
    "enrich_cre_contents",
    "load_linked_standard_refs",
]
