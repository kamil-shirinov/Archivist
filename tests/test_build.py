import hashlib
import json
import subprocess
from collections import Counter

import pytest
from PIL import Image

from archivist.schema import PageGT
from archivist.synth import build, degrade
from archivist.synth.world import World, generate_world

SEED = 4
PARAMS = dict(n_accounts=1, cards_per_account=1, memo_rate=0.25, source_error_rate=0.3)  # 4 pages
TINY = dict(n_accounts=1, cards_per_account=1, memo_rate=0.0, source_error_rate=0.0)  # 1 page
LEVELS = range(len(degrade.LEVELS))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build.build_split("dev", SEED, **PARAMS, out_root=tmp_path_factory.mktemp("built"))


def _pages(split_dir):
    """Every page ground truth, keyed by page_id; world.json is not a page."""
    return {
        path.stem: PageGT.model_validate_json(path.read_text())
        for path in (split_dir / "gt").glob("*.json")
        if path.stem != "world"
    }


def test_every_page_has_an_image_and_a_ground_truth(built):
    world = World.model_validate_json((built / "gt" / "world.json").read_text())
    assert world == generate_world(SEED, **PARAMS)
    expected = {doc.doc_id for doc in (*world.cards, *world.memos)}
    pages = _pages(built)
    assert set(pages) == {path.stem for path in (built / "images").iterdir()} == expected
    for page_id, gt in pages.items():
        assert gt.page_id == page_id
        assert gt.image_path == f"images/{page_id}.png"
        with Image.open(built / gt.image_path) as image:
            assert image.size == (gt.width, gt.height)


def test_folders_hold_only_their_own_kind_of_file(built):
    images = [path.name for path in (built / "images").iterdir()]
    assert images and all(name.endswith(".png") for name in images)
    assert all(path.suffix == ".json" for path in (built / "gt").iterdir())
    assert sorted(path.name for path in built.iterdir()) == ["gt", "images", "manifest.json"]


def test_manifest_records_the_build_and_its_hashes_match_the_files(built):
    manifest = json.loads((built / "manifest.json").read_text())
    assert list(manifest) == [
        "split", "seed", "params", "generator_commit", "dirty", "counts", "files",
    ]  # fmt: skip
    assert (manifest["split"], manifest["seed"], manifest["params"]) == ("dev", SEED, PARAMS)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert manifest["generator_commit"] == head
    assert isinstance(manifest["dirty"], bool)
    on_disk = {
        path.relative_to(built).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("images", "gt")
        for path in (built / folder).rglob("*")
        if path.is_file()
    }
    assert manifest["files"] == on_disk
    assert "gt/world.json" in on_disk


def test_counts_match_the_pages_and_severities_are_balanced(built):
    counts = json.loads((built / "manifest.json").read_text())["counts"]
    pages = _pages(built).values()
    assert counts["by_doc_type"] == {
        kind: sum(gt.doc_type == kind for gt in pages) for kind in ("ledger", "memo")
    }
    actual = Counter(gt.severity for gt in pages)
    assert counts["by_severity"] == {str(s): actual[s] for s in LEVELS}
    levels = list(counts["by_severity"].values())
    assert sum(levels) >= len(LEVELS)  # enough pages for every level to appear
    assert max(levels) - min(levels) <= 1


@pytest.mark.parametrize("n_pages", range(1, 14))
def test_severity_cycle_is_balanced_for_any_page_count(n_pages):
    counts = Counter(build._severities(SEED, n_pages))
    levels = [counts[s] for s in LEVELS]
    assert sum(levels) == n_pages
    assert max(levels) - min(levels) <= 1


def test_severity_cycle_is_shuffled_but_fixed_by_the_seed():
    cycle = build._severities(SEED, 40)
    assert cycle != [i % len(LEVELS) for i in range(40)]
    assert cycle == build._severities(SEED, 40)
    assert cycle != build._severities(SEED + 1, 40)


def test_same_seed_gives_identical_manifests(built, tmp_path):
    again = build.build_split("dev", SEED, **PARAMS, out_root=tmp_path)
    assert (again / "manifest.json").read_bytes() == (built / "manifest.json").read_bytes()


def test_existing_split_is_not_overwritten_without_overwrite(tmp_path):
    split = build.build_split("dev", SEED, **TINY, out_root=tmp_path)
    before = (split / "manifest.json").read_bytes()

    with pytest.raises(FileExistsError):
        build.build_split("dev", SEED + 1, **TINY, out_root=tmp_path)
    assert (split / "manifest.json").read_bytes() == before
    assert [path.name for path in tmp_path.iterdir()] == ["dev"]  # no scratch folder left over

    (split / "images" / "stale.png").write_bytes(b"")
    assert build.build_split("dev", SEED + 1, **TINY, out_root=tmp_path, overwrite=True) == split
    assert json.loads((split / "manifest.json").read_text())["seed"] == SEED + 1
    assert not (split / "images" / "stale.png").exists()
    assert [path.name for path in tmp_path.iterdir()] == ["dev"]


@pytest.mark.parametrize("name", ["", "../dev", "a/b", ".hidden", "dev set"])
def test_split_name_cannot_leave_the_output_root(name, tmp_path):
    with pytest.raises(ValueError):
        build.build_split(name, SEED, **TINY, out_root=tmp_path)
    assert not any(tmp_path.iterdir())
