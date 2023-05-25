from typing import List
from vertexai.preview.language_models import TextEmbeddingModel
from google.cloud import aiplatform
from vertexai.preview.language_models import ChatModel
from google.oauth2 import service_account
from vertexai.preview.language_models import (
    ChatModel,
    InputOutputTextPair,
    TextGenerationModel,
    TextEmbeddingModel,
)
import os
import pathlib
import vertexai
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# get client https://googleapis.dev/python/google-api-core/latest/auth.html
# https://github.com/googleapis/python-aiplatform/tree/d7c5b8e54c304f5cda59688af74e5b8d9bd35034
# test chat completion
class VertexPromptClient:
    context = 'You are "chat-CRE" a chatbot for security information that exists in opencre.org. You will be given text of security topics and questions on the topics, please answer the questions based on the content provided. Delimit any code snippet with three backticks.'

    def __init__(self, project_id, location) -> None:
        service_account_secrets_file = os.path.join(
            pathlib.Path(__file__).parent.parent.parent, "gcp_sa_secret.json"
        )
        if os.environ.get("SERVICE_ACCOUNT_CREDENTIALS"):
            with open(service_account_secrets_file, "w") as f:
                f.write(os.environ.get("SERVICE_ACCOUNT_CREDENTIALS"))
                os.environ[
                    "GOOGLE_APPLICATION_CREDENTIALS"
                ] = service_account_secrets_file
                print(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
        else:
            logger.fatal("env SERVICE_ACCOUNT_CREDENTIALS has not been set")

        # vertexai.init(project=project_id, location=location)
        self.chat_model = ChatModel.from_pretrained("chat-bison@001")
        self.embeddings_model = TextEmbeddingModel.from_pretrained(
            "textembedding-gecko@001"
        )
        self.chat = self.chat_model.start_chat(context=self.context)

    def get_text_embeddings(self, text: str) -> List[float]:
        """Text embedding with a Large Language Model."""
        if len(text) > 8000:
            logger.info(
                f"embedding content is more than the vertex hard limit of 8k tokens, reducing to 8000"
            )
            text = text[:8000]
        embeddings = self.embeddings_model.get_embeddings([text])
        if not embeddings:
            return None
        return embeddings[0].values

    def create_chat_completion(self, prompt, closest_object_str) -> str:
        msg = (
            f"Answer the following question based on this area of knowledge: {closest_object_str} delimit any code snippet with three backticks \nQuestion: {prompt}",
        )

        response = self.chat.send_message(msg)
        return response.text
