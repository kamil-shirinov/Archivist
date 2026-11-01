"""The one-command verification (P42), offline and fast: every check is exercised on small stand-ins.

Nothing here runs the real command (it rebuilds three exports and the test report, about a minute
and a half; CI runs it on its own). What is tested is the part that is ours: that a difference is
a failure, that a missing Treasury scan is a skip and any other missing file is a failure, that the
SQLite file is compared by its contents and the CSVs by their bytes, and what the summary says.
"""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from archivist import verify
from archivist.eval import test_report
from archivist.export import bundle as export_bundle
from archivist.export import database
from archivist.verify import FAIL, PASS, SKIP, Result

ROOT = Path(__file__).resolve().parents[1]


# --- the test report -------------------------------------------------------------------------------


def _fake_main(json_text: str, md_text: str):
    """Stands in for test_report.main: writes where the module's OUT_JSON and OUT_MD point."""

    def main(argv=None):
        test_report.OUT_JSON.write_text(json_text, encoding="utf-8")
        test_report.OUT_MD.write_text(md_text, encoding="utf-8")

    return main


HYPOTHESES = json.dumps(
    {"hypotheses": {"H1": {"met": True}, "H2": {"met": True}, "H3": {"met": False}}}, indent=2
)


def _committed(tmp_path: Path, monkeypatch, json_text: str, md_text: str) -> None:
    out = tmp_path / "committed"
    out.mkdir()
    (out / "test_report.json").write_text(json_text, encoding="utf-8")
    (out / "TEST_RESULTS.md").write_text(md_text, encoding="utf-8")
    monkeypatch.setattr(test_report, "OUT_JSON", out / "test_report.json")
    monkeypatch.setattr(test_report, "OUT_MD", out / "TEST_RESULTS.md")


def test_test_report_main_writes_to_the_module_paths(tmp_path, monkeypatch):
    # verify.py relies on this: it points OUT_JSON and OUT_MD at a scratch folder and calls main()
    monkeypatch.setattr(test_report, "build_report", lambda: {"hypotheses": {}})
    monkeypatch.setattr(test_report, "render", lambda report, deviations: "text\n")
    monkeypatch.setattr(test_report, "_deviations", lambda path: "")
    monkeypatch.setattr(test_report, "OUT_JSON", tmp_path / "a.json")
    monkeypatch.setattr(test_report, "OUT_MD", tmp_path / "a.md")
    test_report.main([])
    assert json.loads((tmp_path / "a.json").read_text())["hypotheses"] == {}
    assert (tmp_path / "a.md").read_text() == "text\n"


def test_report_that_regenerates_identically_passes(tmp_path, monkeypatch):
    _committed(tmp_path, monkeypatch, HYPOTHESES, "# Results\n")
    monkeypatch.setattr(test_report, "main", _fake_main(HYPOTHESES, "# Results\n"))
    (result,) = verify.check_test_report()
    assert result.status == PASS
    assert "2 of 3 pre-registered targets met: H1, H2; not met: H3" in result.says


def test_report_that_differs_by_one_character_fails_and_says_where(tmp_path, monkeypatch):
    _committed(tmp_path, monkeypatch, HYPOTHESES, "# Results\nH1 is 0.36%\n")
    monkeypatch.setattr(test_report, "main", _fake_main(HYPOTHESES, "# Results\nH1 is 0.37%\n"))
    (result,) = verify.check_test_report()
    assert result.status == FAIL
    (problem,) = result.problems
    assert "TEST_RESULTS.md" in problem
    assert "line 2" in problem and "0.36%" in problem and "0.37%" in problem


def test_missing_committed_report_fails(tmp_path, monkeypatch):
    _committed(tmp_path, monkeypatch, HYPOTHESES, "# Results\n")
    (tmp_path / "committed" / "test_report.json").unlink()
    monkeypatch.setattr(test_report, "main", _fake_main(HYPOTHESES, "# Results\n"))
    (result,) = verify.check_test_report()
    assert result.status == FAIL
    assert "test_report.json is missing" in result.problems[0]


def test_checking_the_report_leaves_the_committed_paths_alone(tmp_path, monkeypatch):
    _committed(tmp_path, monkeypatch, HYPOTHESES, "# Results\n")
    monkeypatch.setattr(test_report, "main", _fake_main(HYPOTHESES, "# Results\n"))
    before = (test_report.OUT_JSON, test_report.OUT_MD)
    verify.check_test_report()
    assert (test_report.OUT_JSON, test_report.OUT_MD) == before
    assert sorted(p.name for p in (tmp_path / "committed").iterdir()) == [
        "TEST_RESULTS.md",
        "test_report.json",
    ]


# --- the charts ------------------------------------------------------------------------------------


def test_charts_check_follows_the_scripts_exit_status(tmp_path, monkeypatch):
    script = tmp_path / "charts.py"
    monkeypatch.setattr(verify, "CHARTS_SCRIPT", script)
    script.write_text("import sys\nprint('charts match the report')\nsys.exit(0)\n")
    assert verify.check_charts()[0].status == PASS
    script.write_text("import sys\nprint('out of date: chart-a.svg')\nsys.exit(1)\n")
    (result,) = verify.check_charts()
    assert result.status == FAIL
    assert result.problems == ["out of date: chart-a.svg"]


def test_missing_charts_script_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "CHARTS_SCRIPT", tmp_path / "nothing.py")
    assert verify.check_charts()[0].status == FAIL


def test_the_committed_charts_pass_the_real_script(monkeypatch):
    monkeypatch.chdir(ROOT)  # the script is quick: it redraws three SVGs from the report
    (result,) = verify.check_charts()
    assert result.status == PASS, result.problems


# --- the databases ---------------------------------------------------------------------------------


def _database(path: Path, rows: list[tuple], page_size: int = 4096) -> None:
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA page_size = {page_size}")
    db.execute("CREATE TABLE accounts (id TEXT, balance TEXT)")
    db.executemany("INSERT INTO accounts VALUES (?, ?)", rows)
    db.commit()
    db.close()


def test_sqlite_files_are_compared_by_contents_not_bytes(tmp_path):
    rows = [("a", "10.00"), ("b", "20.00")]
    _database(tmp_path / "one.sqlite", rows, page_size=4096)
    _database(tmp_path / "two.sqlite", rows, page_size=8192)  # different bytes, same tables
    _database(tmp_path / "three.sqlite", [("a", "10.00"), ("b", "20.01")])
    assert (tmp_path / "one.sqlite").read_bytes() != (tmp_path / "two.sqlite").read_bytes()
    assert verify._dump(tmp_path / "one.sqlite") == verify._dump(tmp_path / "two.sqlite")
    assert verify._dump(tmp_path / "one.sqlite") != verify._dump(tmp_path / "three.sqlite")


def _fresh_export(rows: list[tuple], csv_text: str, page_size: int):
    """A stand-in for database.write: a CSV and a SQLite file in the folder it is given."""

    def write(bundle, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "accounts.csv").write_text(csv_text, encoding="utf-8")
        _database(out_dir / "archivist.sqlite", rows, page_size)
        return [out_dir / "accounts.csv", out_dir / "archivist.sqlite"]

    return write


BUILT = SimpleNamespace(run=SimpleNamespace(run_id="demo"))
ROWS = [("a", "10.00"), ("b", "20.00")]


def _committed_export(tmp_path: Path, rows: list[tuple], csv_text: str) -> Path:
    exports = tmp_path / "exports" / "demo"
    exports.mkdir(parents=True)
    (exports / "accounts.csv").write_text(csv_text, encoding="utf-8")
    _database(exports / "archivist.sqlite", rows, page_size=4096)
    return exports


def test_database_that_matches_in_content_passes_even_if_its_bytes_differ(tmp_path, monkeypatch):
    exports = _committed_export(tmp_path, ROWS, "id,balance\na,10.00\n")
    monkeypatch.setattr(database, "write", _fresh_export(ROWS, "id,balance\na,10.00\n", 8192))
    assert verify._database_problems(BUILT, exports) == []


def test_database_with_a_changed_row_fails(tmp_path, monkeypatch):
    exports = _committed_export(tmp_path, ROWS, "id,balance\na,10.00\n")
    changed = [("a", "10.00"), ("b", "99.00")]
    monkeypatch.setattr(database, "write", _fresh_export(changed, "id,balance\na,10.00\n", 4096))
    (problem,) = verify._database_problems(BUILT, exports)
    assert "archivist.sqlite" in problem and "different tables or rows" in problem


def test_a_csv_is_compared_byte_for_byte(tmp_path, monkeypatch):
    exports = _committed_export(tmp_path, ROWS, "id,balance\na,10.00\n")
    monkeypatch.setattr(database, "write", _fresh_export(ROWS, "id,balance\na,10.0\n", 4096))
    (problem,) = verify._database_problems(BUILT, exports)
    assert "accounts.csv differs" in problem


def test_a_file_missing_from_the_committed_export_fails(tmp_path, monkeypatch):
    exports = _committed_export(tmp_path, ROWS, "id,balance\na,10.00\n")
    (exports / "accounts.csv").unlink()
    monkeypatch.setattr(database, "write", _fresh_export(ROWS, "id,balance\na,10.00\n", 4096))
    (problem,) = verify._database_problems(BUILT, exports)
    assert "accounts.csv is missing" in problem


# --- the exports, with and without the Treasury scans ----------------------------------------------


def test_a_missing_treasury_scan_is_a_skip_and_the_bundle_gets_the_lesser_check(monkeypatch):
    monkeypatch.chdir(ROOT)
    scan = export_bundle.REAL_PAGES / "1939-12" / "p025.jpg"

    def build(run_dir):
        raise FileNotFoundError(2, "No such file or directory", str(scan))

    monkeypatch.setattr(export_bundle, "build", build)
    monkeypatch.setattr(verify, "_committed_runs", lambda: ["treasury-development"])
    shown, skipped = verify.check_exports()
    assert (shown.status, skipped.status) == (PASS, SKIP)  # committed bundle and images are here
    assert "less than a rebuild" in shown.says
    assert "not committed" in skipped.says and str(scan) in skipped.says


def test_a_bundle_whose_page_images_are_missing_fails_even_without_scans(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    source = ROOT / "data" / "bundles" / "treasury-development"
    copy = tmp_path / "bundles"
    (copy / "treasury-development").mkdir(parents=True)
    bundle_file = copy / "treasury-development" / "bundle.json"
    bundle_file.write_bytes((source / "bundle.json").read_bytes())  # its images are not copied
    monkeypatch.setattr(export_bundle, "BUNDLES_DIR", copy)
    error = FileNotFoundError(2, "No such file or directory", "data/real/pages/x/p001.jpg")
    shown, skipped = verify._check_without_scans("treasury-development", error)
    assert shown.status == FAIL and skipped.status == SKIP
    assert any("is missing" in problem for problem in shown.problems)


def test_a_missing_file_that_is_not_a_scan_is_not_a_skip(monkeypatch):
    def build(run_dir):
        raise FileNotFoundError(2, "No such file or directory", "data/test/images/card-01-1.jpg")

    monkeypatch.setattr(export_bundle, "build", build)
    monkeypatch.setattr(verify, "_committed_runs", lambda: ["test-archivist-A"])
    with pytest.raises(FileNotFoundError):
        verify.check_exports()
    (result,) = verify.run_checks([("the exports", verify.check_exports)])
    assert result.status == FAIL and "FileNotFoundError" in result.problems[0]


def test_the_committed_runs_are_the_indexed_ones_and_the_exported_ones(monkeypatch):
    monkeypatch.chdir(ROOT)
    runs = verify._committed_runs()
    assert {"test-archivist-A", "test-archivist-B", "treasury-development"} <= set(runs)
    assert runs == sorted(runs)


# --- running them and the summary ------------------------------------------------------------------


def test_a_check_that_cannot_run_is_a_failure_and_the_others_still_run():
    def refuses():
        raise SystemExit("data/test/manifest.json is not the pre-registered file")

    def fine():
        return [Result(PASS, "Fine", "It holds.")]

    results = verify.run_checks([("the refusing check", refuses), ("the fine check", fine)])
    assert [r.status for r in results] == [FAIL, PASS]
    assert "pre-registered file" in results[0].problems[0]


def test_summary_of_a_clean_run_says_what_passed():
    text = verify.summary([Result(PASS, "Charts", "They match.")])
    assert "What passed:" in text and "Charts: They match." in text
    assert "VERIFIED: 1 passed, 0 failed." in text
    assert "What failed" not in text and "NOT VERIFIED" not in text


def test_summary_never_calls_a_run_with_a_skip_fully_verified():
    text = verify.summary([Result(PASS, "A", "ok"), Result(SKIP, "B", "needs scans")])
    assert "What could not be checked here:" in text and "B: needs scans" in text
    assert "VERIFIED, EXCEPT WHAT IS LISTED AS NOT CHECKED" in text
    assert "1 passed, 0 failed, 1 not checked." in text


def test_summary_of_a_failure_lists_its_problems_and_cuts_a_long_list():
    problems = [f"file {i} differs" for i in range(verify.SHOWN_PROBLEMS + 3)]
    text = verify.summary([Result(PASS, "A", "ok"), Result(FAIL, "B", "It differs.", problems)])
    assert "NOT VERIFIED: 1 passed, 1 failed." in text
    assert "file 0 differs" in text and "... and 3 more" in text
    assert f"file {verify.SHOWN_PROBLEMS} differs" not in text


def test_main_exit_status_follows_the_results(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(verify, "CHECKS", (("one", lambda: [Result(PASS, "One", "ok")]),))
    assert verify.main([]) == 0
    assert "VERIFIED: 1 passed, 0 failed." in capsys.readouterr().out
    monkeypatch.setattr(verify, "CHECKS", (("one", lambda: [Result(FAIL, "One", "no", ["x"])]),))
    assert verify.main([]) == 1
    assert "NOT VERIFIED" in capsys.readouterr().out


def test_main_asks_to_be_run_from_the_repository_root(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert verify.main([]) == 2
    assert "repository root" in capsys.readouterr().out
