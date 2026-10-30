"""Development checks only: timed fallback, precision verification, validation and costs."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from archivist.glimmer.data import load_frozen
from archivist.glimmer.metrics import score
from archivist.glimmer.phase2 import parse_phase2
from archivist.glimmer.prepare_phase2 import development_payload
from archivist.models import LLMRequest, load_roles
from archivist.models.glimmer_access import MODEL, REVISION
from archivist.models.glimmer_allocation import NotAllocated
from archivist.models.glimmer_development_backend import DevelopmentBackend, RATES
from archivist.models.registry import register_backend

OUT = Path('results/glimmer/development_checks')
CAP = 24.31
JOB_SECONDS = 900
CHARGED_ALLOWANCE_SECONDS = 1215


def write(name, data):
    (OUT/name).write_text(json.dumps(data, indent=2)+'\n')


def reserve():
    if (OUT/'budget.json').exists():
        raise ValueError('development checks already reserved; no unrecorded retry')
    old = sum(r['maximum_usd'] for r in json.loads(Path('results/glimmer/cost.json').read_text())) + 2.5
    for path in (Path('results/glimmer/phase2_preparation/cost.json'),
                 Path('results/glimmer/phase2_preparation/cost_attempt1.json')):
        old += json.loads(path.read_text())['maximum_usd']
    maxima = {gpu: CHARGED_ALLOWANCE_SECONDS*rate for gpu,rate in RATES.items()}
    total = old + sum(maxima.values())
    if total >= CAP:
        raise ValueError('development reservations exceed the retained ceiling')
    record = {'cap_usd': CAP, 'historical_retained_usd': old, 'new_gpu_maxima_usd': maxima,
              'retained_after_checks_usd': total, 'remaining_for_future_run_usd': CAP-total,
              'execution_seconds': JOB_SECONDS, 'allocation_wait_seconds': 900,
              'startup_seconds': 300, 'shutdown_transport_seconds': 15,
              'future_5_08_placeholder_superseded': True}
    write('budget.json', record)
    return record


def events_for(gpu):
    def record(item):
        path = OUT/f'{gpu}_events.json'
        events = json.loads(path.read_text()) if path.exists() else []
        events.append(item)
        write(path.name, events)
        if item['event'] in ('submitted','allocation_status','cancelled_unallocated','completed'):
            print(gpu, json.dumps(item), flush=True)
    return record


def run():
    from archivist.models import glimmer_development_modal as remote
    OUT.mkdir(parents=True, exist_ok=True)
    rows, families, payload = development_payload()
    budget = reserve()
    print('Reserved:',json.dumps(budget),flush=True)
    payload['expected_adapter_sha256'] = hashlib.sha256(Path('results/glimmer/adapter/adapter_model.safetensors').read_bytes()).hexdigest()
    files = [Path(__file__),Path('src/archivist/models/glimmer_batch.py'),
             Path('src/archivist/models/glimmer_development_backend.py'),
             Path('src/archivist/models/glimmer_allocation.py'),
             Path('src/archivist/models/glimmer_development_modal.py')]
    code_id = hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()
    state = {'gpu':'L4'}
    register_backend('modal_glimmer_development','llm',lambda model_id,**settings:
        DevelopmentBackend(model_id, remote=remote.primary if state['gpu']=='L4' else remote.fallback,
             gpu=state['gpu'],event=events_for(state['gpu']),code_id=code_id,**settings),priced=True)
    os.environ['BUDGET_CAP_USD'] = str(CAP)
    result = None
    with remote.modal.enable_output(), remote.app.run():
        for gpu in ('L4','L40S'):
            state['gpu'] = gpu
            model_id = f'{MODEL}@{REVISION}/development-check/{gpu}/{code_id}'
            config = OUT/f'{gpu}_roles.toml'
            config.write_text(f'''[roles.check]
kind = "llm"
backend = "modal_glimmer_development"
model_id = "{model_id}"
[prices."{model_id}"]
input_per_mtok = 0.0
output_per_mtok = 0.0
''')
            roles=load_roles(config, cache_dir=Path('cache/glimmer-development-checks'),
                             ledger_path=OUT/'spend_ledger.jsonl')
            try:
                response=roles['check'].complete(LLMRequest(role='glimmer_development_check',
                       prompt=json.dumps(payload),max_output_tokens=512))
                result=json.loads(response.text)
                write('benchmark_raw.json',result)
                break
            except NotAllocated as error:
                write(f'{gpu}_allocation_failure.json',{'gpu':gpu,'error':str(error),
                    'maximum_retained_usd':budget['new_gpu_maxima_usd'][gpu]})
                if gpu == 'L40S':
                    raise
                print('L4 unavailable for 15 minutes; confirmed cancellation permits L40S fallback.',flush=True)
    if result is None:
        raise RuntimeError('no development result')
    labels = [f['family'] for f in families]+['other']
    expected={r['page']:r['target'] for r in rows}
    for arm,record in result['arm_results'].items():
        if [a['index'] for a in record['outputs']] != list(range(40)):
            raise ValueError('development input/output order mismatch')
        predicted={row['page']:parse_phase2(answer['text'],labels,at_token_limit=answer['at_token_limit'])
                   for row,answer in zip(rows,record['outputs'],strict=True)}
        record['metrics']=score(expected,predicted,labels)
    result.update(pages=40,input_page_ids=[r['page'] for r in rows],ocr_prefix_chars=1024,
                  status='development_check_not_phase1_replacement_or_heldout_result')
    rate=result['rate_per_second_usd']
    # Reserve a future maximum only within the user's retained ceiling. No future job starts.
    future_limit=math.floor(budget['remaining_for_future_run_usd']/rate)-315
    result['prospective_function_limit_seconds']=max(0,min(14400,future_limit))
    result['startup_allowance_seconds']=300
    result['idle_allowance_seconds']=15
    write('benchmark.json',result)
    print('Development check complete:',{a:r['metrics']['accuracy'] for a,r in result['arm_results'].items()},flush=True)


if __name__=='__main__':
    run()
