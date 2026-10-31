"""Scientific protocol and task-ownership checks; no cloud/network access."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sparkft import cloud
from sparkft.dataset import bundle,reference_rows
from sparkft.runtime import inputs
from sparkft.scoring import adoption,parse,score
from archivist.schema import BBox


def test_only_recorded_task_apps_can_be_stopped(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud,'OUT',tmp_path)
    monkeypatch.setattr(cloud,'OWNER',tmp_path/'owned.json')
    cloud.append_event({'event':'started','app_id':'ap-sparkft-one'})
    cloud.require_owned('ap-sparkft-one')
    with pytest.raises(ValueError,match='not started'):
        cloud.require_owned('ap-glimmer-concurrent')


def test_cpu_reservations_survive_failure_and_cannot_use_serving_money(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud,'OUT',tmp_path)
    cloud.reserve_cpu('failed-inspect')
    cloud.reserve_cpu('download')
    budget=json.loads((tmp_path/'budget.json').read_text())
    assert budget['serving_reserve_usd']==20
    assert budget['cpu_attempts'][0]['retained']
    for _ in range(2):cloud.reserve_cpu('inspect')
    with pytest.raises(ValueError,match='sub-budget'):
        cloud.reserve_cpu('inspect')


def test_native_final_channel_and_truncation_are_prospective():
    answer='{"c00":{"value":"123","box":[1,2,3,4]}}'
    assert parse(' to=user<|message|>'+answer+'<|eot|>',{'c00'})['c00']['value']=='123'
    assert parse(' to=self<|message|>thinking<|eom|><|start|>assistant to=user<|message|>'+answer,
                 {'c00'})['c00']['value']=='123'
    with pytest.raises(ValueError):parse(' to=self<|message|>123',{'c00'})
    with pytest.raises(ValueError):parse(answer,{'c00'},at_limit=True)
    with pytest.raises(ValueError):parse(answer,{'c00','c01'})
    with pytest.raises(ValueError):parse(answer.replace('[1,2,3,4]','[true,2,3,4]'),{'c00'})


def test_value_box_and_joint_scores_are_distinct_and_both_gains_required():
    ref={'page':'1939-01_p001','fields':['f'],'size':[1000,1000],
         'target':{'c00':{'value':'123'}},'ocr_boxes':[{'x0':10,'y0':10,'x1':20,'y1':20}]}
    def result(value,box):
        return {'text':json.dumps({'c00':{'value':value,'box':box}}),'at_token_limit':False}
    baseline=score([result('124',[10,10,20,20])],[ref])
    fixed_value=score([result('123',[10,10,20,20])],[ref])
    assert baseline['value_accuracy']==0 and baseline['box_containment']==1
    assert fixed_value['joint_accuracy']==1
    assert not adoption(baseline,fixed_value)  # box tie is rejection
    bad=score([result('124',[11,11,19,19])],[ref])
    assert adoption(bad,fixed_value)


def test_validation_reference_selection_ignores_every_teacher_box():
    values=[{'field_id':'T.x:1939-01_p001:01:m','value':'123','abstained':False,
             'citation':{'bbox':{'x0':900,'y0':900,'x1':901,'y1':901}}}]
    word=SimpleNamespace(text='123',box=BBox(x0=10,y0=10,x1=20,y1=20))
    refs=reference_rows(values,[word],frozenset({'m'}))
    assert refs[0]['ocr_box']==word.box.model_dump()
    assert reference_rows(values,[word,word],frozenset({'m'}))==[]


def test_inference_processor_never_receives_validation_answers():
    buffer=io.BytesIO();Image.new('RGB',(8,8),'white').save(buffer,format='PNG')
    class Processor:
        def apply_chat_template(self,turns,**kwargs):
            assert all(t['role']!='assistant' for t in turns)
            assert 'secret_reference_937421' not in str(turns)
            return turns
    item={'system':'Read numbers','prompt':'row 01 column m','target':{'secret_reference_937421':'123'}}
    inputs(Processor(),item,buffer.getvalue(),answer=False)
