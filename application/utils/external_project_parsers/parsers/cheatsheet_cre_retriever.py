import logging
import numpy as np

from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity
from typing import List

from application.database import db
from application.defs.candidate_cre_defs import CandidateCRE
from application.defs.cheatsheet_defs import CheatsheetRecord
from application.defs import cre_defs
from application.prompt_client import prompt_client

logger = logging.getLogger(__name__)


def retrieve_candidate_cres(
    record: CheatsheetRecord,
    cache: db.Node_collection,
    ph: prompt_client.PromptHandler,
    top_k: int = 20,
) -> List[CandidateCRE]:
    """Retrieve top-k CRE candidates for a CheatsheetRecord using embedding similarity.

    Args:
        record: the cheatsheet record to find CRE candidates for.
        cache: database instance for retrieving CRE embeddings.
        ph: PromptHandler instance for generating text embeddings.
        top_k: number of top candidates to return, defaults to 20.

    Returns:
        List of CandidateCRE objects sorted descending by similarity score.
    """
    # build query text from record summary and headings
    query_text = record.summary + " " + " ".join(record.headings)

    # embed query text via PromptHandler
    query_vector = ph.get_text_embeddings(query_text)

    # fetch all pre-stored CRE vectors from DB
    db_cre_embeddings = cache.get_embeddings_by_doc_type(
        cre_defs.Credoctypes.CRE.value
    )

    # build ordered lists of internal ids and their vectors
    internal_ids = list(db_cre_embeddings.keys())
    cre_matrix = sparse.csr_matrix(
        np.array(list(db_cre_embeddings.values())).astype(np.float64)
    )

    # compute cosine similarity between query and all CRE vectors
    query_array = sparse.csr_matrix(
        np.array(query_vector).reshape(1, -1).astype(np.float64)
    )
    similarities = cosine_similarity(query_array, cre_matrix)[0]

    # get top-k indices sorted descending by score
    top_k_indices = np.argsort(similarities)[::-1][:top_k]

    # fetch full CRE objects and build CandidateCRE list
    candidates = []
    for idx in top_k_indices:
        internal_id = internal_ids[idx]
        cre = cache.get_cre_by_db_id(internal_id)
        candidates.append(
            CandidateCRE(
                cre_id=cre.id,
                name=cre.name,
                description=cre.description or "",
                score=float(similarities[idx]),
            )
        )

    return candidates