"""Module B evaluation harness — Stage 2 prompt fitness function.

Runs the labeled dataset through the real Module B gate (Stage 1 regex ->
Stage 1.5 sanitize -> Stage 2 LLM classifier) and scores predictions against
the gold labels. This is the primary metric used to iterate the Stage 2 prompt
toward the mid-evaluation target.

Recall-first framing: the headline numbers are KNOWLEDGE recall and the
KNOWLEDGE->NOISE leakage count (gold-KNOWLEDGE chunks wrongly dropped -- the
"security lost forever" failure). NOISE rows are dropped before Module C, so
those are the costly mistakes.

This hits the real LLM API. Cost per full 100-record run is well under $0.01
with the lite model; monitor exact spend on your provider dashboard.

Usage:
    python scripts/evaluate_noise_filter.py                 # full dataset
    python scripts/evaluate_noise_filter.py --limit 10      # smoke test
    python scripts/evaluate_noise_filter.py --threshold 0.7 --out results.csv
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

# Allow running directly as `python scripts/evaluate_noise_filter.py`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from application.utils.noise_filter.config_loader import load_config
from application.utils.noise_filter.llm_classifier import LLMClassifier
from application.utils.noise_filter.regex_filter import RegexFilter
from application.utils.noise_filter.sanitize import sanitize_text
from application.utils.noise_filter.schemas import ChangeRecord

logger = logging.getLogger(__name__)

LABELS = ["KNOWLEDGE", "NOISE", "UNCERTAIN"]
DEFAULT_DATASET = "application/tests/noise_filter/fixtures/labeled_data.json"


# --- prediction ----------------------------------------------------------


@dataclasses.dataclass
class Prediction:
    chunk_id: str
    gold: str
    predicted: str
    confidence: float
    stage: str  # "regex" | "llm"
    reasoning: str


def _apply_threshold(label: str, confidence: float, threshold: float) -> str:
    """A KNOWLEDGE verdict below the threshold is treated as UNCERTAIN (HITL),
    matching the pipeline's enqueue rule. NOISE/UNCERTAIN pass through."""
    if label == "KNOWLEDGE" and confidence < threshold:
        return "UNCERTAIN"
    return label


def _sanitized(record: ChangeRecord) -> ChangeRecord:
    """Stage 1.5: return a copy with sanitized text (no-op on clean input)."""
    try:
        clean = sanitize_text(record.text)
    except ValueError:
        return record  # sanitization emptied the text; keep original for the LLM
    return record.model_copy(update={"text": clean})


def run_eval(
    records: list[tuple[ChangeRecord, str]],
    config,
    threshold: float,
    use_regex: bool,
) -> tuple[list[Prediction], int]:
    """Run the gate over (record, gold) pairs. Returns predictions + LLM call count."""
    regex = RegexFilter()
    predictions: list[Prediction] = []

    survivors: list[ChangeRecord] = []
    survivor_gold: list[str] = []
    for rec, gold in records:
        if use_regex:
            is_noise, reason = regex.is_noise_record(rec)
            if is_noise:
                predictions.append(
                    Prediction(rec.chunk_id, gold, "NOISE", 1.0, "regex", reason)
                )
                continue
        survivors.append(_sanitized(rec))
        survivor_gold.append(gold)

    classifier = LLMClassifier(config)
    results = classifier.classify_batch(survivors)
    n_calls = (len(survivors) + config.batch_size - 1) // config.batch_size

    for rec, gold, res in zip(survivors, survivor_gold, results):
        predicted = _apply_threshold(res.label, res.confidence, threshold)
        predictions.append(
            Prediction(
                rec.chunk_id,
                gold,
                predicted,
                res.confidence,
                "llm",
                res.reasoning or "",
            )
        )
    return predictions, n_calls


# --- metrics -------------------------------------------------------------


def _confusion(preds: list[Prediction]) -> dict[tuple[str, str], int]:
    return Counter((p.gold, p.predicted) for p in preds)


def _prf(cm: dict[tuple[str, str], int], label: str) -> tuple[float, float, float]:
    tp = cm.get((label, label), 0)
    fp = sum(cm.get((g, label), 0) for g in LABELS if g != label)
    fn = sum(cm.get((label, p), 0) for p in LABELS if p != label)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def _print_report(
    preds: list[Prediction], threshold: float, n_calls: int, use_regex: bool
) -> None:
    total = len(preds)
    correct = sum(1 for p in preds if p.gold == p.predicted)
    cm = _confusion(preds)

    print("\n" + "=" * 64)
    print("MODULE B — EVALUATION REPORT")
    print("=" * 64)
    print(f"records:        {total}")
    print(f"threshold:      {threshold}  (KNOWLEDGE below this -> UNCERTAIN)")
    print(f"regex stage:    {'on' if use_regex else 'off'}")
    print(f"LLM batches:    {n_calls}")
    print(f"accuracy:       {correct}/{total} = {correct / total:.3f}")

    # Recall-first headline.
    k_recall = _prf(cm, "KNOWLEDGE")[1]
    leak = cm.get(("KNOWLEDGE", "NOISE"), 0)
    gold_k = sum(cm.get(("KNOWLEDGE", p), 0) for p in LABELS)
    print("\n--- recall-first headline ---")
    print(f"KNOWLEDGE recall:            {k_recall:.3f}")
    print(
        f"KNOWLEDGE -> NOISE leakage:  {leak}/{gold_k}  "
        f"(security chunks wrongly dropped)"
    )

    print("\n--- 3x3 confusion matrix (rows=gold, cols=pred) ---")
    header = "gold\\pred".ljust(12) + "".join(lbl[:9].rjust(10) for lbl in LABELS)
    print(header)
    for g in LABELS:
        row = g[:11].ljust(12) + "".join(
            str(cm.get((g, p), 0)).rjust(10) for p in LABELS
        )
        print(row)

    print("\n--- per-class precision / recall / f1 ---")
    for lbl in LABELS:
        p, r, f = _prf(cm, lbl)
        print(f"{lbl.ljust(11)} P={p:.3f}  R={r:.3f}  F1={f:.3f}")

    llm_preds = [p for p in preds if p.stage == "llm"]
    if llm_preds:
        mean_conf = sum(p.confidence for p in llm_preds) / len(llm_preds)
        llm_correct = sum(1 for p in llm_preds if p.gold == p.predicted)
        print("\n--- Stage 2 (LLM) only ---")
        print(
            f"reached LLM:    {len(llm_preds)}  (regex dropped {total - len(llm_preds)})"
        )
        print(
            f"LLM accuracy:   {llm_correct}/{len(llm_preds)} = {llm_correct / len(llm_preds):.3f}"
        )
        print(f"mean confidence: {mean_conf:.3f}")
    print("=" * 64 + "\n")


def _write_csv(preds: list[Prediction], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "chunk_id",
                "gold",
                "predicted",
                "confidence",
                "stage",
                "correct",
                "reasoning",
            ]
        )
        for p in preds:
            writer.writerow(
                [
                    p.chunk_id,
                    p.gold,
                    p.predicted,
                    f"{p.confidence:.3f}",
                    p.stage,
                    int(p.gold == p.predicted),
                    p.reasoning,
                ]
            )
    print(f"wrote per-record results -> {out_path}")


# --- cli -----------------------------------------------------------------


def _load_dataset(path: Path, limit: int) -> list[tuple[ChangeRecord, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if limit > 0:
        raw = raw[:limit]
    out: list[tuple[ChangeRecord, str]] = []
    for row in raw:
        gold = row.get("label")
        if gold not in LABELS:
            logger.warning("skipping record with missing/invalid label: %s", gold)
            continue
        out.append((ChangeRecord.model_validate(row), gold))
    return out


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Module B against labeled data."
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=0, help="0 = all records")
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="confidence cutoff; default from config",
    )
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument(
        "--model", default=None, help="override CRE_NOISE_FILTER_LLM_MODEL"
    )
    parser.add_argument("--no-regex", action="store_true", help="skip Stage 1 regex")
    parser.add_argument("--out", default="noise_filter_eval_results.csv")
    args = parser.parse_args(argv)

    config = load_config()
    overrides = {}
    if args.batch_size is not None:
        overrides["batch_size"] = args.batch_size
    if args.model is not None:
        overrides["llm_model"] = args.model
    if overrides:
        config = dataclasses.replace(config, **overrides)
    threshold = (
        args.threshold if args.threshold is not None else config.confidence_threshold
    )

    records = _load_dataset(Path(args.dataset), args.limit)
    print(f"loaded {len(records)} labeled records from {args.dataset}")
    print(f"model: {config.llm_model}  batch_size: {config.batch_size}")

    preds, n_calls = run_eval(records, config, threshold, use_regex=not args.no_regex)
    _print_report(preds, threshold, n_calls, use_regex=not args.no_regex)
    _write_csv(preds, Path(args.out))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
