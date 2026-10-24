#!/usr/bin/env python3
"""Live multi-turn check, run INSIDE a deployed web container (uses the real models, costs a few cents).

    docker exec -w /code <web-container> env PYTHONPATH=/code python scripts/ops/multiturn_probe.py

Each scenario asks a question, then a follow-up that depends on it, sending the conversation as history
exactly like the chat page does. A follow-up answer must (1) mention what it was asked about and (2) NOT
repeat the previous answer. Exit 1 when a scenario fails.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import time
from typing import Dict, List

SCENARIOS: List[Dict] = [
    {
        "name": "agentic AI risks",
        "first": "Does the OWASP AI Exchange cover agentic AI?",
        "follow_up": "What are some key risks",
        "expect_any": ["risk", "threat", "attack", "injection"],
    },
    {
        "name": "SAMM levels",
        "first": "What is OWASP SAMM?",
        "follow_up": "How many levels does it define per practice?",
        "expect_any": ["three", "3 "],
    },
    {
        "name": "membership by country",
        "first": "What does OWASP membership cost in Switzerland?",
        "follow_up": "and in Morocco?",
        "expect_any": ["morocco"],
    },
    {
        "name": "project purpose",
        "first": "Who leads the OWASP Developer Guide project?",
        "follow_up": "What is its purpose?",
        "expect_any": ["guide", "developer", "security"],
    },
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").lower()


def evaluate(first_answer: str, second_answer: str, expect_any: List[str]) -> List[str]:
    problems = []
    sim = difflib.SequenceMatcher(
        None, _norm(first_answer), _norm(second_answer)
    ).ratio()
    if sim > 0.6:
        problems.append(f"follow-up repeats the previous answer (similarity {sim:.2f})")
    if not any(k in _norm(second_answer) for k in expect_any):
        problems.append(f"follow-up answer mentions none of {expect_any}")
    return problems


def main() -> int:
    os.environ["NO_LOGIN"] = "1"
    from application import create_app

    app = create_app(mode="production")
    client = app.test_client()
    failed = 0
    for sc in SCENARIOS:
        t = time.time()
        first = (
            client.post("/rest/v1/completion", json={"prompt": sc["first"]}).get_json()
            or {}
        )
        a1 = first.get("response") or first.get("error") or ""
        history = [
            {"role": "user", "content": sc["first"]},
            {"role": "assistant", "content": a1},
        ]
        second = (
            client.post(
                "/rest/v1/completion",
                json={"prompt": sc["follow_up"], "messages": history},
            ).get_json()
            or {}
        )
        a2 = second.get("response") or second.get("error") or ""
        problems = evaluate(a1, a2, sc["expect_any"])
        failed += bool(problems)
        print(
            json.dumps(
                {
                    "scenario": sc["name"],
                    "ok": not problems,
                    "problems": problems,
                    "seconds": round(time.time() - t, 1),
                    "follow_up_answer": a2[:160].replace("\n", " "),
                }
            ),
            flush=True,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
