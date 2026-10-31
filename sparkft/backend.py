"""Modal experiment backend, built by the standard registry/cache/budget layer."""
from __future__ import annotations
import json
import time
from pathlib import Path
from archivist.models.base import LLMResponse,Usage
from sparkft.cloud import OUT,append_event,require_owned,submitted_epoch,wait

RATE=.01655392


class SparkftBackend:
    name='modal_sparkft'

    def __init__(self,model_id,*,remote,settings_id):
        self.model_id=model_id
        self.remote=remote
        self.settings={'protocol':'sparkft-coverage-v2-bf16','code_id':settings_id}

    def complete(self,request):
        import hashlib
        import modal
        from sparkft.modal_app import app
        payload=json.loads(request.prompt)
        identity=hashlib.sha256(request.prompt.encode()).hexdigest()
        submission=OUT/'experiment_call.json'
        budget_path=OUT/'budget.json'
        budget=json.loads(budget_path.read_text())
        if submission.exists():
            saved=json.loads(submission.read_text())
            require_owned(saved['app_id'])
            if saved['request_sha256']!=identity:raise ValueError('Frozen remote request changed')
            call_id=saved['call_id']
            call=modal.FunctionCall.from_id(call_id)
            result=wait(call,'reconnected experiment',app_id=saved['app_id'],wall_seconds=4950,call_id=call_id)
        else:
            if budget['gpu_attempts']:
                raise ValueError('GPU attempt already reserved; no automatic retry')
            if float(budget['retained_training_validation_ceiling_usd'])>95:
                raise ValueError('Experiment exceeds training/validation allowance')
            budget['gpu_attempts'].append({'ceiling_usd':budget['gpu_reservation_usd'],
                                           'retained':True,'status':'reserved_before_launch'})
            budget_path.write_text(json.dumps(budget,indent=2)+'\n')
            # Detached app outlives this client. Never cancel it on client exit.
            with app.run(name='archivist-sparkft-p34-train-validate',detach=True):
                append_event({'event':'started','app_id':app.app_id,'stage':'experiment'})
                payload['budget_deadline_epoch']=time.time()+4920
                call=self.remote.spawn(payload,request.images)
                call_id=call.object_id
                submission.write_text(json.dumps({'app_id':app.app_id,'call_id':call.object_id,
                    'request_sha256':identity,'detached':True,'dataset_sha256':payload['dataset_sha256'],
                    'checkpoint_path':'/sparkft-store/experiment-v1/latest.json'},indent=2)+'\n')
                print('Detached submission saved:',call.object_id,flush=True)
                result=wait(call,'experiment',app_id=app.app_id,wall_seconds=4950)
        budget['gpu_attempts'][-1]['status']='completed'
        wall=time.time()-submitted_epoch(call_id)
        cost=(wall+15)*RATE
        result['dispatch_wall_seconds']=wall
        result['cost_basis']='Upper bound from submission to result plus shutdown; includes restarts'
        result['cost_upper_bound_usd']=cost
        budget['gpu_attempts'][-1]['reported_runtime_estimate_usd']=cost
        budget_path.write_text(json.dumps(budget,indent=2)+'\n')
        (OUT/'raw_result.json').write_text(json.dumps(result,indent=2)+'\n')
        return LLMResponse(json.dumps(result),Usage(0,0,cost),self.name,self.model_id)


def frozen_payload():
    import hashlib
    from archivist.templates.pages import resolve
    from sparkft.boxes import gate
    dataset_path=OUT/'validation_v2/dataset.json'
    raw=dataset_path.read_bytes()
    expected=json.loads((OUT/'validation_v2/dataset_hash.json').read_text())['sha256']
    if hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('Frozen dataset changed')
    payload=json.loads(raw)
    payload['dataset_sha256']=expected
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


def code_digest():
    import hashlib
    paths=['backend.py','runtime.py','modal_app.py','scoring.py','cloud.py']
    return hashlib.sha256(b''.join((Path('sparkft')/p).read_bytes() for p in paths)).hexdigest()


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
    import tomllib
    configured=tomllib.loads((OUT/'roles.toml').read_text())['roles']['experiment']['settings']['settings_id']
    if configured!=code_digest():raise ValueError('Executable code changed after protocol freeze')
    payload['code_sha256']=configured

    # Only the explicit prompt/system/image are passed to the processor; validation
    # targets stay dispatcher-side and are never included in an inference prompt.
    BACKEND_CAPS['modal_sparkft']=('SPARKFT_MODAL_CAP_USD',95)
    register_backend('modal_sparkft','llm',lambda model_id,settings_id:
                     SparkftBackend(model_id,remote=experiment,settings_id=settings_id))
    roles=load_roles(OUT/'roles.toml',cache_dir=Path('cache/sparkft-training'))
    result=json.loads(roles['experiment'].complete(LLMRequest(
        role='experiment',prompt=json.dumps(payload,sort_keys=True),images=tuple(images),
        max_output_tokens=1)).text)
    references=payload['validation']
    base=score(result['base'],references);trained=score(result['trained'],references)
    (OUT/'comparison.json').write_text(json.dumps(
        {'base':base,'trained':trained,'adopt':adoption(base,trained,payload['required_families']),
         'dataset_sha256':expected,'model':MODEL,'revision':REVISION},indent=2)+'\n')
    print('Adopt adapter:',adoption(base,trained,payload['required_families']),'base',base['value_accuracy'],base['box_containment'],
          'trained',trained['value_accuracy'],trained['box_containment'],flush=True)


if __name__=='__main__':
    run()
