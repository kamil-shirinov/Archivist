"""Bounded lifecycle control: only this process's explicitly recorded app IDs."""
from __future__ import annotations
import json
import time
from pathlib import Path

OUT = Path('results/sparkft/training')
OWNER = OUT/'owned_apps.json'


def append_event(event):
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(OWNER.read_text()) if OWNER.exists() else []
    data.append(event)
    OWNER.write_text(json.dumps(data,indent=2)+'\n')


def owned_ids():
    events=json.loads(OWNER.read_text()) if OWNER.exists() else []
    return {e['app_id'] for e in events if e['event']=='started'}


def require_owned(app_id):
    if app_id not in owned_ids():
        raise ValueError('Refusing to stop an app not started by sparkft')


def wait(call, stage):
    started=time.monotonic()
    while True:
        try:
            return call.get(timeout=30)
        except TimeoutError:
            print(stage + ': waiting for owned Modal call',flush=True)
            if time.monotonic()-started > 12600:
                call.cancel(terminate_containers=True)
                raise TimeoutError('Owned call exceeded outer wall-clock deadline')


def reserve_cpu(stage):
    from decimal import Decimal
    path=OUT/'budget.json'
    OUT.mkdir(parents=True,exist_ok=True)
    data=json.loads(path.read_text()) if path.exists() else {
        'training_validation_cap_usd':95, 'serving_reserve_usd':20,
        'gpu_reservation_usd':'85.92259680', 'preparation_reserve_usd':'5',
        'retained_training_validation_ceiling_usd':'90.92259680',
        'cpu_attempts':[], 'gpu_attempts':[]}
    amount=Decimal('0.00342030') if stage=='cleanup' else Decimal('0.46290000')
    if sum((Decimal(x['ceiling_usd']) for x in data['cpu_attempts']),Decimal(0))+amount>Decimal('2'):
        raise ValueError('CPU attempts exhausted the declared preparation sub-budget')
    data['cpu_attempts'].append({'stage':stage,'ceiling_usd':str(amount),'retained':True})
    path.write_text(json.dumps(data,indent=2)+'\n')


def reserve_probe():
    path=OUT/'budget.json'
    data=json.loads(path.read_text())
    if data.get('gradient_probe'):
        raise ValueError('Gradient probe already reserved; no automatic retry')
    data['gradient_probe']={'gpu':'B300','execution_timeout_s':300,'startup_timeout_s':60,
                            'ceiling_usd':'0.77247000','retained':True}
    data['retained_training_validation_ceiling_usd']='91.69506680'
    if float(data['retained_training_validation_ceiling_usd'])>95:
        raise ValueError('Probe exceeds training allowance')
    path.write_text(json.dumps(data,indent=2)+'\n')


def cpu(stage, download=False):
    from sparkft.modal_app import app, prepare, cleanup_base, tokenize, gradient_probe
    reserve_probe() if stage=='gradient' else reserve_cpu(stage)
    OUT.mkdir(parents=True,exist_ok=True)
    with app.run(name='archivist-sparkft-p34-'+stage):
        append_event({'event':'started','app_id':app.app_id,'stage':stage})
        try:
            if stage=='gradient':
                config=json.loads(Path('results/scratch/sparkft/runtime_preflight/unsloth_nvfp4_config.json').read_text())
                call=gradient_probe.spawn(config)
            elif stage=='tokenize':
                from sparkft.backend import frozen_payload
                payload,images,_=frozen_payload()
                call=tokenize.spawn(payload,tuple(images))
            else:
                function=cleanup_base if stage=='cleanup' else prepare
                call=function.spawn() if stage=='cleanup' else function.spawn(download)
            result=wait(call,stage)
            (OUT/(stage+'.json')).write_text(json.dumps(result,indent=2)+'\n')
            return result
        except Exception as error:
            (OUT/(stage+'_failure.json')).write_text(json.dumps(
                {'type':type(error).__name__,'message':str(error)},indent=2)+'\n')
            raise
        finally:
            require_owned(app.app_id)
            append_event({'event':'run_context_exiting','app_id':app.app_id,'stage':stage})
    # App.run owns and stops only its own ephemeral app.


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['inspect','download','tokenize','gradient','cleanup'])
    args=parser.parse_args()
    cpu(args.stage,download=args.stage=='download')
