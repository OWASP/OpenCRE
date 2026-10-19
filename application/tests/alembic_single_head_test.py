"""The migration chain must end in exactly one head.

Two heads break `flask db upgrade` ("Multiple head revisions"). When two branches each add
a migration, add a merge migration whose down_revision lists both parents.
"""

import re
import unittest
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def _heads() -> list:
    revisions, parents = {}, set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*(.+)$", text, re.M)
        if rev:
            revisions[rev.group(1)] = path.name
        if down:
            parents.update(re.findall(r"['\"]([0-9a-zA-Z_]+)['\"]", down.group(1)))
    return sorted(r for r in revisions if r not in parents)


class AlembicSingleHeadTest(unittest.TestCase):
    def test_exactly_one_head(self) -> None:
        self.assertEqual(
            len(_heads()),
            1,
            f"migration chain has multiple heads: {_heads()}; add a merge migration",
        )


if __name__ == "__main__":
    unittest.main()
