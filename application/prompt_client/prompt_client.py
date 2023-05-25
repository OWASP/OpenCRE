from application.database import db
from application.defs import cre_defs
from datetime import datetime
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Any
import logging
import numpy as np
import os
import re
import requests
from playwright.sync_api import sync_playwright
import nltk
from multiprocessing import Pool
from scipy import sparse
from application.prompt_client import openai_prompt_client,vertex_prompt_client

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SIMILARITY_THRESHOLD = 0.8

def is_valid_url(url):
    return url.startswith("http://") or url.startswith("https://")


class in_memory_embeddings:
    __instance = None
    node_embeddings: Dict[str, List[float]] = {}
    cre_embeddings: Dict[str, List[float]] = {}
    __webkit = None
    __browser = None
    __context = None
    __playwright = None

    def __init__(sel):
        raise ValueError(
            "class in_memory_embeddings is a singleton, please call instance() instead"
        )

    # Function to get text content from a URL
    @classmethod
    def get_content(cls, url):
        try:
            page = cls.__context.new_page()
            logger.info(f"loading page {url}")
            page.goto(url)
            text = page.locator("body").inner_text()
            page.close()
            return text
        except requests.exceptions.RequestException as e:
            print(f"Error fetching content for URL: {url} - {str(e)}")
            return ""

    @classmethod
    def clean_content(cls, content):
        content = re.sub("\s+", "", content.strip())

        # split into words
        tokens = word_tokenize(content)
        # convert to lower case
        words = [w.lower() for w in tokens]
        # # remove punctuation from each word
        # table = str.maketrans("", "", string.punctuation)
        # stripped = [w.translate(table) for w in tokens]
        # # remove remaining tokens that are not alphabetic
        # words = [word for word in stripped if word.isalpha()]
        # filter out stop words
        # stop_words = set(stopwords.words("english"))
        # words = [w for w in words if not w in stop_words]
        return " ".join(words)

    @classmethod
    def instance(cls, database: db.Node_collection, ai_client:Any):
        if cls.__instance is None:
            cls.__instance = cls.__new__(cls)

            missing_embeddings = cls.load_embeddings(database)
            if missing_embeddings:
                if not os.environ.get(
                    "NO_GEN_EMBEDDINGS"
                ):  # in case we want to run without connectivity to ai_client or playwright
                    cls.__playwright = sync_playwright().start()
                    nltk.download("punkt")
                    nltk.download("stopwords")
                    cls.__webkit = cls.__playwright.webkit
                    cls.__browser = (
                        cls.__webkit.launch()
                    )  # headless=False, slow_mo=1000)
                    cls.__context = cls.__browser.new_context()

                    cls.generate_embeddings(database, missing_embeddings, ai_client)
                    cls.__browser.close()
                    cls.__playwright.stop()
                else:
                    logger.info(
                        f"there are {len(missing_embeddings)} embeddings missing from the dataset, your db is inclompete"
                    )
        return cls.__instance

    @classmethod
    def load_embeddings(cls, database: db.Node_collection) -> List[str]:
        logger.info(f"syncing nodes with embeddings")
        missing_embeddings = []
        for doc_type in cre_defs.Credoctypes:
            db_ids = []
            if doc_type.value == cre_defs.Credoctypes.CRE:
                db_ids = [a[0] for a in database.list_cre_ids()]
            else:
                db_ids = [a[0] for a in database.list_node_ids_by_ntype(doc_type.value)]

            embeddings = database.get_embeddings_by_doc_type(doc_type.value)
            for id, embedding in embeddings.items():
                if doc_type.value == cre_defs.Credoctypes.CRE:
                    cls.cre_embeddings[id] = embedding
                else:
                    cls.node_embeddings[id] = embedding
            a = [
                db_id for db_id in embeddings.keys() if db_id not in db_ids
            ]  # embeddings that have no nodes (bug detection?)
            b = [db_id for db_id in db_ids if db_id not in embeddings.keys()]
            if a != []:
                logger.fatal(
                    "the following embeddings have no corresponding nodes, BUG", a
                )
            if b != []:
                missing_embeddings.extend(b)
        return missing_embeddings

    @classmethod
    def generate_embeddings(
        cls,
        database: db.Node_collection,
        missing_embeddings: List[str],
        ai_client,
    ):
        """method generate embeddings accepts a list of Database IDs of object which do not have embeddings and generates embeddings for those objects"""
        logger.info(f"generating {len(missing_embeddings)} embeddings")
        for id in missing_embeddings:
            cre = database.get_cre_by_db_id(id)
            node = database.get_node_by_db_id(id)
            content = ""
            if node:
                if is_valid_url(node.hyperlink):
                    content = cls.clean_content(cls.get_content(node.hyperlink))
                else:
                    content = f"{node.doctype}\n name:{node.name}\n section:{node.section}\n subsection:{node.subsection}\n section_id:{node.sectionID}\n "
                logger.info(f"making embedding for {node.hyperlink}")

                embedding = ai_client.get_text_embeddings(content)
                dbnode = db.dbNodeFromNode(node)
                if not dbnode:
                    logger.fatal(node, "cannot be converted to database Node")
                    continue
                dbnode.id = id
                database.add_embedding(dbnode, node.doctype, embedding, content)
                cls.node_embeddings[id] = embedding
            elif cre:
                content = f"{cre.doctype}\n name:{cre.name}\n description:{cre.description}\n id:{cre.id}\n "
                logger.info(f"making embedding for {content}")
                embedding = ai_client.get_text_embeddings(content)
                dbcre = db.dbCREfromCRE(cre)
                if not dbcre:
                    logger.fatal(node, "cannot be converted to database Node")
                dbcre.id = id
                database.add_embedding(
                    dbcre, cre_defs.Credoctypes.CRE, embedding, content
                )
                cls.cre_embeddings[id] = embedding

class PromptHandler:
    def __init__(self, database: db.Node_collection) -> None:
        self.ai_client = None
        if os.environ.get("SERVICE_ACCOUNT_CREDENTIALS"):
            logger.info("using Google Vertex AI engine")
            self.ai_client = vertex_prompt_client.VertexPromptClient(
                os.environ.get("VERTEX_PROJECT_ID"),
                os.environ.get("VERTEX_PROJECT_LOCATION"),
            )
        elif os.getenv("OPENAI_API_KEY"):
            logger.info("using Open AI engine")
            self.ai_client = openai_prompt_client.OpenAIPromptClient(os.getenv("OPENAI_API_KEY"))
        else:
            logger.error("cannot instantiate ai client, neither OPENAI_API_KEY nor GOOGLE_APPLICATION_CREDENTIALS are set ")
        self.database = database
        self.embeddings_instance = in_memory_embeddings.instance(database, ai_client=self.ai_client)

        existing = []
        existing_ids = []
        for id, e in self.embeddings_instance.node_embeddings.items():
            existing.append(e)
            existing_ids.append(id)
        self.existing = sparse.csr_matrix(np.array(existing).astype(np.float64))
        self.existing_ids = existing_ids
        if not self.embeddings_instance or not self.embeddings_instance.node_embeddings:
            logger.fatal(
                f"in memory embeddings is {self.embeddings_instance} and embeddings are {self.embeddings_instance.node_embeddings} bug?"
            )

        existing_cres = []
        existing_cre_ids = []
        for id, e in self.embeddings_instance.cre_embeddings.items():
            existing_cres.append(e)
            existing_cre_ids.append(id)
        self.existing_cres = sparse.csr_matrix(
            np.array(existing_cres).astype(np.float64)
        )
        self.existing_cre_ids = existing_cre_ids
        if not self.embeddings_instance or not self.embeddings_instance.cre_embeddings:
            logger.fatal(
                f"in memory embeddings is {self.embeddings_instance} and embeddings are {self.embeddings_instance.cre_embeddings} bug?"
            )
    def get_text_embeddings(self, text):
        return self.ai_client.get_text_embeddings(text)

    def get_cre_embeddings(self):
        return self.embeddings_instance.cre_embeddings

    def get_id_of_most_similar_cre(
        self, item_embedding: List[float], embeddings: Dict[str, List[float]]
    ) -> str:
        embedding_array = sparse.csr_matrix(
            np.array(item_embedding).reshape(1, -1)
        )  # convert embedding into a 1-dimentional numpy array

        similarities = cosine_similarity(embedding_array, self.existing_cres)
        most_similar_index = np.argmax(similarities)
        if np.max(similarities) < SIMILARITY_THRESHOLD:
            logger.info(
                f"there is no good cre candidate for this standard section, returning nothing"
            )
            return None
        id = self.existing_cre_ids[most_similar_index]
        return id

    def get_id_of_most_similar_node(
        self, question_embedding: List[float], embeddings: Dict[str, List[float]]
    ) -> str:
        embedding_array = sparse.csr_matrix(
            np.array(question_embedding).reshape(1, -1)
        )  # convert embedding into a 1-dimentional numpy array
        similarities = cosine_similarity(embedding_array, self.existing)
        most_similar_index = np.argmax(similarities)
        id = self.existing_ids[most_similar_index]
        return id

    def generate_text(self, prompt: str):
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        if not prompt:
            return {"response": "", "table": "", "timestamp": timestamp}
        logger.info(f"getting embeddings for {prompt}")
        question_embedding = self.ai_client.get_text_embeddings(prompt)
        logger.info(f"retrieved embeddings for {prompt}")

        # Find the closest area in the existing embeddings
        closest_id = self.get_id_of_most_similar_node(
            question_embedding, self.embeddings_instance.node_embeddings
        )
        closest_object = self.database.get_node_by_db_id(closest_id)
        closest_object_str = "\n".join(
            [f"{k}:{v}" for k, v in closest_object.shallow_copy().todict().items()]
        )[
            :8000
        ]  # openai has a model limit of 8100 characters
        logger.info(f"most similar object is {closest_object.name}")


        answer = self.ai_client.create_chat_completion(prompt=prompt,closest_object_str=closest_object_str,)
        logger.info(f"retrieved completion from openAI for {prompt}")
        table = [closest_object]
        result = f"Answer: {answer}"
        return {"response": result, "table": table}
