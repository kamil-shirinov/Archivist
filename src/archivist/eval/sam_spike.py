"""Can SAM 3.1 find the artefacts that occlude fields? python -m archivist.eval.sam_spike

Takes 12 dev pages, 3 per severity, chosen by a seeded shuffle of the ground truth: two ledger
cards and one memo at severities 0 and 2, one card and two memos at 1 and 3. Each page is
segmented once per prompt, and the predictions of each prompt are matched one-to-one to the
ground-truth artefacts of its kind, greedily by IoU. Every prediction counts; no score threshold
is applied. Stamps and stains are the artefacts that cover money fields, so they decide:

GO for SAM as the occlusion detector if stamps and stains combined reach recall >= 0.7 and
precision >= 0.7 at IoU >= 0.5; otherwise NO-GO.

Calls go through load_roles(), so a rerun replays the cache and spends nothing. The results go
to results/sam_spike.json with the model config, the decision and the cost of the calls.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from archivist.models import SegmentRequest, describe_config, load_roles
from archivist.schema import BBox, PageGT

SPLIT_DIR = Path("data/dev")
RESULTS_PATH = Path("results/sam_spike.json")
SELECTION_SEED = 8
IOU_THRESHOLD = 0.5
# Ground-truth kind -> the prompt that looks for it: a short noun phrase, one concept each.
PROMPTS = {
    "stamp": "stamp",
    "signature": "signature",
    "stain": "stain",
    "handwritten_amendment": "pencil mark",
}
OCCLUDERS = ("stamp", "stain")
GO_RECALL = GO_PRECISION = 0.7
DECISION_RULE = (
    f"GO for SAM as the occlusion detector if {' and '.join(OCCLUDERS)} combined reach "
    f"recall >= {GO_RECALL} and precision >= {GO_PRECISION} at IoU >= {IOU_THRESHOLD}; "
    "otherwise NO-GO."
)


def load_pages(split_dir: Path = SPLIT_DIR) -> list[PageGT]:
    paths = sorted(p for p in (split_dir / "gt").glob("*.json") if p.name != "world.json")
    return [PageGT.model_validate_json(p.read_text()) for p in paths]


def choose_pages(pages: list[PageGT], seed: int = SELECTION_SEED) -> list[PageGT]:
    """3 pages per severity, cards and memos alternating which type gets two."""
    rng = random.Random(seed)
    chosen = []
    for severity in range(4):
        by_type = {
            doc_type: [p for p in pages if p.severity == severity and p.doc_type == doc_type]
            for doc_type in ("ledger", "memo")
        }
        for group in by_type.values():
            rng.shuffle(group)
        n_cards = 2 if severity % 2 == 0 else 1
        chosen += by_type["ledger"][:n_cards] + by_type["memo"][: 3 - n_cards]
    if len(chosen) != 12:
        raise LookupError(f"the split has too few pages per severity and type: {len(chosen)}")
    return chosen


def page_image(page: PageGT, split_dir: Path = SPLIT_DIR) -> bytes:
    """The scan the ground truth describes, checked against the manifest's hash."""
    path = split_dir / page.image_path
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; rebuild the dev images (D17)")
    image = path.read_bytes()
    manifest = json.loads((split_dir / "manifest.json").read_text())
    if hashlib.sha256(image).hexdigest() != manifest["files"][page.image_path]:
        raise RuntimeError(f"{path} does not match the manifest; rebuild the split")
    return image


def match(truth: list[BBox], predicted: list[BBox]) -> list[float]:
    """IoUs of a one-to-one greedy matching, best pairs first, keeping those >= the threshold."""
    pairs = sorted(
        ((t.iou(p), i, j) for i, t in enumerate(truth) for j, p in enumerate(predicted)),
        reverse=True,
    )
    used_t, used_p, ious = set(), set(), []
    for iou, i, j in pairs:
        if iou < IOU_THRESHOLD:
            break
        if i not in used_t and j not in used_p:
            used_t.add(i)
            used_p.add(j)
            ious.append(iou)
    return ious


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None  # undefined, never 0


def summarise(n_truth: int, n_predicted: int, ious: list[float]) -> dict:
    return {
        "ground_truth": n_truth,
        "predicted": n_predicted,
        "matched": len(ious),
        "recall": _ratio(len(ious), n_truth),
        "precision": _ratio(len(ious), n_predicted),
        "mean_iou": math.fsum(ious) / len(ious) if ious else None,
    }


def _box(bbox: BBox) -> list[int]:
    return [bbox.x0, bbox.y0, bbox.x1, bbox.y1]


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def main() -> None:
    pages = choose_pages(load_pages())
    segmenter = load_roles()["segmenter"]

    counts = {kind: [0, 0, []] for kind in PROMPTS}  # ground truth, predicted, matched IoUs
    page_records, total_cost, calls, cache_hits = [], 0.0, 0, 0
    for page in pages:
        image = page_image(page)
        record = {
            "page_id": page.page_id,
            "doc_type": page.doc_type,
            "severity": page.severity,
            "ground_truth": [{"kind": a.kind, "bbox": _box(a.bbox)} for a in page.artefacts],
            "predicted": [],
        }
        for kind, prompt in PROMPTS.items():
            response = segmenter.segment(
                SegmentRequest(role="segmenter", image=image, prompts=(prompt,))
            )
            calls += 1
            cache_hits += response.cached
            total_cost += response.usage.cost_usd
            truth = [a.bbox for a in page.artefacts if a.kind == kind]
            predicted = [r.bbox for r in response.regions]
            counts[kind][0] += len(truth)
            counts[kind][1] += len(predicted)
            counts[kind][2] += match(truth, predicted)
            record["predicted"] += [
                {
                    "kind": kind,
                    "bbox": _box(r.bbox),
                    "score": None if math.isnan(r.score) else r.score,
                }
                for r in response.regions
            ]
        page_records.append(record)

    per_kind = {kind: summarise(*counts[kind]) for kind in PROMPTS}
    occluders = summarise(
        sum(counts[k][0] for k in OCCLUDERS),
        sum(counts[k][1] for k in OCCLUDERS),
        [iou for k in OCCLUDERS for iou in counts[k][2]],
    )
    go = (occluders["recall"] or 0) >= GO_RECALL and (occluders["precision"] or 0) >= GO_PRECISION
    decision = "GO" if go else "NO-GO"
    results = {
        "spike": "sam_artefacts",
        "split": SPLIT_DIR.name,
        "config": describe_config(),
        "selection_seed": SELECTION_SEED,
        "iou_threshold": IOU_THRESHOLD,
        "prompts": PROMPTS,
        "per_kind": per_kind,
        "occluders": {"kinds": list(OCCLUDERS), **occluders},
        "decision_rule": DECISION_RULE,
        "decision": decision,
        "calls": calls,
        "cache_hits": cache_hits,
        "total_cost_usd": total_cost,  # as billed when each call was first made
        "pages": page_records,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n")

    print(f"pages    {', '.join(p.page_id for p in pages)}")
    print(f"model    {segmenter.name} / {segmenter.model_id}")
    print()
    print(f"{'kind':<24}{'prompt':<14}{'GT':>4}{'pred':>6}{'recall':>8}{'prec':>7}{'mIoU':>7}")
    rows = [(k, PROMPTS[k], per_kind[k]) for k in PROMPTS]
    rows.append((" + ".join(OCCLUDERS), "", occluders))
    for kind, prompt, s in rows:
        print(
            f"{kind:<24}{prompt:<14}{s['ground_truth']:>4}{s['predicted']:>6}"
            f"{_fmt(s['recall']):>8}{_fmt(s['precision']):>7}{_fmt(s['mean_iou']):>7}"
        )
    print()
    print(f"rule     {DECISION_RULE}")
    print(f"decision {decision}")
    print(f"cost     ${total_cost:.4f} for {calls} calls ({cache_hits} from cache)")
    print(f"written  {RESULTS_PATH}")


if __name__ == "__main__":
    main()
