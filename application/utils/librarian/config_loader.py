"""Loads CRE_LIBRARIAN_* environment variables into a typed config.

One source of truth for every tunable in Module C: the retriever (C.1), the
cross-encoder (C.2), the calibration temperature (C.3), and the auto-link
threshold (C.4). Defaults match the OIE design doc.

Two of these are fitted numbers, not preferences, and both come off a run of
``scripts/evaluate_librarian.py --use_live_embeddings``:

- ``CRE_LIBRARIAN_TEMPERATURE`` is C.3's ``T``. The harness fits it and prints
  it; there is no other place it is stored. The default of 1.0 is the identity
  transform — an *uncalibrated* softmax, honest about being unfitted rather
  than pretending to a temperature nobody measured.
- ``CRE_LIBRARIAN_LINK_THRESHOLD`` is τ, held at 0.80 by the W7 sweep.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import math
import os
from dataclasses import dataclass
from typing import Optional

# Retrieval backends (see candidate_retriever.RetrieverBackend). Kept as a
# plain set here so the loader stays dependency-free; the retriever owns the
# enum it maps to.
_RETRIEVER_BACKENDS = frozenset({"in_memory", "pgvector"})

# Default γ for CRE_LIBRARIAN_MARGIN_GAMMA when the env is present but empty /
# boolean-true (distinct from CRE_LIBRARIAN_HYBRID_GAMMA).
_DEFAULT_MARGIN_GAMMA = 0.85


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_csv(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_optional_margin_gamma(name: str) -> Optional[float]:
    """Unset → off (None). Set → float, or 0.85 for empty / boolean-true."""
    raw = os.getenv(name)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or stripped.lower() in ("1", "true", "yes", "on"):
        return _DEFAULT_MARGIN_GAMMA
    return float(stripped)


@dataclass(frozen=True)
class LibrarianConfig:
    crossencoder_model: str
    retriever_backend: str
    top_k_retrieval: int
    top_k_rerank: int
    link_threshold: float
    temperature: float
    batch_size: int
    ece_target: float
    conformal_alpha: float
    standard_retrieval: bool = False
    standard_retrieval_families: tuple[str, ...] = ()
    standard_top_k: int = 10
    standard_max_cres_per_hit: int = 4
    cre_text_enrich: bool = False
    cre_summary: bool = True
    dual_index: bool = True
    prior_cage: bool = True
    focus_query: bool = False
    pref_inject: bool = True
    prefer_audit_ids: bool = True
    hybrid_beta: float = 0.0
    hybrid_gamma: float = 0.70
    #: After C.2, promote Contains children over hub umbrellas when they score better.
    leaf_drilldown: bool = True
    #: Optional name allowlist (empty = no name filter). Length gate is primary.
    leaf_drilldown_resources: tuple[str, ...] = ()
    #: Bypass ``min_sections`` for these resources (empty = none; set ``api`` to force).
    leaf_drilldown_force_resources: tuple[str, ...] = ()
    #: Skip Contains hubs with fewer than this many children.
    leaf_drilldown_min_children: int = 3
    #: Skip drill when resource family has fewer chunks than this (≤1 disables).
    leaf_drilldown_min_sections: int = 20
    #: E1: keep drilled hubs inside scored top-2.
    leaf_drilldown_keep_hub: bool = False
    #: E2: never put leaf ahead of hub (leaf always specificity #2).
    leaf_drilldown_hub_first: bool = False
    #: E5: max umbrella parents promoted into preferred shortlist.
    umbrella_promote_cap: int = 8
    #: Grounded judge: max CRE ids (3 aligns with score top_k=3).
    shortlist_judge_max_picks: int = 3
    #: Relative CE shortlist cutoff after C.2 (None = off).
    margin_gamma: Optional[float] = None


def _env_leaf_drilldown_resources() -> tuple[str, ...]:
    """Unset / ``*`` / empty → no name filter. Otherwise comma list."""
    raw = os.getenv("CRE_LIBRARIAN_LEAF_DRILLDOWN_RESOURCES")
    if raw is None:
        return ()
    stripped = raw.strip()
    if not stripped or stripped == "*":
        return ()
    return tuple(part.strip().lower() for part in stripped.split(",") if part.strip())


def _env_leaf_drilldown_force_resources() -> tuple[str, ...]:
    """Comma list; empty/unset → no length-gate bypass.

    Cold-start (``FORCE=api``) raised GitHub d1 but dropped API exact 60%→50%;
    keep off by default — set ``CRE_LIBRARIAN_LEAF_DRILLDOWN_FORCE_RESOURCES=api``
    only for explicit experiments.
    """
    raw = os.getenv("CRE_LIBRARIAN_LEAF_DRILLDOWN_FORCE_RESOURCES")
    if raw is None or not raw.strip():
        return ()
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def load_config() -> LibrarianConfig:
    crossencoder_model = os.getenv(
        "CRE_LIBRARIAN_CROSSENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    retriever_backend = os.getenv("CRE_LIBRARIAN_RETRIEVER_BACKEND", "in_memory")
    top_k_retrieval = int(os.getenv("CRE_LIBRARIAN_TOP_K_RETRIEVAL", "20"))
    top_k_rerank = int(os.getenv("CRE_LIBRARIAN_TOP_K_RERANK", "5"))
    link_threshold = float(os.getenv("CRE_LIBRARIAN_LINK_THRESHOLD", "0.8"))
    temperature = float(os.getenv("CRE_LIBRARIAN_TEMPERATURE", "1.0"))
    batch_size = int(os.getenv("CRE_LIBRARIAN_BATCH_SIZE", "32"))
    ece_target = float(os.getenv("CRE_LIBRARIAN_ECE_TARGET", "0.10"))
    conformal_alpha = float(os.getenv("CRE_LIBRARIAN_CONFORMAL_ALPHA", "0.10"))
    standard_retrieval = _env_bool("CRE_LIBRARIAN_STANDARD_RETRIEVAL", False)
    standard_retrieval_families = _env_csv("CRE_LIBRARIAN_STANDARD_RETRIEVAL_FAMILIES")
    standard_top_k = int(os.getenv("CRE_LIBRARIAN_STANDARD_TOP_K", "10"))
    standard_max_cres_per_hit = int(
        os.getenv("CRE_LIBRARIAN_STANDARD_MAX_CRES_PER_HIT", "4")
    )
    cre_text_enrich = _env_bool("CRE_LIBRARIAN_CRE_TEXT_ENRICH", False)
    # Ship pair: summaries feed C.2 + dual C.1 body pool; dual needs summaries.
    # Env can still force either off (CRE_LIBRARIAN_CRE_SUMMARY=0 / DUAL_INDEX=0).
    cre_summary = _env_bool("CRE_LIBRARIAN_CRE_SUMMARY", True)
    dual_index = _env_bool("CRE_LIBRARIAN_DUAL_INDEX", True)
    # Lawrence OOD audit (17 Sep 2026) + clone A/B: keep cage / Lever 4 /
    # prefer_audit. FOCUS_QUERY defaults off (full narrative). Hybrid is
    # CE-led (β=0 / γ=0.70). Env can restore the name-heavy mix.
    prior_cage = _env_bool("CRE_LIBRARIAN_PRIOR_CAGE", True)
    focus_query = _env_bool("CRE_LIBRARIAN_FOCUS_QUERY", False)
    pref_inject = _env_bool("CRE_LIBRARIAN_PREF_INJECT", True)
    prefer_audit_ids = _env_bool("CRE_LIBRARIAN_PREFER_AUDIT_IDS", True)
    hybrid_beta = float(os.getenv("CRE_LIBRARIAN_HYBRID_BETA", "0"))
    hybrid_gamma = float(os.getenv("CRE_LIBRARIAN_HYBRID_GAMMA", "0.70"))
    leaf_drilldown = _env_bool("CRE_LIBRARIAN_LEAF_DRILLDOWN", True)
    leaf_drilldown_resources = _env_leaf_drilldown_resources()
    leaf_drilldown_force_resources = _env_leaf_drilldown_force_resources()
    leaf_drilldown_min_children = int(
        os.getenv("CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_CHILDREN", "3")
    )
    leaf_drilldown_min_sections = int(
        os.getenv("CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_SECTIONS", "20")
    )
    leaf_drilldown_keep_hub = _env_bool("CRE_LIBRARIAN_LEAF_DRILLDOWN_KEEP_HUB", False)
    leaf_drilldown_hub_first = _env_bool(
        "CRE_LIBRARIAN_LEAF_DRILLDOWN_HUB_FIRST", False
    )
    umbrella_promote_cap = int(os.getenv("CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP", "8"))
    shortlist_judge_max_picks = int(
        os.getenv("CRE_LIBRARIAN_SHORTLIST_JUDGE_MAX_PICKS", "3")
    )
    margin_gamma = _env_optional_margin_gamma("CRE_LIBRARIAN_MARGIN_GAMMA")

    if retriever_backend not in _RETRIEVER_BACKENDS:
        raise ValueError(
            f"CRE_LIBRARIAN_RETRIEVER_BACKEND must be one of "
            f"{sorted(_RETRIEVER_BACKENDS)}, got {retriever_backend!r}"
        )
    if top_k_retrieval <= 0:
        raise ValueError(
            f"CRE_LIBRARIAN_TOP_K_RETRIEVAL must be > 0, got {top_k_retrieval}"
        )
    if top_k_rerank <= 0:
        raise ValueError(f"CRE_LIBRARIAN_TOP_K_RERANK must be > 0, got {top_k_rerank}")
    if top_k_rerank > top_k_retrieval:
        raise ValueError(
            f"CRE_LIBRARIAN_TOP_K_RERANK ({top_k_rerank}) must be <= "
            f"CRE_LIBRARIAN_TOP_K_RETRIEVAL ({top_k_retrieval})"
        )
    if batch_size <= 0:
        raise ValueError(f"CRE_LIBRARIAN_BATCH_SIZE must be > 0, got {batch_size}")
    if not 0.0 <= link_threshold <= 1.0:
        raise ValueError(
            f"CRE_LIBRARIAN_LINK_THRESHOLD must be in [0.0, 1.0], got {link_threshold}"
        )
    # Mirrors TemperatureScaler's own guard: T divides the logits, so zero or
    # negative is not a bad setting, it is undefined.
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError(
            f"CRE_LIBRARIAN_TEMPERATURE must be finite and > 0, got {temperature}"
        )
    if not 0.0 <= ece_target <= 1.0:
        raise ValueError(
            f"CRE_LIBRARIAN_ECE_TARGET must be in [0.0, 1.0], got {ece_target}"
        )
    if not 0.0 <= conformal_alpha <= 1.0:
        raise ValueError(
            f"CRE_LIBRARIAN_CONFORMAL_ALPHA must be in [0.0, 1.0], got {conformal_alpha}"
        )
    if standard_top_k <= 0:
        raise ValueError(
            f"CRE_LIBRARIAN_STANDARD_TOP_K must be > 0, got {standard_top_k}"
        )
    if standard_max_cres_per_hit <= 0:
        raise ValueError(
            "CRE_LIBRARIAN_STANDARD_MAX_CRES_PER_HIT must be > 0, "
            f"got {standard_max_cres_per_hit}"
        )
    if not math.isfinite(hybrid_beta) or hybrid_beta < 0:
        raise ValueError(
            f"CRE_LIBRARIAN_HYBRID_BETA must be finite and >= 0, got {hybrid_beta}"
        )
    if not math.isfinite(hybrid_gamma) or hybrid_gamma < 0:
        raise ValueError(
            f"CRE_LIBRARIAN_HYBRID_GAMMA must be finite and >= 0, got {hybrid_gamma}"
        )
    if leaf_drilldown_min_children < 1:
        raise ValueError(
            "CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_CHILDREN must be >= 1, "
            f"got {leaf_drilldown_min_children}"
        )
    if leaf_drilldown_min_sections < 0:
        raise ValueError(
            "CRE_LIBRARIAN_LEAF_DRILLDOWN_MIN_SECTIONS must be >= 0, "
            f"got {leaf_drilldown_min_sections}"
        )
    if umbrella_promote_cap < 1:
        raise ValueError(
            "CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP must be >= 1, "
            f"got {umbrella_promote_cap}"
        )
    if shortlist_judge_max_picks < 1 or shortlist_judge_max_picks > 5:
        raise ValueError(
            "CRE_LIBRARIAN_SHORTLIST_JUDGE_MAX_PICKS must be in [1, 5], "
            f"got {shortlist_judge_max_picks}"
        )
    if margin_gamma is not None and (
        not math.isfinite(margin_gamma) or margin_gamma <= 0
    ):
        raise ValueError(
            "CRE_LIBRARIAN_MARGIN_GAMMA must be finite and > 0 when set, "
            f"got {margin_gamma}"
        )

    # Mirror promote cap into the process env so ParentIndex._promote_cap sees it
    # without plumbing the index through every call site.
    os.environ["CRE_LIBRARIAN_UMBRELLA_PROMOTE_CAP"] = str(umbrella_promote_cap)
    os.environ["CRE_LIBRARIAN_SHORTLIST_JUDGE_MAX_PICKS"] = str(
        shortlist_judge_max_picks
    )

    return LibrarianConfig(
        crossencoder_model=crossencoder_model,
        retriever_backend=retriever_backend,
        top_k_retrieval=top_k_retrieval,
        top_k_rerank=top_k_rerank,
        link_threshold=link_threshold,
        temperature=temperature,
        batch_size=batch_size,
        ece_target=ece_target,
        conformal_alpha=conformal_alpha,
        standard_retrieval=standard_retrieval,
        standard_retrieval_families=standard_retrieval_families,
        standard_top_k=standard_top_k,
        standard_max_cres_per_hit=standard_max_cres_per_hit,
        cre_text_enrich=cre_text_enrich,
        cre_summary=cre_summary,
        dual_index=dual_index,
        prior_cage=prior_cage,
        focus_query=focus_query,
        pref_inject=pref_inject,
        prefer_audit_ids=prefer_audit_ids,
        hybrid_beta=hybrid_beta,
        hybrid_gamma=hybrid_gamma,
        leaf_drilldown=leaf_drilldown,
        leaf_drilldown_resources=leaf_drilldown_resources,
        leaf_drilldown_force_resources=leaf_drilldown_force_resources,
        leaf_drilldown_min_children=leaf_drilldown_min_children,
        leaf_drilldown_min_sections=leaf_drilldown_min_sections,
        leaf_drilldown_keep_hub=leaf_drilldown_keep_hub,
        leaf_drilldown_hub_first=leaf_drilldown_hub_first,
        umbrella_promote_cap=umbrella_promote_cap,
        shortlist_judge_max_picks=shortlist_judge_max_picks,
        margin_gamma=margin_gamma,
    )
