from application.database import db
from application.defs import cre_defs
from datetime import datetime
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from sklearn.metrics.pairwise import cosine_similarity
from typing import Any, Dict, List, Optional, Tuple, cast
import logging
import numpy as np
import openai
import os
import re
import requests
from playwright.sync_api import sync_playwright
import nltk
from multiprocessing import Pool
from scipy import sparse

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_embeddings(openai_key: str, text: str, model: str = "text-embedding-ada-002"):
    openai.api_key = openai_key
    if len(text) > 8000:
        logger.info(
            f"embedding content is more than the openai hard limit of 8k tokens, reducing to 8000"
        )
        text = text[:8000]
    return openai.Embedding.create(input=[text], model=model)["data"][0]["embedding"]


def is_valid_url(url):
    return url.startswith("http://") or url.startswith("https://")


class in_memory_embeddings:
    __instance = None
    embeddings: Dict[str, List[float]] = {}
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
    def instance(cls, database: db.Node_collection, openai_key: str):
        if cls.__instance is None:
            cls.__instance = cls.__new__(cls)
            
            if not os.environ.get("NO_GEN_EMBEDDINGS"): # in case we want to run without connectivity to openai or playwright
                cls.__playwright = sync_playwright().start()
                nltk.download("punkt")
                nltk.download("stopwords")
                cls.__webkit = cls.__playwright.webkit
                cls.__browser = cls.__webkit.launch()  # headless=False, slow_mo=1000)
                cls.__context = cls.__browser.new_context()
                cls.generate_embeddings(database, openai_key)
                cls.__browser.close()
                cls.__playwright.stop()
        return cls.__instance

    @classmethod
    def generate_embeddings(cls, database: db.Node_collection, openai_key: str):
        logger.info(f"syncing nodes with embeddings")
        for doc_type in cre_defs.Credoctypes:
            if doc_type.value == cre_defs.Credoctypes.CRE:
                pass  # TODO: if there is ever a need to correlate with CREs, load cre embeddings
            else:
                node_ids = [
                    a[0] for a in database.list_node_ids_by_ntype(doc_type.value)
                ]
                embeddings = database.get_embeddings_by_doc_type(doc_type.value)
                for id, embedding in embeddings.items():
                    cls.embeddings[id] = embedding
                a = [
                    node_id for node_id in embeddings.keys() if node_id not in node_ids
                ]  # embeddings that have no nodes (bug detection?)
                b = [
                    node_id for node_id in node_ids if node_id not in embeddings.keys()
                ]
                if a != []:
                    logger.fatal(
                        "the following embeddings have no corresponding nodes, BUG", a
                    )
                if b != []:
                    logger.info(
                        f"generating {len(b)} embeddings out of {len(node_ids)} total nodes"
                    )
                    for id in b:
                        node = database.get_node_by_db_id(id)
                        content = ""
                        if is_valid_url(node.hyperlink):
                            content = cls.clean_content(cls.get_content(node.hyperlink))
                        else:
                            content = f"{node.doctype}\n name:{node.name}\n section:{node.section}\n subsection:{node.subsection}\n section_id:{node.sectionID}\n "

                        logger.info(f"making embedding for {node.hyperlink}")
                        embedding = get_embeddings(openai_key, content)
                        dbnode = db.dbNodeFromNode(node)
                        if not dbnode:
                            logger.fatal(node, "cannot be converted to database Node")
                        dbnode.id = id
                        database.add_embedding(dbnode, doc_type, embedding, content)
                        cls.embeddings[id] = embedding


class PromptHandler:
    def __init__(self, database: db.Node_collection, openai_key: str) -> None:
        self.api_key = openai_key
        self.database = database
        self.embeddings_instance = in_memory_embeddings.instance(
            database, openai_key=openai_key
        )
        existing = []
        existing_ids = []
        for id, e in self.embeddings_instance.embeddings.items():
            existing.append(e)
            existing_ids.append(id)
        self.existing = sparse.csr_matrix(np.array(existing).astype(np.float64))
        self.existing_ids = existing_ids
        if not self.embeddings_instance or not self.embeddings_instance.embeddings:
            logger.fatal(
                f"in memory embeddings is {self.embeddings_instance} and embeddings are {self.embeddings_instance.embeddings} bug?"
            )

    def __get_id_of_most_similar_item(
        self, embedding: List[float], embeddings: Dict[str, List[float]]
    ) -> str:
        embedding_array = sparse.csr_matrix(
            np.array(embedding).reshape(1, -1)
        )  # convert embedding into a 1-dimentional numpy array
        similarities = cosine_similarity(embedding_array, self.existing)
        most_similar_index = np.argmax(similarities)
        id = self.existing_ids[most_similar_index]
        return id

    def generate_text(self, prompt: str):
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        if not prompt:
            return {"response": "", "table": "", "timestamp": timestamp}

        question_embedding = get_embeddings(self.api_key, prompt)

        # Find the closest area in the existing embeddings
        closest_id = self.__get_id_of_most_similar_item(
            question_embedding, self.embeddings_instance.embeddings
        )
        closest_object = self.database.get_node_by_db_id(closest_id)
        closest_object_str = "\n".join(
            [f"{k}:{v}" for k, v in closest_object.shallow_copy().todict().items()]
        )[
            :8000
        ]  # openai has a model limit of 8100 characters

        # Send the question and the closest area to the LLM to get an answer
        messages = [
            {
                "role": "system",
                "content": "Assistant is a large language model trained by OpenAI.",
            },
            {
                "role": "user",
                "content": f"Answer the following question based on this area of knowledge: {closest_object_str} delimit any code snippet with three backticks \nQuestion: {prompt}",
            },
        ]

        openai.api_key = self.api_key
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )

        answer = response.choices[0].message["content"].strip()

        table = [closest_object]
        result = f"Answer: {answer}"
        return {"response": result, "table": table, "timestamp": timestamp}
