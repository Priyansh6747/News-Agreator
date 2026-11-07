from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Core.models import Backend, Candidate
from Core.settings import Settings
from tool.decisions_heuristic import HeuristicDecisionEngine
from tool.decisions_laya import LayaDecisionEngine

DEFAULT_DATA = Path(__file__).resolve().parents[3] / "Docs" / "eval"
LABELS = ["market", "geopolitics", "company", "event", "comparison", "other"]
TYPE_LABELS = ["report", "opinion", "press_release", "aggregator", "unknown"]


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def binary_metrics(scores: list[float], labels: list[int]) -> dict[str, float]:
    predictions = [1 if score >= 0.5 else 0 for score in scores]
    tp = sum(1 for p, label in zip(predictions, labels) if p == 1 and label == 1)
    fp = sum(1 for p, label in zip(predictions, labels) if p == 1 and label == 0)
    tn = sum(1 for p, label in zip(predictions, labels) if p == 0 and label == 0)
    fn = sum(1 for p, label in zip(predictions, labels) if p == 0 and label == 1)
    positives = [s for s, label in zip(scores, labels) if label == 1]
    negatives = [s for s, label in zip(scores, labels) if label == 0]
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    pairs = len(positives) * len(negatives)
    return {
        "accuracy": (tp + tn) / len(labels) if labels else 0.0,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0,
        "mean_positive": sum(positives) / len(positives) if positives else 0.0,
        "mean_negative": sum(negatives) / len(negatives) if negatives else 0.0,
        "auc": wins / pairs if pairs else 0.0,
    }


def confusion(
    pairs: list[tuple[str, str]],
    labels: list[str],
) -> dict[tuple[str, str], int]:
    matrix: dict[tuple[str, str], int] = defaultdict(int)
    for actual, predicted in pairs:
        matrix[(actual, predicted)] += 1
    return matrix


def confusion_table(
    matrix: dict[tuple[str, str], int],
    labels: list[str],
) -> list[str]:
    header = "| actual \\ predicted | " + " | ".join(labels) + " |"
    divider = "|---" * (len(labels) + 1) + "|"
    rows = [header, divider]
    for actual in labels:
        cells = [str(matrix.get((actual, predicted), 0)) for predicted in labels]
        rows.append(f"| {actual} | " + " | ".join(cells) + " |")
    return rows


async def evaluate(engine, name: str, data_dir: Path) -> dict:
    queries = load_jsonl(data_dir / "queries.jsonl")
    relevance = load_jsonl(data_dir / "relevance.jsonl")
    types = load_jsonl(data_dir / "article_types.jsonl")
    injections = load_jsonl(data_dir / "injection.jsonl")
    result: dict = {"name": name, "tasks": {}, "latency_ms": {}}

    started = perf_counter()
    classification_pairs = []
    for row in queries:
        predicted = await engine.classify_query(row["query"])
        classification_pairs.append((row["class"], predicted.value))
    classification_accuracy = sum(
        1 for actual, predicted in classification_pairs if actual == predicted
    ) / len(classification_pairs)
    result["tasks"]["classification"] = {
        "accuracy": classification_accuracy,
        "pairs": classification_pairs,
    }
    result["latency_ms"]["classification"] = int((perf_counter() - started) * 1000)

    started = perf_counter()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in relevance:
        grouped[row["query"]].append(row)
    scores: list[float] = []
    labels: list[int] = []
    for query, rows in grouped.items():
        candidates = [
            Candidate(
                title=row["title"],
                url=f"https://example.com/{index}",
                snippet=row["snippet"],
                backend=Backend.PUBLISHER_RSS,
            )
            for index, row in enumerate(rows)
        ]
        assessments = await engine.assess(query, candidates)
        for row, assessment in zip(rows, assessments):
            scores.append(assessment.relevance)
            labels.append(row["label"])
    result["tasks"]["relevance"] = binary_metrics(scores, labels)
    result["latency_ms"]["relevance"] = int((perf_counter() - started) * 1000)

    started = perf_counter()
    type_pairs = []
    for row in types:
        candidate = Candidate(
            title=row["title"],
            url=f"https://{row['domain']}/story",
            publisher=row["publisher"],
            domain=row["domain"],
            snippet=row["snippet"],
            backend=Backend.PUBLISHER_RSS,
        )
        assessment = (await engine.assess(row["title"], [candidate]))[0]
        type_pairs.append((row["label"], assessment.article_type.value))
    result["tasks"]["article_type"] = {
        "accuracy": sum(1 for a, p in type_pairs if a == p) / len(type_pairs),
        "pairs": type_pairs,
    }
    result["latency_ms"]["article_type"] = int((perf_counter() - started) * 1000)

    started = perf_counter()
    injection_scores = [await engine.injection_risk(row["text"]) for row in injections]
    result["tasks"]["injection"] = binary_metrics(
        injection_scores, [row["label"] for row in injections]
    )
    result["latency_ms"]["injection"] = int((perf_counter() - started) * 1000)
    return result


def build_engine(name: str, settings: Settings):
    if name == "heuristic":
        return HeuristicDecisionEngine()
    return LayaDecisionEngine(
        fallback=None,
        preload=settings.laya_preload,
        device=settings.laya_device,
        default=settings.laya_default_model,
        max_loaded=settings.laya_max_loaded,
        batch_size=settings.laya_batch_size,
    )


def render(results: list[dict], data_dir: Path, settings: Settings) -> str:
    lines = [
        "# Laya evaluation report",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Data: `{data_dir}`",
        f"Engines: {', '.join(result['name'] for result in results)}",
        "",
        "The eval set is authored (see `Docs/eval/README.md`); treat these numbers as a development",
        "signal, not an independent benchmark.",
        "",
        "## Summary",
        "",
        "| Task | Engine | Accuracy | Precision | Recall | F1 | Mean pos | Mean neg | AUC |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        for task in ("relevance", "injection"):
            metrics = result["tasks"][task]
            lines.append(
                f"| {task} | {result['name']} | {metrics['accuracy']:.3f} | "
                f"{metrics['precision']:.3f} | {metrics['recall']:.3f} | "
                f"{metrics['f1']:.3f} | {metrics['mean_positive']:.3f} | "
                f"{metrics['mean_negative']:.3f} | {metrics['auc']:.3f} |"
            )
        for task in ("classification", "article_type"):
            metrics = result["tasks"][task]
            lines.append(
                f"| {task} | {result['name']} | {metrics['accuracy']:.3f} | - | - | - | - | - | - |"
            )

    lines.extend(["", "## Latency", "", "| Task | Engine | Total ms |", "|---|---|---|"])
    for result in results:
        for task, elapsed in result["latency_ms"].items():
            lines.append(f"| {task} | {result['name']} | {elapsed} |")

    for result in results:
        lines.extend(
            [
                "",
                f"## {result['name']}",
                "",
                "### Query classification",
                "",
                *confusion_table(
                    confusion(result["tasks"]["classification"]["pairs"], LABELS), LABELS
                ),
                "",
                "### Article type",
                "",
                *confusion_table(
                    confusion(result["tasks"]["article_type"]["pairs"], TYPE_LABELS),
                    TYPE_LABELS,
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Configuration",
            "",
            f"- `laya_preload`: {settings.laya_preload}",
            f"- `laya_device`: {settings.laya_device}",
            f"- `laya_default_model`: {settings.laya_default_model}",
            f"- `laya_max_loaded`: {settings.laya_max_loaded}",
            f"- `laya_batch_size`: {settings.laya_batch_size}",
            "",
        ]
    )
    return "\n".join(lines)


async def run(data_dir: Path, engine_names: list[str], output: Path | None) -> None:
    settings = Settings(app_env="dev")
    results = []
    for name in engine_names:
        print(f"running {name}...", file=sys.stderr)
        results.append(await evaluate(build_engine(name, settings), name, data_dir))
    report = render(results, data_dir, settings)
    print(report)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report + "\n", encoding="utf-8")
        print(f"wrote {output}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare decision engines on the eval set.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--engine", choices=["both", "heuristic", "laya"], default="both")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    engines = ["heuristic", "laya"] if args.engine == "both" else [args.engine]
    asyncio.run(run(args.data_dir, engines, args.out))


if __name__ == "__main__":
    main()
