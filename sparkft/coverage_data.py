"""Build references for a frozen public-domain development-only coverage draw."""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from PIL import Image
from archivist.doctypes import from_config
from archivist.models import LLMRequest,load_roles
from archivist.models.budget import BudgetGuard
from archivist.templates.pages import resolve
from archivist.templates.ocr import words
from archivist.templates.test import output_tokens
from sparkft.boxes import gate
from sparkft.dataset import bundle,cached_teacher,reference_rows

OUT=Path('results/sparkft/training/validation_v2')


def main():
    if (OUT/'dataset.json').exists():raise ValueError('Coverage dataset already frozen')
    sources=json.loads(Path('data/real/sources.json').read_text())
    if sources['rights']['statement']!='No Copyright - United States':
        raise ValueError('Public-domain provenance not established')
    draw=json.loads((OUT/'draw.json').read_text())
    split=json.loads(Path('data/real/split.json').read_text())
    for record in draw['validation']:gate(record['page'],split)
    types=from_config(Path('config/real_test.toml'))
    original=json.loads(Path('results/sparkft/data_manifest.json').read_text())
    selected_train=[r for r in original['training'] if r['page'] in draw['training_pages']]
    train=[json.loads(s) for s in Path('results/sparkft/training_answers.jsonl').read_text().splitlines()]
    train=[r for r in train if r['page'] in draw['training_pages']]
    (OUT/'training_answers.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in train))
    state_path=OUT/'reference_budget.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {
        'baseten_spent_before':BudgetGuard(0).spent('baseten'),'task_cap_usd':5,'attempts':[],
        'public_domain_source':sources['title_url'],'rights':sources['rights']['statement']}
    payload={'protocol':'sparkft-coverage-v2','train':[],'validation':[],'pages':{},
             'required_families':draw['all_approved_families'],'minimum_pages_per_layout':3,
             'draw_sha256':hashlib.sha256((OUT/'draw.json').read_bytes()).hexdigest()}
    for record in selected_train+draw['validation']:
        ref=record['page'];gate(ref,split);page=resolve(ref)
        image=page.path.read_bytes()
        with Image.open(page.path) as im:size=list(im.size)
        image_sha=hashlib.sha256(image).hexdigest()
        if image_sha!=record['image_sha256']:raise ValueError('Frozen page hash changed')
        payload['pages'][ref]={'sha256':image_sha,'size':size}
        plugin=types[record['family']]
        if record in selected_train:
            rows=sorted([r for r in train if r['page']==ref],key=lambda r:r['field_id'])
            for start in range(0,len(rows),8):
                payload['train'].append({**bundle(ref,plugin,rows[start:start+8],size),
                                         'family':record['family']})
            continue
        path=OUT/(ref+'_reference.json')
        if path.exists():
            frozen=json.loads(path.read_text());references=frozen['reference']
        else:
            try:
                values,hashes=cached_teacher(ref,plugin,image);host='cached_meta_1.3'
            except FileNotFoundError:
                # A single budgeted request, never a new Meta/Fireworks read.
                if len(state['attempts'])>=16:raise ValueError('Baseten reference reservations exhausted')
                state['attempts'].append({'page':ref,'reservation_usd':.30})
                state_path.write_text(json.dumps(state,indent=2)+'\n')
                os.environ['BASETEN_CAP_USD']=str(min(80,state['baseten_spent_before']+5))
                roles=load_roles(Path('sparkft/reference_roles.toml'),cache_dir=Path('cache/sparkft-reference'))
                req=LLMRequest(role='extractor',prompt=plugin.extraction_prompt(grounding=False),
                               images=(image,),json_schema=plugin.extraction_schema(),
                               max_output_tokens=output_tokens(plugin))
                response=roles['extractor'].complete(req)
                values=[v.model_dump() for v in plugin.parse(ref,json.loads(response.text),*size)]
                hashes={'response_sha256':hashlib.sha256(response.text.encode()).hexdigest()}
                host='baseten_muse_spark_open'
            references=reference_rows(values,words(ref),plugin.money_fields)
            frozen={'page':ref,'family':record['family'],'layout':record['layout'],
                    'reference':references,'support':len(references),'source':host,
                    'source_hashes':hashes,'returned_figure_fields':sum(
                        v['field_id'].rsplit(':',1)[1] in plugin.money_fields for v in values)}
            path.write_text(json.dumps(frozen,indent=2)+'\n')
        payload['validation'].append({**bundle(ref,plugin,references,size),
                                      'family':record['family'],'layout':record['layout'],
                                      'ocr_boxes':[r['ocr_box'] for r in references]})
        print(ref,record['family'],'references',len(references),flush=True)
    expected={(r['family'],r['layout']) for r in draw['validation']}
    coverage=Counter((r['family'],r['layout']) for r in payload['validation'] if r['fields'])
    if set(coverage)!=expected or any(n<3 for n in coverage.values()):
        raise ValueError('Insufficient scorable pages per family/layout; no training')
    raw=(json.dumps(payload,sort_keys=True,indent=2)+'\n').encode()
    (OUT/'dataset.json').write_bytes(raw)
    (OUT/'dataset_hash.json').write_text(json.dumps({'sha256':hashlib.sha256(raw).hexdigest()},indent=2)+'\n')
    state['baseten_spent_after']=BudgetGuard(0).spent('baseten')
    state['new_baseten_spend_usd']=state['baseten_spent_after']-state['baseten_spent_before']
    state_path.write_text(json.dumps(state,indent=2)+'\n')
    print('Frozen:',len(train),'training answers,',len(payload['validation']),'validation pages',flush=True)


if __name__=='__main__':main()
