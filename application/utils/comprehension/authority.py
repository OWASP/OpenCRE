"""Admin-editable authority weights: favour or soften projects in answers.

Stored as one JSON setting ``{repo slug: weight}`` in ``admin_runtime_setting``. Unlisted
projects are 1.0 (neutral).

* Below 1: the project's chunk scores are multiplied by the weight before ranking (0 hides it).
* Above 1 ("featured"): ranking is left alone, so answers do not get worse, but the project's best
  matching chunk is listed among the answer's references whenever it is reasonably relevant to the
  question. The higher the weight, the less relevant a match may be. Never shown for abstentions.
"""

from __future__ import annotations

import json
import time
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

KEY = "COMPREHENSION_AUTHORITY"
MIN_WEIGHT, MAX_WEIGHT = 0.0, 3.0
_CACHE: Dict[str, Any] = {"at": 0.0, "weights": {}}
_TTL = 30.0


def validate(raw: Any) -> Dict[str, float]:
    """Clean ``{slug: weight}``; neutral (1.0) entries are dropped. Raises ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("weights must be an object of slug -> number")
    out: Dict[str, float] = {}
    for slug, val in raw.items():
        if not isinstance(slug, str) or not slug.strip():
            raise ValueError("project slug must be a non-empty string")
        if isinstance(val, bool) or not isinstance(val, (int, float, str)):
            raise ValueError(f"weight for {slug} must be a number")
        try:
            w = float(val)
        except ValueError:
            raise ValueError(f"weight for {slug} must be a number") from None
        if not MIN_WEIGHT <= w <= MAX_WEIGHT:
            raise ValueError(
                f"weight for {slug} must be between {MIN_WEIGHT} and {MAX_WEIGHT}"
            )
        if abs(w - 1.0) > 1e-9:
            out[slug.strip()] = round(w, 3)
    return out


def weights(fresh: bool = False) -> Dict[str, float]:
    """Current weights (30 s cache); {} when none are set or the database is unavailable."""
    if not fresh and time.time() - _CACHE["at"] < _TTL:
        return _CACHE["weights"]
    loaded: Dict[str, float] = {}
    try:
        from application.utils.admin_panel import runtime_settings

        raw = runtime_settings.get_setting(KEY)
        if raw:
            loaded = validate(json.loads(raw))
    except (
        Exception
    ):  # noqa: BLE001 - authority is a bias, never a reason to fail an answer
        loaded = {}
    _CACHE.update(at=time.time(), weights=loaded)
    return loaded


def save(new: Dict[str, float], actor: Optional[str] = None) -> Dict[str, float]:
    from application.utils.admin_panel import runtime_settings

    clean = validate(new)
    runtime_settings.set_setting(KEY, json.dumps(clean, sort_keys=True), actor=actor)
    _CACHE.update(at=0.0, weights={})
    return clean


_FEATURED: "ContextVar[List[str]]" = ContextVar("authority_featured", default=[])


def reset_featured() -> None:
    _FEATURED.set([])


def featured_urls() -> List[str]:
    return list(_FEATURED.get())


def tolerance(weight: float) -> float:
    """How far below the best score a featured project's chunk may fall and still be listed."""
    return max(0.02, min(0.2, 0.08 * (weight - 1.0) / 0.15))


def set_featured(urls: List[str]) -> None:
    _FEATURED.set(list(urls))


def bias(hits: List[Any], slug_of) -> List[Any]:
    """Multiply each hit's score by its project's weight, drop weight-0 projects, re-sort."""
    w = weights()
    if not w or all(v >= 1.0 for v in w.values()):
        return hits
    out = []
    for h in hits:
        factor = min(1.0, w.get(slug_of(h) or "", 1.0))
        if factor <= 0:
            continue
        h.score = float(h.score) * factor
        out.append(h)
    out.sort(key=lambda h: -float(h.score))
    return out


def diversify(hits: List[Any], slug_of, projects: int = 3, per: int = 5) -> List[Any]:
    """Make sure the best ``projects`` projects each get up to ``per`` hits at the front."""
    chosen: List[str] = []
    for h in hits:
        s = slug_of(h)
        if s and s not in chosen:
            chosen.append(s)
        if len(chosen) >= projects:
            break
    if len(chosen) < 2:
        return hits
    taken: Dict[str, int] = {}
    front: List[Any] = []
    for h in hits:
        s = slug_of(h)
        if s in chosen and taken.get(s, 0) < per:
            taken[s] = taken.get(s, 0) + 1
            front.append(h)
    seen = {id(h) for h in front}
    return front + [h for h in hits if id(h) not in seen]


def project_table(slugs: List[str]) -> List[Dict[str, Any]]:
    from application.utils.comprehension.retrieve import alias_phrase

    w = weights(fresh=True)
    rows = [
        {"slug": s, "name": alias_phrase(s), "weight": w.get(s, 1.0)}
        for s in sorted(set(slugs) | set(w))
    ]
    return rows
