"""Development-only gates and classification scoring; no network or archive pages."""
import json
from pathlib import Path

import pytest

from archivist.glimmer.data import checked_ref, fixed_slice, reject_leakage, sweep_labels
from archivist.glimmer.metrics import INVALID, parse_answer, score
from archivist.templates.pages import PageRefused


def _split(root, source, dev, held):
    directory = root / source
    directory.mkdir(parents=True)
    (directory/'split.json').write_text(json.dumps({'development':dev,'held_out':held}))


def test_source_gate_checks_split_before_opening_pages_and_keeps_namespaces(tmp_path):
    _split(tmp_path,'real',['1984-06'],['1990-06'])
    _split(tmp_path,'real_frb',['1990-06'],['1984-06'])
    _split(tmp_path,'real_occ',['1925'],['1915'])
    assert checked_ref('1984-06_p001',tmp_path)==('real','1984-06',1)
    assert checked_ref('frb-1990-06_p001',tmp_path)==('real_frb','1990-06',1)
    assert checked_ref('1925-v1_p001',tmp_path)==('real_occ','1925-v1',1)
    for ref in ('1990-06_p001','frb-1984-06_p001','1915-v2_p001','dev/x','../../bad'):
        with pytest.raises(PageRefused):
            checked_ref(ref,tmp_path)
    # There are deliberately no PDFs or images in this fixture.


def test_sweep_reconciles_title_rejections_and_refuses_missing_title_checks(tmp_path):
    data=tmp_path/'data'
    _split(data,'real',['1939-12'],['1940-01'])
    directory=tmp_path/'real_test/development'
    directory.mkdir(parents=True)
    (directory/'sweep.json').write_text(json.dumps({'side':'development','issues':['1939-12'],'pages':3}))
    rows=[{'page':f'1939-12_p{n:03d}','classified_as':kind}
          for n,kind in ((1,'family'),(2,'family'),(3,'unsupported'))]
    (directory/'sweep.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    titles=[{**rows[0],'pattern':'title'},{**rows[1],'pattern':None}]
    (directory/'titles.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in titles))
    labels=sweep_labels(directory,data,{'family'})
    assert [r['target'] for r in labels]==['family','other','other']
    assert labels[1]['stratum']=='title_other'
    (directory/'titles.jsonl').write_text(json.dumps(titles[0])+'\n')
    with pytest.raises(ValueError,match='title check'):
        sweep_labels(directory,data,{'family'})
    rows.append({'page':'1940-01_p001','classified_as':'unsupported'})
    (directory/'sweep.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(PageRefused):
        sweep_labels(directory,data,{'family'})
    with pytest.raises(ValueError,match='only'):
        sweep_labels(directory.parent/'held_out',data,{'family'})


def test_fixed_validation_is_deterministic_disjoint_and_keeps_title_negatives():
    rows=[{'page':f'p{n}','stratum':'classifier_other'} for n in range(11)]
    rows += [{'page':'rejected','stratum':'title_other'},{'page':'positive','stratum':'confirmed'}]
    train,val=fixed_slice(rows)
    assert fixed_slice(list(reversed(rows)))==(train,val)
    assert len(train)==8 and len(val)==5
    assert {'positive','rejected'} <= {r['page'] for r in val}
    assert not {r['page'] for r in train}&{r['page'] for r in val}


def test_duplicate_ocr_is_removed_from_training_and_duplicate_ids_refused():
    validation=[{'page':'a','input_sha256':'same'}]
    train=[{'page':'b','input_sha256':'same'},{'page':'c','input_sha256':'different'}]
    assert reject_leakage(train,validation)==[train[1]]
    with pytest.raises(ValueError,match='overlap'):
        reject_leakage(validation,validation)


def test_scoring_penalizes_false_positives_failures_and_missing_answers():
    expected={'a':'f','b':'f','c':'other','d':'other'}
    result=score(expected,{'a':'f','b':'other','c':'f'},['f','other'])
    assert result['accuracy']==.25
    assert result['invalid']==result['missing']==1
    assert result['per_family']['f']==dict(tp=1,fp=1,fn=1,support=2,precision=.5,recall=.5)
    assert result['per_family']['other']['recall']==0
    absent=score({'a':'f'},{'a':'f'},['f','other'])['per_family']['other']
    assert absent['precision'] is absent['recall'] is None
    with pytest.raises(ValueError,match='unknown page'):
        score(expected,{'unexpected':'f'},['f','other'])


def test_strict_final_answer_parsing_does_not_accept_a_label_in_reasoning():
    labels=['family','other']
    assert parse_answer(' family\n',labels)=='family'
    assert parse_answer('family<|eot|>',labels)=='family'
    assert parse_answer('reasoning: other<|start|>assistant to=user<|message|>family<|eot|>',labels)=='family'
    for text in ('I think family','{"family":"family"}','family or other','reasoning: family'):
        assert parse_answer(text,labels)==INVALID


def test_failed_jobs_keep_reservations_and_total_cannot_exceed_cap(tmp_path, monkeypatch):
    from archivist.glimmer import cost
    path=tmp_path/'cost.json'
    baseline=cost.reserve('baseline',path)
    cost.finish('baseline',None,path,'failure')
    assert json.loads(path.read_text())[0]['maximum_usd']==baseline['maximum_usd']
    with pytest.raises(ValueError,match='already reserved'):
        cost.reserve('baseline',path)
    monkeypatch.setattr(cost,'CAP',baseline['maximum_usd']+cost.OVERHEAD_RESERVE+.01)
    with pytest.raises(ValueError,match='cap'):
        cost.reserve('train',path)
    assert len(json.loads(path.read_text()))==1


def test_backend_routes_text_without_images_and_reports_compute_cost():
    from archivist.models.base import LLMRequest
    from archivist.models.glimmer_backend import ModalGlimmer
    class Remote:
        calls=0
        def remote(self,payload):
            self.calls+=1
            return {'runtime_seconds':2,'outputs':[{'input_tokens':3,'output_tokens':4}]}
    remote=Remote()
    backend=ModalGlimmer('model',remote=remote,stage='baseline',dataset_id='fixed')
    with pytest.raises(ValueError,match='text only'):
        backend.complete(LLMRequest(role='job',prompt='{}',images=(b'forbidden',)))
    assert remote.calls==0
    answer=backend.complete(LLMRequest(role='job',prompt='{}'))
    assert remote.calls==1 and answer.usage.cost_usd>0
    assert answer.usage.input_tokens==3


def test_assistant_only_training_masks_prompt_and_refuses_context_overflow():
    from archivist.models.glimmer_runtime import encode_training
    class Tokenizer:
        def apply_chat_template(self,turns,**kwargs):
            assert kwargs['tokenize'] is False
            return 'prompt:' + (turns[-1]['content'] if turns[-1]['role']=='assistant' else '')
        def __call__(self,text,**kwargs):
            return {'input_ids':[ord(c) for c in text]}
    item={'system':'system','prompt':'public OCR','target':'other'}
    encoded=encode_training(Tokenizer(),[item])[0]
    assert encoded['labels'][:7]==[-100]*7
    assert encoded['labels'][7:]==[ord(c) for c in 'other']
    with pytest.raises(ValueError,match='4096'):
        encode_training(Tokenizer(),[{**item,'target':'x'*4096}])


def test_training_return_wrapper_commits_the_completed_adapter_without_preflight(monkeypatch):
    import ast
    from types import SimpleNamespace
    from archivist.models import glimmer_runtime
    tree=ast.parse(Path('src/archivist/models/glimmer_modal.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='train')
    function.decorator_list=[]
    calls=[]
    result={'archive':b'completed adapter','training':{'epoch':3}}
    monkeypatch.setattr(glimmer_runtime,'run',lambda stage,payload:result)
    namespace={'volume':SimpleNamespace(commit=lambda:calls.append('committed'))}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'training_wrapper','exec'),namespace)
    assert namespace['train']({'items':[]}) is result
    assert calls==['committed']


def test_native_framing_diagnostic_reattaches_only_the_open_assistant_header():
    from archivist.glimmer.native_diagnostic import decode_native_continuation
    labels=['family','other']
    assert decode_native_continuation(' to=user<|message|>family<|eot|>',labels)=='family'
    assert decode_native_continuation(' to=self<|message|>other<|eom|><|start|>assistant to=user<|message|>family<|eot|>',labels)=='family'
    assert decode_native_continuation(' to=self<|message|>family<|eot|>',labels)==INVALID
    assert decode_native_continuation(' to=user<|message|>I think family<|eot|>',labels)==INVALID
    assert decode_native_continuation(' to=tool<|message|>family<|eot|>',labels)==INVALID
