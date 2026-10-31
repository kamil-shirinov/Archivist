"""Development OCR inventory and prospective family/layout coverage draw."""
from __future__ import annotations
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
import pypdfium2 as pdfium
from archivist.doctypes import from_config
from archivist.ingest.fraser import pdf_name
from archivist.templates.real_test import title_match
from sparkft.boxes import gate

OUT=Path('results/sparkft/training/validation_v2')


def sha(data):return hashlib.sha256(data).hexdigest()


def layout(plugin,width,height):
    schema={'row_mode':type(plugin.layout.rows).__name__,
            'columns':[(c.key,c.kind,c.printed) for c in plugin.layout.columns],
            'panels':1,'orientation':'portrait' if height>=width else 'landscape'}
    return sha(json.dumps(schema,sort_keys=True).encode())[:12],schema


def main():
    if (OUT/'draw.json').exists():raise ValueError('Coverage draw already frozen')
    split=json.loads(Path('data/real/split.json').read_text())
    manifest=json.loads(Path('data/real/manifest.json').read_text())
    sources=json.loads(Path('data/real/sources.json').read_text())
    types=from_config(Path('config/real_test.toml'))
    old=json.loads(Path('results/sparkft/data_manifest.json').read_text())
    train={r['page'] for r in old['training']}
    originals={r['page']:r['family'] for r in old['validation']}
    known={}
    for family in types:
        evidence=json.loads(Path('templates',family+'.evidence.json').read_text())
        for row in evidence['pages']:known[row['ref']]=family
    rows=defaultdict(list)
    for row in manifest['pages']:
        if row['issue'] in split['development']:rows[row['issue']].append(row)
    inventory=[];pdf_hashes={}
    for issue in split['development']:
        gate(issue+'_p001',split)
        path=Path('data/real/pdf',pdf_name(issue))
        expected=next(x['sha256'] for x in sources['files'] if x['issue']==issue)
        actual=sha(path.read_bytes())
        if actual!=expected:raise ValueError('Development PDF hash mismatch')
        pdf_hashes[issue]=actual
        pdf=pdfium.PdfDocument(path)
        try:
            for row in rows[issue]:
                ref=f"{issue}_p{row['page']:03d}";gate(ref,split)
                page=pdf[row['page']-1];textpage=page.get_textpage()
                try:text=textpage.get_text_range()
                finally:textpage.close();page.close()
                for family,plugin in types.items():
                    matched=title_match(plugin,text[:1024]) is not None
                    contents=bool(re.search(r'\bcontents\b',text[:256],re.I))
                    numeric=len(re.findall(r'\b\d[\d,.]*\b',text))
                    approved=known.get(ref)==family
                    if approved or (matched and not contents and numeric>=20):
                        key,signature=layout(plugin,row['width'],row['height'])
                        inventory.append({'page':ref,'family':family,'layout':key,
                                          'layout_signature':signature,'title_matched':matched,
                                          'approved_evidence':approved,'image_sha256':row['sha256']})
        finally:pdf.close()
    by=defaultdict(list)
    for row in inventory:by[(row['family'],row['layout'])].append(row)
    withdrawn=set();selected=[]
    for (family,key),pool in sorted(by.items()):
        ordered=sorted(pool,key=lambda r:sha(f"sparkft-coverage-3402:{family}:{key}:{r['page']}".encode()))
        available=[r for r in ordered if r['page'] not in train]
        need=max(0,3-len(available))
        take=[r for r in ordered if r['page'] in train][:need]
        withdrawn.update(r['page'] for r in take);available.extend(take)
        if len(available)<3:raise ValueError('Insufficient development pages for '+family+'/'+key)
        keep=[r for r in available if originals.get(r['page'])==family]
        for row in available:
            if len(keep)>=3:break
            if row not in keep:keep.append(row)
        selected.extend(keep)
    assert set(types)=={r['family'] for r in selected}
    final_train=sorted(train-withdrawn)
    assert set(final_train).isdisjoint({r['page'] for r in selected})
    result={'rule':'RULE.md','inventory':inventory,'pdf_hashes':pdf_hashes,
            'training_pages':final_train,'withdrawn_training_pages':sorted(withdrawn),
            'validation':sorted(selected,key=lambda r:(r['family'],r['layout'],r['page'])),
            'prior_validation_preserved':sorted(originals),
            'all_approved_families':sorted(types),'minimum_pages_per_layout':3}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'draw.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Selected validation pages',len(selected),'training',final_train,'withdrawn',sorted(withdrawn))
    for row in result['validation']:print(row['family'],row['layout'],row['page'])


if __name__=='__main__':main()
