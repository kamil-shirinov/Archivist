"""Freeze development-only prompts and independent evaluation proxies before inference."""
from __future__ import annotations
import hashlib
import json
import math
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image
from archivist.doctypes import from_config
from archivist.models import load_roles
from archivist.models.cache import Cache, cache_key
from archivist.pipeline.extract import read_page
from archivist.templates.ocr import words
from archivist.templates.pages import resolve
from archivist.templates.test import output_tokens
from sparkft.boxes import P33_REVISION, blob, gate
from sparkft.prepare import number

OUT=Path('results/sparkft/training')
SYSTEM='Read public archive tables faithfully. Return only the requested cells and boxes around their printed figures.'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prompt(plugin, fields):
    requested={f'c{i:02d}': {'row':f.rsplit(':',2)[1], 'column':f.rsplit(':',1)[1]}
               for i,f in enumerate(fields)}
    return ('Read these cells from the printed table '+plugin.template.identity.title+'.\n'
            +plugin.rows_and_columns()+'\nRequested cells: '+json.dumps(requested)+'\n'
            'Return exactly one JSON object mapping each requested cNN key to '
            '{"value":"printed number","box":[x0,y0,x1,y1]}. '
            'Boxes use a 0-1000 grid, origin top left, around all ink of the figure. '
            'Use null for an unreadable value and null for a missing box. No other keys or prose.')


def grid(box, size):
    w,h=size
    return [math.floor(box['x0']*1000/w),math.floor(box['y0']*1000/h),
            math.ceil(box['x1']*1000/w),math.ceil(box['y1']*1000/h)]


def bundle(ref, plugin, rows, size):
    fields=[r['field_id'] for r in rows]
    return {'page':ref,'system':SYSTEM,'prompt':prompt(plugin,fields),
            'fields':fields,'size':size,
            'target':{f'c{i:02d}':{'value':r['value'],'box':grid(r['ocr_box'],size)}
                      for i,r in enumerate(rows)}}


def cached_teacher(ref, plugin, image):
    for key in ('BUDGET_CAP_USD','BASETEN_CAP_USD','FIREWORKS_CAP_USD'):
        os.environ[key]='0'
    original=Cache._through
    source=Path.cwd().parents[1]/'cache'
    inputs={}

    def stage(self, request, call, load):
        key=cache_key(self.name,self.model_id,request,self.settings)
        path=self.cache_dir/key[:2]/(key+'.json')
        if not path.exists():
            src=source/key[:2]/(key+'.json')
            if not src.is_file():
                raise FileNotFoundError('Validation teacher cache missing; no paid fallback: '+ref)
            path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,path)
        inputs[key]=digest(path.read_bytes())
        return original(self,request,call,load)

    Cache._through=stage
    try:
        roles=load_roles(Path('config/templates.toml'))
        values=read_page(image,ref,roles['extractor'],plugin,'S0',output_tokens(plugin))
    finally:
        Cache._through=original
    return [v.model_dump() for v in values],inputs


def reference_rows(values, layer, fields):
    by=defaultdict(list)
    for word in layer:
        num=number(word.text,ocr=True)
        if num is not None:
            by[num].append(word)
    candidates=[v for v in values if not v['abstained'] and
                v['field_id'].rsplit(':',1)[1] in fields and number(v['value']) is not None]
    counts=Counter(number(v['value']) for v in candidates)
    selected=[]
    for v in candidates:
        num=number(v['value'])
        if counts[num]==1 and len(by[num])==1:
            word=by[num][0]
            selected.append({'field_id':v['field_id'],'value':v['value'],
                             'canonical_value':num,'ocr_box':word.box.model_dump(),
                             'ocr_text':word.text})
    return sorted(selected,key=lambda r:digest(('sparkft-validation-3401:'+r['field_id']).encode()))[:20]


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    destination=OUT/'dataset.json'
    if destination.exists():
        raise ValueError('Frozen dataset already exists; refusing to overwrite')
    manifest=json.loads(Path('results/sparkft/data_manifest.json').read_text())
    split=json.loads(Path('data/real/split.json').read_text())
    types=from_config(Path('config/real_test.toml'))
    train=[json.loads(line) for line in Path('results/sparkft/training_answers.jsonl').read_text().splitlines()]
    payload={'train':[],'validation':[],'pages':{},'teacher_cache_hashes':{},
             'reference_kind':'Cached independent Muse Spark 1.3 semantic IDs + exact unique PDF OCR',
             'training_answers_sha256':manifest['training_answers_sha256']}
    for record in manifest['training']+manifest['validation']:
        ref=record['page']; gate(ref,split); page=resolve(ref)
        raw=page.path.read_bytes()
        with Image.open(page.path) as image:size=list(image.size)
        if digest(raw)!=record['image_sha256']:
            raise ValueError('Image changed')
        payload['pages'][ref]={'sha256':digest(raw),'size':size}
        plugin=types[record['family']]
        if record in manifest['training']:
            rows=sorted([r for r in train if r['page']==ref],key=lambda r:r['field_id'])
            for start in range(0,len(rows),8):
                payload['train'].append(bundle(ref,plugin,rows[start:start+8],size))
        else:
            values,hashes=cached_teacher(ref,plugin,raw)
            payload['teacher_cache_hashes'][ref]=hashes
            refs=reference_rows(values,words(ref),plugin.money_fields)
            payload['validation'].append(bundle(ref,plugin,refs,size))
            (OUT/(ref+'_reference.json')).write_text(json.dumps(
                {'page':ref,'family':record['family'],'reference':refs,'support':len(refs),
                 'returned_figure_fields':sum(v['field_id'].rsplit(':',1)[1] in plugin.money_fields for v in values)},
                 indent=2)+'\n')
    raw=(json.dumps(payload,sort_keys=True,indent=2)+'\n').encode()
    destination.write_bytes(raw)
    (OUT/'dataset_hash.json').write_text(json.dumps({'sha256':digest(raw)},indent=2)+'\n')
    print('Training conversations',len(payload['train']), 'validation supports',
          [len(x['fields']) for x in payload['validation']], 'dataset',digest(raw))


if __name__=='__main__':
    main()
