import logging
import os
import sys

logger = logging.getLogger(__name__)


def validate_web_config(mode: str) -> None:
    """Validates critical configuration for web server startup.

    Logs warnings for optional services that are not configured and aborts
    with a clear error message if required variables are missing.
    Skipped entirely in test/testing mode.

    Args:
        mode: the Flask configuration mode (e.g. "production", "development").
    """
    if mode.upper() in ("TESTING", "TEST"):
        return

    errors = []
    no_login = os.environ.get("NO_LOGIN")

    if not no_login:
        if not os.environ.get("GOOGLE_CLIENT_SECRET"):
            errors.append(
                "GOOGLE_CLIENT_SECRET is not set. "
                "Flask requires a secret key to sign sessions securely. "
                "Set GOOGLE_CLIENT_SECRET or set NO_LOGIN=True to disable authentication."
            )
        if not os.environ.get("GOOGLE_CLIENT_ID"):
            errors.append(
                "GOOGLE_CLIENT_ID is not set. "
                "Google OAuth login will not work. "
                "Set GOOGLE_CLIENT_ID or set NO_LOGIN=True to disable authentication."
            )

    if not os.environ.get("NEO4J_URL"):
        logger.warning(
            "NEO4J_URL is not set. Gap analysis features will be unavailable."
        )

    if not os.environ.get("REDIS_URL") and not os.environ.get("REDIS_HOST"):
        logger.warning(
            "REDIS_URL is not set. Background job processing will be unavailable."
        )

    if errors:
        for error in errors:
            logger.error("[startup] %s", error)
        sys.exit(1)


def validate_embeddings_config() -> None:
    """Checks that an AI provider API key is present before generating embeddings.

    Aborts with a clear message if none of OPENAI_API_KEY, GEMINI_API_KEY,
    or GCP_NATIVE is configured.
    """
    if (
        not os.environ.get("OPENAI_API_KEY")
        and not os.environ.get("GEMINI_API_KEY")
        and not os.environ.get("GCP_NATIVE")
    ):
        logger.error(
            "[startup] No AI provider configured. "
            "Set OPENAI_API_KEY, GEMINI_API_KEY, or GCP_NATIVE before generating embeddings."
        )
        sys.exit(1)


def validate_neo4j_config() -> None:
    """Checks that NEO4J_URL is set before attempting Neo4j database operations.

    Aborts with a clear message if NEO4J_URL is not configured.
    """
    if not os.environ.get("NEO4J_URL"):
        logger.error(
            "[startup] NEO4J_URL is not set. "
            "Cannot populate the Neo4j database. "
            "Set NEO4J_URL to your Neo4j instance URL and retry."
        )
        sys.exit(1)
