"""Builds the live C.1/C.2/C.3 components from config + the OpenCRE database.

Until now the only place that knew how to construct a real retriever and
reranker was ``cre_main.run_librarian``, inline. That is why the OIE
orchestrator (#996) could not drive ``LibrarianPipeline`` — it had the pipeline
class but no way to produce the components it takes. This module is that seam.

Everything here is *construction only*: no rows are read, no run is executed.
Callers that want a run use ``queue_runner.run_librarian_queue``.

The DB and embedding imports are deliberately function-local. The rest of the
librarian package is hermetically testable precisely because it never imports
the database at module scope, and this module is the boundary where that stops
being true — keeping the imports inside the call preserves it for everyone else.
"""

from cre_logging import get_logger

logger = get_logger(__name__)

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional, Sequence

from application.utils.librarian.config_loader import LibrarianConfig, load_config
from application.utils.librarian.pipeline import Reranker, Retriever, Scaler

_CRE_EXT_RE = re.compile(r"^\d{3}-\d{3}$")


@dataclass(frozen=True)
class LibrarianComponents:
    """The three live stages plus the CRE id registry, built once and reused.

    ``known_cre_ids`` is the set of ``cre.external_id`` values C.0.5 may resolve
    against (ids that have a hub embedding). ``cre_id_map`` maps those external
    ids onto the hub key used in envelopes (usually the CRE UUID).
    ``cre_membership`` is every real ``cre.id`` / ``cre.external_id`` the emit
    path may stamp on a ProposedLink (C.4 grounding).
    """

    retriever: Retriever
    reranker: Reranker
    scaler: Scaler
    known_cre_ids: FrozenSet[str]
    cre_id_map: Mapping[str, str] = field(default_factory=dict)
    #: Real ``cre.id`` / ``cre.external_id`` values for emit-time grounding.
    #: ``None`` means grounding is off (hermetic stubs / hand-built components);
    #: an empty frozenset is active and rejects every id.
    cre_membership: Optional[FrozenSet[str]] = None
    #: C.0.6 graph/family prior; when set, C.1 is wrapped in ``PriorCagedRetriever``.
    cre_prior: Optional[Any] = None
    #: Grounded shortlist judge LLM (system, user) -> text. None disables lever C.
    shortlist_llm_fn: Optional[Callable[[str, str], str]] = None


def build_scaler(config: Optional[LibrarianConfig] = None) -> Scaler:
    """The C.3 calibrator at the configured temperature.

    ``T`` is not learned here. It is fitted offline by
    ``scripts/evaluate_librarian.py --use_live_embeddings`` and set as
    ``CRE_LIBRARIAN_TEMPERATURE``; the default 1.0 means *uncalibrated*, so a
    deployment that never ran the fit gets a plain softmax rather than a
    confidence dressed up as calibrated.
    """
    from application.utils.librarian.calibration.temperature import TemperatureScaler

    config = config or load_config()
    if config.temperature == 1.0:
        logger.warning(
            "CRE_LIBRARIAN_TEMPERATURE is 1.0 (uncalibrated). Fit it with "
            "scripts/evaluate_librarian.py --use_live_embeddings and set the "
            "value it prints, or the C.4 threshold is being applied to an "
            "uncalibrated confidence."
        )
    return TemperatureScaler(config.temperature)


def build_components(
    database: Any,
    *,
    config: Optional[LibrarianConfig] = None,
    embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
) -> LibrarianComponents:
    """Construct C.1 + C.2 + C.3 against a connected OpenCRE database.

    Args:
        database: a connected ``db.Node_collection`` (the caller owns it, the
            same way Module B's ``run_noise_filter`` takes a session it did not
            open).
        config: Module C settings; defaults to ``load_config()``.
        embed_fn: text -> embedding. Defaults to the prompt handler's embedder,
            which calls the paid embedding API; injectable so a caller can
            supply a local or fake embedder.

    Raises whatever the pgvector guard raises when that backend is configured
    but unavailable — deliberately, rather than falling back to a different
    retrieval path and producing silently different rankings.
    """
    from application.defs import cre_defs as defs
    from application.utils.librarian.candidate_retriever import (
        CandidatePool,
        RetrieverBackend,
        build_retriever,
    )
    from application.utils.librarian.cross_encoder import (
        CrossEncoderReranker,
        build_cross_encoder_score_fn,
    )

    config = config or load_config()
    backend = RetrieverBackend(config.retriever_backend)

    if backend is RetrieverBackend.pgvector:
        from application.database.pgvector_utils import fail_pgvector_unavailable

        if not database.can_use_pgvector_similarity():
            fail_pgvector_unavailable(
                context="CRE_LIBRARIAN_RETRIEVER_BACKEND=pgvector"
            )

    if embed_fn is None:
        from application.prompt_client import prompt_client

        embed_fn = prompt_client.PromptHandler(database=database).get_text_embeddings

    cre_embeddings = database.get_embeddings_by_doc_type(defs.Credoctypes.CRE.value)
    # C.2 hybrid-ranks the shortlist (vector + CRE name/title + down-weighted CE
    # inside small prior cages). CRE names feed the lexical name boost.
    cre_names = _cre_names_by_hub_key(database)
    cre_texts = database.get_embedding_contents_by_doc_type(defs.Credoctypes.CRE.value)
    if config.cre_text_enrich:
        from application.utils.librarian.cre_text import (
            enrich_cre_contents,
            load_linked_standard_refs,
        )

        cre_texts = enrich_cre_contents(
            cre_texts, load_linked_standard_refs(database), cre_names
        )

    summary_vectors = None
    if config.cre_summary:
        from application.utils.librarian.cre_summary import (
            default_cache_dir,
            default_llm_fn,
            inject_cre_summaries,
            load_cre_records,
        )
        from application.utils.librarian.cre_text import load_linked_standard_refs

        try:
            cre_texts, summary_vectors = inject_cre_summaries(
                cre_texts=cre_texts,
                records=load_cre_records(database),
                linked=load_linked_standard_refs(database),
                llm_fn=default_llm_fn(),
                cache_dir=default_cache_dir(),
                embed_fn=embed_fn,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "CRE_LIBRARIAN_CRE_SUMMARY inject failed; keeping hub CRE texts",
                exc_info=True,
            )
            summary_vectors = None
        else:
            if summary_vectors:
                logger.info(
                    "CRE_LIBRARIAN_CRE_SUMMARY: in-memory C.1 pool from %s summaries",
                    len(summary_vectors),
                )
            else:
                logger.info(
                    "CRE_LIBRARIAN_CRE_SUMMARY: C.2 text only (no in-memory vectors)"
                )

    # in_memory holds the hub matrix in RAM; pgvector ranks in the DB over the
    # embedding_vec column and needs no pool. Both satisfy the same retrieve().
    # Hidden CRE summaries may replace the C.1 pool for this process only —
    # never persisted to Postgres embeddings. Dual index keeps the name-stub
    # hub *and* the summary hub: header titles search names, body searches
    # summaries.
    if summary_vectors:
        summary_pool = CandidatePool.from_mapping(summary_vectors)
        summary_retriever = build_retriever(
            RetrieverBackend.in_memory,
            embed_fn=embed_fn,
            top_k=config.top_k_retrieval,
            threshold=config.link_threshold,
            pool=summary_pool,
            cre_names=cre_names,
        )
        if config.dual_index and cre_embeddings:
            from application.utils.librarian.dual_index_retriever import (
                DualIndexRetriever,
            )

            name_pool = CandidatePool.from_mapping(cre_embeddings)
            name_retriever = build_retriever(
                RetrieverBackend.in_memory,
                embed_fn=embed_fn,
                top_k=config.top_k_retrieval,
                threshold=config.link_threshold,
                pool=name_pool,
                cre_names=cre_names,
            )
            retriever = DualIndexRetriever(
                name_retriever,
                summary_retriever,
                top_k=config.top_k_retrieval,
                threshold=config.link_threshold,
            )
            logger.info(
                "CRE_LIBRARIAN_DUAL_INDEX: header→%s names, body→%s summaries",
                len(cre_embeddings),
                len(summary_vectors),
            )
        else:
            retriever = summary_retriever
    else:
        pool = (
            CandidatePool.from_mapping(cre_embeddings)
            if backend is RetrieverBackend.in_memory
            else None
        )
        retriever = build_retriever(
            backend,
            embed_fn=embed_fn,
            top_k=config.top_k_retrieval,
            threshold=config.link_threshold,
            pool=pool,
            connection=(
                database.session.connection()
                if backend is RetrieverBackend.pgvector
                else None
            ),
        )

    reranker = CrossEncoderReranker(
        score_fn=build_cross_encoder_score_fn(config.crossencoder_model),
        top_n=config.top_k_rerank,
        cre_texts=cre_texts,
        cre_names=cre_names,
        hybrid_beta=config.hybrid_beta,
        hybrid_gamma=config.hybrid_gamma,
    )

    known_external, cre_id_map = _hub_external_registry(database, cre_embeddings)
    cre_membership, membership_map = _cre_table_membership(database, cre_embeddings)
    # Prefer table UUID canonicalisation; fall back to hub external→key map.
    merged_map = {**cre_id_map, **membership_map}

    _install_taxonomy_index(database)
    cre_prior = _build_cre_prior(database)
    edition_transfer = _build_edition_transfer(database)
    control_names = _build_control_name_index(database)
    exact_names = _build_exact_name_index(database)
    parent_index = _build_parent_index(database)
    standard_links = _build_standard_link_index(database)
    neighbor_transfer = _build_neighbor_transfer_index(database)
    if cre_prior is not None and config.prior_cage:
        from application.utils.librarian.prior_caged_retriever import (
            PriorCagedRetriever,
        )

        retriever = PriorCagedRetriever(
            retriever,
            cre_prior,
            edition_transfer=edition_transfer,
            control_name_index=control_names,
            exact_name_index=exact_names,
            parent_index=parent_index,
            standard_links=standard_links,
            neighbor_transfer=neighbor_transfer,
        )

    if config.standard_retrieval:
        retriever = _maybe_wrap_standard_hop(
            retriever,
            database,
            config=config,
            embed_fn=embed_fn,
            backend=backend,
            cre_names=cre_names,
        )

    shortlist_llm = None
    try:
        from application.utils.librarian.shortlist_judge import (
            default_litellm_fn,
            judge_enabled,
        )

        if judge_enabled():
            shortlist_llm = default_litellm_fn()
    except Exception:  # noqa: BLE001
        logger.warning(
            "shortlist judge LLM unavailable; lever C disabled", exc_info=True
        )

    return LibrarianComponents(
        retriever=retriever,
        reranker=reranker,
        scaler=build_scaler(config),
        known_cre_ids=known_external,
        cre_id_map=merged_map,
        cre_membership=cre_membership,
        cre_prior=cre_prior,
        shortlist_llm_fn=shortlist_llm,
    )


def _maybe_wrap_standard_hop(
    retriever: Retriever,
    database: Any,
    *,
    config: LibrarianConfig,
    embed_fn: Callable[[str], Sequence[float]],
    backend: Any,
    cre_names: Mapping[str, str],
) -> Retriever:
    """Union Standard-prose hits (via Links) when the Standard hub is usable."""
    from application.defs import cre_defs as defs
    from application.utils.librarian.candidate_retriever import (
        CandidatePool,
        RetrieverBackend,
        build_retriever,
    )
    from application.utils.librarian.standard_hop_retriever import StandardHopRetriever

    try:
        std_emb = database.get_embeddings_by_doc_type(defs.Credoctypes.Standard.value)
    except Exception:  # noqa: BLE001
        logger.warning("standard embeddings unavailable; skip hop", exc_info=True)
        return retriever
    if not std_emb:
        logger.warning("CRE_LIBRARIAN_STANDARD_RETRIEVAL on but Standard hub is empty")
        return retriever
    hops = _node_to_cre_hops(database)
    if not hops:
        logger.warning("standard retrieval on but no cre_node_links; skip hop")
        return retriever
    try:
        std_retriever = build_retriever(
            backend,
            embed_fn=embed_fn,
            top_k=config.standard_top_k,
            threshold=config.link_threshold,
            pool=(
                CandidatePool.from_mapping(std_emb)
                if backend is RetrieverBackend.in_memory
                else None
            ),
            connection=(
                database.session.connection()
                if backend is RetrieverBackend.pgvector
                and getattr(database, "session", None) is not None
                else None
            ),
            doc_type=defs.Credoctypes.Standard.value,
            id_column="node_id",
        )
    except Exception:  # noqa: BLE001
        logger.warning("could not build Standard retriever; skip hop", exc_info=True)
        return retriever
    contents = database.get_embedding_contents_by_doc_type(
        defs.Credoctypes.Standard.value
    )
    return StandardHopRetriever(
        inner=retriever,
        standard_retriever=std_retriever,
        node_to_cres=hops,
        node_contents=contents,
        node_names=_node_names_by_id(database),
        allowed_families=config.standard_retrieval_families or None,
        max_cres_per_hit=config.standard_max_cres_per_hit,
        cre_names=cre_names,
    )


def _node_to_cre_hops(database: Any) -> Dict[str, tuple]:
    session = getattr(database, "session", None)
    if session is None:
        return {}
    try:
        from collections import defaultdict

        from application.database.db import Links

        grouped: Dict[str, list] = defaultdict(list)
        for node_id, cre_id in session.query(Links.node, Links.cre).all():
            if node_id and cre_id:
                grouped[str(node_id)].append(str(cre_id))
        return {key: tuple(vals) for key, vals in grouped.items()}
    except Exception:  # noqa: BLE001
        logger.debug("node→CRE hop index unavailable", exc_info=True)
        return {}


def _node_names_by_id(database: Any) -> Dict[str, str]:
    session = getattr(database, "session", None)
    if session is None:
        return {}
    try:
        from application.database.db import Node

        return {
            str(row.id): str(row.name or "")
            for row in session.query(Node.id, Node.name).all()
            if row.id
        }
    except Exception:  # noqa: BLE001
        logger.debug("node names unavailable", exc_info=True)
        return {}


def _install_taxonomy_index(database: Any) -> None:
    """Load Node ``document_metadata.oie`` into the process-wide TaxonomyIndex."""
    session = getattr(database, "session", None)
    if session is None:
        return
    try:
        from application.utils.librarian.oie_taxonomy import (
            load_taxonomy_index_from_session,
            set_default_taxonomy_index,
        )

        set_default_taxonomy_index(load_taxonomy_index_from_session(session))
    except Exception:  # noqa: BLE001
        logger.debug("OIE taxonomy index unavailable", exc_info=True)


def _build_cre_prior(database: Any) -> Optional[Any]:
    """Load C.0.6 prior from CRE rows + linked standard names. None if no session."""
    session = getattr(database, "session", None)
    if session is None:
        return None
    try:
        from collections import defaultdict

        from application.database.db import CRE, Links, Node
        from application.utils.librarian.cre_prior import build_cre_prior_index
        from application.utils.librarian.oie_taxonomy import (
            get_default_taxonomy_index,
            load_taxonomy_index_from_session,
            set_default_taxonomy_index,
        )

        # Ensure taxonomy is available for related/transfer maps.
        tax = get_default_taxonomy_index()
        if not tax.section_id_to_class:
            tax = load_taxonomy_index_from_session(session)
            set_default_taxonomy_index(tax)

        cres = session.query(CRE).all()
        linked_names: Dict[str, list] = defaultdict(list)
        for cre_id, node_name in (
            session.query(Links.cre, Node.name).join(Node, Node.id == Links.node).all()
        ):
            if node_name:
                linked_names[cre_id].append(str(node_name))
        return build_cre_prior_index(
            cre_rows=cres, linked_names_by_cre=linked_names, taxonomy=tax
        )
    except Exception:  # noqa: BLE001
        logger.debug("CRE prior index unavailable", exc_info=True)
        return None


def _build_edition_transfer(database: Any) -> Optional[Any]:
    """Predecessor-edition remap service (LLM cached). None if no session."""
    session = getattr(database, "session", None)
    if session is None:
        return None
    try:
        from application.utils.librarian.edition_remap import (
            build_edition_transfer_from_db,
            default_litellm_fn,
        )

        return build_edition_transfer_from_db(session, llm_fn=default_litellm_fn())
    except Exception:  # noqa: BLE001
        logger.debug("edition transfer service unavailable", exc_info=True)
        return None


def _build_control_name_index(database: Any) -> Optional[Any]:
    """Cross-standard control-title → CRE seed index. None if no session."""
    session = getattr(database, "session", None)
    if session is None:
        return None
    try:
        from application.utils.librarian.control_name_seed import (
            build_control_name_index,
        )

        return build_control_name_index(session)
    except Exception:  # noqa: BLE001
        logger.debug("control-name index unavailable", exc_info=True)
        return None


def _build_exact_name_index(database: Any) -> Optional[Any]:
    session = getattr(database, "session", None)
    if session is None:
        return None
    try:
        from application.utils.librarian.umbrella_promote import build_exact_name_index

        return build_exact_name_index(session)
    except Exception:  # noqa: BLE001
        logger.debug("exact-name index unavailable", exc_info=True)
        return None


def _build_standard_link_index(database: Any) -> Optional[Any]:
    """Hub Links for known standard families (LLM, K8s, Top10, API, …)."""
    session = getattr(database, "session", None)
    if session is None:
        return None
    try:
        from application.utils.librarian.standard_link_seed import (
            build_standard_link_index,
        )

        return build_standard_link_index(session)
    except Exception:  # noqa: BLE001
        logger.debug("standard link index unavailable", exc_info=True)
        return None


def _build_neighbor_transfer_index(database: Any) -> Optional[Any]:
    """Organic neighbor winners + heuristic topic remap for brand-new catalogs.

    LLM neighbor remap is off by default: B2 showed Pro remap noisy (API
    regression). Title latch + heuristic remap remain; K8s is heuristic-only
    even if a caller later injects ``llm_fn``.
    """
    session = getattr(database, "session", None)
    if session is None:
        return None
    try:
        from application.utils.librarian.neighbor_transfer import (
            build_neighbor_transfer_index,
        )

        return build_neighbor_transfer_index(session, llm_fn=None)
    except Exception:  # noqa: BLE001
        logger.debug("neighbor transfer index unavailable", exc_info=True)
        return None


def _build_parent_index(database: Any) -> Optional[Any]:
    session = getattr(database, "session", None)
    if session is None:
        return None
    try:
        from application.utils.librarian.umbrella_promote import build_parent_index

        return build_parent_index(session)
    except Exception:  # noqa: BLE001
        logger.debug("parent index unavailable", exc_info=True)
        return None


def _cre_table_membership(
    database: Any, cre_embeddings: Mapping[str, Any]
) -> tuple[FrozenSet[str], Dict[str, str]]:
    """All real CRE ids (UUID + external_id) for emit-time grounding.

    Hub embedding keys are included as a fallback so hermetic fakes without a
    ``cre`` session still ground against the retrieval universe.
    """
    membership: set[str] = set()
    canonical: Dict[str, str] = {}

    session = getattr(database, "session", None)
    if session is not None:
        try:
            from application.database.db import CRE

            for row in session.query(CRE.id, CRE.external_id).all():
                if row.id:
                    membership.add(row.id)
                    canonical[row.id] = row.id
                ext = (row.external_id or "").strip()
                if not ext:
                    continue
                membership.add(ext)
                if row.id:
                    canonical[ext] = row.id
                else:
                    canonical.setdefault(ext, ext)
        except Exception:  # noqa: BLE001 — hermetic fakes may lack CRE
            logger.debug("CRE table unavailable for membership registry", exc_info=True)

    for key in cre_embeddings.keys():
        membership.add(key)
        canonical.setdefault(key, key)

    return frozenset(membership), canonical


def _hub_external_registry(
    database: Any, cre_embeddings: Mapping[str, Any]
) -> tuple[FrozenSet[str], Dict[str, str]]:
    """Build C.0.5 known external ids + map to hub keys used in envelopes."""
    known: set[str] = set()
    cre_id_map: Dict[str, str] = {}
    hub_keys = set(cre_embeddings.keys())

    session = getattr(database, "session", None)
    if session is not None:
        try:
            from application.database.db import CRE

            for row in session.query(CRE.id, CRE.external_id).all():
                ext = (row.external_id or "").strip()
                if not ext:
                    continue
                if row.id in hub_keys:
                    known.add(ext)
                    cre_id_map[ext] = row.id
                elif ext in hub_keys:
                    known.add(ext)
                    cre_id_map[ext] = ext
        except Exception:  # noqa: BLE001 — hermetic fakes may lack CRE
            logger.debug("CRE table unavailable for C.0.5 registry", exc_info=True)

    for key in hub_keys:
        if _CRE_EXT_RE.match(key):
            known.add(key)
            cre_id_map.setdefault(key, key)

    return frozenset(known), cre_id_map


def _cre_names_by_hub_key(database: Any) -> Dict[str, str]:
    """Map CRE UUID / external_id → human CRE name for C.2 lexical boost."""
    names: Dict[str, str] = {}
    session = getattr(database, "session", None)
    if session is None:
        return names
    try:
        from application.database.db import CRE

        for row in session.query(CRE.id, CRE.external_id, CRE.name).all():
            name = (row.name or "").strip()
            if not name:
                continue
            if row.id:
                names[row.id] = name
            ext = (row.external_id or "").strip()
            if ext:
                names[ext] = name
    except Exception:  # noqa: BLE001
        logger.debug("CRE names unavailable for C.2 title boost", exc_info=True)
    return names


__all__ = ["LibrarianComponents", "build_components", "build_scaler"]
