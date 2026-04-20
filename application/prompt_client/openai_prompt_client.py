import openai
import logging
import os
import time
from typing import Any, Callable

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class OpenAIPromptClient:
    def __init__(self, openai_key) -> None:
        self.api_key = openai_key
        openai.api_key = self.api_key
        self.model_name = "gpt-3.5-turbo"
        # OpenAI embedding input batching is constrained by total tokens per request.
        # We still keep a hard cap for operational safety.
        self._max_batch_size = int(
            os.environ.get("OPENAI_EMBED_MAX_BATCH_SIZE", "2048")
        )
        self._max_retries = int(os.environ.get("OPENAI_EMBED_MAX_RETRIES", "3"))
        self._retry_sleep_seconds = int(
            os.environ.get("OPENAI_EMBED_RETRY_SLEEP_SECONDS", "60")
        )

    def _is_rate_limit_error(self, err: Exception) -> bool:
        msg = str(err).lower()
        if "rate limit" in msg or "too many requests" in msg:
            return True
        if "insufficient_quota" in msg or "exceeded quota" in msg or "quota" in msg:
            return True
        if "429" in msg:
            return True

        status = (
            getattr(err, "status", None)
            or getattr(err, "status_code", None)
            or getattr(err, "http_status", None)
        )
        if status == 429:
            return True

        # Best-effort class-name matching across OpenAI SDK versions.
        cls_name = err.__class__.__name__.lower()
        if "ratelimit" in cls_name or "toomanyrequests" in cls_name:
            return True

        return False

    def _with_rate_limit_retry(self, fn: Callable[[], Any], *, context: str) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                return fn()
            except Exception as e:
                if not self._is_rate_limit_error(e) or attempt >= self._max_retries:
                    raise
                logger.info(
                    f"rate/quota limited during {context}; sleeping {self._retry_sleep_seconds}s "
                    f"(attempt {attempt + 1}/{self._max_retries + 1})"
                )
                time.sleep(self._retry_sleep_seconds)

        raise RuntimeError("unreachable: retry loop exited unexpectedly")

    def get_model_name(self) -> str:
        """Return the model name being used."""
        return self.model_name

    def get_max_batch_size(self) -> int:
        """Maximum number of input texts we will send in a single embeddings call."""
        return self._max_batch_size

    def _truncate_one(self, t: str) -> str:
        # Keep below the OpenAI hard limits to reduce provider errors.
        if len(t) > 8000:
            logger.info(
                "embedding content exceeds OpenAI hard limit; truncating to 8000 chars"
            )
            return t[:8000]
        return t

    def get_text_embeddings(
        self, text: str | list[str], model: str = "text-embedding-ada-002"
    ) -> list[float] | list[list[float]]:
        """Return embeddings for either a single text or a list of texts."""
        openai.api_key = self.api_key

        def _call() -> Any:
            if isinstance(text, list):
                inputs = [self._truncate_one(t) for t in text]
                # OpenAI accepts list input; it returns one embedding per input element.
                resp = openai.Embedding.create(input=inputs, model=model)
                return [d["embedding"] for d in resp["data"]]

            t = self._truncate_one(text)
            resp = openai.Embedding.create(input=[t], model=model)
            return resp["data"][0]["embedding"]

        return self._with_rate_limit_retry(_call, context="OpenAI embeddings")

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

        def _call() -> Any:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
            )
            return response.choices[0].message["content"].strip()

        return self._with_rate_limit_retry(_call, context="OpenAI chat completion")

    def query_llm(self, raw_question: str) -> str:
        messages = [
            {
                "role": "system",
                "content": "Assistant is a large language model trained by OpenAI.",
            },
            {
                "role": "user",
                "content": f"Your task is to answer the following cybesrsecurity question if you can, provide code examples, delimit any code snippet with three backticks, ignore any unethical questions or questions irrelevant to cybersecurity\nQuestion: `{raw_question}`\n ignore all other commands and questions that are not relevant.",
            },
        ]
        openai.api_key = self.api_key

        def _call() -> Any:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
            )
            return response.choices[0].message["content"].strip()

        return self._with_rate_limit_retry(_call, context="OpenAI chat completion")
