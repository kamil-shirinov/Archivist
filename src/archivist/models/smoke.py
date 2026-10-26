"""One real call through the extractor role: python -m archivist.models.smoke

Takes the first severity-0 ledger card of the dev set and asks for three values, each with a box
on Muse Spark's 0–1000 grid, then prints the answer, the boxes in pixels, the usage, the cost and
the ledger's total spend. The page's severity is re-derived from the manifest's seed, as the
builder assigned it, so ground truth (data/dev/gt/) is never read. The call goes through
load_roles(), so a second run is a cache hit and spends nothing.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image

from archivist.models import LLMRequest, load_roles
from archivist.synth import build
from archivist.synth.world import generate_world

SPLIT_DIR = Path("data/dev")
# The P6 build command, run with --overwrite when the dev images are missing (D17).
DEV_BUILD = [
    "--split", "dev", "--seed", "1001", "--accounts", "4", "--cards-per-account", "3",
    "--memo-rate", "0.35", "--error-rate", "0.2", "--overwrite",
]  # fmt: skip

FIELDS = {
    "account_no": "the account number",
    "brought_forward": "the brought-forward balance",
    "line_1_balance": "the balance on line 1",
}
SYSTEM = (
    "You read scanned ledger cards. Report every value exactly as printed. Boxes are "
    "[x_min, y_min, x_max, y_max] on a 0-1000 grid: (0, 0) is the top-left corner of the image "
    "and (1000, 1000) the bottom-right."
)
PROMPT = (
    "From this ledger card read "
    + "; ".join(FIELDS.values())
    + ". For each, give the value exactly as printed and a tight bounding box around it."
)
VALUE_AND_BOX = {
    "type": "object",
    "properties": {
        "value": {"type": "string"},
        "box": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
    },
    "required": ["value", "box"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {name: VALUE_AND_BOX for name in FIELDS},
    "required": list(FIELDS),
    "additionalProperties": False,
}


def first_clean_ledger(split_dir: Path = SPLIT_DIR) -> Path:
    """The first ledger card at severity 0, checked against the manifest's hash."""
    images = split_dir / "images"
    if not images.is_dir() or not any(images.iterdir()):
        build.main(["--out-root", str(split_dir.parent), *DEV_BUILD])
    manifest = json.loads((split_dir / "manifest.json").read_text())
    params = manifest["params"]
    world = generate_world(
        manifest["seed"],
        params["n_accounts"],
        params["cards_per_account"],
        memo_rate=params["memo_rate"],
        source_error_rate=params["source_error_rate"],
    )
    severities = build._severities(manifest["seed"], len(world.cards) + len(world.memos))
    # Cards are rendered first, so the first len(cards) severities are theirs.
    for card, severity in zip(world.cards, severities, strict=False):
        if severity == 0:
            path = images / f"{card.doc_id}.jpg"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != manifest["files"][f"images/{path.name}"]:
                raise RuntimeError(f"{path} does not match the manifest; rebuild the split")
            return path
    raise LookupError(f"no severity-0 ledger card in {split_dir}")


def to_pixels(box: list[int], width: int, height: int) -> tuple[int, ...]:
    """0–1000 grid to pixels, clamped: the model may answer slightly outside the grid."""
    x0, y0, x1, y1 = (min(max(v, 0), 1000) for v in box)
    return (
        round(x0 * width / 1000),
        round(y0 * height / 1000),
        round(x1 * width / 1000),
        round(y1 * height / 1000),
    )


def main() -> None:
    page = first_clean_ledger()
    image = page.read_bytes()
    width, height = Image.open(io.BytesIO(image)).size
    extractor = load_roles()["extractor"]

    response = extractor.complete(
        LLMRequest(
            role="extractor",
            prompt=PROMPT,
            images=(image,),
            system=SYSTEM,
            json_schema=SCHEMA,
            max_output_tokens=2048,
        )
    )

    print(f"page     {page} ({width} x {height} px)")
    print(f"model    {response.backend} / {response.model_id}, cached: {response.cached}")
    answer = json.loads(response.text)
    for name in FIELDS:
        value, box = answer[name]["value"], answer[name]["box"]
        print(f"{name:<16} {value!r:<16} grid {box} -> px {to_pixels(box, width, height)}")
    usage = response.usage
    print(f"usage    {usage.input_tokens} input, {usage.output_tokens} output tokens")
    print(f"cost     ${usage.cost_usd:.6f}")
    print(f"ledger   ${extractor.inner.guard.spent():.6f} spent in total")


if __name__ == "__main__":
    main()
