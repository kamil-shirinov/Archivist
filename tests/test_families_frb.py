"""Federal Reserve Bulletin tables chosen for drafting (P28): its pages, and the rule.

No model is called and no page image is opened; the chosen tables come from the committed manifest.
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from archivist.doctypes.template import file_sha256
from archivist.ingest import frb
from archivist.ingest.survey_frb import Seen, Table
from archivist.templates import families_frb, pages
from archivist.templates.pages import Page, PageRefused

ROOT = Path(__file__).resolve().parents[1]


def test_frb_pages_are_sent_only_from_development_issues(tmp_path):
    root = tmp_path / "real_frb"
    root.mkdir()
    (root / "split.json").write_text((ROOT / "data/real_frb/split.json").read_text())
    real = json.loads((ROOT / "data/real_frb/manifest.json").read_text())
    entries = []
    for issue in ("1990-06", "1991-06"):
        image = root / "pages" / issue / "p010.jpg"
        image.parent.mkdir(parents=True)
        Image.new("RGB", (20, 20), (90, 90, 90)).save(image)
        entry = next(p for p in real["pages"] if p["issue"] == issue)
        entries.append(entry | {"page": 10, "sha256": file_sha256(image)})
    (root / "manifest.json").write_text(json.dumps(real | {"pages": entries}))

    def resolve(ref: str) -> Page:
        return pages.resolve(ref, tmp_path / "real", tmp_path / "synth", tmp_path / "occ", root)

    page = resolve("frb-1990-06_p010")
    assert (page.page_id, page.path) == ("frb-1990-06_p010", root / "pages/1990-06/p010.jpg")
    with pytest.raises(PageRefused, match="not a development issue"):
        resolve("frb-1991-06_p010")  # refused before its file is looked at
    (root / "pages/1990-06/p010.jpg").write_bytes(b"changed")
    for ref in ("frb-1990-06_p010", "frb-1990-06_p011", "frb-1990-6_p010"):
        with pytest.raises(PageRefused):
            resolve(ref)


def test_a_june_treasury_issue_is_never_taken_for_an_frb_one():
    with pytest.raises(PageRefused, match="not a development issue"):
        pages.resolve("1990-06_p010")  # the Treasury Bulletin's held-out June 1990


def _table(number: str, title: str, pages_by_issue: dict, totals=1) -> Table:
    table = Table(number)
    table.spellings[title] += 1
    for issue, found in pages_by_issue.items():
        table.seen[issue] = Seen(number, title, list(found), totals)
    return table


SPLIT = frb.Split(
    development=["1980-06", "1990-06", "2000-06"],
    held_out=["1981-06", "1982-06", "1983-06"],
    note="a test",
)


def test_bank_assets_and_liabilities_come_first_then_held_out_pages():
    held = {"1981-06": [5, 6, 7], "1982-06": [5, 6], "1983-06": [5]}
    banks = _table("3.17", "LIABILITIES TO FOREIGNERS Reported by Banks in the United States1",
                   {"1990-06": [127], "2000-06": [131], "1981-06": [1], "1982-06": [2]})
    busy = _table("2.13", "INDUSTRIAL PRODUCTION Indexes", {"1980-06": [9], "1990-06": [9], **held})
    thin = _table("1.24", "MAJOR NONDEPOSIT FUNDS OF COMMERCIAL BANKS", {"1990-06": [3], **held})
    quiet = _table("1.17", "OPEN MARKET TRANSACTIONS", {"1980-06": [1], "1990-06": [1], **held},
                   totals=0)
    found = families_frb.candidates([banks, busy, thin, quiet], SPLIT)
    assert [c.failed for c in found] == [None, None, 2, 1]
    assert [c.table.number for c in families_frb.rank([c for c in found if c.failed is None])] == [
        "3.17",
        "2.13",
    ]
    assert found[0].banks and not found[1].banks
    assert families_frb.drafting_pages(found[0]) == ["frb-1990-06_p127", "frb-2000-06_p131"]
    assert families_frb.printed_title(found[0]) == (
        "3.17 LIABILITIES TO FOREIGNERS Reported by Banks in the United States"
    )
    assert families_frb.family_key(found[0]) == "frb_3_17_liabilities_to_foreigners"


@pytest.mark.parametrize(
    "title, banks",
    [
        ("LOANS AND SECURITIES All Commercial Banks1", True),
        ("FEDERAL RESERVE BANKS Condition and Federal Reserve Note Statements1", True),
        ("DOMESTIC FINANCE COMPANIES Assets and Liabilities1", False),
        ("RESERVES AND BORROWINGS Depository Institutions1", False),
    ],
)
def test_a_bank_table_names_banks_and_what_they_hold_or_owe(title, banks):
    assert families_frb.is_bank_balance(title) is banks


def test_the_committed_choice_is_what_the_rule_gives():
    root = ROOT / "data/real_frb"
    manifest = frb.Manifest.model_validate_json((root / "manifest.json").read_text())
    split = frb.Split.model_validate_json((root / "split.json").read_text())
    found, chosen = families_frb.choose(manifest, split)
    committed = (ROOT / families_frb.OUT).read_text(encoding="utf-8")
    assert committed == families_frb.render(found, chosen)
    assert all(c.banks for c in chosen) and len(chosen) == families_frb.MAX_FAMILIES
