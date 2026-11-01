"""Explicit phase-2 stages: frame check -> one frozen draw -> OCR -> raw inference.

No comparison or human-label reader is imported or run here. All local outputs stay in
results/glimmer/phase2. The only held-out result paths opened are the three allowlisted
sweep records. Source pages are accessed only through sampled_text after the one draw.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import UTC,datetime
from pathlib import Path

from archivist.glimmer.data import SYSTEM,prompt
from archivist.glimmer.heldout_frame import digest,read_frame
from archivist.glimmer.heldout_ocr import sampled_text
from archivist.glimmer.phase2 import draw_sample,decision_text
from archivist.glimmer.phase2_cost import require_budget_fit
from archivist.ingest.fraser import pdf_name
from archivist.models import LLMRequest,load_roles
from archivist.models.glimmer_access import MODEL,REVISION
from archivist.models.registry import register_backend

OUT=Path('results/glimmer/phase2')
SOURCE=Path('../..')
RETAINED=20.461749
CODE_PATHS=[Path('src/archivist/glimmer')/name for name in
    ('run_phase2.py','heldout_frame.py','heldout_ocr.py','phase2.py','phase2_cost.py','data.py','compare_phase2.py','metrics.py')]
CODE_PATHS += [Path('src/archivist/models')/name for name in
    ('glimmer_phase2_runtime.py','glimmer_phase2_modal.py','glimmer_phase2_backend.py',
     'glimmer_batch.py','glimmer_runtime.py','glimmer_image.py','glimmer_allocation.py')]


def write_once(name,value):
    with (OUT/name).open('x') as f:
        f.write(json.dumps(value,indent=2)+'\n')


def current_code():
    return {str(p):digest(p.read_bytes()) for p in CODE_PATHS}


def frame():
    families=json.loads(Path('results/glimmer/families.json').read_text())
    return read_frame(SOURCE/'results/real_test/held_out',Path('data/real/split.json'),
                      [f['family'] for f in families],go=True)


def verify_frame(record):
    frozen=json.loads((OUT/'frame_check.json').read_text())
    if record != frozen:
        raise ValueError('permitted source frame changed after preflight; no redraw')


def preflight():
    if (OUT/'frame_check.json').exists():
        raise ValueError('frame already checked; inspect retained artifact instead of overwriting')
    _,_,_,record=frame()
    benchmark=json.loads(Path('results/glimmer/development_checks/benchmark.json').read_text())
    estimate=require_budget_fit(benchmark,record['counts']['sample'],RETAINED)
    OUT.mkdir(parents=True,exist_ok=True)
    write_once('frame_check.json',record)
    write_once('cost_estimate.json',estimate)
    print(json.dumps({'frame':record,'estimate':estimate},indent=2),flush=True)


def freeze():
    if (OUT/'sample.json').exists():
        raise ValueError('sample already frozen; no redraw')
    assignments,_,split,record=frame()
    verify_frame(record)
    benchmark=json.loads(Path('results/glimmer/development_checks/benchmark.json').read_text())
    require_budget_fit(benchmark,record['counts']['sample'],RETAINED)
    families=[f['family'] for f in json.loads(Path('results/glimmer/families.json').read_text())]
    sample=draw_sample(assignments,families,
        split['held_out'],go=True)
    if len(sample)!=791:
        raise ValueError('sample count changed from validated 791')
    write_once('sample.json',{'seed':4005,'sample_pages':791,
        'frame_source_sha256':record['source_sha256'],'pages':[asdict(row) for row in sample]})
    inputs=['results/glimmer/adapter/adapter_model.safetensors','results/glimmer/adapter/adapter_config.json',
        'results/glimmer/families.json','results/glimmer/data_manifest.json','config/real_test.toml',
        'data/real/split.json','pyproject.toml','uv.lock']
    write_once('freeze.json',{'created_at':datetime.now(UTC).isoformat(),'model':MODEL,'revision':REVISION,
        'sample_sha256':digest((OUT/'sample.json').read_bytes()),'code':current_code(),
        'artifacts':{s:digest(Path(s).read_bytes()) for s in inputs},
        'settings':{'ocr_chars':1024,'batch_size':8,'max_new_tokens':512,
            'reasoning':'low','greedy':True,'parser':'native-assistant-header-v1',
            'gpu':'L4','execution_timeout':10825,'startup_timeout':300,'retries':0}})
    print('Frozen one 791-page sample and code/base/adapter/settings, before OCR.',flush=True)


def verify_freeze():
    frozen=json.loads((OUT/'freeze.json').read_text())
    if frozen['code'] != current_code():
        raise ValueError('inference/preparation code changed after freeze')
    for s,h in frozen['artifacts'].items():
        if digest(Path(s).read_bytes()) != h:
            raise ValueError('frozen artifact changed: '+s)
    if digest((OUT/'sample.json').read_bytes()) != frozen['sample_sha256']:
        raise ValueError('frozen sample changed')
    return frozen


def prepare_ocr():
    verify_freeze()
    if (OUT/'inputs.jsonl').exists():
        raise ValueError('frozen OCR already prepared')
    _,_,split,record=frame()
    verify_frame(record)
    sample=json.loads((OUT/'sample.json').read_text())['pages']
    allowed={row['page'] for row in sample}
    # Use only issue/page/dimensions of sampled records; never inspect any title_hint.
    manifest=json.loads(Path('data/real/manifest.json').read_text())
    dimensions={f"{r['issue']}_p{r['page']:03d}":(r['width'],r['height'])
        for r in manifest['pages'] if f"{r['issue']}_p{r['page']:03d}" in allowed}
    if set(dimensions)!=allowed:
        raise ValueError('sampled pages missing manifest dimension metadata')
    families=json.loads(Path('results/glimmer/families.json').read_text())
    rows=[]
    for i,row in enumerate(sample):
        ref=row['page']
        issue=ref.rsplit('_p',1)[0]
        text=sampled_text(ref,allowed,set(split['held_out']),SOURCE/'data/real/pdf'/pdf_name(issue),
                          *dimensions[ref])
        excerpt=decision_text(text)
        item={'page':ref,'ocr':excerpt,'original_ocr_chars':len(text),'retained_chars':len(excerpt),
              'full_ocr_sha256':digest(text.encode()),'ocr_sha256':digest(excerpt.encode()),
              'prompt_sha256':digest(prompt(excerpt,families).encode())}
        rows.append(item)
        if (i+1)%50==0: print(f'Sampled OCR prepared: {i+1}/791',flush=True)
    with (OUT/'inputs.jsonl').open('x') as f:
        for row in rows: f.write(json.dumps(row)+'\n')
    write_once('inputs_manifest.json',{'input_sha256':digest((OUT/'inputs.jsonl').read_bytes()),
        'pages':len(rows),'empty_ocr_pages':sum(not r['ocr'] for r in rows),
        'truncated_pages':sum(r['original_ocr_chars']>1024 for r in rows),
        'manifest_sha256':digest(Path('data/real/manifest.json').read_bytes()),
        'source_scope':'sampled PDF text layer only; no image rendered or opened'})
    print('Frozen 791 OCR prefixes; no model called and no reference comparison.',flush=True)


def infer():
    frozen=verify_freeze()
    if (OUT/'reservation.json').exists():
        raise ValueError('GPU already reserved/submitted; no automatic retry')
    if digest((OUT/'inputs.jsonl').read_bytes()) != json.loads((OUT/'inputs_manifest.json').read_text())['input_sha256']:
        raise ValueError('frozen input bytes changed')
    rows=[json.loads(line) for line in (OUT/'inputs.jsonl').read_text().splitlines()]
    sample=json.loads((OUT/'sample.json').read_text())
    if [r['page'] for r in rows] != [r['page'] for r in sample['pages']] or len(rows)!=791:
        raise ValueError('inference input/order differs from frozen sample')
    families=json.loads(Path('results/glimmer/families.json').read_text())
    benchmark=json.loads(Path('results/glimmer/development_checks/benchmark.json').read_text())
    estimate=require_budget_fit(benchmark,791,RETAINED)
    write_once('reservation.json',{'reserved_at':datetime.now(UTC).isoformat(),
        'prior_retained_usd':RETAINED,'maximum_usd':estimate['gpu_job_ceiling_usd'],
        'combined_retained_usd':RETAINED+estimate['gpu_job_ceiling_usd'],'cap_usd':24.31,
        'expected_usd':estimate['expected_cost_usd'],'conservative_usd':estimate['conservative_cost_usd'],
        'timeout_seconds':10825,'startup_timeout_seconds':300,'shutdown_allowance_seconds':15,
        'gpu':'L4','cpu_cores':4,'host_memory_gib':32,'maximum_containers':1,'retries':0})
    print('Before GPU submission:',(OUT/'reservation.json').read_text(),flush=True)
    from archivist.models import glimmer_phase2_modal as remote
    from archivist.models.glimmer_phase2_backend import Phase2Backend
    def event(item):
        with (OUT/'allocation_events.jsonl').open('a') as f: f.write(json.dumps(item)+'\n')
        if item['event'] in ('submitted','completed','cancelled_unallocated') or item['event']=='allocation_status':
            print(json.dumps(item),flush=True)
    code_id=digest(json.dumps(frozen['code'],sort_keys=True).encode())
    register_backend('modal_glimmer_phase2','llm',lambda model_id,**options:
        Phase2Backend(model_id,remote=remote.infer,event=event,code_id=code_id,**options),priced=True)
    model_id=f'{MODEL}@{REVISION}/phase2/{frozen["sample_sha256"]}/{code_id}'
    roles_path=OUT/'roles.toml'
    with roles_path.open('x') as f:
        f.write(f'''[roles.sort]
kind = "llm"
backend = "modal_glimmer_phase2"
model_id = "{model_id}"
[prices."{model_id}"]
input_per_mtok = 0.0
output_per_mtok = 0.0
''')
    os.environ['BUDGET_CAP_USD']=str(estimate['gpu_job_ceiling_usd'])
    role=load_roles(roles_path,cache_dir=Path('cache/glimmer-phase2'),
                    ledger_path=OUT/'spend_ledger.jsonl')['sort']
    payload={'phase2_authorized':True,'dataset_id':digest(Path('results/glimmer/data_manifest.json').read_bytes()),
        'sample_sha256':frozen['sample_sha256'],'input_sha256':digest((OUT/'inputs.jsonl').read_bytes()),
        'adapter_sha256':frozen['artifacts']['results/glimmer/adapter/adapter_model.safetensors'],
        'items':[{'system':SYSTEM,'prompt':prompt(r['ocr'],families)} for r in rows]}
    try:
        with remote.modal.enable_output(),remote.app.run():
            write_once('own_app.json',{'app_id':remote.app.app_id,
                'description':'archivist-glimmer-phase2-20261031'})
            response=role.complete(LLMRequest(role='glimmer_phase2',prompt=json.dumps(payload),
                                            max_output_tokens=512))
            # Save bytes before any scoring or parsing of generated text.
            with (OUT/'raw_response.json').open('x') as f: f.write(response.text+'\n')
        print('Both raw arms saved. Run Check, commit and push before any comparison.',flush=True)
    except BaseException as error:
        write_once('failure.json',{'error_type':type(error).__name__,'message':str(error)[:1000],
            'maximum_retained_usd':estimate['gpu_job_ceiling_usd'],'retry_permitted':False})
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['preflight','freeze','prepare-ocr','infer'])
    parser.add_argument('--go',action='store_true',required=True)
    args=parser.parse_args()
    {'preflight':preflight,'freeze':freeze,'prepare-ocr':prepare_ocr,'infer':infer}[args.stage]()


if __name__=='__main__': main()
