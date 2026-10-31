"""The local live app (P35): the event stream of a read, the development-only page check, the
modes, and the server, all offline.

The models are a scripted backend registered with the real registry, so every call goes through
the real Cache(Budget(Backend)) roles, the real spend ledger and the real caps, with temporary
cache, ledger and scratch folders. Nothing here touches the network, a key or a held-out page.
"""

import http.client
import io
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from archivist.doctypes import from_config
from archivist.doctypes.ledger import MEMO_FIELDS
from archivist.export.bundle import model_name
from archivist.export.schema import Bundle
from archivist.live import events, pages, reader, server, session
from archivist.live.session import LiveApp, Request, StartRefused
from archivist.models import describe_config, load_roles
from archivist.models.base import LLMResponse, Region, SegmentResponse, Usage
from archivist.models.registry import register_backend
from archivist.pipeline import extract, verify
from archivist.schema import BBox

ROOT = Path(__file__).resolve().parents[1]
HOSTED, OPEN, SAM = "muse-spark-1.3-contributor", "meta-models/muse-spark-open-1026", "sam-3.1"
PAGE = "dev/memo-0001"


class Scripted:
    """A backend that answers from a function and counts what reaches it (the cache and the cap
    stand in front of it, as they do in front of every real one)."""

    name = "scripted"
    answers = {"llm": None, "segmenter": None}
    reached: list[str] = []
    gate: threading.Event | None = None
    delay = 0.0  # how long an answer takes, for the browser test to see a call in flight

    def __init__(self, model_id: str, kind: str, **settings) -> None:
        self.model_id, self.kind, self.settings = model_id, kind, dict(settings)

    def complete(self, request):
        Scripted.reached.append("llm")
        time.sleep(Scripted.delay)
        if Scripted.gate is not None:
            Scripted.gate.wait(5)
        text = Scripted.answers["llm"](request)
        return LLMResponse(text, Usage(100, 20, 0.002), self.name, self.model_id)

    def segment(self, request):
        Scripted.reached.append("segmenter")
        time.sleep(Scripted.delay)
        regions = Scripted.answers["segmenter"](request)
        return SegmentResponse(tuple(regions), Usage(0, 0, 0.0025), self.name, self.model_id)


register_backend("scripted", "llm", lambda m, **s: Scripted(m, "llm", **s))
register_backend("scripted", "segmenter", lambda m, **s: Scripted(m, "segmenter", **s))

CONFIG = """
[doc_types]
enabled = ["ledger_card", "payment_memo"]

[roles.extractor]
kind = "llm"
backend = "scripted"
model_id = "{llm}"
settings = {{ reasoning_effort = "low" }}

[roles.rereader]
kind = "llm"
backend = "scripted"
model_id = "{llm}"
settings = {{ reasoning_effort = "low" }}

[roles.segmenter]
kind = "segmenter"
backend = "scripted"
model_id = "sam-3.1"

[prices."{llm}"]
input_per_mtok = 1.0
output_per_mtok = 1.0

[prices."sam-3.1"]
input_per_mtok = 0.0
output_per_mtok = 0.0
per_image_usd = 0.0025
"""


def answer(request) -> str:
    properties = request.json_schema["properties"]
    if "doc_type" in properties:
        return json.dumps({"doc_type": "payment_memo"})
    if "fields" in properties:
        cells = {
            name: {"value": "1.00", "box": [100, 60 + 100 * i, 400, 120 + 100 * i]}
            for i, name in enumerate(MEMO_FIELDS)
        }
        return json.dumps({"fields": cells})
    return json.dumps({"value": "1.00"})  # a blind re-read


def stamp_only(request) -> list[Region]:
    if request.prompts == ("stamp",):
        return [Region("stamp", BBox(x0=100, y0=40, x1=300, y1=110), 0.9)]
    return []


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A repository's worth of folders in tmp_path, a scripted pair of arms, and an app on them."""
    monkeypatch.chdir(ROOT)
    for variable in ("BUDGET_CAP_USD", "BASETEN_CAP_USD", "FIREWORKS_CAP_USD"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(session, "key_present", lambda backend: True)
    Scripted.answers = {"llm": answer, "segmenter": stamp_only}
    Scripted.reached, Scripted.gate, Scripted.delay = [], None, 0.0

    data = tmp_path / "data"
    (data / "dev" / "images").mkdir(parents=True)
    Image.new("RGB", (400, 300), "white").save(data / "dev" / "images" / "memo-0001.jpg")
    arms = {}
    for arm, llm in (("a", HOSTED), ("b", OPEN)):
        arms[arm] = tmp_path / f"arm-{arm}.toml"
        arms[arm].write_text(CONFIG.format(llm=llm))
    app = LiveApp(
        tmp_path / "live",
        real_root=tmp_path / "real",
        synthetic_root=data,
        sweep_dir=tmp_path / "sweep",
        arms=arms,
        cache_dir=tmp_path / "cache",
        ledger_path=tmp_path / "ledger.jsonl",
        keys=lambda config: [],
    )
    return app


def read(app: LiveApp, **request) -> list[dict]:
    """Begin a read and wait for its stream to end; its events."""
    started = app.start(Request(**{"page": PAGE, **request}))
    started.thread.join(30)
    assert not started.thread.is_alive()
    return started.log.events()


def of(evs: list[dict], type: str, **match) -> list[dict]:
    return [e for e in evs if e["type"] == type and all(e.get(k) == v for k, v in match.items())]


def ledger(app: LiveApp) -> list[dict]:
    if not app.ledger_path.exists():
        return []
    return [json.loads(line) for line in app.ledger_path.read_text().splitlines()]


# --- the event stream ---------------------------------------------------------------------------


def test_a_live_read_streams_the_seven_steps_in_order_and_every_call(world):
    evs = read(world)
    assert [e["seq"] for e in evs] == list(range(len(evs)))
    assert evs[0]["type"] == "session" and evs[0]["mode"] == "live"
    assert evs[-1]["type"] == "done" and evs[-1]["outcome"] == "read"
    assert [m["name"] for m in evs[0]["models"]] == ["Muse Spark 1.3", "Muse Spark 1.3", "SAM 3.1"]

    started = [e["step"] for e in of(evs, "step", state="start")]
    assert started == list(events.STEPS)  # each lit once, in the order the pipeline takes them
    finished = [e["step"] for e in of(evs, "step", state="done")]
    assert finished == list(events.STEPS)
    for a, b in zip(evs, evs[1:], strict=False):  # a step starts only after the one before is done
        if a["type"] == "step" and a["state"] == "start" and a["index"]:
            earlier = [e for e in evs[: a["seq"]] if e["type"] == "step" and e["state"] == "done"]
            assert earlier[-1]["index"] == a["index"] - 1

    calls = of(evs, "call")
    assert [c["step"] for c in calls[:2]] == ["recognise", "read"]
    assert {c["role"] for c in of(evs, "call", step="sam")} == {"segmenter"}
    assert [c["detail"] for c in of(evs, "call", step="sam")] == ["stamp", "stain"]
    assert len(of(evs, "call", step="blind")) == len(MEMO_FIELDS)
    for c in calls:
        assert c["ok"] and c["source"] == "live"
        assert c["model"] == model_name(c["model_id"]) and c["latency_ms"] >= 0
        assert c["input_tokens"] >= 0 and c["cost_usd"] > 0 and c["cost_full_usd"] == c["cost_usd"]
    assert len(of(evs, "call_start")) == len(calls)
    assert {c["id"] for c in calls} == {c["id"] for c in of(evs, "call_start")}

    values = of(evs, "values")[0]
    assert values["count"] == len(MEMO_FIELDS) == values["to_reread"]
    assert all(f["box"] and f["value"] == "1.00" for f in values["fields"])
    assert len(of(evs, "verdicts")[0]["fields"]) == len(MEMO_FIELDS)
    assert of(evs, "detections", prompt="stamp")[0]["regions"][0]["label"] == "stamp"


def test_every_call_goes_through_the_cache_the_cap_and_the_ledger(world):
    evs = read(world)
    totals = evs[-1]["totals"]
    paid = sum(c["cost_usd"] for c in of(evs, "call"))
    assert totals["calls"] == len(of(evs, "call")) == len(Scripted.reached) == len(ledger(world))
    assert totals["live"] == totals["calls"] and totals["cache"] == 0
    assert totals["cost_usd"] == pytest.approx(paid)
    assert sum(line["cost_usd"] for line in ledger(world)) == pytest.approx(paid)  # D18
    assert {line["backend"] for line in ledger(world)} == {"scripted"}

    # the same page again: answered from the cache, nothing reaches a backend, nothing is spent
    again = read(world)
    assert again[-1]["totals"]["cache"] == totals["calls"] and again[-1]["totals"]["live"] == 0
    assert {c["source"] for c in of(again, "call")} == {"cache"}
    assert {c["cost_usd"] for c in of(again, "call")} == {0.0}
    assert len(Scripted.reached) == totals["calls"] and len(ledger(world)) == totals["calls"]


def test_a_cap_stops_a_live_read_before_the_model_is_reached(world, monkeypatch):
    monkeypatch.setenv("BUDGET_CAP_USD", "0.000001")
    evs = read(world)
    assert evs[-1]["type"] == "error" and evs[-1]["kind"] == "budget"
    assert Scripted.reached == [] and ledger(world) == []
    assert not of(evs, "call", ok=True) and of(evs, "call", ok=False)[0]["source"] is None


def test_the_live_flow_is_the_pipelines_own(world):
    """The extraction and verdicts a read writes are what extract_page and verify give on the same
    answers: asked again by the pipeline itself, every request is in the cache already."""
    evs = read(world)
    run_id = evs[-1]["run_id"]
    reached = len(Scripted.reached)
    run_dir = world.root / "runs" / run_id
    written = extract.load_predictions(world.root / "runs" / f"{run_id}-read" / "predictions.jsonl")

    config = world.arms["a"]
    roles = load_roles(config, cache_dir=world.cache_dir, ledger_path=world.ledger_path)
    doc_types = from_config(config)
    page = world.resolve(PAGE)
    theirs = extract.extract_page(page.path, roles, doc_types=doc_types)
    assert written[0].model_dump() == theirs.model_dump()
    corrected, _ = verify.to_correct(extract.recorded_citations(doc_types), doc_types)
    verdicts, _ = verify.verify(
        [theirs],
        {page.page_id: page.path},
        roles,
        correct_citations=corrected,
        doc_types=doc_types,
        policy="v2",
        second_looks=False,
    )
    ours = verify.load_verdicts(run_dir / verify.VERDICTS_FILE)
    assert [v.model_dump() for v in ours] == [v.model_dump() for v in verdicts]
    assert len(Scripted.reached) == reached  # the pipeline asked nothing the read had not asked


def test_a_finished_read_is_a_bundle_the_normal_views_open(world):
    evs = read(world)
    run_id = evs[-1]["run_id"]
    assert run_id.startswith("live-") and run_id.endswith("memo-0001")
    bundle_dir = world.root / "bundles" / run_id
    built = Bundle.model_validate_json((bundle_dir / "bundle.json").read_text())
    assert built.run.collection == "Live read: memo-0001"
    assert [d.page_id for d in built.documents] == ["memo-0001"]
    assert built.run.verification["cost_usd"] + built.run.extraction["cost_usd"] == pytest.approx(
        evs[-1]["totals"]["cost_usd"]
    )
    assert (bundle_dir / built.pages[0].image.url).is_file()
    index = json.loads((world.root / "bundles" / "index.json").read_text())
    assert [r["run_id"] for r in index["runs"]] == [run_id]
    merged = json.loads(server.merged_index(ROOT, world.root / "bundles"))
    committed = json.loads((ROOT / "data/bundles/index.json").read_text())
    assert [r["run_id"] for r in merged["runs"]][: len(committed["runs"])] == [
        r["run_id"] for r in committed["runs"]
    ]
    assert merged["runs"][-1]["run_id"] == run_id
    assert not list((ROOT / "data/bundles").glob("live-*"))  # the committed folder is untouched


def test_two_reads_in_one_second_do_not_share_a_run(world, monkeypatch):
    from archivist.live import artifacts

    monkeypatch.setattr(artifacts, "stamp", lambda now=None: "20261031-120000")
    first, second = read(world), read(world)
    ids = [first[-1]["run_id"], second[-1]["run_id"]]
    assert ids[0] != ids[1] and ids[1].endswith("-2")
    for run_id in ids:
        assert (world.root / "bundles" / run_id / "bundle.json").is_file()


def test_an_unsupported_page_is_reported_and_leaves_no_bundle(world):
    Scripted.answers["llm"] = lambda request: json.dumps({"doc_type": "unsupported"})
    evs = read(world)
    assert evs[-1]["outcome"] == "unsupported" and len(of(evs, "call")) == 1
    assert not (world.root / "bundles").exists()
    assert [e["step"] for e in of(evs, "step", state="start")] == ["recognise"]


# --- replay ---------------------------------------------------------------------------------------


def test_a_replay_plays_the_cache_at_the_recorded_pace_and_spends_nothing(world):
    read(world)
    for key_line in world.latency.path.read_text().splitlines():  # the originals took 40 ms each
        entry = json.loads(key_line)
        world.latency.record(entry["key"], 40.0, entry["role"])
    spent, reached = len(ledger(world)), len(Scripted.reached)

    evs = read(world, mode="replay", speed=4.0)
    assert evs[0]["mode"] == "replay" and evs[-1]["outcome"] == "read"
    calls = of(evs, "call")
    assert {c["source"] for c in calls} == {"cache"} and {c["cost_usd"] for c in calls} == {0.0}
    assert {c["latency_ms"] for c in calls} == {40.0}
    assert {c["latency_of"] for c in calls} == {"recorded"}
    assert len(ledger(world)) == spent and len(Scripted.reached) == reached
    assert [e["step"] for e in of(evs, "step", state="start")] == list(events.STEPS)
    assert evs[-1]["run_id"].startswith("replay-")
    built = Bundle.model_validate_json(
        (world.root / "bundles" / evs[-1]["run_id"] / "bundle.json").read_text()
    )
    assert built.run.collection == "Replay: memo-0001" and "nothing was spent" in built.run.description
    # two extractor calls in turn at 40 ms / 4: no faster than the recorded pace allows
    assert evs[-1]["totals"]["elapsed_s"] >= 0.02


def test_a_replay_is_faster_by_the_factor_it_is_given(world):
    read(world)
    for line in world.latency.path.read_text().splitlines():
        entry = json.loads(line)
        world.latency.record(entry["key"], 200.0, entry["role"])
    slow = read(world, mode="replay", speed=1.0)[-1]["totals"]["elapsed_s"]
    fast = read(world, mode="replay", speed=50.0)[-1]["totals"]["elapsed_s"]
    assert slow >= 0.4 and fast < slow / 3  # the two extractor calls alone are 0.4 s at 1x


def test_a_hit_whose_original_was_never_timed_is_played_at_a_stated_nominal_pace(world):
    read(world)
    world.latency.path.unlink()
    world.latency = events.LatencyLog(world.latency.path)
    evs = read(world, mode="replay", speed=50.0)
    calls = of(evs, "call")
    assert {c["latency_of"] for c in calls} == {"nominal"} and {c["latency_ms"] for c in calls} == {None}


def test_a_replay_of_a_page_not_in_the_cache_stops_without_reaching_a_backend(world):
    read(world)  # fills the cache with this page's answers
    shifted = world.synthetic_root / "dev" / "images" / "memo-0002.jpg"
    Image.new("RGB", (400, 300), "gray").save(shifted)
    reached, spent = len(Scripted.reached), len(ledger(world))
    evs = read(world, page="dev/memo-0002", mode="replay")
    assert evs[-1]["type"] == "error" and evs[-1]["kind"] == "not_cached"
    assert len(Scripted.reached) == reached and len(ledger(world)) == spent


def test_a_replay_needs_a_cache_and_no_key(world):
    world._keys = lambda config: ["META_API_KEY"]  # no key is set
    with pytest.raises(StartRefused) as refused:
        world.start(Request(PAGE, mode="replay"))
    assert refused.value.status == 412 and "empty or missing" in refused.value.message
    world.cache_dir.mkdir()
    (world.cache_dir / "x").mkdir()
    with pytest.raises(StartRefused) as live:  # live still needs the key
        world.start(Request(PAGE, mode="live"))
    assert live.value.status == 412 and "META_API_KEY" in live.value.message
    assert Scripted.reached == []


def test_a_replay_that_reaches_a_backend_is_an_error_not_a_quiet_spend(world):
    """Mock prices are zero, so a zero cap would not refuse them: the observer does."""
    rec = events.Recorder(
        events.EventLog("t"), events.Steps(events.EventLog("t"), {}), world.latency, mode="replay"
    )
    inner = load_roles(world.arms["a"], cache_dir=world.cache_dir, ledger_path=world.ledger_path)
    role = events.Observed(inner["segmenter"], "segmenter", rec)
    from archivist.models.base import SegmentRequest

    with pytest.raises(RuntimeError, match="not in the cache"):
        role.segment(SegmentRequest(role="segmenter", image=b"x", prompts=("stamp",)))


# --- stopping, keys and one read at a time ----------------------------------------------------------


def test_a_read_can_be_stopped_and_asks_nothing_further(world):
    Scripted.gate = threading.Event()
    started = world.start(Request(PAGE))
    deadline = time.time() + 5
    while not Scripted.reached and time.time() < deadline:
        time.sleep(0.01)
    assert world.cancel(started.id)
    Scripted.gate.set()
    started.thread.join(10)
    evs = started.log.events()
    assert evs[-1]["type"] == "error" and evs[-1]["kind"] == "stopped"
    assert len(Scripted.reached) == 1  # the one call in flight; the page was not read on
    assert world.cancel(started.id) is False


def test_only_one_read_runs_at_a_time(world):
    Scripted.gate = threading.Event()
    first = world.start(Request(PAGE))
    with pytest.raises(StartRefused) as busy:
        world.start(Request(PAGE))
    assert busy.value.status == 409
    Scripted.gate.set()
    first.thread.join(30)
    assert world.status()["running"] is None
    read(world)  # free again


def test_a_live_read_without_its_key_does_not_start(world):
    world._keys = lambda config: ["BASETEN_API_KEY", "META_API_KEY"]
    with pytest.raises(StartRefused) as refused:
        world.start(Request(PAGE, mode="live", arm="b"))
    assert refused.value.status == 412
    assert "BASETEN_API_KEY, META_API_KEY" in refused.value.message and "Replay" in refused.value.message
    assert Scripted.reached == [] and world.status()["running"] is None


def test_the_open_weight_arm_shows_the_open_model_by_name(world):
    evs = read(world, arm="b")
    assert [m["name"] for m in evs[0]["models"]] == ["Muse Spark Open", "Muse Spark Open", "SAM 3.1"]
    assert {c["model"] for c in of(evs, "call")} == {"Muse Spark Open", "SAM 3.1"}


def test_errors_never_carry_a_key(world, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "sk-secret-0123456789")

    def boom(request):
        raise RuntimeError("401 for key sk-secret-0123456789")

    Scripted.answers["llm"] = boom
    evs = read(world)
    text = json.dumps(evs)
    assert "sk-secret-0123456789" not in text and "[key]" in text
    assert evs[-1]["type"] == "error"


def test_the_status_says_which_keys_are_set_and_never_what_they_are(world, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "sk-secret-0123456789")
    status = world.status()
    assert "sk-secret-0123456789" not in json.dumps(status)
    assert set(status["keys"].values()) <= {True, False}
    assert status["steps"] == list(events.STEPS) and status["live"]["available"] is True


# --- the development-only check -------------------------------------------------------------------


@pytest.fixture
def real(tmp_path):
    """A tiny data/real: one development page that matches its manifest, and the committed split."""
    root = tmp_path / "real"
    (root / "pages" / "1939-12").mkdir(parents=True)
    scan = io.BytesIO()
    Image.new("RGB", (60, 80), "white").save(scan, format="JPEG")
    path = root / "pages" / "1939-12" / "p053.jpg"
    path.write_bytes(scan.getvalue())
    import hashlib

    manifest = json.loads((ROOT / "data/real/manifest.json").read_text())
    for entry in manifest["pages"]:
        if (entry["issue"], entry["page"]) == ("1939-12", 53):
            entry["sha256"] = hashlib.sha256(scan.getvalue()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "split.json").write_text((ROOT / "data/real/split.json").read_text())
    return root


def test_a_development_page_of_the_split_is_let_through(real, tmp_path):
    page = pages.resolve("1939-12_p053", real_root=real, synthetic_root=tmp_path)
    assert (page.kind, page.split, page.page_id) == ("treasury", "real", "1939-12_p053")
    assert page.path == real / "pages" / "1939-12" / "p053.jpg"


@pytest.mark.parametrize("issue", ["1940-01", "1941-06", "1985-06", "1994-06", "1942-12"])
def test_a_held_out_page_is_refused_before_its_file_is_opened(real, tmp_path, issue):
    split = json.loads((real / "split.json").read_text())
    assert issue in split["held_out"] and issue not in split["development"]
    with pytest.raises(pages.LiveRefused, match="not a development issue"):
        pages.resolve(f"{issue}_p010", real_root=real, synthetic_root=tmp_path)
    assert not (real / "pages" / issue).exists()  # nothing was even looked for


def test_a_treasury_read_needs_its_scan_and_its_pdf_and_says_so_before_any_call(
    world, real, tmp_path
):
    """Neither the scans nor the archive PDFs are committed: a page without its PDF is not offered as
    readable, and a read of it is refused before a model is asked."""
    world.real_root = real
    assert not pages.downloaded(real, "1939-12", 53)
    listed = {p["ref"]: p for g in world.pages() for p in g["pages"] if g["id"] == "treasury"}
    assert listed["1939-12_p053"]["scan"] is False
    with pytest.raises(StartRefused) as refused:
        world.start(Request("1939-12_p053", mode="live"))
    assert refused.value.status == 412 and "archive PDF" in refused.value.message
    assert Scripted.reached == [] and world.status()["running"] is None
    (real / "pdf").mkdir()
    (real / "pdf" / "1939_12_treasurybulletin.pdf").write_bytes(b"%PDF")
    assert pages.downloaded(real, "1939-12", 53)


def test_every_issue_of_the_committed_split_is_one_or_the_other():
    split = json.loads((ROOT / "data/real/split.json").read_text())
    assert not set(split["development"]) & set(split["held_out"])


def test_without_the_split_file_no_real_page_is_read(real, tmp_path):
    (real / "split.json").unlink()
    with pytest.raises(pages.LiveRefused, match="split.json is missing"):
        pages.resolve("1939-12_p053", real_root=real, synthetic_root=tmp_path)
    assert pages.listing(real_root=real, synthetic_root=tmp_path) == []


def test_a_scan_that_is_not_the_manifests_is_refused(real, tmp_path):
    (real / "pages" / "1939-12" / "p053.jpg").write_bytes(b"not the scan")
    with pytest.raises(pages.LiveRefused, match="does not match the manifest"):
        pages.resolve("1939-12_p053", real_root=real, synthetic_root=tmp_path)


@pytest.mark.parametrize(
    "ref",
    [
        "test/card-01-1",  # the frozen test set
        "dev/../test/card-01-1",
        "dev/card-01-1.jpg",
        "../../etc/passwd",
        "1925_p341",  # the Comptroller's reports: no approved template reads them
        "frb-1990-06_p077",  # the Federal Reserve Bulletin likewise
        "1939-12_p053/../../x",
        "",
        "1939-12",
    ],
)
def test_nothing_else_is_a_page(real, tmp_path, ref):
    with pytest.raises(pages.LiveRefused):
        pages.resolve(ref, real_root=real, synthetic_root=tmp_path)


def test_the_synthetic_test_split_is_never_listed_or_read(world):
    (world.synthetic_root / "test" / "images").mkdir(parents=True)
    Image.new("RGB", (40, 40), "white").save(world.synthetic_root / "test" / "images" / "card-01-1.jpg")
    with pytest.raises(pages.LiveRefused):
        world.resolve("test/card-01-1")
    listed = [p["ref"] for g in world.pages() for p in g["pages"]]
    assert listed == [PAGE]


def test_the_list_holds_development_pages_only():
    """Built from the committed split and manifest: every page offered is of a development issue,
    none of a held-out one."""
    split = json.loads((ROOT / "data/real/split.json").read_text())
    groups = pages.listing(synthetic_root=Path("/nonexistent"))
    offered = [p["ref"] for g in groups for p in g["pages"]]
    assert offered, "the committed manifest offers no page"
    assert {ref.split("_")[0] for ref in offered} <= set(split["development"])
    assert not {ref.split("_")[0] for ref in offered} & set(split["held_out"])
    assert all(p["family"] for g in groups for p in g["pages"])


def test_the_server_refuses_a_held_out_page_whatever_the_browser_says(web, world):
    world.real_root = ROOT / "data/real"
    for route in ("page", "image"):
        status, body = http_get(world, f"/api/live/{route}?ref=1940-01_p001")
        assert status == 403 and "not a development issue" in body["error"]
    status, body = http_post(world, "/api/live/read", {"page": "1940-01_p001", "mode": "replay"})
    assert status == 403
    status, body = http_post(world, "/api/live/read", {"page": "test/card-01-1", "mode": "live"})
    assert status == 403 and not Scripted.reached


# --- the server -----------------------------------------------------------------------------------


class Running:
    """The server on a free loopback port, in a thread, for as long as a test needs it."""

    def __init__(self, app: LiveApp) -> None:
        self.httpd = server.serve(app, ROOT, "127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def web(world):
    running = Running(world)
    world.web = running
    yield running
    running.close()


def request(app, method, path, body=None, headers=None, host=None):
    port = app.web.port
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    sent = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    conn.request(method, path, body=body, headers=sent)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, response, data


def http_get(app, path, **kw):
    status, response, data = request(app, "GET", path, **kw)
    kind = response.getheader("Content-Type") or ""
    return status, json.loads(data) if "json" in kind else data


def http_post(app, path, payload, headers=None, host=None):
    sent = {"Content-Type": "application/json", server.HEADER: "1", **(headers or {})}
    status, response, data = request(app, "POST", path, json.dumps(payload), sent, host)
    return status, json.loads(data)


def test_the_app_is_marked_local_only_in_the_page_this_server_serves(web, world):
    status, html = http_get(world, "/ui/")
    assert status == 200 and server.MARKER.encode() in html
    on_disk = (ROOT / "ui" / "index.html").read_text()
    assert "archivist-live" not in on_disk and "api/live" not in on_disk  # the published page
    assert 'type="file"' not in on_disk and "upload" not in on_disk.lower()  # D13: no upload box
    for path in ("/ui/index.html", "/ui"):
        assert server.MARKER.encode() in http_get(world, path)[1]
    assert request(world, "GET", "/")[0] == 302


def test_only_the_app_and_the_bundles_are_served(web, world):
    for path in (
        "/.env",
        "/pyproject.toml",
        "/data/real/manifest.json",
        "/data/dev/manifest.json",
        "/src/archivist/live/server.py",
        "/ui/../.env",
        "/data/bundles/../../.env",
        "/data/bundles/%2e%2e/%2e%2e/.env",
        "/ui/%2e%2e/pyproject.toml",
        "/data/pages/../../CLAUDE.md",
    ):
        status, _, body = request(world, "GET", path)
        assert status == 404, path
        assert b"[project]" not in body and b"CLAUDE" not in body
    assert request(world, "GET", "/ui/js/main.js")[0] == 200
    assert request(world, "GET", "/data/bundles/index.json")[0] == 200


def test_the_api_answers_only_this_machine_and_only_the_app(web, world):
    payload = {"page": PAGE, "mode": "replay"}
    assert http_get(world, "/api/live/status", host="evil.example:80")[0] == 403
    assert http_post(world, "/api/live/read", payload, host="evil.example")[0] == 403
    assert http_post(world, "/api/live/read", payload, headers={"Origin": "http://evil.example"})[0] == 403
    status, _, _ = request(
        world, "POST", "/api/live/read", json.dumps(payload), {"Content-Type": "text/plain"}
    )
    assert status == 403  # a plain form post cannot send the header or the type
    status, _, _ = request(
        world, "POST", "/api/live/read", json.dumps(payload), {"Content-Type": "application/json"}
    )
    assert status == 403  # a script on another site cannot send the header without a preflight
    assert Scripted.reached == [] and world.status()["running"] is None
    with pytest.raises(SystemExit):
        server.serve(world, ROOT, "0.0.0.0", 0)  # noqa: S104: local only, whatever is asked


def test_a_read_over_http_streams_its_events_and_leaves_a_bundle_the_app_can_open(web, world):
    status, body = http_post(world, "/api/live/read", {"page": PAGE, "mode": "live"})
    assert status == 200
    session_id = body["session"]
    conn = http.client.HTTPConnection("127.0.0.1", web.port, timeout=30)
    conn.request("GET", f"/api/live/events/{session_id}", headers={"Host": f"127.0.0.1:{web.port}"})
    response = conn.getresponse()
    assert response.status == 200 and response.getheader("Content-Type") == "text/event-stream"
    text = response.read().decode()
    conn.close()
    sent = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    ids = [int(line[4:]) for line in text.splitlines() if line.startswith("id: ")]
    assert ids == [e["seq"] for e in sent] == list(range(len(sent)))
    assert sent[0]["type"] == "session" and sent[-1]["type"] == "done"
    assert sent == world.get(session_id).log.events()  # what was streamed is what happened

    status, listed = http_get(world, f"/api/live/session/{session_id}")
    assert listed["events"] == sent

    run_id = sent[-1]["run_id"]
    status, index = http_get(world, "/data/bundles/index.json")
    assert run_id in [r["run_id"] for r in index["runs"]] and "test-archivist-A" in json.dumps(index)
    status, built = http_get(world, f"/data/bundles/{run_id}/bundle.json")
    assert status == 200 and built["run"]["run_id"] == run_id
    url = built["pages"][0]["image"]["url"]
    assert url == "../../pages/dev/memo-0001.jpg"
    assert request(world, "GET", f"/data/pages/dev/memo-0001.jpg")[0] == 200
    assert request(world, "GET", "/data/pages/test/card-01-1.jpg")[0] == 200  # the committed ones too


def test_a_stream_can_be_picked_up_where_it_left_off(web, world):
    evs = read(world)
    session_id = next(iter(world._sessions))
    conn = http.client.HTTPConnection("127.0.0.1", web.port, timeout=30)
    conn.request(
        "GET",
        f"/api/live/events/{session_id}",
        headers={"Host": f"127.0.0.1:{web.port}", "Last-Event-ID": "4"},
    )
    text = conn.getresponse().read().decode()
    conn.close()
    sent = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    assert [e["seq"] for e in sent] == list(range(5, len(evs)))


def test_a_refused_start_is_an_http_error_with_the_reason(web, world):
    world._keys = lambda config: ["META_API_KEY"]
    status, body = http_post(world, "/api/live/read", {"page": PAGE, "mode": "live"})
    assert status == 412 and "META_API_KEY" in body["error"]
    status, body = http_post(world, "/api/live/read", {"page": PAGE, "mode": "dry"})
    assert status == 400
    status, body = http_post(world, "/api/live/read", {"page": PAGE, "mode": "live", "arm": "z"})
    assert status == 400 and "no arm" in body["error"]
    status, _, _ = request(world, "GET", "/api/live/events/nope")
    assert status == 404


# --- the real-page flow ---------------------------------------------------------------------------


def test_a_treasury_page_is_read_as_the_real_pages_test_reads_it(tmp_path, monkeypatch):
    """The five approved tables, S0 then S0+grid boxes, SAM, and verification under policy v2 with
    no second looks, on a drawn page and a fake OCR layer (the PDFs are not in the repository)."""
    from test_real_test import RAILROAD, RAILROAD_TITLE, _railroad_answer

    from archivist.models.mock import MockLLM, MockSegmenter
    from archivist.templates import real_test

    monkeypatch.chdir(ROOT)
    path = tmp_path / "real" / "pages" / "1939-12" / "p025.jpg"
    path.parent.mkdir(parents=True)
    image = Image.new("RGB", (1000, 1000), "white")
    from PIL import ImageDraw

    canvas = ImageDraw.Draw(image)
    for r in range(1, 18):
        for i in range(6):
            x0, y0 = 120 + 140 * i, 50 + 50 * r
            canvas.rectangle([x0, y0, x0 + 60, y0 + 20], fill=(10, 10, 10))
    image.save(path)
    page = pages.LivePage("1939-12_p025", "1939-12_p025", path, "treasury", "real")

    def respond(request):
        if "doc_type" in request.json_schema["properties"]:
            return json.dumps({"doc_type": RAILROAD})
        if "rows" in request.json_schema["properties"]:
            return _railroad_answer(request)
        return json.dumps({"value": "1.0"})

    log = events.EventLog("t")
    names = {"extractor": "Muse Spark 1.3", "rereader": "Muse Spark 1.3", "segmenter": "SAM 3.1"}
    rec = events.Recorder(log, events.Steps(log, names), events.LatencyLog(tmp_path / "l"), mode="live")
    extractor, rereader, segmenter = MockLLM(respond), MockLLM(respond), MockSegmenter()
    roles = {
        "extractor": events.Observed(extractor, "extractor", rec),
        "rereader": events.Observed(rereader, "rereader", rec),
        "segmenter": events.Observed(segmenter, "segmenter", rec),
    }
    doc_types = real_test._types(ROOT / real_test.CONFIG)
    layer = tuple(reader.ocr.Word(w, BBox(x0=0, y0=0, x1=1, y1=1)) for w in RAILROAD_TITLE.split())
    outcome = reader.read_treasury(page, roles, doc_types, rec, layer_of=lambda p: layer)

    assert outcome.doc_type == RAILROAD and outcome.title_confirmed is True
    assert outcome.citations == "S0+grid" and len(outcome.verdicts) == 17 * 6
    assert outcome.calls["second_looks"] == 0
    # the pipeline's own deep check, on the same answers, gives the same verdicts
    theirs_dir = tmp_path / "out"
    theirs_dir.mkdir()
    monkeypatch.setattr(real_test, "resolve", lambda ref, side, root=None: page.page)
    (theirs_dir / "titles.jsonl").write_text(
        json.dumps({"page": page.ref, "classified_as": RAILROAD, "pattern": "railroad"}) + "\n"
    )
    verdicts, _ = real_test.deep(
        theirs_dir,
        "development",
        {"extractor": MockLLM(respond), "rereader": MockLLM(respond), "segmenter": MockSegmenter()},
        doc_types,
        per_family=1,
        workers=4,
        layer_of=lambda p: layer,
    )
    assert [v.model_dump() for v in outcome.verdicts] == [v.model_dump() for v in verdicts]
    # and it leaves a bundle the normal views open, from the same exporter as the committed runs
    from archivist.export import bundle as export
    from archivist.live import artifacts

    monkeypatch.setattr(export, "REAL_PAGES", tmp_path / "real" / "pages")
    root = tmp_path / "live"
    now = datetime.now(UTC)
    run_dir = artifacts.write_run(
        root, "live-x-1939-12-p025", outcome, config=describe_config(ROOT / real_test.CONFIG),
        doc_types=doc_types, rec=rec, started=now, finished=now,
    )
    run_id = artifacts.export_run(root, run_dir, mode="live", outcome=outcome, cost=0.0)
    built = Bundle.model_validate_json((root / "bundles" / run_id / "bundle.json").read_text())
    assert built.run.split == "real" and built.run.source == "public-domain scans"
    assert built.run.collection == "Live read: December 1939, page 25"
    assert built.run.publication is not None and built.run.citations == "S0+grid"
    page_row = built.pages[0]
    assert (page_row.issue, page_row.number) == ("1939-12", 25) and page_row.title
    assert len(built.fields) == 17 * 6 and (root / "bundles" / run_id / page_row.image.url).is_file()
    evs = log.events()
    started = [e["step"] for e in of(evs, "step", state="start")]
    assert started == list(events.STEPS)
    assert {c["role"] for c in of(evs, "call", step="blind")} == {"rereader"}
    assert {c["role"] for c in of(evs, "call", step="read")} == {"extractor"}
    assert of(evs, "step", step="recognise", state="done")[0]["facts"]["title_confirmed"] is True
