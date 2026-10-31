"""P37: text sorting, fallback, title confirmation and money protection, entirely offline."""
import json
from pathlib import Path

import pytest

from archivist.doctypes import UNSUPPORTED, from_config
from archivist.models import SortRequest, SortFamily, load_roles
from archivist.models.base import SortAnswer, SortResponse, Usage
from archivist.models.mock import MockLLM, MockTextSorter
from archivist.models.cache import Cache
from archivist.models.budget import Budget, BudgetGuard, BudgetExceeded, Price
from archivist.models.text_sorting import families_of, payload
from archivist.pipeline import extract

CONFIG = Path('config/archive_glimmer.toml')
TYPES = from_config(CONFIG)
FAMILY = next(iter(TYPES))


def request(text='header', ref='1939-12_p053'):
    return SortRequest('sorter', (text,), families_of(TYPES), (ref,))


def test_prompt_prefix_and_family_order_are_exactly_the_frozen_phase2_protocol():
    from archivist.glimmer.data import load_frozen, prompt, SYSTEM
    _, rows, families = load_frozen()
    for row in rows:
        r = request(row['ocr'], row['page'])
        assert r.texts == (row['ocr'][:1024],)
        assert payload(r) == [{'system':SYSTEM,'prompt':prompt(row['ocr'][:1024],families)}]


def test_typed_sort_cache_ignores_discarded_tail_and_replays_with_cap_zero(tmp_path):
    model = MockTextSorter(lambda r:[FAMILY],cost_usd=.1)
    ledger = tmp_path/'ledger.jsonl'
    cached = Cache(Budget(model,BudgetGuard(1,ledger),Price(0,0,0,.2)),tmp_path/'cache')
    first = cached.sort(request('a'*1024+'tail one'))
    assert first.answers[0].family == FAMILY and not first.cached
    replay_model = MockTextSorter(lambda r:pytest.fail('cache miss'))
    replay = Cache(Budget(replay_model,BudgetGuard(0,ledger),Price(0,0,0,.2)),tmp_path/'cache')
    second = replay.sort(request('a'*1024+'different discarded tail'))
    assert second.cached and second.answers == first.answers
    assert len(model.calls)==1 and not replay_model.calls
    assert len(ledger.read_text().splitlines())==1


def test_sort_request_prices_reserve_before_call_and_record_uncertain_failures(tmp_path):
    model=MockTextSorter(lambda r:pytest.fail('cap bypass'))
    ledger=tmp_path/'ledger.jsonl'
    budget=Budget(model,BudgetGuard(.19,ledger),Price(0,0,0,.2))
    with pytest.raises(BudgetExceeded): budget.sort(request())
    assert not model.calls and not ledger.exists()
    class Failing:
        name='modal_glimmer_sorter'
        model_id='mock'
        def sort(self,r): raise RuntimeError('connection lost after submission')
    budget=Budget(Failing(),BudgetGuard(.3,ledger),Price(0,0,0,.2))
    with pytest.raises(RuntimeError): budget.sort(request())
    assert json.loads(ledger.read_text())['cost_usd']==.2
    with pytest.raises(BudgetExceeded): budget.sort(request())


def test_optional_sorter_uses_text_and_never_vision_repair_for_invalid_answers():
    vision=MockLLM(lambda r:pytest.fail('vision should not classify a text page'))
    sorter=MockTextSorter(lambda r:[FAMILY])
    assert extract.classify(b'image',vision,TYPES,sorter=sorter,text='title',source_ref='1939-12_p053')==FAMILY
    assert len(sorter.calls)==1 and not vision.calls
    other=MockTextSorter(lambda r:['other'])
    assert extract.classify(b'image',vision,TYPES,sorter=other,text='x')==UNSUPPORTED
    invalid=MockTextSorter(lambda r:['invalid'])
    with pytest.raises(extract.ExtractionFailed,match='invalid text-sort'):
        extract.classify(b'image',vision,TYPES,sorter=invalid,text='x')
    assert not vision.calls


def test_no_text_layer_or_no_role_retains_the_existing_image_classifier():
    vision=MockLLM(lambda r:json.dumps({'doc_type':FAMILY}))
    sorter=MockTextSorter(lambda r:pytest.fail('no text layer'))
    assert extract.classify(b'image',vision,TYPES,sorter=sorter,text=None)==FAMILY
    assert extract.classify(b'image',vision,TYPES,text='available without a sorter role')==FAMILY
    assert len(vision.calls)==2 and not sorter.calls


def test_existing_title_check_is_shared_and_blocks_unconfirmed_new_extraction(tmp_path,monkeypatch):
    from archivist.glimmer.data import load_frozen
    from archivist.doctypes.titles import title_match
    from archivist.templates import real_test
    assert real_test.title_match is title_match
    _,rows,_=load_frozen()
    positive=next(r for r in rows if r['target']==FAMILY)
    image=tmp_path/'page.jpg';image.write_bytes(b'not opened by a field reader in this test')
    vision=MockLLM(lambda r:pytest.fail('vision classification should not run'))
    sorter=MockTextSorter(lambda r:[FAMILY])
    calls=[]
    monkeypatch.setattr(extract,'read_page',lambda *a,**k:calls.append(a) or [])
    roles={'extractor':vision,'sorter':sorter}
    good=extract.extract_page(image,roles,'S0',doc_types=TYPES,
        text=positive['ocr'],text_source_ref=positive['page'])
    assert good.doc_type==FAMILY and len(calls)==1
    rejected=extract.extract_page(image,roles,'S0',doc_types=TYPES,
        text='a different printed title',text_source_ref='1939-12_p003')
    assert rejected.doc_type==UNSUPPORTED and rejected.values==[] and len(calls)==1


def test_production_backend_refuses_heldout_before_endpoint_lookup(tmp_path,monkeypatch):
    from archivist.models import glimmer_sorter_backend as backend
    model=backend.GlimmerSorter(price=Price(0,0,0,backend.MAX_CALL_USD))
    monkeypatch.setattr(backend,'remote_sort',lambda _:pytest.fail('endpoint lookup on held-out input'))
    wrapped=Cache(Budget(model,BudgetGuard(10,tmp_path/'ledger'),Price(0,0,0,backend.MAX_CALL_USD)),tmp_path/'cache')
    with pytest.raises(backend.SortRefused): wrapped.sort(request(ref='1940-01_p001'))
    assert not (tmp_path/'ledger').exists()


def test_registered_backend_is_lazy_capped_and_parses_native_outputs(monkeypatch,tmp_path):
    from archivist.models import glimmer_sorter_backend as backend
    monkeypatch.setenv('GLIMMER_CAP_USD','0')
    monkeypatch.setattr(backend,'remote_sort',lambda _:pytest.fail('zero-cap endpoint lookup'))
    roles=load_roles(CONFIG,cache_dir=tmp_path/'cache',ledger_path=tmp_path/'ledger')
    with pytest.raises(BudgetExceeded): roles['sorter'].sort(request())
    monkeypatch.setenv('GLIMMER_CAP_USD','10')
    monkeypatch.setattr(backend,'remote_sort',lambda _:object())
    captured=[]
    def remote(_,body,**settings):
        captured.append(body)
        assert settings['execution_seconds']==900
        return {'runtime_seconds':2,'outputs':[{'index':0,'text':' to=user<|message|>'+FAMILY+'<|eot|>',
            'input_tokens':300,'output_tokens':12,'at_token_limit':False}]}
    monkeypatch.setattr(backend,'wait_for_call',remote)
    role=load_roles(CONFIG,cache_dir=tmp_path/'cache',ledger_path=tmp_path/'ledger')['sorter']
    answer=role.sort(request())
    assert answer.answers[0].family==FAMILY
    assert captured[0]=={'development_only':True,'items':payload(request())}
    assert answer.usage.cost_usd<=backend.MAX_CALL_USD
    assert json.loads((tmp_path/'ledger').read_text())['backend']=='modal_glimmer_sorter'
    assert role.sort(request()).cached and len(captured)==1


def test_changing_sorter_configuration_requires_a_new_run_before_calls(tmp_path):
    from archivist.doctypes import enabled,recorded
    types=enabled(['ledger_card','payment_memo'])
    images=tmp_path/'images';images.mkdir();(images/'page.jpg').write_bytes(b'image')
    run=tmp_path/'run';run.mkdir()
    (run/'run.json').write_text(json.dumps({'config':{},'doc_types':recorded(types)}))
    with pytest.raises(ValueError,match='sorter configuration changed'):
        extract.run(images,run,{'extractor':MockLLM()},guard=BudgetGuard(0,tmp_path/'ledger'),
            config={'sorter':{'model_id':'new'}},doc_types=types)
