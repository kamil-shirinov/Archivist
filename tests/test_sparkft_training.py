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
    for _ in range(7):cloud.reserve_cpu('inspect')
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


def test_pooled_gain_cannot_hide_a_family_or_layout_regression():
    def metrics(value,boxes):
        return {'pages':3,'n':30,'value_accuracy':value,'box_containment':boxes}
    base={'n':90,'value_accuracy':.5,'box_containment':.5,
          'per_family':{'a':metrics(.9,.5),'b':metrics(.3,.5),'c':metrics(.3,.5)},
          'per_layout':{'a1':metrics(.9,.5),'b1':metrics(.3,.5),'c1':metrics(.3,.5)}}
    tuned=json.loads(json.dumps(base));tuned.update(value_accuracy=.6,box_containment=.6)
    assert adoption(base,tuned,['a','b','c'])
    tuned['per_family']['a']['value_accuracy']=.8
    assert not adoption(base,tuned,['a','b','c'])
    tuned['per_family']['a']['value_accuracy']=.9
    tuned['per_layout']['a1']['box_containment']=.4
    assert not adoption(base,tuned,['a','b','c'])
    tuned['per_layout']['a1']['box_containment']=.5
    assert not adoption(base,tuned,['a','b','c','missing'])
    tuned['per_layout']['c1']['pages']=2
    assert not adoption(base,tuned,['a','b','c'])


def test_fixed_coverage_draw_has_no_training_overlap_or_missing_approved_family():
    root=Path(__file__).resolve().parents[1]/'results/sparkft/training/validation_v2'
    data=json.loads((root/'dataset.json').read_text())
    draw=json.loads((root/'draw.json').read_text())
    train={row['page'] for row in data['train']}
    val={row['page'] for row in data['validation']}
    assert not train & val
    assert len(val)==15
    assert train==set(draw['training_pages'])
    assert '1982-06_p094' not in train
    assert {r['family'] for r in data['validation']}==set(data['required_families'])
    for layout in {r['layout'] for r in data['validation']}:
        assert sum(r['layout']==layout and bool(r['fields']) for r in data['validation'])>=3


def test_detached_handoff_refuses_incomplete_or_different_weights():
    from sparkft.launch_when_ready import verify_preparation
    from sparkft.runtime import MODEL,REVISION
    verify_preparation({'model':MODEL,'revision':REVISION,'weight_shards':65})
    with pytest.raises(ValueError):
        verify_preparation({'model':MODEL,'revision':REVISION,'weight_shards':64})
    with pytest.raises(ValueError):
        verify_preparation({'model':MODEL,'revision':'different','weight_shards':65})


def test_bf16_continuation_is_reserved_once_inside_existing_subcap(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud,'OUT',tmp_path)
    cloud.reserve_cpu('download_bf16_resume')
    data=json.loads((tmp_path/'budget.json').read_text())
    assert data['cpu_attempts'][0]['ceiling_usd']=='0.90728400'
    with pytest.raises(ValueError,match='Only one'):
        cloud.reserve_cpu('download_bf16_resume')


def test_stop_helper_never_invokes_cli_for_an_unowned_app(tmp_path,monkeypatch):
    import subprocess
    monkeypatch.setattr(cloud,'OWNER',tmp_path/'owned.json')
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:pytest.fail('Stop must not run'))
    with pytest.raises(ValueError,match='not started'):
        cloud.stop_owned('ap-glimmer-concurrent')


def test_weight_staging_has_only_two_bounded_continuations():
    from sparkft.launch_when_ready import next_stage
    assert next_stage(0)==1 and next_stage(1)==2
    with pytest.raises(ValueError,match='No further'):
        next_stage(2)
