# Chat eval (#1078)

How to check that OpenCRE chat answers are grounded and cite the right sources, and
the verdict of the #1078 spike on how to run that check.

## What is measured

Two parts, kept apart on purpose.

**Hermetic scorer** (`application/utils/ask_eval/gold.py`, runs in `make test`). No LLM,
no network. For each gold question it reads a recorded `/rest/v1/completion` answer and
checks:

| Metric | Question it answers | Gates `passed`? |
|---|---|---|
| CRE recall | Did any expected CRE come back in the table or citations? | yes |
| Cite groups | Was each required source family cited, e.g. SAMM when the question says "according to SAMM", both halves of a compound question? | yes |
| Abstain | Did refusal rows refuse and answer rows answer? | yes |
| Citation markers | Does every `[n]` point at a returned passage? | yes |
| Must contain | Does the answer use the expected key term (e.g. "hash")? | yes |
| CRE precision | Share of returned CREs that the gold row lists | no, reported only (gold rows list accepted CREs, not every correct sibling) |

**Faithfulness** (`scripts/chat_eval_faithfulness.py`, optional, local). Splits each
answer into claims and asks an LLM judge whether each claim is supported by the passages
the answer returned (Ragas `Faithfulness`). This is the part a hermetic check cannot do:
`[n]` pointing at a real passage does not mean the passage says what the sentence says.
The input selection and the report are hermetic and tested
(`application/utils/ask_eval/faithfulness.py`); only the judge call needs an LLM.

## Gold set

`application/tests/fixtures/ask_regressions/chat_eval_gold.jsonl`, 29 questions:

- 18 single-topic practice questions (passwords, sessions, XSS, SQLi, CSRF, SSRF, TLS,
  logging, secrets, dependencies, access control, training, ...)
- the #962 threat-modeling pair (plain, and "according to SAMM")
- 2 AI security questions (direct and indirect prompt injection)
- 2 compound questions where both halves must be cited (password storage plus
  credential stuffing, suggested in review by @SomyaJain0308; session cookies plus XSS)
- 5 refusals: off topic (2), nothing indexed (1), a future edition that does not exist
  (1), a CVE that does not exist (1)

Every expected CRE id was checked against the CRE table.

## How to run

Record answers once, then score offline as often as needed:

```bash
# record (one chat call per question)
OPENCRE_API_KEY=... python scripts/chat_eval_gold.py --live \
    --base-url https://staging.opencre.org --record tmp/chat_eval/staging.jsonl

# hermetic score, optionally against an older recording
python scripts/chat_eval_gold.py --responses tmp/chat_eval/staging.jsonl \
    --baseline tmp/chat_eval/older.jsonl
```

If live mode fails with `CERTIFICATE_VERIFY_FAILED` on macOS python.org builds, run it
with `SSL_CERT_FILE=$(python -m certifi)`.

Faithfulness, in its own virtualenv (see "Why not in requirements" below):

```bash
python3 -m venv .venv-ragas
.venv-ragas/bin/pip install -r requirements.txt \
    "ragas==0.4.3" "langchain-community>=0.3,<0.4"
GEMINI_API_KEY=... .venv-ragas/bin/python scripts/chat_eval_faithfulness.py \
    --responses tmp/chat_eval/staging.jsonl --output-json tmp/chat_eval/faith.json
```

Any OpenAI-compatible judge works (`--judge-model`, `--judge-base-url`,
`--judge-key-env`). Cost is two judge calls per judged answer, 48 for the current set.

## Results on staging (2026-11-11)

Hermetic scorer, 29 questions: **26/29 passed**. CRE recall 0.958, CRE precision 0.708,
cite groups 1.0, abstain correct 3/5, no false abstains. The 24 questions shared with
the 2026-11-09 run scored identically, so the recording plus offline scoring is stable.

Real failures:

- `refuse_future_top10`: asked for the OWASP Top 10 2031, chat lists the 2021
  categories as the answer instead of saying no 2031 edition exists.
- `refuse_no_context`: asked about a 2031 AppSec venue, chat returns the 2025
  Washington DC event.
- `mfa_sms`: the answer is right, but CRE 354-752 (strong authenticators for critical
  access) is not returned.

The two refusal misses share one cause: a question about a future year is matched to
the nearest past item and answered. Faithfulness would not catch this, because the
2021 list is faithful to its source. Only the abstain check does.

One gold fix after the first run: `compound_pw_stuffing` first failed its
credential stuffing cite group, but the answer cites ASVS V2 Authentication, whose
2.2.1 anti-automation requirement names credential stuffing. The group now accepts
`v2-authentication`. That was a gold row error, not a chat error.

Faithfulness: **pending a judge run**. The script, input selection and report are done
and tested; 24 answers are judgeable (the 5 refusal rows have no claims to check).

## Evidence truncation

The API cuts each evidence snippet (`owasp_agent.data.evidence[].snippet`) at 500
characters. On the 2026-11-11 run, **79 of 127 passages (62%) are cut**, and in 5
answers every passage is cut. A claim backed by text after the cut will be judged
unsupported, so faithfulness scored from the API response is a lower bound. The report
prints `cut at cap` per row so a low score can be checked against this.

To score faithfulness properly the recording needs the full passage text the generator
saw. That is a change on the chat side (return or log full evidence for eval runs), not
in this harness.

## Verdict

The spike asked: RAGAS in CI, a custom unittest over fixtures, or a manual script?

**Custom hermetic scorer in `make test`, plus Ragas faithfulness as an optional local
script. Not Ragas in CI.**

Why:

1. **Ragas' faithfulness needs an LLM judge.** There is no hermetic mode. In CI that
   means a paid key, network, and a score that moves between runs. #1078's own kill
   criteria say to keep it as an optional local command in that case.
2. **Ragas does not install cleanly next to the app.** With current packages:
   - `ragas==0.4.3` fails to import with `langchain-community>=0.4`
     (`langchain_community.chat_models.vertexai` was removed), so it needs
     `langchain-community<0.4`.
   - `ragas` depends on `instructor==1.3.2`, which requires `openai<2`, while the app's
     `litellm` pulls `openai` 2.x. pip reports the conflict. It still runs, but that is
     not something to put in `requirements-dev.txt`.
   - The metric's public `ascore()` only returns a ratio. Listing the unsupported claims,
     which is what a person needs to act on, uses two private methods, so the script pins
     `ragas==0.4.3`.
3. **What CI needs is already covered hermetically.** Citation and context recall (the
   SAMM-when-asked check), CRE recall, refusals and marker validity all run on recorded
   answers with no LLM and catch the failures found so far.
4. **Faithfulness scores from the API are biased low** until full passages are recorded
   (62% are cut today), so it is not yet a number to gate on anyway.

So `requirements.txt` and `requirements-dev.txt` are unchanged, and nothing LLM-judged
runs in `make test`.

## Follow-ups

- Chat: refuse questions about future editions and events instead of answering with the
  nearest past one (`refuse_future_top10`, `refuse_no_context`).
- Chat: return full evidence text (or an eval flag that does) so faithfulness is not
  scored against truncated passages.
- Run faithfulness on the 2026-11-11 recording once a judge key is set, and record the
  numbers here.
- Re-run the gold set on #1161 (top-k retrieval) against the same questions.
