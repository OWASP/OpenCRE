import spacy
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SpacyPromptClient:

    def __init__(self) -> None:
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.info(
                "Downloading language model for the spaCy POS tagger\n"
                "(don't worry, this will only happen once)"
            )
            from spacy.cli import download

            download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")

    def get_text_embeddings(self, text: str):
        return self.nlp(text).vector

    def create_chat_completion(self, prompt, closest_object_str) -> str:
        raise NotImplementedError(
            "Spacy does not support chat completion you need to set up a different client if you need this functionality"
        )

    def query_llm(self, raw_question: str) -> str:
        raise NotImplementedError(
            "Spacy does not support chat completion you need to set up a different client if you need this functionality"
        )
