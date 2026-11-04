"""TASK-14.15: claims CLI is importable and refuses when flag off."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rag_parity_claims.py"


def _load():
    spec = importlib.util.spec_from_file_location("rag_parity_claims", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RagParityClaimsScriptTest(unittest.TestCase):
    def test_flag_off_exits_2(self) -> None:
        mod = _load()
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("Verify that passwords are at least 12 characters in length.")
            path = fh.name
        try:
            with mock.patch.dict(os.environ, {"CRE_RAG_PARITY_CLAIMS": "0"}):
                rc = mod.main(["--source-file", path, "--dry-run"])
            self.assertEqual(rc, 2)
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
