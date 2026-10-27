"""The run exporter: a hand-built run in tmp_path whose joins are obvious, and the committed runs.

No model, no network. Only the rule-id test imports archivist.eval, to hold the export's rule ids
to eval.run_eval.check_rule.
"""

import ast
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

import jsonschema
import pytest
from PIL import Image

from archivist.doctypes import REGISTRY
from archivist.export import bundle, database, rules
from archivist.export.schema import SCHEMA_PATH, SCHEMA_VERSION, Bundle, Truth, json_schema
from archivist.pipeline.checks import run_checks
from archivist.pipeline.extract import PageExtraction
from archivist.pipeline.verify import ReRead, decide, load_verdicts
from archivist.schema import (
    BBox,
    Citation,
    ExtractedValue,
    FieldGT,
    PageGT,
    ledger_header_id,
    ledger_line_id,
    memo_field_id,
)

RUN, SOURCE, SPLIT = "demo-verify", "demo-extract", "demo"
ACCOUNT, HOLDER = "12345678", "Ann Lee"
BOX = BBox(x0=1, y0=1, x1=20, y1=10)
ROOT = Path(__file__).resolve().parents[1]
EXPORT_SRC = ROOT / "src" / "archivist" / "export"
COMMITTED_RUNS = ROOT / "results" / "runs"
COMMITTED = sorted(p.name for p in COMMITTED_RUNS.glob("test-archivist-*"))


def _page(page_id: str, doc_type: str, values: dict[str, str]) -> PageExtraction:
    return PageExtraction(
        page_id=page_id,
        doc_type=doc_type,
        values=[
            ExtractedValue(
                field_id=f,
                value=values.get(f, ""),
                citation=Citation(page_id=page_id, bbox=BOX),
            )
            for f in REGISTRY[doc_type].field_ids(page_id)
        ],
    )


def _card(page_id: str, sheet: int, account: str, brought: str, lines, carried: str):
    values = {
        ledger_header_id(page_id, "account_no"): account,
        ledger_header_id(page_id, "holder"): HOLDER,
        ledger_header_id(page_id, "sheet_no"): str(sheet),
        ledger_header_id(page_id, "brought_forward"): brought,
        ledger_header_id(page_id, "carried_forward"): carried,
    }
    for no, row in enumerate(lines, 1):
        for column, text in zip(("date", "description", "debit", "credit", "balance"), row):
            values[ledger_line_id(page_id, no, column)] = text
    return _page(page_id, "ledger_card", values)


def _memo(page_id: str, date: str, amount: str, words: str, ref: str) -> PageExtraction:
    values = {
        "memo_no": page_id[-3:],
        "date": date,
        "account_no": ACCOUNT,
        "counterparty": "Acme Ltd",
        "amount": amount,
        "amount_words": words,
        "ledger_ref": ref,
    }
    return _page(page_id, "payment_memo", {memo_field_id(page_id, k): v for k, v in values.items()})


def _pages() -> list[PageExtraction]:
    """One account, sheets 1 to 3; sheet 3 misreads the account. Memo 001 matches its line, 002
    pays more than its line debits, 003 cites a sheet that isn't in the batch."""
    return [
        _card(
            "card-1",
            1,
            ACCOUNT,
            "100.00",
            [
                ("01/01/86", "CHQ 100001", "20.00", "", "80.00"),
                ("05/01/86", "CASH", "30.00", "", "50.00"),
            ],
            "50.00",
        ),
        _card(
            "card-2",
            2,
            ACCOUNT,
            "50.00",
            [
                ("10/01/86", "SALARY", "", "200.00", "250.00"),
                ("12/01/86", "CHQ 100002", "40.00", "", "210.00"),
            ],
            "210.00",
        ),
        _card(
            "card-3",
            3,
            "12345679",
            "210.00",
            [("15/01/86", "CASH", "10.00", "", "200.00")],
            "200.00",
        ),
        _memo("memo-001", "03/01/86", "30.00", "Thirty pounds only", "Sheet 1 / Line 02"),
        _memo("memo-002", "11/01/86", "45.00", "Forty-five pounds only", "Sheet 2 / Line 02"),
        _memo("memo-003", "11/01/86", "5.00", "Five pounds only", "Sheet 9 / Line 01"),
        PageExtraction(page_id="blank", doc_type="unsupported", values=[]),
    ]


def _world(root: Path) -> Path:
    """A split, an extraction run and its verification (every re-read agrees) under root, laid out
    as the repository is, with a gt/ folder beside the images; returns the verification run."""
    images = root / "data" / SPLIT / "images"
    images.mkdir(parents=True)
    pages = _pages()
    for page_id in [p.page_id for p in pages] + ["lost"]:
        Image.new("RGB", (40, 30), "white").save(images / f"{page_id}.jpg")
    gt = root / "data" / SPLIT / "gt"
    gt.mkdir()
    for severity, page in enumerate(
        pages + [PageExtraction(page_id="lost", doc_type="x", values=[])]
    ):
        page_gt = PageGT(
            page_id=page.page_id,
            doc_type="memo",
            image_path=f"images/{page.page_id}.jpg",
            width=40,
            height=30,
            severity=severity % 4,
            fields=[FieldGT(field_id=v.field_id, printed=v.value, bbox=BOX) for v in page.values],
            artefacts=[],
            source_errors=[],
        )
        (gt / f"{page.page_id}.json").write_text(page_gt.model_dump_json())

    relative_images = f"data/{SPLIT}/images"
    source = root / "results" / "runs" / SOURCE
    source.mkdir(parents=True)
    (source / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))
    (source / "run.json").write_text(
        json.dumps(
            {
                "run_id": SOURCE,
                "images": relative_images,
                "citations": "S0+ink",
                "failed_pages": {"lost": "ExtractionFailed: classification"},
            }
        )
    )
    flags: dict[str, list] = {}
    for flag in run_checks(pages):
        flags.setdefault(flag.field_id, []).append(flag)
    verdicts = [
        decide(
            page.page_id,
            page.doc_type,
            v,
            flags.get(v.field_id, []),
            occluders=[],
            reading=ReRead(v.value),
            reread_flags=flags.get(v.field_id, []),  # the re-reads agree, so do their checks
        )
        for page in pages
        for v in page.values
    ]
    run = root / "results" / "runs" / RUN
    run.mkdir()
    (run / "verdicts.jsonl").write_text("".join(v.model_dump_json() + "\n" for v in verdicts))
    (run / "run.json").write_text(
        json.dumps(
            {
                "run_id": RUN,
                "source_run": SOURCE,
                "images": relative_images,
                "citations": "S0+ink",
                "policy": {"version": "v2"},
            }
        )
    )
    return run


@pytest.fixture
def world(tmp_path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)  # paths in the runs are relative to the repository, as on disk
    return _world(tmp_path)


@pytest.fixture
def built(world) -> Bundle:
    return bundle.build(Path("results/runs") / RUN)


def _field(b: Bundle, field_id: str):
    return next(f for f in b.fields if f.field_id == field_id)


def _link(b: Bundle, link_id: str):
    return next(link for link in b.links if link.link_id == link_id)


# --- the hand-built run ------------------------------------------------------------------------


def test_pages_include_unsupported_and_failed_ones_with_their_size(built):
    pages = {p.page_id: p for p in built.pages}
    assert len(pages) == 8
    assert pages["lost"].doc_type == "failed"
    assert pages["lost"].failure == "ExtractionFailed: classification"
    assert pages["blank"].doc_type == "unsupported" and pages["blank"].field_ids == []
    assert (pages["card-1"].width, pages["card-1"].height) == (40, 30)
    assert pages["card-1"].image_path == f"data/{SPLIT}/images/card-1.jpg"
    assert built.run.split == SPLIT and built.run.extraction_run == SOURCE


def test_the_account_holds_its_sheets_in_order_with_the_misread_card(built):
    [account] = built.accounts
    assert account.account_no == ACCOUNT and account.holder == HOLDER
    assert [(s.sheet, s.page_id, s.agrees) for s in account.sheets] == [
        (1, "card-1", True),
        (2, "card-2", True),
        (3, "card-3", False),
    ]
    assert account.missing_sheets == []


def test_links_say_whether_they_agree(built):
    m1, m2, m3 = (_link(built, f"memo_line:memo-00{n}") for n in (1, 2, 3))
    assert (m1.target, m1.agrees) == ("card-1", True)
    assert m1.checks == {"account": True, "amount": True, "date": True}
    assert ledger_line_id("card-1", 2, "debit") in m1.target_fields
    assert (m2.target, m2.agrees, m2.checks["amount"]) == ("card-2", False, False)
    assert (m3.target, m3.agrees) == (None, None)
    assert "no card for sheet 9" in m3.note

    cards = {n: _link(built, f"card_account:card-{n}") for n in (1, 2, 3)}
    assert [(c.target, c.agrees) for c in cards.values()] == [(ACCOUNT, True)] * 2 + [
        (ACCOUNT, False)
    ]
    assert "12345679" in cards[3].note

    sheets = [link for link in built.links if link.kind == "sheet_sheet"]
    assert [(s.source, s.target, s.agrees) for s in sheets] == [
        ("card-1", "card-2", True),
        ("card-2", "card-3", True),
    ]


def test_transactions_are_the_used_lines_joined_to_their_memos(built):
    txns = {t.txn_id: t for t in built.transactions}
    assert list(txns) == ["card-1:01", "card-1:02", "card-2:01", "card-2:02", "card-3:01"]
    assert all(t.account_no == ACCOUNT for t in txns.values())
    assert (txns["card-1:02"].memos, txns["card-1:02"].memos_agree) == (["memo-001"], True)
    assert (txns["card-2:02"].memos, txns["card-2:02"].memos_agree) == (["memo-002"], False)
    assert (txns["card-2:01"].memos, txns["card-2:01"].memos_agree) == ([], None)
    assert (txns["card-2:02"].debit, txns["card-2:02"].balance) == ("40.00", "210.00")
    assert txns["card-1:01"].status == "accepted"
    assert txns["card-2:02"].status == "review"  # memo 002 flags its debit


def test_flags_carry_their_rule_their_equation_and_review_reasons(built):
    amount = _field(built, memo_field_id("memo-002", "amount"))
    [flag] = [f for f in amount.flags if f.rule == "memo_amount"]
    assert flag.related == [ledger_line_id("card-2", 2, "debit")]
    assert amount.status == "review"
    assert [(r.code, r.rule) for r in amount.reasons] == [("rule_failed", "memo_amount")]
    debit = _field(built, ledger_line_id("card-2", 2, "debit"))
    assert [f.related for f in debit.flags if f.rule == "memo_amount"] == [
        [memo_field_id("memo-002", "amount")]
    ]

    account = _field(built, ledger_header_id("card-3", "account_no"))
    [flag] = account.flags
    assert flag.rule == "card_account_by_holder" and flag.suggested == ACCOUNT
    assert flag.related == [ledger_header_id(f"card-{n}", "account_no") for n in (1, 2)]

    ref = _field(built, memo_field_id("memo-003", "ledger_ref"))
    assert [(f.rule, f.related) for f in ref.flags] == [("unresolvable", [])]
    assert ref.status == "accepted" and ref.reasons == []

    ok = _field(built, ledger_line_id("card-1", 1, "debit"))
    assert (ok.status, ok.reasons, ok.box, ok.original_box) == ("accepted", [], BOX, BOX)
    assert ok.reread == "20.00" and ok.reread_status == "agrees"


def test_a_running_balance_flag_names_the_line_before_it():
    lines = [
        ("01/01/86", "CHQ 100001", "20.00", "", "80.00"),
        ("05/01/86", "CASH", "35.00", "", "50.00"),  # the balances imply a debit of 30.00
    ]
    pages = [_card("card-1", 1, ACCOUNT, "100.00", lines, "50.00")]
    reading = rules.Reading(pages)
    flags = [f for f in run_checks(pages) if f.field_id == ledger_line_id("card-1", 2, "debit")]
    assert [rules.rule_id(f) for f in flags] == ["running_balance"]
    assert rules.related(flags[0], reading) == [
        ledger_line_id("card-1", 1, "balance"),
        ledger_line_id("card-1", 2, "credit"),
        ledger_line_id("card-1", 2, "balance"),
    ]


def test_the_bundle_validates_against_its_schema(world, built):
    [path] = bundle.write(built, Path("data/bundles") / RUN)
    loaded = Bundle.model_validate_json(path.read_text())
    assert loaded == built and loaded.schema_version == SCHEMA_VERSION


def test_the_committed_json_schema_is_current():
    assert (ROOT / SCHEMA_PATH).read_text() == json_schema(), (
        "run python -m archivist.export.schema"
    )


def test_database_row_counts_match_the_verdicts(world, built):
    out = Path("exports") / RUN
    database.write(built, out)
    verdicts = load_verdicts(world / "verdicts.jsonl")
    db = sqlite3.connect(out / database.DATABASE_FILE)

    def count(table: str) -> int:
        return db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    assert count("field_values") == len(verdicts)
    by_status = dict(db.execute("SELECT status, COUNT(*) FROM field_values GROUP BY status"))
    assert by_status == dict(Counter(v.status for v in verdicts))
    assert count("documents") == 8 and count("memos") == 3 and count("accounts") == 1
    assert count("transactions") == 5 and count("links") == 3 + 3 + 2
    row = db.execute(
        "SELECT status, confidence, page_id, x0, y0, x1, y1, checks, proposal FROM field_values "
        "WHERE field_id = ?",
        (memo_field_id("memo-002", "amount"),),
    ).fetchone()
    assert row == ("review", 0.3, "memo-002", 1, 1, 20, 10, "memo_amount", None)
    assert db.execute(
        "SELECT debit_pence, balance_pence, memos, memos_agree FROM transactions "
        "WHERE txn_id = 'card-2:02'"
    ).fetchone() == (4000, 21000, "memo-002", 0)
    db.close()
    lines = (out / "field_values.csv").read_text().splitlines()
    assert len(lines) == len(verdicts) + 1 and lines[0].startswith("field_id,")


def test_output_is_byte_identical_across_two_runs(world):
    outputs = []
    for attempt in ("a", "b"):
        b = bundle.build(Path("results/runs") / RUN)
        written = bundle.write(b, Path(attempt) / "bundle", with_truth=True)
        written += database.write(b, Path(attempt) / "exports")
        outputs.append({p.relative_to(attempt): p.read_bytes() for p in written})
    assert outputs[0] == outputs[1]
    assert len(outputs[0]) == 2 + 7


def test_check_passes_on_a_fresh_export_and_fails_on_a_changed_one(world, built, tmp_path):
    out = Path("data/bundles") / RUN
    bundle.write(built, out)
    assert bundle.check(built, out) == []
    text = (out / bundle.BUNDLE_FILE).read_text()
    (out / bundle.BUNDLE_FILE).write_text(text.replace('"accepted"', '"review"', 1))
    assert any("differs" in p for p in bundle.check(built, out))
    database.write(built, Path("exports") / RUN)
    assert database.check(built, Path("exports") / RUN, tmp_path / "scratch") == []


# --- boundaries --------------------------------------------------------------------------------


def test_the_exporter_imports_neither_eval_nor_synth():
    for path in EXPORT_SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
            for name in names:
                assert not name.startswith(("archivist.eval", "archivist.synth")), (path, name)
    modules = "archivist.export.bundle, archivist.export.database, archivist.export.schema"
    code = (
        f"import sys, {modules}; "
        "print([m for m in sys.modules if m.startswith(('archivist.eval', 'archivist.synth'))])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through file permissions")
def test_no_ground_truth_is_read_without_truth(world, tmp_path):
    gt = tmp_path / "data" / SPLIT / "gt"
    for path in gt.iterdir():
        path.write_text("not ground truth")
    gt.chmod(0)  # any read of gt/ now raises
    try:
        bundle.main(["--run", RUN])
        database.main(["--run", RUN])
        bundle.main(["--run", RUN, "--check"])
    finally:
        gt.chmod(0o755)
    assert not (Path("data/bundles") / RUN / bundle.TRUTH_FILE).exists()
    assert (Path("exports") / RUN / database.DATABASE_FILE).exists()


def test_truth_is_written_apart_from_the_bundle(world):
    out = Path("data/bundles") / RUN
    bundle.main(["--run", RUN])
    without = (out / bundle.BUNDLE_FILE).read_bytes()
    bundle.main(["--run", RUN, "--truth"])
    assert (out / bundle.BUNDLE_FILE).read_bytes() == without
    truth = Truth.model_validate_json((out / bundle.TRUTH_FILE).read_text())
    pages = {p.page_id: p for p in truth.pages}
    assert len(pages) == 8 and pages["card-1"].severity == 0
    assert pages["memo-002"].values[memo_field_id("memo-002", "amount")] == "45.00"
    assert b"severity" not in without


# --- the committed test runs -------------------------------------------------------------------


@pytest.mark.parametrize("run", COMMITTED)
def test_rule_ids_agree_with_eval_on_every_committed_flag(run):
    from archivist.eval.run_eval import check_rule

    for verdict in load_verdicts(COMMITTED_RUNS / run / "verdicts.jsonl"):
        for flag in [*verdict.flags, *verdict.evidence.reread_flags]:
            ours, theirs = rules.rule_id(flag), check_rule(flag)
            if flag.check in rules.CHECKS:
                assert ours == theirs, flag
            else:  # the verification's notes: eval has no rule for them, the export does
                assert theirs == "other" and ours != "other", flag


@pytest.mark.parametrize("run", COMMITTED)
def test_every_committed_flag_is_explained(run, monkeypatch):
    monkeypatch.chdir(ROOT)
    b = bundle.build(COMMITTED_RUNS / run)
    for f in b.fields:
        for flag in [*f.flags, *f.reread_flags]:
            needs = flag.check in rules.CHECKS and flag.rule not in ("unreadable", "unresolvable")
            assert bool(flag.related) == needs, (f.field_id, flag)
        causes = [r for r in f.reasons if r.code != "obscured"]
        assert bool(causes) == (f.status != "accepted"), f.field_id


@pytest.mark.parametrize(
    "run", [r for r in COMMITTED if (ROOT / bundle.BUNDLES_DIR / r / bundle.BUNDLE_FILE).exists()]
)
def test_committed_exports_are_current(run, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)  # the runs name their images relative to the repository
    b = bundle.build(COMMITTED_RUNS / run)
    assert bundle.check(b, bundle.BUNDLES_DIR / run) == []
    assert database.check(b, database.EXPORTS_DIR / run, tmp_path) == []
    verdicts = load_verdicts(COMMITTED_RUNS / run / "verdicts.jsonl")
    db = sqlite3.connect(database.EXPORTS_DIR / run / database.DATABASE_FILE)
    by_status = dict(db.execute("SELECT status, COUNT(*) FROM field_values GROUP BY status"))
    db.close()
    assert by_status == dict(Counter(v.status for v in verdicts))


@pytest.mark.parametrize(
    "run", [r for r in COMMITTED if (ROOT / bundle.BUNDLES_DIR / r / bundle.BUNDLE_FILE).exists()]
)
def test_committed_bundles_validate_against_the_ui_schema(run):
    """The committed bundles against ui/schema/bundle.schema.json, the file the UI's types come
    from, by a validator that is not pydantic."""
    schema = json.loads((ROOT / SCHEMA_PATH).read_text())
    data = json.loads((ROOT / bundle.BUNDLES_DIR / run / bundle.BUNDLE_FILE).read_text())
    jsonschema.validate(data, schema, cls=jsonschema.Draft202012Validator)
