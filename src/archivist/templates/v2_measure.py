"""P40 development-only box audit and paired measurement; never reads held-out records."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from archivist.doctypes import from_config
from archivist.models import load_roles
from archivist.schema import ExtractedValue
from archivist.templates import grid, ocr
from archivist.templates.pages import resolve

OUT = Path('results/v2')
READS = Path('results/scratch/v2/reads')


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def box(b):
    return [getattr(b, k) for k in ('x0', 'y0', 'x1', 'y1')]


def contains(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]


def inputs():
    types = from_config(Path('config/real_test.toml'))
    for t in types.values():
        for ref in t.template.provenance.drafted_from:
            resolve(ref)  # Gate before opening a cached read, image or PDF.
            path = READS / 'meta' / f'{ref}.json'
            if path.exists():
                yield 'meta', path, json.loads(path.read_text()), t
    pick = json.loads(Path('results/openw_measure/pick.json').read_text())
    # P33's five declared development pages only; do not enumerate a cache.
    for family, row in pick['pages'].items():
        ref = row['ref']
        resolve(ref)
        path = Path('results/openw_measure/reads/baseten') / f'{ref}.json'
        read = json.loads(path.read_text())
        if read['ok']:
            yield 'baseten', path, read, types[family]


def references(values, layer, t):
    """Strict global unique-digit proxy, independent of either predicted box (P34's audit).

    No claim of human correctness: references are conditioned on first-read/OCR agreement.
    """
    figures = [v for v in values if not v.abstained and v.value and
               v.field_id.rsplit(':', 1)[1] in t.money_fields]
    counts = Counter(re.sub(r'\D', '', v.value) for v in figures)
    words = defaultdict(list)
    for w in layer:
        if len(w.digits) >= 3:
            words[w.digits].append(w)
    return {v.field_id: words[d][0].box for v in figures
            if len(d := re.sub(r'\D', '', v.value)) >= 3 and counts[d] == 1 and len(words[d]) == 1}


def baseline():
    pages = []
    for host, path, read, t in inputs():
        ref = read['ref']; image = resolve(ref).path.read_bytes(); layer = ocr.words(ref)
        values = [ExtractedValue.model_validate(v) for v in read['values']]
        cited, sources, info = grid.assign(values, t, image, layer)
        refs = references(values, layer, t)
        # Row pitch from the PDF figure centres, clustered without model-box proximity.
        ys = sorted((b.y0+b.y1)/2 for b in refs.values())
        lines = []
        for y in ys:
            if not lines or y-lines[-1] > 8:
                lines.append(y)
        gaps = [b-a for a,b in zip(lines,lines[1:]) if 12 <= b-a <= 70]
        pitch = statistics.median(gaps) if gaps else None
        targets = {v.field_id:v for v in values}
        records = []
        for v in cited:
            if v.field_id not in refs or v.citation is None:
                continue
            target = refs[v.field_id]; b = v.citation.bbox
            dy = ((b.y0+b.y1)-(target.y0+target.y1))/2
            raw = targets[v.field_id].citation.bbox
            raw_dy = ((raw.y0+raw.y1)-(target.y0+target.y1))/2
            records.append({'field_id':v.field_id,'target':box(target),'v1':box(b),'model':box(raw),
                            'source':sources[v.field_id], 'contains':contains(box(b),box(target)),
                            'dy':dy,'model_dy':raw_dy,
                            'row_offset':round(dy/pitch) if pitch else None,
                            'model_row_offset':round(raw_dy/pitch) if pitch else None})
        row = {'host':host,'ref':ref,'family':t.name,'read_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
               'figures':sum(v.field_id.rsplit(':',1)[1] in t.money_fields and bool(v.value) for v in values),
               'pitch':pitch,'v1_info':info,'sources':dict(Counter(sources.values())), 'cells':records}
        pages.append(row)
        print(host,ref,len(records),sum(c['contains'] for c in records),
              Counter(c['row_offset'] for c in records),flush=True)
        dump(OUT/'baseline.json',{'pages':pages,'note':'Unique-digit OCR proxy, not human labels; no order guard needed unless recorded.'})


def geometry():
    from archivist.templates import table_v2
    pages=[]
    for host,path,read,t in inputs():
        ref=read['ref']; image=resolve(ref).path.read_bytes(); layer=ocr.words(ref)
        raw=[ExtractedValue.model_validate(v) for v in read['values']]
        before=grid.assign(raw,t,image,layer)
        after=table_v2.assign(raw,t,image,layer,fallback=before)
        refs=references(raw,layer,t)
        a={v.field_id:v for v in before[0]}; b={v.field_id:v for v in after[0]}
        cells=[]
        for f,target in refs.items():
            if a[f].citation is None: continue
            cells.append({'field_id':f,'target':box(target),
                          'v1':box(a[f].citation.bbox),'v2':box(b[f].citation.bbox),
                          'v1_contains':contains(box(a[f].citation.bbox),box(target)),
                          'v2_contains':contains(box(b[f].citation.bbox),box(target)),
                          'v2_source':after[1][f]})
        pages.append({'host':host,'ref':ref,'family':t.name,'cells':cells,
                      'v2_sources':dict(Counter(after[1].values())),
                      'figure_sources':dict(Counter(after[1][v.field_id] for v in raw if
                          not v.abstained and v.value and v.field_id.rsplit(':',1)[1] in t.money_fields)),
                      'sources':{f:{'v1':before[1][f],'v2':after[1][f]} for f in before[1]},
                      'info':after[2]})
        dump(OUT/'geometry.json',{'pages':pages})
        # Preserve boxes for the exact frozen paired draw, before any re-read.
        out=READS.parent/'boxed'/host
        dump(out/f'{ref}.json',{'family':t.name,'v1':[v.model_dump() for v in before[0]],
                               'v2':[v.model_dump() for v in after[0]]})
        print(host,ref,len(cells),sum(c['v1_contains'] for c in cells),
              sum(c['v2_contains'] for c in cells),Counter(after[1].values()),flush=True)


def acquire():
    from archivist.pipeline import extract
    from archivist.templates.test import output_tokens
    roles=load_roles(Path('config/templates.toml'))
    missing=[]
    for t in from_config(Path('config/real_test.toml')).values():
        for ref in t.template.provenance.drafted_from:
            page=resolve(ref)
            try:
                values=extract.read_page(page.path.read_bytes(),ref,roles['extractor'],t,'S0',output_tokens(t))
            except Exception as error:
                missing.append({'ref':ref,'error':type(error).__name__})
                continue
            path=READS/'meta'/f'{ref}.json'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'ref':ref,'family':t.name,
                                        'values':[v.model_dump() for v in values]}))
    dump(OUT/'missing_reads.json',missing)


class Seeded:
    """Copy only the requested cached entry; main's cache is never opened for writing."""
    def __init__(self, llm):
        self.llm=llm
    def complete(self, request):
        import shutil
        from archivist.models.cache import cache_key
        key=cache_key(self.llm.name,self.llm.model_id,request,self.llm.settings)
        target=self.llm.cache_dir/key[:2]/f'{key}.json'
        source=Path('cache')/key[:2]/f'{key}.json'
        if not target.exists() and source.is_file():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
        return self.llm.complete(request)


def task_roles():
    from archivist.models.budget import BudgetGuard, BACKEND_CAPS
    caps_path=OUT/'caps.json'
    if not caps_path.exists():
        guard=BudgetGuard(0)
        start={b:guard.spent(b) for b in BACKEND_CAPS}
        limits={b:min(default,start[b]+(5 if b in ('meta','baseten') else 0))
                for b,(var,default) in BACKEND_CAPS.items()}
        dump(caps_path,{'starting_usd':start,'caps_usd':limits,
                        'allowance_usd':{'meta':5,'baseten':5}})
    caps=json.loads(caps_path.read_text())
    for b,(var,default) in BACKEND_CAPS.items():
        os.environ[var]=str(caps['caps_usd'][b])
    cache=Path('results/scratch/v2/cache')
    return {host:Seeded(load_roles(Path(config),cache_dir=cache)['rereader'])
            for host,config in [('meta','config/templates.toml'),('baseten','config/models_open.toml')]}


def paired(host_filter=None):
    from archivist.templates.test import reread_cells
    roles=task_roles()
    types=from_config(Path('config/real_test.toml'))
    draw=json.loads((OUT/'draw.json').read_text())
    # This hash freezes the candidate before any paired re-read is examined.
    freeze=OUT/'development_freeze.json'
    if not freeze.exists():
        dump(freeze,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     [Path('src/archivist/templates/table_v2.py'),OUT/'PLAN.md',OUT/'draw.json']})
    for entry in draw['pages']:
        host,ref=entry['host'],entry['ref']
        if host_filter and host != host_filter:
            continue
        page=resolve(ref)
        t=types[entry['family']]
        path=OUT/'rereads'/host/f'{ref}.json'
        if path.exists():
            continue
        data=json.loads((READS.parent/'boxed'/host/f'{ref}.json').read_text())
        result={**entry,'strategies':{}}
        for strategy in ('v1','v2'):
            values=[ExtractedValue.model_validate(v) for v in data[strategy]]
            second=reread_cells(page.path.read_bytes(),values,set(entry['cells']),t,roles[host],8)
            first={v.field_id:v for v in values}
            result['strategies'][strategy]=[{
                'field_id':f,'first':first[f].value,'reread':second[f].text,
                'failure':second[f].why,'agree':second[f].text is not None and
                t.canonical(f,first[f].value)==t.canonical(f,second[f].text),
                'box':box(first[f].citation.bbox)} for f in entry['cells']]
        dump(path,result)
        print(host,ref,{s:sum(c['agree'] for c in cells) for s,cells in result['strategies'].items()},flush=True)


def diagnose():
    from PIL import Image
    geometry=json.loads((OUT/'geometry.json').read_text())['pages']
    info={(p['host'],p['ref']):p['info'] for p in geometry}
    records=[]
    for host,path,read,t in inputs():
        ref=read['ref']; found=info[host,ref]
        width=Image.open(resolve(ref).path).width
        rows={k:v for k,v in found['rows'].items() if v['source']=='label-occurrence'}
        ys=sorted(v['y'] for v in found['rows'].values())
        gaps=[b-a for a,b in zip(ys,ys[1:]) if 8<b-a<50]
        pitch=statistics.median(gaps) if gaps else None
        raw={v['field_id']:v for v in read['values']}
        boxed=json.loads((READS.parent/'boxed'/host/f'{ref}.json').read_text())
        cells=[]
        for v in boxed['v1']:
            row,col=v['field_id'].rsplit(':',2)[-2:]
            if (row not in rows or col not in t.money_fields or v['abstained'] or
                    not v['value'] or not v['citation'] or pitch is None):
                continue
            record={'field_id':v['field_id'],'expected_y':rows[row]['y']}
            for name,cell in [('v1',v),('model',raw[v['field_id']])]:
                b=cell['citation']['bbox']
                y=(b['y0']+b['y1'])/2-found.get('shear',0)*((b['x0']+b['x1'])/2-width/2)
                record[name+'_row_offset']=round((y-rows[row]['y'])/pitch)
            cells.append(record)
        records.append({'host':host,'ref':ref,'family':t.name,'pitch':pitch,
                        'matched_repeated_labels':len(rows),
                        'counts':{s:dict(Counter(c[s+'_row_offset'] for c in cells)) for s in ('model','v1')},
                        'cells':cells})
    dump(OUT/'repeated_label_diagnostic.json',{
        'note':'Exploratory occurrence-aligned OCR row proxy; not human labels or the adoption measure. Equal counts required; unmatched repetitions excluded and reported in geometry.json.',
        'pages':records})


def summarize():
    from archivist.models.budget import BudgetGuard
    geometry=json.loads((OUT/'geometry.json').read_text())['pages']
    draw=json.loads((OUT/'draw.json').read_text())['pages']
    baseline=json.loads((OUT/'baseline.json').read_text())['pages']
    caps=json.loads((OUT/'caps.json').read_text())
    guard=BudgetGuard(0)
    costs={h:guard.spent(h)-start for h,start in caps['starting_usd'].items()}
    results=[]
    for entry in draw:
        path=OUT/'rereads'/entry['host']/f"{entry['ref']}.json"
        if not path.exists():
            continue
        record=json.loads(path.read_text())
        assert record['cells']==entry['cells']
        results.append(record)
    summaries={}
    for host in ('meta','baseten'):
        mine=[p for p in geometry if p['host']==host]
        reads=[p for p in results if p['host']==host]
        references=[c for p in mine for c in p['cells']]
        n=sum(len(p['cells']) for p in reads)
        contain={s:sum(c[s+'_contains'] for c in references) for s in ('v1','v2')}
        centre={s:sum(contains(c[s],[(c['target'][0]+c['target'][2])/2,
                                    (c['target'][1]+c['target'][3])/2,
                                    (c['target'][0]+c['target'][2])/2,
                                    (c['target'][1]+c['target'][3])/2])
                      for c in references) for s in ('v1','v2')}
        agreement={s:sum(c['agree'] for p in reads for c in p['strategies'][s]) for s in ('v1','v2')}
        complete=len(reads)==sum(p['host']==host for p in draw)
        summaries[host]={'references':len(references),'contains':contain,'sampled':n,
                         'agreement':agreement,'centre_contains':centre,'complete':complete,
                         'qualifies':complete and contain['v2']>contain['v1'] and agreement['v2']>agreement['v1']}
    adopted=all(r['qualifies'] for r in summaries.values())
    data={'readers':summaries,'adopted':adopted,'cost_usd':costs,
          'code_sha256':hashlib.sha256(Path('src/archivist/templates/table_v2.py').read_bytes()).hexdigest()}
    dump(OUT/'summary.json',data)
    lines=['# P40 — boxes anchored to the table: development results','',
           '**Development only. '+('The adoption rule passes.' if adopted else 'The adoption rule fails; keep v1.')+'**','',
           'The candidate is an opt-in `S0+table-v2` function beside the unchanged `S0+grid`. '
           'It uses this page’s unique OCR figures to establish columns and row consensus, '
           'equal-count label occurrences to distinguish repeated dates, and ruled lines/ink '
           'to bound cells. It takes the token physically in the named cell even when its value '
           'differs from the first read. Ambiguous cells retain v1 with an explicit source. '
           'No prompt, reader, template, decision, policy, tag or scorer changed.','',
           'The prewritten gate in PLAN.md requires strict pooled improvement in both whole-figure '
           'containment and blind re-read agreement, separately for both readers. Ties keep v1. '
           'The candidate hash and rule/sample hashes were recorded before paired re-reads.','',
           '| Reader | Whole OCR figure contained, v1 → v2 | Paired re-read agreement, v1 → v2 | Gate |',
           '|---|---|---|---|']
    def rate(n,d):
        return f'{n}/{d} ({n/d:.2%})' if d else 'unavailable'
    for host,r in summaries.items():
        lines.append(f"| {host} | {rate(r['contains']['v1'],r['references'])} → {rate(r['contains']['v2'],r['references'])} | "
                     f"{rate(r['agreement']['v1'],r['sampled'])} → {rate(r['agreement']['v2'],r['sampled'])} | {'pass' if r['qualifies'] else 'fail'} |")
    lines += ['', 'Fifteen Spark 1.3 drafting pages and the five P33 Baseten Open pages; no fresh '
              'extraction. Forty cells per page/reader, seed 40, fixed before v2 geometry: '
              '600 Spark and 200 Open cells, both strategies on each cell. Re-reads use the '
              'existing prompts, crop padding, schema, 2,048-token allowance, retry and template '
              'canonical comparison. Spark reasons at minimal, Open at low as in P33. '
              'Failures/nulls count as disagreements. No sample cell is dropped.', '',
              '| Reader | Family | Whole figure v1 → v2 | Agreement v1 → v2 |',
              '|---|---|---|---|']
    for host in ('meta','baseten'):
        for family in sorted({p['family'] for p in geometry}):
            geo=[c for p in geometry if p['host']==host and p['family']==family for c in p['cells']]
            rereads=[p for p in results if p['host']==host and p['family']==family]
            n=sum(len(p['cells']) for p in rereads)
            full=[sum(c[s+'_contains'] for c in geo) for s in ('v1','v2')]
            agree=[sum(c['agree'] for p in rereads for c in p['strategies'][s]) for s in ('v1','v2')]
            lines.append(f'| {host} | {family} | {full[0]}/{len(geo)} → {full[1]}/{len(geo)} | {agree[0]}/{n} → {agree[1]}/{n} |')
    lines += ['', '| Reader | OCR centre contained v1 → v2 | New figure-box sources |',
              '|---|---|---|']
    for host,r in summaries.items():
        sources=Counter()
        for page in geometry:
            if page['host']==host:
                sources.update(page['figure_sources'])
        total=sum(sources.values())
        text=', '.join(f'{key}: {value}/{total}' for key,value in sorted(sources.items()))
        lines.append(f"| {host} | {rate(r['centre_contains']['v1'],r['references'])} → {rate(r['centre_contains']['v2'],r['references'])} | {text} |")
    lines += ['', 'Baseline diagnosis:', '',
              '| Reader | Unique OCR references | Model one row high / low | V1 one row high / low | V1 full figure |',
              '|---|---:|---:|---:|---:|']
    for host in ('meta','baseten'):
        cells=[c for p in baseline if p['host']==host for c in p['cells']]
        lines.append(f"| {host} | {len(cells)} | {sum(c['model_row_offset']==-1 for c in cells)} / {sum(c['model_row_offset']==1 for c in cells)} | "
                     f"{sum(c['row_offset']==-1 for c in cells)} / {sum(c['row_offset']==1 for c in cells)} | {sum(c['contains'] for c in cells)} |")
    lines += ['', 'The strict containment proxy requires at least three digits, a unique first-read '
              'figure and a unique full-page OCR match. It does not use either predicted box to '
              'choose the reference. It is conditioned on first-read/OCR agreement and excludes '
              'short/repeated values; it is not human-scored citation accuracy or value accuracy. '
              'Row offsets round centre displacement divided by PDF line pitch; remote false '
              'digit matches and unavailable pitch remain in baseline.json.','',
              'The repeated-label diagnostic uses equal-count OCR stub occurrences in table '
              'order, independently of model-box proximity. It is exploratory, uses the candidate’s '
              'row resolver on the original v1 boxes, and does not enter the adoption gate:', '',
              '| Reader | Matched figure cells | V1 one row high | V1 one row low | V1 farther away |',
              '|---|---:|---:|---:|---:|']
    diagnostic=json.loads((OUT/'repeated_label_diagnostic.json').read_text())['pages']
    for host in ('meta','baseten'):
        cells=[c for p in diagnostic if p['host']==host for c in p['cells']]
        lines.append(f"| {host} | {len(cells)} | {sum(c['v1_row_offset']==-1 for c in cells)} | {sum(c['v1_row_offset']==1 for c in cells)} | {sum(abs(c['v1_row_offset'])>1 for c in cells)} |")
    lines += ['', 'Why: v1 searches for matching digits within 100 px of the model box, maps '
              'columns using model/nearby OCR centres and allows label matching only near the '
              'model’s row. Repeated dates can leave short values without anchors or preserve '
              'a wrong neighbouring band. Open’s page-specific drift is much larger than that '
              'window, so its wrong model positions propagate into the grid. Structural row '
              'and column anchors remove much of that dependence, but sparse/misread OCR still '
              'leaves fallbacks, and tighter/moved crops can reduce agreement. Neither OCR '
              'agreement nor re-read agreement proves correctness.','',
              '| Reader | Page | References | Full figure v1 → v2 | Agreement v1 → v2 |',
              '|---|---|---:|---:|---:|']
    by_read={(p['host'],p['ref']):p for p in results}
    for p in geometry:
        r=by_read.get((p['host'],p['ref']))
        agree=[sum(c['agree'] for c in r['strategies'][s]) for s in ('v1','v2')] if r else ['missing','missing']
        full=[sum(c[s+'_contains'] for c in p['cells']) for s in ('v1','v2')]
        lines.append(f"| {p['host']} | {p['ref']} | {len(p['cells'])} | {full[0]} → {full[1]} | {agree[0]} → {agree[1]} |")
    lines += ['', 'Per-cell targets, boxes, sources, rejected row mappings, unmatched label counts '
              'and ruled-line diagnostics are in geometry.json; every paired answer and failure '
              'is under rereads/. The occurrence diagnostic is repeated_label_diagnostic.json. '
              'Sources use `table:ocr`, `table:ink`, or explicit `v1:ocr/grid/model` fallback. '
              'In particular 1984-06 p058 has only three strict OCR references and no v2 column '
              'mapping: that layout remains a limitation, rather than being inferred from another page.', '',
              f"Cost: Meta **${costs['meta']:.6f} / $5**, Baseten **${costs['baseten']:.6f} / $5**; "
              'no new Fireworks, Glimmer or SAM calls. caps.json records starting totals and '
              'absolute ceilings; answered calls are in the canonical spend ledger. The failed '
              'sandbox network pass is preserved separately (EXECUTION.md); connection failures '
              'have no provider usage recorded. These are model-reported token costs, not invoices.', '']
    if not adopted:
        lines += ['**No v2 run is frozen for adoption and no held-out pre-registration is drafted:** '
                  'the prewritten gate failed. The development candidate is retained for review, '
                  'with its failures. A future candidate needs another prospective development '
                  'plan. If one qualifies, the requested draft must reuse the same 58 pages and '
                  '400 drawn cell IDs, reuse the first reads, re-read only those cells and use '
                  'v1’s unchanged scorer and all reporting variants; any optional Open arm needs '
                  'its own declared freeze and budget. This task authorizes no held-out run.','']
    (OUT/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(data,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['acquire','baseline','geometry','paired','diagnose','summarize'])
    parser.add_argument('--host', choices=['meta','baseten'])
    args=parser.parse_args()
    for variable in ('BUDGET_CAP_USD','BASETEN_CAP_USD','FIREWORKS_CAP_USD','GLIMMER_CAP_USD'):
        os.environ[variable]='0'
    if args.stage == 'paired':
        paired(args.host)
    else:
        {'acquire':acquire,'baseline':baseline,'geometry':geometry,'diagnose':diagnose,'summarize':summarize}[args.stage]()


if __name__ == '__main__':
    main()
