"""Bounded lifecycle control: only this process's explicitly recorded app IDs."""
from __future__ import annotations
import json
import time
from pathlib import Path

OUT = Path('results/sparkft/training')
OWNER = OUT/'owned_apps.json'


def append_event(event):
    import fcntl
    OUT.mkdir(parents=True, exist_ok=True)
    lock=Path('results/scratch/sparkft/owned-apps.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        data=json.loads(OWNER.read_text()) if OWNER.exists() else []
        data.append(event)
        pending=OWNER.with_suffix('.pending.json')
        pending.write_text(json.dumps(data,indent=2)+'\n')
        pending.replace(OWNER)


def owned_ids():
    events=json.loads(OWNER.read_text()) if OWNER.exists() else []
    return {e['app_id'] for e in events if e['event']=='started'}


def require_owned(app_id):
    if app_id not in owned_ids():
        raise ValueError('Refusing to stop an app not started by sparkft')


def stop_owned(app_id):
    import subprocess
    import sys
    require_owned(app_id)
    subprocess.run([sys.executable,'-m','modal','app','stop','--yes',app_id],check=True)
    append_event({'event':'stopped','app_id':app_id})


class WallBudgetTimeout(RuntimeError):
    """A remote call's original budget window expired, including infrastructure restarts."""


def submitted_epoch(call_id):
    # Modal 1.6.3 call IDs contain a ULID, whose first 48 bits are UTC milliseconds.
    body=call_id.removeprefix('fc-')
    if len(body)!=26:raise ValueError('Unknown call ID format; cannot establish budget deadline')
    value=0
    for char in body:value=(value<<5)+'0123456789ABCDEFGHJKMNPQRSTVWXYZ'.index(char)
    return (value>>80)/1000


def cpu_wall_seconds(stage):
    if stage in ('download_bf16_resume','download_bf16_resume2'):return 3660
    if stage in ('cleanup','kernel_transport','cache_integrity'):return 180
    if stage=='gradient':return 660
    if stage=='tokenize':return 960
    return 1860


def wait(call,stage,*,app_id,wall_seconds,call_id=None):
    require_owned(app_id)
    try:
        deadline=submitted_epoch(call_id or call.object_id)+wall_seconds-15
    except ValueError:
        stop_owned(app_id)
        raise
    while True:
        # Nonblocking retrieval permits collection after a finished app's deadline.
        try:return call.get(timeout=0)
        except TimeoutError:pass
        remaining=deadline-time.time()
        if remaining<=0:
            try:call.cancel(terminate_containers=True)
            finally:stop_owned(app_id)
            raise WallBudgetTimeout('Original budget window expired: '+stage)
        try:
            return call.get(timeout=min(15,remaining))
        except TimeoutError:
            print(stage+': waiting within original budget window',flush=True)


def reserve_cpu(stage):
    from decimal import Decimal
    path=OUT/'budget.json'
    OUT.mkdir(parents=True,exist_ok=True)
    data=json.loads(path.read_text()) if path.exists() else {
        'training_validation_cap_usd':95, 'serving_reserve_usd':20,
        'gpu_reservation_usd':'82.19021280', 'preparation_reserve_usd':'6',
        'retained_training_validation_ceiling_usd':'94.21547880',
        'cpu_attempts':[], 'gpu_attempts':[]}
    if stage.startswith('download_bf16_resume') and any(x['stage']==stage for x in data['cpu_attempts']):
        raise ValueError('Only one attempt for each declared BF16 continuation is permitted')
    amount=(Decimal('0.68046300') if stage=='download_bf16_resume2' else
            Decimal('0.90728400') if stage=='download_bf16_resume' else
            Decimal('0.00342030') if stage in ('cleanup','kernel_transport') else Decimal('0.46290000'))
    if sum((Decimal(x['ceiling_usd']) for x in data['cpu_attempts']),Decimal(0))+amount>Decimal('4.5'):
        raise ValueError('CPU attempts exhausted the declared preparation sub-budget')
    data['cpu_attempts'].append({'stage':stage,'ceiling_usd':str(amount),'retained':True})
    path.write_text(json.dumps(data,indent=2)+'\n')


def reserve_probe():
    path=OUT/'budget.json'
    data=json.loads(path.read_text())
    if 'gradient_probe' in data:
        data['gradient_probe_attempts']=[data.pop('gradient_probe')]
    attempts=data.setdefault('gradient_probe_attempts',[])
    if len(attempts)>=7:
        raise ValueError('Only seven explicitly declared gradient attempts are allowed')
    attempts.append({'gpu':'B300','execution_timeout_s':600,'startup_timeout_s':60,
                     'ceiling_usd':'1.39044600','retained':True})
    from decimal import Decimal
    data['retained_training_validation_ceiling_usd']=str(Decimal('85.72304480') + sum((Decimal(x['ceiling_usd']) for x in attempts),Decimal(0)))
    if float(data['retained_training_validation_ceiling_usd'])>95:
        raise ValueError('Probe exceeds training allowance')
    path.write_text(json.dumps(data,indent=2)+'\n')


def cpu(stage, download=False):
    from sparkft.modal_app import app, prepare, cleanup_base, tokenize, gradient_probe, kernel_transport, prepare_resume, prepare_final
    reserve_probe() if stage=='gradient' else reserve_cpu(stage)
    OUT.mkdir(parents=True,exist_ok=True)
    with app.run(name='archivist-sparkft-p34-'+stage,detach=True):
        append_event({'event':'started','app_id':app.app_id,'stage':stage})
        try:
            if stage=='kernel_transport':
                call=kernel_transport.spawn()
            elif stage=='gradient':
                config=json.loads(Path('results/scratch/sparkft/runtime_preflight/unsloth_nvfp4_config.json').read_text())
                call=gradient_probe.spawn(config)
            elif stage=='tokenize':
                from sparkft.backend import frozen_payload
                payload,images,_=frozen_payload()
                call=tokenize.spawn(payload,tuple(images))
            else:
                function=(cleanup_base if stage=='cleanup' else
                          prepare_resume if stage=='download_bf16_resume' else
                          prepare_final if stage=='download_bf16_resume2' else prepare)
                call=function.spawn() if stage in ('cleanup','download_bf16_resume','download_bf16_resume2') else function.spawn(download)
            (OUT/(stage+'_call.json')).write_text(json.dumps(
                {'app_id':app.app_id,'call_id':call.object_id,'stage':stage},indent=2)+'\n')
            result=wait(call,stage,app_id=app.app_id,wall_seconds=cpu_wall_seconds(stage))
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
    parser.add_argument('stage',choices=['inspect','download','download_resume','download_bf16','download_bf16_resume','download_bf16_resume2','kernel_transport','tokenize','gradient','cleanup'])
    args=parser.parse_args()
    cpu(args.stage,download=args.stage.startswith('download'))
