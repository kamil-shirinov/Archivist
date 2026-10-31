"""Modal experiment backend, built by the standard registry/cache/budget layer."""
from __future__ import annotations
import json
from pathlib import Path
from archivist.models.base import LLMResponse,Usage
from sparkft.cloud import OUT,append_event,require_owned,wait

RATE=.00866592


class SparkftBackend:
    name='modal_sparkft'

    def __init__(self,model_id,*,remote,settings_id):
        self.model_id=model_id
        self.remote=remote
        self.settings={'protocol':'sparkft-v1','code_id':settings_id}

    def complete(self,request):
        from sparkft.modal_app import app
        payload=json.loads(request.prompt)
        budget_path=OUT/'budget.json'
        budget=json.loads(budget_path.read_text())
        if budget['gpu_attempts']:
            raise ValueError('GPU attempt already reserved; no automatic retry')
        if float(budget['retained_training_validation_ceiling_usd'])>95:
            raise ValueError('Experiment exceeds training/validation allowance')
        budget['gpu_attempts'].append({'ceiling_usd':budget['gpu_reservation_usd'],
                                       'retained':True,'status':'reserved_before_launch'})
        budget_path.write_text(json.dumps(budget,indent=2)+'\n')
        with app.run(name='archivist-sparkft-p34-train-validate'):
            append_event({'event':'started','app_id':app.app_id,'stage':'experiment'})
            try:
                call=self.remote.spawn(payload,request.images)
                result=wait(call,'experiment')
                budget['gpu_attempts'][-1]['status']='completed'
                budget['gpu_attempts'][-1]['reported_runtime_estimate_usd']=result['runtime_seconds']*RATE
                (OUT/'raw_result.json').write_text(json.dumps(result,indent=2)+'\n')
                cost=result['runtime_seconds']*RATE
                return LLMResponse(json.dumps(result),Usage(0,0,cost),self.name,self.model_id)
            except Exception as error:
                budget['gpu_attempts'][-1]['status']='failed_or_cancelled'
                (OUT/'gpu_failure.json').write_text(json.dumps(
                    {'type':type(error).__name__,'message':str(error)},indent=2)+'\n')
                raise
            finally:
                budget_path.write_text(json.dumps(budget,indent=2)+'\n')
                require_owned(app.app_id)
                append_event({'event':'run_context_exiting','app_id':app.app_id,'stage':'experiment'})


def frozen_payload():
    import hashlib
    from archivist.templates.pages import resolve
    from sparkft.boxes import gate
    dataset_path=OUT/'dataset.json'
    raw=dataset_path.read_bytes()
    expected=json.loads((OUT/'dataset_hash.json').read_text())['sha256']
    if hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('Frozen dataset changed')
    payload=json.loads(raw)
    split=json.loads(Path('data/real/split.json').read_text())
    refs=sorted(payload['pages'])
    images=[]
    for ref in refs:
        gate(ref,split)
        image=resolve(ref).path.read_bytes()
        if hashlib.sha256(image).hexdigest()!=payload['pages'][ref]['sha256']:
            raise ValueError('A frozen page image changed')
        images.append(image)
    for item in payload['train']+payload['validation']:
        item['image_index']=refs.index(item['page'])
    return payload, images, expected


def run():
    import hashlib
    from archivist.models import LLMRequest,load_roles
    from archivist.models.registry import register_backend
    from archivist.models.budget import BACKEND_CAPS
    from archivist.templates.pages import resolve
    from sparkft.boxes import gate
    from sparkft.modal_app import MODEL,REVISION,experiment
    from sparkft.scoring import adoption,score
    payload,images,expected=frozen_payload()
    # Only the explicit prompt/system/image are passed to the processor; validation
    # targets stay dispatcher-side and are never included in an inference prompt.
    BACKEND_CAPS['modal_sparkft']=('SPARKFT_MODAL_CAP_USD',90)
    register_backend('modal_sparkft','llm',lambda model_id,settings_id:
                     SparkftBackend(model_id,remote=experiment,settings_id=settings_id))
    roles=load_roles(OUT/'roles.toml',cache_dir=Path('cache/sparkft-training'))
    result=json.loads(roles['experiment'].complete(LLMRequest(
        role='experiment',prompt=json.dumps(payload,sort_keys=True),images=tuple(images),
        max_output_tokens=1)).text)
    references=[]
    for ref in payload['validation']:
        source=json.loads((OUT/(ref['page']+'_reference.json')).read_text())
        by={r['field_id']:r['ocr_box'] for r in source['reference']}
        references.append({**ref,'ocr_boxes':[by[f] for f in ref['fields']]})
    base=score(result['base'],references);trained=score(result['trained'],references)
    (OUT/'comparison.json').write_text(json.dumps(
        {'base':base,'trained':trained,'adopt':adoption(base,trained),
         'dataset_sha256':expected,'model':MODEL,'revision':REVISION},indent=2)+'\n')
    print('Adopt adapter:',adoption(base,trained),'base',base['value_accuracy'],base['box_containment'],
          'trained',trained['value_accuracy'],trained['box_containment'],flush=True)


if __name__=='__main__':
    run()
