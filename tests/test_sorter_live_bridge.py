"""Apply the handoff patch to its recorded live-reading source; exercise step 1 offline."""
import importlib
import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from archivist.doctypes import from_config
from archivist.models.mock import MockLLM, MockTextSorter
from archivist.templates.ocr import Word
from archivist.schema import BBox


@pytest.fixture
def live(tmp_path,monkeypatch):
    record=json.loads(Path('results/glimmer/sorter/live-reading-patch-check.json').read_text())
    if subprocess.run(["git", "cat-file", "-e", record["commit"]], capture_output=True).returncode:
        pytest.skip("handoff source commit is not present in this clone")
    sources=[*record['files'],'src/archivist/live/pages.py']
    prefix=tmp_path/'tree'
    for name in sources:
        text=subprocess.run(['git','show',record['commit']+':'+name],capture_output=True,text=True,check=True).stdout
        path=prefix/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    subprocess.run(['git','apply','--directory='+str(prefix.relative_to(Path.cwd())),
        'results/glimmer/sorter/live-reading.patch'],check=True)
    # Only the reader/events/pages are imported. UI exporter dependencies live on ui;
    # its patched model-name function has a separate syntax/application check.
    from archivist.export import bundle
    monkeypatch.setattr(bundle,'model_name',lambda name:name,raising=False)
    package=types.ModuleType('archivist.live')
    package.__path__=[str(prefix/'src/archivist/live')]
    monkeypatch.setitem(sys.modules,'archivist.live',package)
    for name in ('events','pages','reader'):
        monkeypatch.delitem(sys.modules,'archivist.live.'+name,raising=False)
    reader=importlib.import_module('archivist.live.reader')
    events=importlib.import_module('archivist.live.events')
    yield reader,events
    for name in ('events','pages','reader'):
        sys.modules.pop('archivist.live.'+name,None)


def test_patched_live_recognition_uses_observed_sorter_and_stops_on_title_rejection(live,tmp_path):
    reader,events=live
    types_=from_config(Path('config/archive_glimmer.toml'));family=next(iter(types_))
    page=SimpleNamespace(path=tmp_path/'page.jpg',ref='1939-12_p003')
    page.path.write_bytes(b'image')
    log=events.EventLog("test-sorter")
    steps=events.Steps(log,{'extractor':'vision','sorter':'glimmer'})
    rec=events.Recorder(log,steps,events.LatencyLog(tmp_path/'latency.jsonl'),mode='live')
    sorter=MockTextSorter(lambda r:[family])
    vision=MockLLM(lambda r:pytest.fail('vision classification on a text page'))
    roles={'extractor':events.Observed(vision,'extractor',rec),
           'sorter':events.Observed(sorter,'sorter',rec)}
    layer=[Word('A different title',BBox(x0=0,y0=0,x1=1,y1=1))]
    outcome=reader.read_treasury(page,roles,types_,rec,layer_of=lambda p:layer)
    assert outcome.doc_type==family and outcome.title_confirmed is False
    assert outcome.extraction is None and not vision.calls and len(sorter.calls)==1
    assert rec.totals['calls']==1


def test_patched_live_without_a_text_layer_uses_current_classifier(live,tmp_path):
    reader,events=live
    types_=from_config(Path('config/archive_glimmer.toml'));family=next(iter(types_))
    page=SimpleNamespace(path=tmp_path/'page.jpg',ref='1939-12_p003')
    page.path.write_bytes(b'image')
    log=events.EventLog("test-sorter");steps=events.Steps(log,{'extractor':'vision','sorter':'glimmer'})
    rec=events.Recorder(log,steps,events.LatencyLog(tmp_path/'latency.jsonl'),mode='live')
    sorter=MockTextSorter(lambda r:pytest.fail('sorter without a text layer'))
    vision=MockLLM(lambda r:json.dumps({'doc_type':family}))
    outcome=reader.read_treasury(page,{'extractor':vision,'sorter':sorter},types_,rec,
                                  layer_of=lambda p:())
    assert len(vision.calls)==1 and not sorter.calls
    assert outcome.title_confirmed is False and outcome.extraction is None
