import io
import itertools
import json
import random

import numpy as np
import pytest

from archivist.schema import PageGT, ledger_header_id, ledger_line_id, memo_field_id
from archivist.synth import render
from archivist.synth.world import LedgerCard, Memo, generate_world

SEED = 7
DARK = 128  # grey level below which a pixel counts as ink; the paper is ~242


@pytest.fixture(scope="module")
def world():
    return generate_world(SEED)


@pytest.fixture(scope="module", params=render.FILLS, ids=lambda f: f.font.split("/")[0])
def pages(request, world):
    """One card and one memo per fill style, so every entry font is exercised."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(render, "_pick_fill", lambda rng: request.param)
        card = render.render_card(world.cards[0], random.Random(SEED))
        memo = render.render_memo(world.memos[0], random.Random(SEED))
    return [card, memo]


def _card_expected(card: LedgerCard) -> dict[str, str]:
    doc = card.doc_id
    expected = {
        ledger_header_id(doc, "account_no"): card.account_no,
        ledger_header_id(doc, "holder"): card.holder,
        ledger_header_id(doc, "sheet_no"): str(card.sheet_no),
        ledger_header_id(doc, "brought_forward"): f"{card.brought_forward:,.2f}",
        ledger_header_id(doc, "carried_forward"): f"{card.carried_forward:,.2f}",
    }
    for line in card.lines:
        n = line.line_no
        expected[ledger_line_id(doc, n, "date")] = line.date.strftime("%d/%m/%y")
        expected[ledger_line_id(doc, n, "description")] = line.description
        for column in ("debit", "credit"):
            amount = getattr(line, column)
            expected[ledger_line_id(doc, n, column)] = "" if amount is None else f"{amount:,.2f}"
        expected[ledger_line_id(doc, n, "balance")] = f"{line.balance:,.2f}"
    return expected


def _memo_expected(memo: Memo) -> dict[str, str]:
    values = {
        "memo_no": memo.memo_no,
        "date": memo.date.strftime("%d/%m/%y"),
        "account_no": memo.account_no,
        "counterparty": memo.counterparty,
        "amount": f"{memo.amount:,.2f}",
        "amount_words": memo.amount_words,
        "ledger_ref": memo.ledger_ref,
    }
    return {memo_field_id(memo.doc_id, name): value for name, value in values.items()}


def test_field_counts(pages):
    (_, card), (_, memo) = pages
    assert len(card.fields) == 95
    assert len(memo.fields) == 7
    assert card.severity == memo.severity == 0
    assert card.artefacts == memo.artefacts == []


def test_printed_strings_match_world(world, pages):
    (_, card), (_, memo) = pages
    assert {f.field_id: f.printed for f in card.fields} == _card_expected(world.cards[0])
    assert {f.field_id: f.printed for f in memo.fields} == _memo_expected(world.memos[0])


def test_bboxes_inside_image_and_disjoint(pages):
    for image, gt in pages:
        assert (gt.width, gt.height) == image.size
        for f in gt.fields:
            assert 0 <= f.bbox.x0 and 0 <= f.bbox.y0, f.field_id
            assert f.bbox.x1 <= gt.width and f.bbox.y1 <= gt.height, f.field_id
        for a, b in itertools.combinations(gt.fields, 2):
            assert a.bbox.iou(b.bbox) == 0.0, (a.field_id, b.field_id)


def test_ink_inside_filled_boxes_only(pages):
    for image, gt in pages:
        dark = np.asarray(image.convert("L")) < DARK
        for f in gt.fields:
            ink = dark[f.bbox.y0 : f.bbox.y1, f.bbox.x0 : f.bbox.x1].any()
            assert ink == bool(f.printed), f.field_id


def test_page_sizes(pages):
    (card_image, _), (memo_image, _) = pages
    assert card_image.size == (1700, 1100)
    assert memo_image.size == (1100, 1400)


def test_same_seed_same_png(world):
    def png(card: LedgerCard) -> bytes:
        image, _ = render.render_card(card, random.Random(SEED))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    assert png(world.cards[0]) == png(world.cards[0])


def test_render_world_writes_pages_with_their_source_errors(tmp_path):
    world = generate_world(SEED, source_error_rate=0.5)
    pages = render.render_world(world, tmp_path, n_cards=3, n_memos=6, seed=SEED)
    assert len(pages) == 9
    for gt in pages:
        for folder, suffix in (("pages", ".png"), ("pages", ".json"), ("overlays", ".png")):
            assert (tmp_path / folder / f"{gt.page_id}{suffix}").is_file()
        saved = (tmp_path / gt.image_path).with_suffix(".json").read_text()
        assert PageGT.model_validate(json.loads(saved)) == gt
        on_page = {f.field_id for f in gt.fields}
        expected = [e for e in world.source_errors if on_page & set(e.field_ids)]
        assert gt.source_errors == expected
    assert any(gt.source_errors for gt in pages)
