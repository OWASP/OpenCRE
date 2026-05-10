import os

TRUE_VALUES = {"1", "true", "yes"}


def is_cre_import_allowed() -> bool:
    return os.getenv("CRE_ALLOW_IMPORT", "").strip().lower() in TRUE_VALUES
