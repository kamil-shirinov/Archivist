"""Prospective phase-2 definitions. No filesystem reader or held-out execution entrypoint."""
from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from archivist.glimmer.metrics import INVALID, parse_answer
from archivist.templates.pages import REAL

OCR_PREFIX_CHARS = 1024
BATCH_SIZE = 8
MAX_NEW_TOKENS = 512
SAMPLE_SEED = 4005
SET_ASIDE_SAMPLE_SIZE = 500
PARSER_VERSION = 'native-assistant-header-v1'


def parse_phase2(text: str, labels: Sequence[str], *, at_token_limit: bool = False) -> str:
    """Decode either native continuation, then apply the unchanged exact-label rule."""
    if at_token_limit:
        return INVALID
    if text.startswith((' to=user<|message|>', ' to=self<|message|>')):
        text = '<|start|>assistant' + text
    return parse_answer(text, list(labels))


def decision_text(ocr: str) -> str:
    """Fixed header excerpt; independent of labels, predicted classes and confidence."""
    return ocr[:OCR_PREFIX_CHARS]


@dataclass(frozen=True)
class SamplePage:
    page: str
    stratum: str
    inclusion_probability: float
    weight: float


def draw_sample(
    assignments: Mapping[str, str],
    families: Collection[str],
    held_out_issues: Collection[str],
    *,
    go: bool = False,
) -> list[SamplePage]:
    """Pure selection after an explicit start. Never reads a page or result file.

    assignments is the validated successful sweep map, supplied only after permission.
    Title-check results play no part in selection: all named-family pages are a census.
    """
    if not go:
        raise PermissionError('phase 2 has not been authorised; do not inspect its frame or draw')
    family_set = set(families)
    if not family_set or 'unsupported' in family_set or 'other' in family_set:
        raise ValueError('expected the approved family IDs only')
    named, set_aside = [], []
    for ref, assigned in assignments.items():
        match = REAL.fullmatch(ref)
        if match is None or match['issue'] not in held_out_issues:
            raise ValueError('frame must contain exclusively held-out Treasury references')
        if assigned in family_set:
            named.append(ref)
        elif assigned == 'unsupported':
            set_aside.append(ref)
        else:
            raise ValueError('failed or unknown classifications are not set-aside pages')
    pool = sorted(set_aside)
    n = min(SET_ASIDE_SAMPLE_SIZE, len(pool))
    selected = random.Random(SAMPLE_SEED).sample(pool, n)
    probability = n / len(pool) if pool else 1.0
    records = [SamplePage(ref, 'named_family', 1.0, 1.0) for ref in named]
    records += [SamplePage(ref, 'classifier_set_aside', probability, 1 / probability)
                for ref in selected]
    return sorted(records, key=lambda row: row.page)


def weighted_score(
    expected: Mapping[str, str],
    predicted: Mapping[str, str],
    labels: Sequence[str],
    weights: Mapping[str, float],
) -> dict:
    """Design-weighted confusion totals against pipeline proxy labels, not human truth."""
    label_set = set(labels)
    if not expected or len(label_set) != len(labels) or INVALID in label_set:
        raise ValueError('nonempty references and unique valid labels required')
    if set(weights) != set(expected) or set(predicted) - set(expected):
        raise ValueError('prediction/weight IDs do not match the sample')
    if set(expected.values()) - label_set:
        raise ValueError('unknown reference label')
    if any(not math.isfinite(w) or w <= 0 for w in weights.values()):
        raise ValueError('weights must be finite and positive')
    counts = defaultdict(float)
    for ref, truth in expected.items():
        answer = predicted.get(ref)
        counts[truth, answer if answer in label_set else INVALID] += weights[ref]
    per_family = {}
    for label in labels:
        tp = counts[label, label]
        fp = sum(n for (truth, answer), n in counts.items() if answer == label and truth != label)
        fn = sum(n for (truth, answer), n in counts.items() if truth == label and answer != label)
        per_family[label] = {
            'tp': tp, 'fp': fp, 'fn': fn, 'support': tp + fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
        }
    return {
        'sample_pages': len(expected), 'weighted_population': sum(weights.values()),
        'per_family': per_family,
        'confusion': [{'expected': t, 'predicted': a, 'count': n}
                      for (t, a), n in sorted(counts.items()) if n],
        'interpretation': 'design-weighted estimates against pipeline proxy labels',
    }
