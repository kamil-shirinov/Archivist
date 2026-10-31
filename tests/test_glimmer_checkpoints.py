"""Missing-batch recovery on invented inputs, with no GPU/network/archive access."""
import json

import pytest

from archivist.models.glimmer_checkpoints import batch_plan,run_arm


class Tokenizer:
    def apply_chat_template(self,messages,**settings):
        assert settings=={'tokenize':False,'add_generation_prompt':True,'reasoning_strength':'low'}
        return messages[1]['content']
    def __call__(self,text,**settings):
        assert settings=={'add_special_tokens':False}
        return {'input_ids':list(range(len(text)))}


def items():
    return [{'system':'system','prompt':str(i%10)+'x'*(1+(i*7)%19)} for i in range(19)]


def generator(calls):
    def generate(model,tokenizer,subset):
        calls.append(list(subset))
        return [{'index':i,'input_tokens':len(row['prompt']),'text':'raw '+row['prompt'],
                 'output_tokens':7,'at_token_limit':False,'batch_size':len(subset)}
                for i,row in enumerate(subset)]
    return generate


def test_resume_reuses_complete_batch_and_reruns_only_missing_original_groups(tmp_path):
    data=items()
    tokenizer=Tokenizer()
    calls=[]
    committed=[]
    def fail_after_first_checkpoint():
        committed.append(True)
        raise RuntimeError('simulated client interruption')
    with pytest.raises(RuntimeError,match='interruption'):
        run_arm(data,tokenizer,None,tmp_path,{'sample':'frozen'},
                generate=generator(calls),persist=fail_after_first_checkpoint)
    assert len(calls)==len(list(tmp_path.glob('batch_*.json')))==1
    resumed_calls=[]
    outputs,counts=run_arm(data,tokenizer,None,tmp_path,{'sample':'frozen'},
        generate=generator(resumed_calls))
    assert counts=={'reused_batches':1,'new_batches':2,'complete_batches':3}
    assert len(resumed_calls)==2
    assert outputs==[{'index':i,'input_tokens':len(row['prompt']),'text':'raw '+row['prompt'],
                     'output_tokens':7,'at_token_limit':False,'batch_size':8 if i in sum(batch_plan(data,tokenizer)[0][:2],[]) else 3}
                    for i,row in enumerate(data)]
    groups,_=batch_plan(data,tokenizer)
    original_order=sorted(range(len(data)),key=lambda i:(len(data[i]['prompt']),i))
    assert groups==[original_order[:8],original_order[8:16],original_order[16:]]
    for group,submitted in zip(groups[1:],resumed_calls,strict=True):
        assert submitted==[data[i] for i in sorted(group)]
        # The generator's original length/tie sort gives the identical tensor order.
        relative=sorted(range(len(submitted)),key=lambda i:(len(submitted[i]['prompt']),i))
        assert [sorted(group)[i] for i in relative]==group
    final_calls=[]
    again,reused=run_arm(data,tokenizer,None,tmp_path,{'sample':'frozen'},generate=generator(final_calls))
    assert not final_calls and again==outputs and reused['reused_batches']==3


@pytest.mark.parametrize('damage',['bytes','identity','partial'])
def test_bad_saved_checkpoint_aborts_before_any_new_generation(tmp_path,damage):
    data=items()
    run_arm(data,Tokenizer(),None,tmp_path,{'sample':'frozen'},generate=generator([]))
    first=tmp_path/'batch_000.json'
    if damage=='bytes':
        record=json.loads(first.read_text());record['outputs'][0]['text']='edited';first.write_text(json.dumps(record))
    elif damage=='identity':
        pass  # A different frozen identity is supplied below.
    else:
        record=json.loads(first.read_text());record['outputs'].pop();first.write_text(json.dumps(record))
    calls=[]
    with pytest.raises(ValueError,match='checkpoint'):
        run_arm(data,Tokenizer(),None,tmp_path,{'sample':'different' if damage=='identity' else 'frozen'},
                generate=generator(calls))
    assert not calls


def test_recovery_cannot_allocate_again_under_the_unraised_retained_cap():
    from archivist.glimmer.recover_phase2 import require_recovery_budget
    for cap in (24.31,28.15,float('nan')):
        with pytest.raises(ValueError): require_recovery_budget(cap)
    record=require_recovery_budget(28.16)
    assert record['combined_retained_usd']==pytest.approx(28.1581522)
    assert record['maximum_usd']==pytest.approx(3.8482016)
    assert record['execution_timeout_seconds']==10825
