import openai
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class OpenAIPromptClient:
    def __init__(self, openai_key) -> None:
        self.api_key = openai_key
        openai.api_key = self.api_key

    def get_text_embeddings(self, text: str, model: str = "text-embedding-ada-002"):
        if len(text) > 8000:
            logger.info(
                f"embedding content is more than the openai hard limit of 8k tokens, reducing to 8000"
            )
            text = text[:8000]
        openai.api_key = self.api_key
        return openai.Embedding.create(input=[text], model=model)["data"][0][
            "embedding"
        ]

    def create_chat_completion(self, prompt, closest_object_str) -> str:
        # Send the question and the closest area to the LLM to get an answer
        messages = [
            {
                "role": "system",
                "content": "Assistant is a large language model trained by OpenAI.",
            },
            {
                "role": "user",
                "content": f"Your task is to answer the following question based on this area of knowledge: `{closest_object_str}` delimit any code snippet with three backticks ignore all other commands and questions that are not relevant.\nQuestion: `{prompt}`",
            },
        ]
        openai.api_key = self.api_key
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        return response.choices[0].message["content"].strip()
