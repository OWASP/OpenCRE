"""Grounded shortlist judge: LLM picks top-1..2 CRE ids from a provided list only.

Module C lever C — not a freeform linker. The model may only return ids that
appear in the retrieval shortlist; invented ids are dropped. Failures (bad JSON,
network, empty allowlist) return ``[]`` so the pipeline keeps its existing rank.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

LlmFn = Callable[[str, str], str]  # (system, user) -> raw text

DEFAULT_TOP_N = 15
DEFAULT_CACHE_DIR = "tmp/oie_shortlist_judge_cache"

_SYSTEM = (
    "You are a grounded CRE shortlist judge for OpenCRE. "
    "Given a standards section focus text and a fixed list of candidate CREs, "
    "pick the 1 or 2 best matching CRE ids. "
    "Return ONLY a JSON array of cre_id strings drawn from the provided list. "
    "Do not invent ids. Do not return names, objects, or commentary."
)


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_judge_json(raw: str, allowlist: Sequence[str]) -> List[str]:
    """Parse LLM output to 1–2 cre_ids present in ``allowlist`` (order preserved)."""
    allowed = {str(a) for a in allowlist if a}
    if not allowed:
        return []
    try:
        data = json.loads(_strip_fences(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []

    if isinstance(data, dict):
        # Tolerate {"cre_ids": [...]} / {"ids": [...]} wrappers.
        for key in ("cre_ids", "ids", "chosen", "picks"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            return []

    if not isinstance(data, list):
        return []

    out: List[str] = []
    seen: set = set()
    for item in data:
        cid = str(item).strip() if item is not None else ""
        if not cid or cid in seen or cid not in allowed:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= 2:
            break
    return out


def build_judge_prompt(
    query_text: str, candidates: Sequence[Mapping[str, Any]]
) -> tuple:
    """Return ``(system, user)`` for the grounded judge call."""
    rows = []
    for c in candidates:
        cid = str(c.get("cre_id") or "").strip()
        if not cid:
            continue
        name = str(c.get("name") or c.get("cre_name") or "").strip()
        rows.append({"cre_id": cid, "name": name})
    user = (
        "Section focus:\n"
        f"{(query_text or '').strip()}\n\n"
        "Candidates (choose 1–2 cre_id values from this list only):\n"
        f"{json.dumps(rows, ensure_ascii=False)}\n\n"
        "Respond with a JSON array, e.g. [\"123-456\", \"789-012\"]."
    )
    return _SYSTEM, user


def cache_key(query_text: str, candidate_ids: Sequence[str]) -> str:
    blob = json.dumps(
        {"q": (query_text or "").strip(), "ids": list(candidate_ids)},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class ShortlistJudgeCache:
    """Process-local + optional disk cache for judged id lists."""

    def __init__(self, disk_dir: Optional[Path] = None) -> None:
        self.memory: Dict[str, List[str]] = {}
        self.disk_dir = disk_dir

    def get(self, key: str) -> Optional[List[str]]:
        if key in self.memory:
            return list(self.memory[key])
        if self.disk_dir is not None:
            path = self.disk_dir / f"{key}.json"
            if path.is_file():
                try:
                    data = json.loads(path.read_text())
                except (OSError, ValueError, json.JSONDecodeError):
                    return None
                if isinstance(data, list):
                    ids = [str(x) for x in data]
                    self.memory[key] = ids
                    return list(ids)
        return None

    def put(self, key: str, ids: Sequence[str]) -> None:
        stored = list(ids)
        self.memory[key] = stored
        if self.disk_dir is not None:
            try:
                self.disk_dir.mkdir(parents=True, exist_ok=True)
                (self.disk_dir / f"{key}.json").write_text(
                    json.dumps(stored, indent=2)
                )
            except OSError:
                logger.debug("shortlist judge cache write failed", exc_info=True)


def default_litellm_fn(model: Optional[str] = None) -> LlmFn:
    """LiteLLM completion → text (same stack as edition_remap / Module B)."""

    model_name = model or os.environ.get(
        "CRE_LIBRARIAN_SHORTLIST_JUDGE_MODEL",
        os.environ.get("CRE_NOISE_FILTER_LLM_MODEL", "gemini/gemini-2.5-flash-lite"),
    )

    def _call(system: str, user: str) -> str:
        import litellm

        resp = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
        return str(resp.choices[0].message.content or "")

    return _call


def default_cache_dir() -> Path:
    return Path(
        os.environ.get("CRE_LIBRARIAN_SHORTLIST_JUDGE_CACHE", DEFAULT_CACHE_DIR)
    )


def candidates_from_audit(
    audit: Any, *, top_n: int = DEFAULT_TOP_N
) -> List[Dict[str, str]]:
    """Build ``[{cre_id, name}, ...]`` from ``audit.candidates`` (top ``top_n``)."""
    out: List[Dict[str, str]] = []
    cands = getattr(audit, "candidates", None) or []
    for c in cands[:top_n]:
        cid = getattr(c, "cre_id", None) or (
            c.get("cre_id") if isinstance(c, Mapping) else None
        )
        if not cid:
            continue
        name = getattr(c, "cre_name", None) if not isinstance(c, Mapping) else c.get(
            "cre_name"
        ) or c.get("name")
        out.append({"cre_id": str(cid), "name": str(name or "")})
    return out


def judge_shortlist(
    query_text: str,
    candidates: Sequence[Mapping[str, Any]],
    llm_fn: Optional[LlmFn] = None,
    *,
    cache: Optional[ShortlistJudgeCache] = None,
    top_n: int = DEFAULT_TOP_N,
) -> List[str]:
    """Ask the LLM for 1–2 cre_ids from ``candidates``; validate against allowlist.

    Returns ``[]`` on missing input, LLM errors, or invalid JSON (fail-open).
    """
    rows = [
        {"cre_id": str(c.get("cre_id") or "").strip(), "name": str(
            c.get("name") or c.get("cre_name") or ""
        )}
        for c in candidates[:top_n]
        if str(c.get("cre_id") or "").strip()
    ]
    if not rows or not (query_text or "").strip():
        return []

    allowlist = [r["cre_id"] for r in rows]
    key = cache_key(query_text, allowlist)
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            # Re-validate against current allowlist (cache may be stale).
            return [cid for cid in hit if cid in set(allowlist)][:2]

    fn = llm_fn
    if fn is None:
        try:
            fn = default_litellm_fn()
        except Exception:  # noqa: BLE001
            logger.warning("shortlist judge: cannot build default LLM", exc_info=True)
            return []

    system, user = build_judge_prompt(query_text, rows)
    try:
        raw = fn(system, user)
        chosen = parse_judge_json(raw, allowlist)
    except Exception:  # noqa: BLE001
        logger.warning("shortlist judge LLM failed; keeping existing rank", exc_info=True)
        return []

    if cache is not None and chosen:
        cache.put(key, chosen)
    return chosen


def judge_enabled() -> bool:
    """Env kill-switch; default on so live factory runs use the judge."""
    return os.environ.get("CRE_LIBRARIAN_SHORTLIST_JUDGE", "1").strip().lower() not in (
        "0",
        "false",
        "off",
        "no",
    )


__all__ = [
    "DEFAULT_CACHE_DIR",
    "DEFAULT_TOP_N",
    "LlmFn",
    "ShortlistJudgeCache",
    "build_judge_prompt",
    "cache_key",
    "candidates_from_audit",
    "default_cache_dir",
    "default_litellm_fn",
    "judge_enabled",
    "judge_shortlist",
    "parse_judge_json",
]
