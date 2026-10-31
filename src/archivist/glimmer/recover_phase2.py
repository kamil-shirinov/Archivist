"""Prepared recovery; new GPU submission remains gated on the owner's retained-cap approval."""
from __future__ import annotations

import argparse
import json
import math
import os
from decimal import Decimal
from datetime import UTC,datetime
from pathlib import Path

from archivist.glimmer.data import SYSTEM,prompt
from archivist.glimmer.heldout_frame import digest
from archivist.glimmer.run_phase2 import OUT,verify_freeze,write_once
from archivist.models import LLMRequest,load_roles
from archivist.models.registry import register_backend

RETAINED_BEFORE_RECOVERY=Decimal('24.3099506')
RECOVERY_MAXIMUM=Decimal('3.8482016')
RECOVERY_FILES=[Path('src/archivist/glimmer/recover_phase2.py')]+[
    Path('src/archivist/models')/name for name in ('glimmer_checkpoints.py',
    'glimmer_phase2_recovery_runtime.py','glimmer_phase2_recovery_modal.py',
    'glimmer_phase2_recovery_backend.py')]


def require_recovery_budget(approved_cap):
    if not math.isfinite(approved_cap): raise ValueError('finite approved cap required')
    combined=RETAINED_BEFORE_RECOVERY+RECOVERY_MAXIMUM
    if Decimal(str(approved_cap))<combined:
        raise ValueError(f'new recovery requires retained bound at least ${combined}; current approval is insufficient')
    return {'prior_retained_usd':float(RETAINED_BEFORE_RECOVERY),'maximum_usd':float(RECOVERY_MAXIMUM),
            'combined_retained_usd':float(combined),'approved_retained_cap_usd':approved_cap,
            'execution_timeout_seconds':10825,'startup_timeout_seconds':300,
            'shutdown_allowance_seconds':15,'gpu':'L4','cpu_cores':4,'host_memory_gib':32}


def prepare():
    frozen=verify_freeze()
    files={str(path):digest(path.read_bytes()) for path in RECOVERY_FILES}
    write_once('recovery_freeze.json',{'original_freeze_sha256':digest((OUT/'freeze.json').read_bytes()),
        'sample_sha256':frozen['sample_sha256'],'input_sha256':digest((OUT/'inputs.jsonl').read_bytes()),
        'code':files,'code_id':digest(json.dumps(files,sort_keys=True).encode()),
        'generation_change':False,'original_batch_membership_preserved':True,
        'checkpoint_scope':'one atomic full original batch; no outputs parsed or scored',
        'client_lifetime':'detached app; existing call may be collected without another GPU',
        'status':'prepared_only_pending_retained_budget_approval'})


def run(stage,approved_cap):
    # Budget is checked BEFORE importing the Modal app, reserving or creating any call.
    budget=require_recovery_budget(approved_cap)
    frozen=verify_freeze()
    recovery=json.loads((OUT/'recovery_freeze.json').read_text())
    for name,checksum in recovery['code'].items():
        if digest(Path(name).read_bytes())!=checksum: raise ValueError('prepared recovery code changed')
    inputs=(OUT/'inputs.jsonl').read_bytes()
    if digest(inputs)!=recovery['input_sha256']: raise ValueError('frozen input changed')
    rows=[json.loads(line) for line in inputs.decode().splitlines()]
    sample=json.loads((OUT/'sample.json').read_text())
    if [r['page'] for r in rows]!=[r['page'] for r in sample['pages']]:
        raise ValueError('input order differs from the original frozen sample')
    families=json.loads(Path('results/glimmer/families.json').read_text())
    from archivist.models.glimmer_phase2_recovery_backend import RecoveryBackend
    remote=None
    receipt=None
    if stage=='submit':
        if (OUT/'recovery_reservation.json').exists(): raise ValueError('recovery already submitted; collect its existing call')
        write_once('recovery_reservation.json',{**budget,'reserved_at':datetime.now(UTC).isoformat()})
        from archivist.models import glimmer_phase2_recovery_modal as remote
    else:
        receipt=json.loads((OUT/'recovery_receipt.json').read_text())
    def event(record):
        with (OUT/'recovery_events.jsonl').open('a') as f: f.write(json.dumps(record)+'\n')
        if record['event']=='submitted': write_once('recovery_receipt.json',{**record,'app_id':remote.app.app_id})
        print(json.dumps(record),flush=True)
    model_id=f"{frozen['model']}@{frozen['revision']}/phase2-recovery/{recovery['code_id']}"
    register_backend('modal_glimmer_phase2_recovery','llm',lambda model_id,**options:
        RecoveryBackend(model_id,code_id=recovery['code_id'],event=event,
            remote=remote.infer if remote else None,
            existing_call_id=receipt['call_id'] if receipt else None,**options),priced=True)
    roles=OUT/'recovery_roles.toml'
    if not roles.exists():
        roles.write_text(f'''[roles.sort]
kind = "llm"
backend = "modal_glimmer_phase2_recovery"
model_id = "{model_id}"
[prices."{model_id}"]
input_per_mtok = 0.0
output_per_mtok = 0.0
''')
    os.environ['BUDGET_CAP_USD']=str(RECOVERY_MAXIMUM)
    role=load_roles(roles,cache_dir=Path('cache/glimmer-phase2-recovery'),
                    ledger_path=OUT/'recovery_spend_ledger.jsonl')['sort']
    payload={'owner_authorised_recovery':True,'sample_sha256':frozen['sample_sha256'],
        'input_sha256':digest(inputs),'adapter_sha256':frozen['artifacts']['results/glimmer/adapter/adapter_model.safetensors'],
        'dataset_id':digest(Path('results/glimmer/data_manifest.json').read_bytes()),
        'recovery_code_id':recovery['code_id'],
        'items':[{'system':SYSTEM,'prompt':prompt(row['ocr'],families)} for row in rows]}
    request=LLMRequest(role='glimmer_phase2_recovery',prompt=json.dumps(payload),max_output_tokens=512)
    if remote:
        with remote.modal.enable_output(),remote.app.run(detach=True):
            write_once('recovery_own_app.json',{'app_id':remote.app.app_id})
            response=role.complete(request)
    else:
        response=role.complete(request)
    raw=OUT/'raw_response.json'
    if raw.exists():
        if raw.read_text()!=response.text+'\n': raise ValueError('refusing to replace saved raw outputs')
    else:
        with raw.open('x') as f:f.write(response.text+'\n')
    print('Raw outputs saved. Check, commit and push before any comparison.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','submit','collect'])
    parser.add_argument('--approved-retained-cap-usd',type=float,default=24.31)
    args=parser.parse_args()
    if args.stage=='prepare': prepare()
    else: run(args.stage,args.approved_retained_cap_usd)


if __name__=='__main__':main()
