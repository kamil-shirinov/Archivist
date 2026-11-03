"""The README's first screen, its links and its numbers (P54).

The README is what a judge reads first, so what it promises is tested: the order of the first screen, the
paragraph the author wrote for "The problem", the links that must resolve, the three community files, the
empty .env.example, a GIF small enough to load, and that archivist.verify fails when a figure the README quotes
stops being what its result file says.
"""

import re
import subprocess
from pathlib import Path

import pytest

from archivist import verify

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
DOCS = ("README.md", "eval/README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md")

PROBLEM = (
    "During a bank internship I used AI to build two things: a parser that turned about 2,000 legacy memos into a "
    "clean spreadsheet database, and a working prototype of an automated loan-processing system. Both hit the same "
    "wall. Nobody held all the memos in one place, there was no archive, and the oldest records existed only on "
    "paper; businesses applying for loans brought their earnings in notebooks and loose sheets that staff typed in "
    "by hand. Archivist is the tool I wanted then: it turns scanned financial records into a verified database, "
    "with every value cited to its spot on the page, read twice, checked by arithmetic, and sent to a person when "
    "in doubt."
)
SOLO = "Solo entry by Kamil Shirinov for the Meta Global AI Developer Hackathon 2026: Indie Developer track, Build for Your World."


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(text: str) -> set[str]:
    return {slug(h) for h in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, re.M)}


def links(text: str) -> list[str]:
    found = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'(?:href|src)="([^"]+)"', text)
    return [u for u in found if not re.match(r"[a-z]+:|mailto:", u)]


def test_the_first_screen_is_in_the_order_judges_read_it():
    order = [
        README.index('<img src="assets/brand/logo-light.svg"'),
        README.index("\n# Archivist\n"),
        README.index("**The archive that shows its work.**"),
        README.index("[![Live demo]"),
        README.index("docs/img/watch-it-work.gif"),
        README.index("- **What it does.**"),
        README.index("- **How well.**"),
        README.index("- **Where your data goes.**"),
        README.index("- **Who built it.**"),
        README.index("[Start here](#start-here) ·"),
        README.index("**Built during the hackathon.**"),
        README.index("\n## Start here\n"),
        README.index("\n## For judges\n"),
        README.index("\n## The problem\n"),
    ]
    assert order == sorted(order)


def test_one_row_of_badges_with_the_four_meta_models():
    row = next(line for line in README.splitlines() if line.startswith("[![Live demo]"))
    alts = re.findall(r"\[!\[([^\]]+)\]", row)
    assert alts == ["Live demo", "CI", "Apache-2.0", "Docker", "Muse Spark 1.3", "Muse Spark Open", "Muse Glimmer", "SAM 3.1"]


def test_the_problem_is_the_authors_paragraph_and_the_solo_line_follows():
    section = README.split("\n## The problem\n", 1)[1].split("\n## ", 1)[0]
    assert section.strip().split("\n\n") == [PROBLEM, SOLO]


def test_start_here_and_for_judges_have_their_rows():
    start = README.split("\n## Start here\n", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| \*\*(\w+)\*\* \|", start, re.M)
    assert rows == ["Watch", "Try", "Run", "Read"]
    assert "[link pending]" in start.split("**Try**")[0]
    for needle in ("eval/README.md", "PREREGISTRATION_REAL.md", "PREREGISTRATION_OPENW.md", "diagnosis.md", "docker run --rm -p 8000:8000 archivist"):
        assert needle in start
    judges = README.split("\n## For judges\n", 1)[1].split("\n## ", 1)[0]
    assert re.findall(r"^\| \*\*([^*]+)\*\* \((\d+)%\)", judges, re.M) == [
        ("Impact", "30"), ("Use of Meta's models", "25"), ("Demo", "25"), ("Technical depth", "20"),
    ]


def test_the_open_weights_section_claims_the_bonus_by_name_and_keeps_its_caveat():
    heading = "## Open weights: the same pipeline on your own hardware"
    section = README.split(heading, 1)[1].split("\n## ", 1)[0]
    assert section.lstrip().startswith("This is Archivist's entry for the open-weights bonus prize.")
    assert "One scheme, one swap" not in README
    for needle in ("Muse Spark Open for both reads", "Muse Glimmer sorting pages", "Two hosts compared", "Not yet proven on-site"):
        assert needle in section


def test_the_logo_is_one_file_and_the_credits_say_so():
    assert "The two files in `assets/brand/`" not in README and "logo-dark" not in README
    assert "The one file `assets/brand/logo-light.svg`" in README
    assert sorted(p.name for p in (ROOT / "assets/brand").iterdir()) == ["logo-light.svg"]


@pytest.mark.parametrize("doc", DOCS)
def test_every_relative_link_resolves(doc):
    path = ROOT / doc
    text = path.read_text(encoding="utf-8")
    for url in links(text):
        target, _, anchor = url.partition("#")
        file = path if not target else (path.parent / target)
        assert file.exists(), f"{doc} links {url}, which is not there"
        if anchor and file.suffix == ".md":
            assert anchor in anchors(file.read_text(encoding="utf-8")), f"{doc} links {url}, but {file.name} has no such heading"


def test_the_gif_is_small_enough_to_load():
    gif = ROOT / "docs/img/watch-it-work.gif"
    assert gif.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
    assert gif.stat().st_size < 5_000_000


def test_the_community_files_have_no_email_address_and_say_where_to_report():
    for doc in ("CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), f"{doc} holds an email address"
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Report a vulnerability" in security and "main" in security and "static" in security
    conduct = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    assert "version 2.1" in conduct and "Report a vulnerability" in conduct
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for needle in ("uv sync --frozen", "uv run pytest -q && uv run python -m archivist.replay", "DECISIONS.md", "archivist.templates.approve", "No tuning on held-out pages"):
        assert needle in contributing


def test_env_example_lists_the_names_live_mode_reads_and_holds_no_value():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    names = re.findall(r"^#?\s*([A-Z][A-Z_]+)=", text, re.M)
    assert names == ["META_API_KEY", "BASETEN_API_KEY", "FIREWORKS_API_KEY", "BUDGET_CAP_USD", "BASETEN_CAP_USD", "FIREWORKS_CAP_USD", "GLIMMER_CAP_USD"]
    assert all(not line.partition("=")[2].strip() for line in text.splitlines() if re.match(r"[A-Z_]+_KEY=", line)), "a key holds a value"
    assert "need none" in text
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    assert ignored and subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=ROOT).returncode == 1


# --- archivist.verify's check of the README's numbers ------------------------------------------------------------


@pytest.fixture
def at_root(monkeypatch):
    monkeypatch.chdir(ROOT)


def test_verify_passes_on_the_readme_as_it_is(at_root):
    results = verify.check_readme()
    assert [r.status for r in results if r.name == "README numbers"] == [verify.PASS], [r.problems for r in results]


def test_verify_fails_when_a_quoted_figure_changes(at_root, monkeypatch, tmp_path):
    for old, new in (("0.36% (0.14% to 0.67%)", "0.35% (0.14% to 0.67%)"), ("36.9% (24.7%–50.4%)", "26.9% (24.7%–50.4%)"), ("27.1% (13.9%–49.9%)", "2.1% (13.9%–49.9%)")):
        assert old in README
        edited = tmp_path / "README.md"
        edited.write_text(README.replace(old, new), encoding="utf-8")
        monkeypatch.setattr(verify, "README", edited)
        found = verify.check_readme()
        assert found[0].status == verify.FAIL and any(old.split(" (")[0] in p or "does not say" in p for p in found[0].problems), old


def test_verify_fails_when_a_sentence_goes(at_root, monkeypatch, tmp_path):
    edited = tmp_path / "README.md"
    edited.write_text(README.replace("sorted all 4,569 held-out", "sorted all held-out"), encoding="utf-8")
    monkeypatch.setattr(verify, "README", edited)
    assert verify.check_readme()[0].status == verify.FAIL


def test_a_missing_run_record_is_skipped_not_passed(at_root, monkeypatch, tmp_path):
    monkeypatch.setattr(verify, "RUN_V1", tmp_path / "run.json")
    results = verify.check_readme()
    assert [r.status for r in results] == [verify.PASS, verify.SKIP]


def test_verify_notices_a_verdict_that_flips(at_root):
    v1, open_ = verify._json(verify.SCORE_V1), verify._json(verify.SCORE_OPEN)
    assert all(ok for _, ok in verify._verdicts(v1, open_))
    open_["o1"]["met"] = True
    assert [what for what, ok in verify._verdicts(v1, open_) if not ok] == ["O1 is not met"]
