"""Evaluate a labelled, time-split JSON snapshot without opening the live DB."""
import argparse
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recommendation import STRATEGIES, date, rank_contents


def metrics_at_k(ranked_ids, relevant_ids, k):
    relevant = set(relevant_ids)
    hits = [int(identifier in relevant) for identifier in ranked_ids[:k]]
    dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
    ideal = sum(1 / math.log2(index + 2) for index in range(min(k, len(relevant))))
    return {"precision": sum(hits) / k,
            "recall": sum(hits) / len(relevant) if relevant else 0.0,
            "hit_rate": float(any(hits)), "ndcg": dcg / ideal if ideal else 0.0}


def evaluate(snapshot, ks=(5, 10)):
    at = date(snapshot.get("cutoff"))
    if at is None or not ks or any(k < 1 for k in ks):
        raise ValueError("A valid cutoff and positive K values are required")
    cases = snapshot["cases"]
    if not cases:
        raise ValueError("At least one labelled case is required")
    ids = [row["id"] for row in snapshot["contents"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Content IDs must be unique")
    totals = {strategy: {str(k): dict.fromkeys(("precision", "recall", "hit_rate", "ndcg"), 0.0)
                        for k in ks} for strategy in STRATEGIES}
    for case in cases:
        history = case.get("history", [])
        # Fail closed: evaluation labels must not be passed in as training events.
        if any(date(e.get("timestamp")) is None or date(e["timestamp"]) >= at for e in history):
            raise ValueError("History must be strictly before cutoff; keep held-out labels separate")
        relevant = set(case["relevant_ids"])
        if not relevant:
            raise ValueError("Each evaluated user needs at least one held-out relevant item")
        for strategy in STRATEGIES:
            ranked = rank_contents(case["user"], snapshot["contents"], history, at=at, strategy=strategy)
            ranked_ids = [row["id"] for row in ranked]
            if not relevant.issubset(ranked_ids):
                raise ValueError("Relevant labels must refer to eligible, published, accessible content at cutoff")
            for k in ks:
                scores = metrics_at_k(ranked_ids, relevant, k)
                for name, value in scores.items():
                    totals[strategy][str(k)][name] += value / len(cases)
    return {"dataset": snapshot.get("name", "unnamed"), "synthetic": snapshot.get("synthetic", False),
            "cutoff": at.isoformat(), "users": len(cases), "contents": len(ids),
            "note": "Macro-average; Precision@K divides by K even with fewer candidates. All strategies use identical access and expiry filters.",
            "results": {s: {k: {n: round(v, 6) for n, v in values.items()} for k, values in rows.items()}
                        for s, rows in totals.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.snapshot.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
