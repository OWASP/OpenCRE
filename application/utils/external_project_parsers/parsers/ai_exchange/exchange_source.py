"""Future: fetch OWASP AI Exchange content and emit master-shaped rows.

``normalize_rows_for_master_import`` in ``csv_source`` is the contract: anything
that feeds the main spreadsheet import should produce those column names.
"""

from __future__ import annotations

from typing import Any, Dict, List


def fetch_exchange_rows_not_implemented() -> List[Dict[str, Any]]:
    raise NotImplementedError(
        "Live AI Exchange import is not implemented; use the CSV export "
        "and application.utils.external_project_parsers.parsers.ai_exchange.csv_source"
    )
