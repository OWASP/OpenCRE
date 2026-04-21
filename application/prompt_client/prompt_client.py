from application.database import db
from application.defs import cre_defs
from application.prompt_client import openai_prompt_client, vertex_prompt_client
from datetime import datetime
from multiprocessing import Pool
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from io import BytesIO
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Any, Tuple, Optional
import logging

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore[misc, assignment]
import nltk
import numpy as np
import os
import json
import re
import requests

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SIMILARITY_THRESHOLD = float(os.environ.get("CHATBOT_SIMILARITY_THRESHOLD", "0.7"))


def is_valid_url(url):
    return url.startswith("http://") or url.startswith("https://")


def _is_likely_pdf_url(url: str) -> bool:
    try:
        return urlparse(url).path.lower().endswith(".pdf")
    except Exception:
        return False


def _playwright_forced_download_error(exc: BaseException) -> bool:
    """Playwright ``goto`` fails when the navigation triggers a file download (e.g. PDF)."""
    return "download is starting" in str(exc).lower()


def _fetch_pdf_text_for_embeddings(url: str) -> Optional[str]:
    """
    Download a PDF via HTTP and extract plain text for embedding.
    Used when the URL is clearly a PDF or when Playwright reports a download response.
    """
    max_bytes = int(os.environ.get("CRE_EMBED_MAX_PDF_BYTES", str(50 * 1024 * 1024)))
    headers = {
        "User-Agent": os.environ.get(
            "CRE_EMBED_REQUEST_USER_AGENT",
            "OpenCRE-embeddings/1.0 (+https://opencre.org)",
        )
    }
    logger.info("Fetching PDF for embeddings: %s", url)
    try:
        with requests.get(
            url,
            timeout=(30, 120),
            headers=headers,
            stream=True,
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            buf = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    logger.warning(
                        "PDF from %s exceeded CRE_EMBED_MAX_PDF_BYTES=%s",
                        url,
                        max_bytes,
                    )
                    return None
        data = bytes(buf)
    except requests.RequestException as e:
        logger.error("PDF fetch failed for %s: %s", url, e)
        return None

    probe = data[: min(len(data), 2048)]
    pdf_mark = probe.find(b"%PDF")
    if pdf_mark < 0:
        logger.warning("Response from %s is not a PDF (missing %%PDF marker)", url)
        return None
    if pdf_mark > 0:
        data = data[pdf_mark:]

    if PdfReader is None:
        logger.error(
            "pypdf is required for PDF embedding extraction; add it to the environment"
        )
        return None

    try:
        reader = PdfReader(BytesIO(data))
        parts: List[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t and t.strip():
                parts.append(t.strip())
        return "\n".join(parts) if parts else None
    except Exception as e:
        logger.error("PDF parse failed for %s: %s", url, e)
        return None


def normalize_embeddings_content(text: Optional[str]) -> str:
    if not text:
        return ""
    # Normalize whitespace so cache comparisons are stable across import/export and crawling.
    return re.sub(r"\s+", " ", text).strip()


def stable_json(v: Any) -> str:
    """
    Canonical JSON encoding for embedding cache comparisons.
    """
    if v is None:
        v = {}
    try:
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return json.dumps(
            str(v), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


def _embedding_text_from_node_resource_fields(node: Any) -> str:
    """Text from DB-backed node fields only (no HTTP). ``__repr__`` uses ``todict()``."""
    return normalize_embeddings_content(node.__repr__())


class in_memory_embeddings:
    __instance = None
    __webkit = None
    __browser = None
    __context = None
    __playwright = None
    ai_client = None

    def __init__(cls):
        raise ValueError(
            "class in_memory_embeddings is a singleton, please call instance() instead"
        )

    # Function to get text content from a URL
    def get_content(self, url) -> Optional[str]:
        for attempts in range(1, 10):
            if _is_likely_pdf_url(url):
                text = _fetch_pdf_text_for_embeddings(url)
                if text:
                    return text
                logger.warning(
                    "PDF URL %s: no extractable text after fetch (attempt %s/9)",
                    url,
                    attempts,
                )
                continue

            page = None
            try:
                page = self.__context.new_page()
                logger.info(f"loading page {url}")
                page.goto(url)
                text = page.locator("body").inner_text()
                return text
            except requests.exceptions.RequestException as e:
                logger.error(
                    f"Error fetching content for URL: {url} - {str(e)} (attempt {attempts}/9)"
                )
                # Retry rather than silently embedding empty content.
                continue
            except PlaywrightTimeoutError as te:
                logger.error(
                    f"Page: {url}, took too long to load, playwright timeout (attempt {attempts}/9) - {str(te)}"
                )
                continue
            except PlaywrightError as pe:
                if _playwright_forced_download_error(pe):
                    logger.info(
                        "Navigation triggered a download for %s; using PDF text extraction",
                        url,
                    )
                    text = _fetch_pdf_text_for_embeddings(url)
                    if text:
                        return text
                    logger.warning(
                        "PDF extraction failed for %s after download-style response (attempt %s/9)",
                        url,
                        attempts,
                    )
                    continue
                logger.error(
                    "Playwright error for %s (attempt %s/9): %s",
                    url,
                    attempts,
                    pe,
                )
                continue
            finally:
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass

        return None

    def clean_content(self, content):
        content = re.sub("\s+", " ", content.strip())

        # split into words
        tokens = word_tokenize(content)
        # convert to lower case
        words = [w.lower() for w in tokens]
        return " ".join(words)

    @classmethod
    def instance(cls):
        if cls.__instance is None:
            cls.__instance = cls.__new__(cls)
        return cls.__instance

    def with_ai_client(self, ai_client):
        self.ai_client = ai_client
        return self

    def setup_playwright(self):
        # in case we want to run without connectivity to ai_client or playwright
        self.__playwright = sync_playwright().start()
        nltk.download("punkt")
        nltk.download("punkt_tab")
        nltk.download("stopwords")
        self.__firefox = self.__playwright.firefox
        self.__browser = self.__firefox.launch()  # headless=False, slow_mo=1000)
        self.__context = self.__browser.new_context()

    def teardown_playwright(self):
        self.__browser.close()
        self.__playwright.stop()

    def find_missing_embeddings(self, database: db.Node_collection) -> List[str]:
        """
        Method used to update embeddings in the database, it needs an environment with access to a supported LLM and playwright

        Args:
            database (db.Node_collection): a database instance

        Returns:
            List[str]: a list of db ids which do not have embeddings
        """
        logger.info(f"syncing nodes with embeddings")
        missing_embeddings = []
        for doc_type in cre_defs.Credoctypes:
            db_ids = []
            if doc_type.value == cre_defs.Credoctypes.CRE:
                db_ids = database.list_cre_ids()
            else:
                db_ids = database.list_node_ids_by_ntype(doc_type.value)

            embeddings = database.get_embeddings_by_doc_type(doc_type.value)
            a = [
                db_id for db_id in embeddings.keys() if db_id not in db_ids
            ]  # embeddings that have no nodes (bug detection?)
            if a != []:
                logger.fatal(
                    "the following embeddings have no corresponding nodes, BUG", a
                )
            b = [db_id for db_id in db_ids if db_id not in embeddings.keys()]
            if b != []:
                missing_embeddings.extend(b)
        return missing_embeddings

    def generate_embeddings_for(self, database: db.Node_collection, item_name: str):
        """Iterates over all database documents related to the item identified by item_name
        and (re)generates embeddings when needed.
            For example if "ASVS" is passed the method will process embeddings for ASVS.
        Args:
            database (db.Node_collection): the Node_collection instance to use
            item_name (str): the item for which to generate embeddings, this can be either `cre_defs.Credoctypes.CRE.value` for generating all CRE embeddings or the name of any Standard or Tool.
        """
        db_ids = []
        if item_name == cre_defs.Credoctypes.CRE.value:
            db_ids = database.list_cre_ids()
        else:
            db_ids = database.list_node_ids_by_name(item_name)
        # Step 4 (incremental embeddings): pass all candidate IDs and let
        # generate_embeddings() skip unchanged content by comparing stored
        # embeddings_content against current extracted/serialized content.
        self.generate_embeddings(database, db_ids)

    def generate_embeddings(
        self, database: db.Node_collection, missing_embeddings: List[str]
    ):
        """
        Generate embeddings for DB ids that are missing them.

        Bonus requirement: batch Playwright-fetched page text (content for embeddings)
        so we send up to the provider's supported `max_batch_size` per embeddings call.
        """
        logger.info(f"generating {len(missing_embeddings)} embeddings")

        def get_provider_batch_size() -> int:
            # Prefer provider-reported max batch size.
            if hasattr(self.ai_client, "get_max_batch_size"):
                return int(self.ai_client.get_max_batch_size())  # type: ignore[attr-defined]
            return int(os.environ.get("CRE_EMBED_BATCH_SIZE", "50"))

        batch_size = max(1, get_provider_batch_size())

        for i in range(0, len(missing_embeddings), batch_size):
            batch_ids = missing_embeddings[i : i + batch_size]
            batch_contents: List[str] = []
            batch_records: List[Tuple[Any, Any, str]] = []

            # Collect all batch content first, so embeddings are batched in one provider call.
            for db_id in batch_ids:
                # ``missing_embeddings`` mixes CRE primary keys and node primary keys.
                # Only call ``get_nodes`` when the id exists in ``node``; CRE ids are not
                # nodes and would otherwise trigger spurious get_nodes "not found" paths.
                if not database.has_node_with_db_id(db_id):
                    cre = database.get_cre_by_db_id(db_id)
                    if cre:
                        content = normalize_embeddings_content(
                            f"{cre.doctype}\n name:{cre.name}\n description:{cre.description}\n id:{cre.id}\n "
                        )
                        if getattr(cre, "metadata", None):
                            metadata_json = stable_json(getattr(cre, "metadata", None))
                            content = normalize_embeddings_content(
                                f"{content}\nmetadata:{metadata_json}"
                            )
                        logger.info(f"making embedding for {content}")
                        dbcre = db.dbCREfromCRE(cre)
                        if not dbcre:
                            logger.fatal(cre, "cannot be converted to database CRE")
                            continue
                        dbcre.id = db_id

                        existing = database.get_embedding(db_id)
                        if (
                            existing
                            and normalize_embeddings_content(
                                getattr(existing[0], "embeddings_content", None)
                            )
                            == content
                        ):
                            logger.debug(
                                f"Skipping embedding for CRE {cre.id} ({db_id}): content unchanged"
                            )
                            continue

                        batch_contents.append(content)
                        batch_records.append((dbcre, cre_defs.Credoctypes.CRE, content))
                    else:
                        logger.warning(
                            f"missing embeddings id={db_id} not found in CRE or Node"
                        )
                    continue

                nodes = database.get_nodes(db_id=db_id)

                if nodes:
                    node = nodes[0] if isinstance(nodes, list) else nodes
                    if is_valid_url(node.hyperlink):
                        raw_content = self.get_content(node.hyperlink)
                        content_from_remote = ""
                        if raw_content:
                            content_from_remote = normalize_embeddings_content(
                                self.clean_content(raw_content)
                            )
                            # Step 4b: metadata must affect embedding meaning/caching.
                            # When embeddings are derived from fetched URL content,
                            # fetched body does not include node.__repr__ / todict fields.
                            if getattr(node, "metadata", None):
                                metadata_json = stable_json(
                                    getattr(node, "metadata", None)
                                )
                                content_from_remote = normalize_embeddings_content(
                                    f"{content_from_remote}\nmetadata:{metadata_json}"
                                )

                        if content_from_remote:
                            content = content_from_remote
                        else:
                            content = _embedding_text_from_node_resource_fields(node)
                            if raw_content:
                                logger.info(
                                    "Remote text for %s cleaned to empty; using stored node fields for embedding",
                                    node.hyperlink,
                                )
                            else:
                                logger.info(
                                    "No extractable remote text for %s; using stored node fields for embedding",
                                    node.hyperlink,
                                )

                        if not content:
                            logger.warning(
                                "Skipping embedding for %s: no text from remote or stored node fields",
                                node.hyperlink,
                            )
                            continue
                    else:
                        content = normalize_embeddings_content(node.__repr__())

                    dbnode = db.dbNodeFromNode(node)
                    if not dbnode:
                        logger.fatal(node, "cannot be converted to database Node")
                        continue

                    dbnode.id = db_id
                    logger.info(
                        f"making embedding for {node.hyperlink if node.hyperlink else content}"
                    )

                    existing = database.get_embedding(db_id)
                    if (
                        existing
                        and normalize_embeddings_content(
                            getattr(existing[0], "embeddings_content", None)
                        )
                        == content
                    ):
                        logger.debug(
                            f"Skipping embedding for {node.name} ({db_id}): content unchanged"
                        )
                        continue

                    batch_contents.append(content)
                    batch_records.append((dbnode, node.doctype, content))
                    continue

                logger.warning(
                    f"missing embeddings id={db_id} not found in CRE or Node"
                )

            if not batch_contents:
                continue

            embeddings = self.ai_client.get_text_embeddings(batch_contents)  # type: ignore[arg-type]

            # Normalize shape: some providers may return a single vector even for list input.
            if embeddings and isinstance(embeddings[0], (int, float)):  # type: ignore[index]
                logger.warning(
                    "provider returned unexpected embedding shape for batch; falling back to per-item calls"
                )
                embeddings = [self.ai_client.get_text_embeddings(t) for t in batch_contents]  # type: ignore[arg-type]

            if len(embeddings) != len(batch_records):  # type: ignore[arg-type]
                logger.warning(
                    "provider returned embeddings length mismatch; falling back to per-item calls"
                )
                embeddings = [
                    self.ai_client.get_text_embeddings(t)  # type: ignore[arg-type]
                    for t in batch_contents
                ]

            for rec, emb in zip(batch_records, embeddings):
                db_obj, doc_type, embedding_text = rec
                database.add_embedding(db_obj, doc_type, emb, embedding_text)


class PromptHandler:
    ai_client = None  # a client instance for a support Chat model
    database: db.Node_collection = None  # instance of our primary db
    embeddings_instance = None  # instance of our in_memory_embeddings singletton

    def __init__(self, database: db.Node_collection, load_all_embeddings=False) -> None:
        self.ai_client = None
        if os.environ.get("GCP_NATIVE") or os.environ.get("GEMINI_API_KEY"):
            logger.info("using Google Vertex AI engine")
            self.ai_client = vertex_prompt_client.VertexPromptClient()
        elif os.getenv("OPENAI_API_KEY"):
            logger.info("using Open AI engine")
            self.ai_client = openai_prompt_client.OpenAIPromptClient(
                os.getenv("OPENAI_API_KEY")
            )
        else:
            logger.error(
                "cannot instantiate ai client, neither OPENAI_API_KEY nor GEMINI_API_KEY are set "
            )
        self.database = database
        self.embeddings_instance = in_memory_embeddings.instance().with_ai_client(
            ai_client=self.ai_client
        )
        if not os.environ.get("NO_GEN_EMBEDDINGS") and load_all_embeddings:
            missing_embeddings = self.embeddings_instance.find_missing_embeddings(
                database
            )
            if missing_embeddings:
                self.embeddings_instance.setup_playwright()
                self.embeddings_instance.generate_embeddings(
                    database, missing_embeddings
                )
                self.embeddings_instance.teardown_playwright()
            else:
                logger.info(
                    f"there are {len(missing_embeddings)} embeddings missing from the dataset, db inclompete"
                )

    def generate_embeddings_for(self, item_name: str):
        # CRE embeddings are generated from the CRE's textual fields only
        # (name/description/id). That path does not require fetching remote
        # content via Playwright, so we can skip browser launch entirely and
        # batch requests to avoid provider rate limits.
        if item_name == cre_defs.Credoctypes.CRE.value:
            # list_cre_ids() returns plain CRE database ids (strings).
            cre_ids = self.database.list_cre_ids()
            pending: List[str] = []
            cre_by_id: Dict[str, cre_defs.CRE] = {}

            for cid in cre_ids:
                cre = self.database.get_cre_by_db_id(cid)
                if not cre:
                    continue
                embedding_text = f"{cre.doctype}\n name:{cre.name}\n description:{cre.description}\n id:{cre.id}\n "
                if getattr(cre, "metadata", None):
                    metadata_json = stable_json(getattr(cre, "metadata", None))
                    embedding_text = f"{embedding_text}\nmetadata:{metadata_json}"
                embedding_text = normalize_embeddings_content(embedding_text)
                existing = self.database.get_embedding(cid)
                if (
                    existing
                    and normalize_embeddings_content(
                        getattr(existing[0], "embeddings_content", None)
                    )
                    == embedding_text
                ):
                    continue
                pending.append(cid)
                cre_by_id[cid] = cre

            if not pending:
                return

            # Batch size is adjustable via env var to tune for quota/limits.
            if hasattr(self.ai_client, "get_max_batch_size"):
                batch_size = int(self.ai_client.get_max_batch_size())  # type: ignore[attr-defined]
            else:
                batch_size = int(os.environ.get("CRE_EMBED_BATCH_SIZE", "50"))
            batch_size = max(1, batch_size)
            for i in range(0, len(pending), batch_size):
                batch_ids = pending[i : i + batch_size]

                contents: List[str] = []
                for cid in batch_ids:
                    cre = cre_by_id[cid]
                    contents.append(
                        f"{cre.doctype}\n name:{cre.name}\n description:{cre.description}\n id:{cre.id}\n "
                    )
                contents = [normalize_embeddings_content(c) for c in contents]

                embeddings = self.ai_client.get_text_embeddings(contents)  # type: ignore[arg-type]
                if not embeddings:
                    raise RuntimeError(
                        "Embedding provider returned no embeddings for CRE batch"
                    )

                # Some providers might return a single vector if given a single item.
                if isinstance(embeddings[0], (int, float)):  # type: ignore[index]
                    embeddings = [embeddings]  # type: ignore[assignment]

                if len(embeddings) != len(batch_ids):
                    # Shape mismatch; fall back to per-item calls.
                    fixed: List[List[float]] = []
                    for ctext in contents:
                        fixed.append(self.ai_client.get_text_embeddings(ctext))  # type: ignore[arg-type]
                    embeddings = fixed

                for cid, emb, embedding_text in zip(batch_ids, embeddings, contents):
                    dbcre = db.dbCREfromCRE(cre_by_id[cid])
                    dbcre.id = cid
                    self.database.add_embedding(
                        dbcre,
                        cre_defs.Credoctypes.CRE,
                        emb,  # type: ignore[arg-type]
                        embedding_text,
                    )

            return

        self.embeddings_instance.setup_playwright()
        self.embeddings_instance.generate_embeddings_for(self.database, item_name)
        self.embeddings_instance.teardown_playwright()

    def __load_cre_embeddings(
        self, db_embeddings: Dict[str, List[float]]
    ) -> Tuple[List[List[float]], List[str]]:
        existing_cre_embeddings = []
        existing_cre_ids = []
        for id, e in db_embeddings.items():
            existing_cre_embeddings.append(e)
            existing_cre_ids.append(id)
        return (
            sparse.csr_matrix(np.array(existing_cre_embeddings).astype(np.float64)),
            existing_cre_ids,
        )

    def __load_node_embeddings(
        self, db_node_embeddings: Dict[str, List[float]]
    ) -> Tuple[List[List[float]], List[str]]:
        """
            given a Dict of [node_id,[embeddings]] returns two lists,
            one with the keys and one with the values, both in order so we can match values to keys
            this is because Dict.values() and Dict.keys() does not guarantee the order of the elements

        Args:
            db_node_embeddings (Dict[str, List[float]]): _description_

        Returns:
            Tuple[List[List[float]], List[str]]: _description_
        """
        existing_node_embeddings = []
        existing_node_ids = []
        for id, e in db_node_embeddings.items():
            existing_node_embeddings.append(e)
            existing_node_ids.append(id)
        return (
            sparse.csr_matrix(np.array(existing_node_embeddings).astype(np.float64)),
            existing_node_ids,
        )

    def get_id_of_most_similar_cre(self, item_embedding: List[float]) -> Optional[str]:
        """
            Backend method, to be used mostly for importing and data processing.


        Args:
            item_embedding (List[float]): _description_

        Returns:
            str: _description_
        """
        if not hasattr(self, "existing_cre_embeddings"):
            (
                self.existing_cre_embeddings,
                self.existing_cre_ids,
            ) = self.__load_cre_embeddings(
                self.database.get_embeddings_by_doc_type(cre_defs.Credoctypes.CRE.value)
            )
        if not self.existing_cre_embeddings.getnnz() or not len(self.existing_cre_ids):
            logger.warning(
                "CRE embeddings empty in DB (e.g. CRE_NO_GEN_EMBEDDINGS=1 checkpoint run); "
                "cannot match by similarity — skipping CRE link suggestions"
            )
            return None
        embedding_array = sparse.csr_matrix(
            np.array(item_embedding).reshape(1, -1)
        )  # convert embedding into a 1-dimentional numpy array
        similarities = cosine_similarity(embedding_array, self.existing_cre_embeddings)
        most_similar_index = np.argmax(similarities)
        if np.max(similarities) < SIMILARITY_THRESHOLD:
            logger.info(
                f"there is no good cre candidate for this standard section,closest similarity: {np.max(similarities)} returning nothing"
            )
            return None
        id = self.existing_cre_ids[most_similar_index]
        logger.info(f"found match with similarity {np.max(similarities)}, id {id}")
        return id

    def get_id_of_most_similar_node(
        self, standard_text_embedding: List[float]
    ) -> Optional[str]:
        """
        Backend method, used for importing standards, this matches the embedding of the text of a standard section
        to the closest embedding from existing standards using cosine similarity.

        Since this loads all embeddings in memory for performance reasons, its memory footprint is very large

        Args:
            standard_text_embedding (List[float]): the embeddings of what we are trying to match

        Returns:
            str: the database id of the closest database standard
        """
        if not hasattr(self, "existing_node_embeddings"):
            (
                self.existing_node_embeddings,
                self.existing_node_ids,
            ) = self.__load_node_embeddings(
                self.database.get_embeddings_by_doc_type(
                    cre_defs.Credoctypes.Standard.value
                )
            )
        if not self.existing_node_embeddings.getnnz() or not len(
            self.existing_node_ids
        ):
            logger.warning(
                "Standard node embeddings empty in DB (e.g. CRE_NO_GEN_EMBEDDINGS=1 "
                "checkpoint run); cannot match by similarity — skipping standard link suggestions"
            )
            return None

        embedding_array = sparse.csr_matrix(
            np.array(standard_text_embedding).reshape(1, -1)
        )  # convert embedding into a 1-dimentional numpy array
        similarities = cosine_similarity(embedding_array, self.existing_node_embeddings)
        most_similar_index = np.argmax(similarities)
        id = self.existing_node_ids[most_similar_index]
        return id

    def get_text_embeddings(self, text):
        return self.ai_client.get_text_embeddings(text)

    def get_id_of_most_similar_cre_paginated(
        self,
        item_embedding: List[float],
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> Optional[Tuple[str, float]]:
        """this method is meant to be used when CRE runs in a web server with limited memory (e.g. firebase/heroku)
            instead of loading all our embeddings in memory we take the slower approach of paginating them

        Args:
            item_embedding (List[float]): embeddings of the item we want to match against CREs

        Returns:
            str: the ID of the CRE with the closest cosine_similarity
        """
        embedding_array = sparse.csr_matrix(
            np.array(item_embedding).reshape(1, -1)
        )  # convert embedding into a 1-dimentional numpy array

        (
            embeddings,
            total_pages,
            starting_page,
        ) = self.database.get_embeddings_by_doc_type_paginated(
            cre_defs.Credoctypes.CRE.value
        )
        max_similarity = -1
        most_similar_index = 0
        most_similar_id = ""
        for page in range(starting_page, total_pages):
            existing_cres, existing_cre_ids = self.__load_cre_embeddings(embeddings)

            similarities = cosine_similarity(embedding_array, existing_cres)
            if np.max(similarities) > max_similarity:
                max_similarity = np.max(similarities)
                most_similar_index = np.argmax(similarities)
                most_similar_id = existing_cre_ids[most_similar_index]
            (
                embeddings,
                total_pages,
                _,
            ) = self.database.get_embeddings_by_doc_type_paginated(
                cre_defs.Credoctypes.CRE.value, page=page
            )

        if max_similarity < similarity_threshold:
            logger.info(
                f"there is no good cre candidate for this standard section, returning nothing"
            )
            return None, None
        return most_similar_id, max_similarity

    def get_id_of_most_similar_node_paginated(
        self,
        question_embedding: List[float],
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> Optional[Tuple[str, float]]:
        """
            this method performs cosine similarity against all nodes found in our database and returns the DB ID of the most similar node
            this method is meant to be used when CRE runs in a web server with limited memory (e.g. firebase/heroku)
            instead of loading all our embeddings in memory we take the slower approach of paginating them
        Args:
            question_embedding (List[float]): embedding of the incoming question or node to be matched against what exists in the database

        Returns:
            str: the db id of the most similar object
        """
        embedding_array = sparse.csr_matrix(
            np.array(question_embedding).reshape(1, -1)
        )  # convert embedding into a 1-dimentional numpy array
        (
            embeddings,
            total_pages,
            starting_page,
        ) = self.database.get_embeddings_by_doc_type_paginated(
            doc_type=cre_defs.Credoctypes.Standard.value,
            page=1,
        )

        max_similarity = -1
        most_similar_index = 0
        most_similar_id = ""
        for page in range(starting_page, total_pages + 1):
            existing_standards, existing_standard_ids = self.__load_node_embeddings(
                embeddings
            )
            similarities = cosine_similarity(embedding_array, existing_standards)
            if np.max(similarities) > max_similarity:
                max_similarity = np.max(similarities)
                most_similar_index = int(np.argmax(similarities))
                most_similar_id = existing_standard_ids[most_similar_index]

            embeddings, _, _ = self.database.get_embeddings_by_doc_type_paginated(
                doc_type=cre_defs.Credoctypes.Standard.value, page=page
            )
        if max_similarity < similarity_threshold:
            logger.info(
                f"there is no good standard candidate for this other standard section, returning nothing, max similarity was {max_similarity}"
            )
            return None, None
        return most_similar_id, max_similarity

    def generate_text(self, prompt: str) -> Dict[str, str]:
        """
        Generate text is a frontend method used for the chatbot
        It matches the prompt/user question to an embedding from our database and then sends both the
        text that generated the embedding and the user prompt to an llm for explaining

        Args:
            prompt (str): user question

        Returns:
            Dict[str,str]: a dictionary with the response and the closest object
        """
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        if not prompt:
            return {"response": "", "table": "", "timestamp": timestamp}
        logger.debug(f"getting embeddings for {prompt}")
        question_embedding = self.ai_client.get_text_embeddings(prompt)
        logger.debug(f"retrieved embeddings for {prompt}")

        # Find the closest area in the existing embeddings
        closest_id, similarity = self.get_id_of_most_similar_node_paginated(
            question_embedding,
            similarity_threshold=SIMILARITY_THRESHOLD,
        )
        closest_object = None
        if closest_id:
            closest_object = self.database.get_nodes(db_id=closest_id)
            if len(closest_object) > 0:
                closest_object = closest_object[0]
            logger.info(
                f"The prompt {prompt}, was most similar to object \n{closest_object}\n, with similarity:{similarity}"
            )

        answer = ""
        closest_content = ""
        accurate = False
        if closest_object:
            if closest_object.hyperlink:
                emb = self.database.get_embedding(closest_id)
                if emb:
                    closest_content = emb[0].embeddings_content

            closest_object_str = f"{closest_content}" + "\n".join(
                [f"{k}:{v}" for k, v in closest_object.shallow_copy().todict().items()]
            )
            closest_object_str = closest_object_str[:8000]
            # vertex and openai have a model limit of 8100 characters
            answer = self.ai_client.create_chat_completion(
                prompt=prompt,
                closest_object_str=closest_object_str,
            )
            accurate = True
        else:
            answer = self.ai_client.query_llm(prompt)

        logger.debug(f"retrieved completion for {prompt}")
        table = [closest_object]
        result = f"Answer: {answer}"
        model_name = self.ai_client.get_model_name() if self.ai_client else "unknown"
        return {
            "response": result,
            "table": table,
            "accurate": accurate,
            "model_name": model_name,
        }
