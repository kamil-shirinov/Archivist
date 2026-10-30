"""P31 classification counts, defined before either Glimmer arm is scored."""
from __future__ import annotations

from collections import Counter

INVALID = "invalid"


def parse_answer(text: str, labels: list[str]) -> str:
    # Native Glimmer reasoning is separated from its final recipient. Never hunt for a
    # convenient label inside prose or reasoning; the whole final answer must be a label.
    marker = "<|start|>assistant to=user<|message|>"
    if marker in text:
        text = text.rsplit(marker, 1)[1]
    for ending in ("<|eot|>", "<|end_of_text|>"):
        text = text.removesuffix(ending).strip()
    value = text.strip()
    return value if value in labels else INVALID


def score(expected: dict[str, str], predicted: dict[str, str], labels: list[str]) -> dict:
    if set(predicted) - set(expected):
        raise ValueError("predictions contain unknown page IDs")
    if not expected or len(set(labels)) != len(labels) or INVALID in labels:
        raise ValueError("nonempty expected set and unique valid labels required")
    if set(expected.values()) - set(labels):
        raise ValueError("unknown reference label")
    counts = Counter()
    missing = 0
    for page, target in expected.items():
        raw = predicted.get(page)
        missing += raw is None
        answer = raw if raw in labels else INVALID
        counts[target, answer] += 1
    per_family = {}
    for label in labels:
        tp = counts[label, label]
        fp = sum(n for (truth, answer), n in counts.items() if answer == label and truth != label)
        fn = sum(n for (truth, answer), n in counts.items() if truth == label and answer != label)
        per_family[label] = {"tp":tp,"fp":fp,"fn":fn,"support":tp+fn,
                             "precision":tp/(tp+fp) if tp+fp else None,
                             "recall":tp/(tp+fn) if tp+fn else None}
    def macro(metric: str) -> float | None:
        values = [row[metric] for row in per_family.values() if row[metric] is not None]
        return sum(values)/len(values) if values else None
    return {
        "pages":len(expected), "accuracy":sum(counts[label,label] for label in labels)/len(expected),
        "invalid":sum(n for (_,answer),n in counts.items() if answer == INVALID),
        "missing":missing, "per_family":per_family,
        "macro_precision_defined_labels":macro("precision"),
        "macro_recall_defined_labels":macro("recall"),
        "confusion":[{"expected":truth,"predicted":answer,"count":n}
                     for (truth,answer),n in sorted(counts.items())],
    }
