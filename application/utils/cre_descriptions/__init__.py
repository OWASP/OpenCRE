"""One-shot CRE description generation helpers (not a Librarian runtime module).

Generate → human approval table under ``tmp/`` → staging surgery later.
Steal grounding ideas from the cre_summary experiment; do not write the DB.
"""

from application.utils.cre_descriptions.generate import (
    CreDescriptionInput,
    propose_descriptions,
    should_skip,
)
from application.utils.cre_descriptions.grounding import (
    grounding_snippet,
    usable_grounding_leaves,
)
from application.utils.cre_descriptions.prompt import (
    build_description_prompt,
    compute_prompt_hash,
    parse_description_text,
)
from application.utils.cre_descriptions.table import (
    APPROVAL_COLUMNS,
    ApprovalRow,
    write_approval_csv,
    write_approval_markdown,
)

__all__ = [
    "APPROVAL_COLUMNS",
    "ApprovalRow",
    "CreDescriptionInput",
    "build_description_prompt",
    "compute_prompt_hash",
    "grounding_snippet",
    "parse_description_text",
    "propose_descriptions",
    "should_skip",
    "usable_grounding_leaves",
    "write_approval_csv",
    "write_approval_markdown",
]
