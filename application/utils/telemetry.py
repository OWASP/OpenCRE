import os
import time
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def emit_import_event(
    import_run_id: str,
    source: str,
    version: Optional[str],
    status: str,
    start_time: float,
    end_time: float,
    error_message: Optional[str] = None,
    op_counts: Optional[Dict[str, int]] = None,
) -> None:
    """
    Emits structured telemetry for an import run.
    If TELEMETRY_ENDPOINT is set, it POSTs the event.
    Otherwise, it appends it to a local file (e.g. import_telemetry.json).
    """
    duration = end_time - start_time

    event = {
        "event_type": "import_run",
        "import_run_id": import_run_id,
        "source": source,
        "version": version or "unknown",
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": duration,
        "error_message": error_message,
        "op_counts": op_counts or {},
    }

    # Remove None values
    event = {k: v for k, v in event.items() if v is not None}

    endpoint = os.environ.get("TELEMETRY_ENDPOINT")

    if endpoint:
        try:
            requests.post(endpoint, json=event, timeout=5.0)
        except Exception as e:
            logger.warning(f"Failed to send telemetry to {endpoint}: {e}")
            _write_to_file(event)
    else:
        _write_to_file(event)


def _write_to_file(event: Dict[str, Any]) -> None:
    filepath = os.environ.get("TELEMETRY_FILE", "import_telemetry.json")
    try:
        with open(filepath, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        logger.error(f"Failed to write telemetry to file {filepath}: {e}")
