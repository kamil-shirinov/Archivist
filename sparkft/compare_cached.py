"""Development-only post-attempt comparison; exact-key caches, no new hosted calls."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from archivist.doctypes import from_config
from archivist.templates.pages import resolve
from sparkft.boxes import PAGES,P33_REVISION,blob,gate
from sparkft.dataset import cached_teacher
from sparkft.scoring import score

OUT=Path('results/sparkft/training/comparison_v2')


def pixel_record(values,reference):
    counts=Counter(v['field_id'] for v in values)
    by={v['field_id']:v for v in values if counts[v['field_id']]==1}
    cells={}
    for key,field in zip(reference['target'],reference['fields'],strict=True):
        if field not in by:continue
        value=by[field];citation=value.get('citation') or {}
        box=citation.get('raw_bbox') or citation.get('bbox')
        cells[key]={'value':value['value'],'abstained':value.get('abstained',False),
                    'box':[box[k] for k in ('x0','y0','x1','y1')] if box else None}
    return {'parsed_pixel_cells':cells}


def returned_figures(values,money_fields):
    figures=[v for v in values if v['field_id'].rsplit(':',1)[1] in money_fields]
    def empty(v):
        return bool(v.get('abstained') or v['value'] is None or not str(v['value']).strip())
    return {'returned_figure_fields':len(figures),'empty_or_abstained':sum(map(empty,figures)),
            'omitted_rows':'unknown; not inferred from returned fields'}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    root=Path('results/sparkft/training/validation_v2')
    raw=(root/'dataset.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=json.loads((root/'dataset_hash.json').read_text())['sha256']:
        raise ValueError('Frozen validation dataset changed')
    data=json.loads(raw);refs=data['validation']
    split=json.loads(Path('data/real/split.json').read_text())
    for ref in refs:gate(ref['page'],split)
    types=from_config(Path('config/real_test.toml'))
    observations={'hosted_meta_1_3':{},'historical_open_baseten':{}}
    unavailable={'hosted_meta_1_3':[],'historical_open_baseten':[]}
    for ref in refs:
        page=ref['page'];gate(page,split);plugin=types[ref['family']]
        image=resolve(page).path.read_bytes()
        if hashlib.sha256(image).hexdigest()!=data['pages'][page]['sha256']:
            raise ValueError('Validation page image changed')
        try:
            values,hashes=cached_teacher(page,plugin,image)
            observations['hosted_meta_1_3'][page]={'values':values,'hashes':hashes}
        except FileNotFoundError:
            unavailable['hosted_meta_1_3'].append(page)
        if page in PAGES:
            template='templates/'+ref['family']+'.yaml'
            if blob(P33_REVISION,template)!=Path(template).read_bytes():
                raise ValueError('Historical Open template semantics changed')
            raw=blob(P33_REVISION,'results/openw_measure/reads/baseten/'+page+'.json')
            read=json.loads(raw)
            if read['ok']:
                observations['historical_open_baseten'][page]={
                    'values':read['values'],'hashes':{'p33_read_sha256':hashlib.sha256(raw).hexdigest()}}
            else:unavailable['historical_open_baseten'].append(page)
        else:unavailable['historical_open_baseten'].append(page)
    result={'dataset_sha256':hashlib.sha256((root/'dataset.json').read_bytes()).hexdigest(),
            'new_meta_calls':0,'new_other_hosted_calls':0,'adopt':False,
            'paired_base_and_adapter':'unavailable: timed out loading; no validation predictions',
            'reference_bias':'Meta 1.3 supplied some OCR-agreed references; its value/empty scores there are conditioned on reference construction',
            'prompt_limitation':'Historical hosted reads use full-table prompts; local paired experiment requested fixed subsets',
            'models':{}}
    for name,by_page in observations.items():
        selected=[ref for ref in refs if ref['page'] in by_page]
        records=[pixel_record(by_page[ref['page']]['values'],ref) for ref in selected]
        supplemental=[]
        for ref in selected:
            found=by_page[ref['page']]
            supplemental.append({'page':ref['page'],'family':ref['family'],'layout':ref['layout'],
                **returned_figures(found['values'],types[ref['family']].money_fields)})
        model={'available_pages':[r['page'] for r in selected],'unavailable_pages':unavailable[name],
               'scores':score(records,selected),'all_returned_figure_fields':supplemental,
               'source_hashes':{p:d['hashes'] for p,d in by_page.items()}}
        result['models'][name]=model
        selected_rows=[];figure_rows=[]
        for ref in selected:
            values=by_page[ref['page']]['values']
            wanted=set(ref['fields']);money=types[ref['family']].money_fields
            for value in values:
                if value['field_id'] in wanted:
                    selected_rows.append({'page':ref['page'],**value})
                if value['field_id'].rsplit(':',1)[1] in money:
                    figure_rows.append({'page':ref['page'],'field_id':value['field_id'],
                                        'value':value['value'],'abstained':value.get('abstained',False)})
        for suffix,rows in [('selected',selected_rows),('returned_figures',figure_rows)]:
            (OUT/(name+'_'+suffix+'.jsonl')).write_text(
                ''.join(json.dumps(row,sort_keys=True)+'\n' for row in rows))
    common=set(observations['hosted_meta_1_3'])&set(observations['historical_open_baseten'])
    selected=[r for r in refs if r['page'] in common]
    result['historical_common_subset']={'pages':sorted(common),'scores':{name:score(
        [pixel_record(by[r['page']]['values'],r) for r in selected],selected)
        for name,by in observations.items()}}
    for name,reason in [('fine_tuned_open','No optimizer update or adapter'),
                        ('matched_local_base','Model loading timed out before inference')]:
        result['models'][name]={'available_pages':[],'unavailable_pages':[r['page'] for r in refs],
                                'scores':None,'reason':reason}
    (OUT/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    for name,model in result['models'].items():
        s=model['scores']
        print(name,'pages',len(model['available_pages']),
              'value/box/empty',None if s is None else (s['value_correct'],s['figure_contained'],s['empty_answers'],s['n']))


if __name__=='__main__':main()
