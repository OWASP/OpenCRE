import os

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except ImportError:
    pass

TRUE_VALUES = {"1", "true", "yes"}


def is_cre_import_allowed() -> bool:
    return os.getenv("CRE_ALLOW_IMPORT", "").strip().lower() in TRUE_VALUES


def is_health_endpoint_enabled() -> bool:
    return os.getenv("CRE_ENABLE_HEALTH", "").strip().lower() in TRUE_VALUES


def is_myopencre_enabled() -> bool:
    """Return True when the MyOpenCRE feature is enabled via CRE_ENABLE_MYOPENCRE."""
    return os.getenv("CRE_ENABLE_MYOPENCRE", "").strip().lower() in TRUE_VALUES
