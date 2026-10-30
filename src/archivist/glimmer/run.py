"""Run phase-1 jobs explicitly. There is intentionally no held-out / phase-2 command."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

from archivist.glimmer import cost
from archivist.glimmer.data import OUT, SYSTEM, load_frozen, prompt
from archivist.glimmer.metrics import INVALID, parse_answer, score
from archivist.models import LLMRequest, load_roles
from archivist.models.glimmer_access import MODEL, REVISION
from archivist.models.glimmer_backend import ModalGlimmer
from archivist.models.registry import register_backend


def _save(name,record):
    (OUT/name).write_text(json.dumps(record,indent=2)+'\n')


def run(stage):
    if stage == 'prepare':
        from archivist.models import glimmer_prepare as remote
    else:
        from archivist.models import glimmer_modal as remote
    train,validation,families=load_frozen()
    dataset_id=hashlib.sha256((OUT/'data_manifest.json').read_bytes()).hexdigest()
    if stage=='prepare':
        with remote.modal.enable_output(), remote.app.run():
            result=remote.prepare_weights.remote({
                'train':[{'system':SYSTEM,'prompt':prompt(row['ocr'],families),'target':row['target']} for row in train],
                'validation':[{'system':SYSTEM,'prompt':prompt(row['ocr'],families)} for row in validation]})
        _save('environment.json',result)
        print(json.dumps(result,indent=2))
        return
    if not (OUT/'environment.json').exists():
        raise ValueError('run prepare first; it uses no GPU')
    if stage=='train' and not (OUT/'baseline_metrics.json').exists():
        raise ValueError('baseline must be saved before training')
    if stage=='trained' and not (OUT/'adapter/adapter_config.json').exists():
        raise ValueError('adapter must be saved before trained validation')
    code_files = sorted(Path('src/archivist/glimmer').glob('*.py')) + sorted(Path('src/archivist/models').glob('glimmer_*.py'))
    code_record = {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in code_files}
    run_manifest = OUT/'run_manifest.json'
    if run_manifest.exists():
        if json.loads(run_manifest.read_text()) != code_record:
            raise ValueError('experiment code changed since the first GPU arm')
    elif stage == 'baseline':
        _save('run_manifest.json',code_record)
    else:
        raise ValueError('baseline must freeze the experiment code first')
    runtime_id = hashlib.sha256(run_manifest.read_bytes()).hexdigest()
    rows=train if stage=='train' else validation
    items=[]
    for row in rows:
        item={'system':SYSTEM,'prompt':prompt(row['ocr'],families)}
        if stage=='train':
            item['target']=row['target']
        repeats=4 if stage=='train' and row['target']!='other' else 1
        items.extend([item]*repeats)
    payload={'items':items,'dataset_id':dataset_id}
    reservation=cost.reserve(stage,OUT/'cost.json')
    print(f"GPU job {stage}: reserve ${reservation['maximum_usd']:.4f}; "
          f"rate ${cost.RATE*3600:.4f}/hour including CPU and memory.",flush=True)
    factory=lambda model_id,**settings:ModalGlimmer(model_id,remote=getattr(remote,stage),
                                stage=stage,dataset_id=dataset_id,runtime_id=runtime_id,**settings)
    register_backend('modal_glimmer','llm',factory,priced=True)
    config=OUT/f'{stage}_roles.toml'
    config.write_text(f'''[roles.glimmer_job]
kind = "llm"
backend = "modal_glimmer"
model_id = "{MODEL}@{REVISION}/{stage}/{dataset_id}"
[prices."{MODEL}@{REVISION}/{stage}/{dataset_id}"]
input_per_mtok = 0.0
output_per_mtok = 0.0
''')
    # This is a new ledger and cap, never the main checkout's live spend ledger.
    os.environ['BUDGET_CAP_USD']='25'
    roles=load_roles(config,cache_dir=Path('cache/glimmer'),ledger_path=OUT/'spend_ledger.jsonl')
    try:
        with remote.modal.enable_output(), remote.app.run():
            response=roles['glimmer_job'].complete(LLMRequest(role='glimmer_job',
                       prompt=json.dumps(payload),max_output_tokens=512,temperature=0.0))
        result=json.loads(response.text)
    except BaseException as error:
        cost.finish(stage,None,OUT/'cost.json',type(error).__name__)
        raise
    cost.finish(stage,result,OUT/'cost.json')
    if stage=='train':
        data=base64.b64decode(result.pop('archive_base64'))
        if hashlib.sha256(data).hexdigest()!=result['sha256']:
            raise ValueError('adapter archive hash mismatch')
        directory=OUT/'adapter'
        directory.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                if Path(member.filename).name!=member.filename:
                    raise ValueError('unexpected adapter archive path')
                (directory/member.filename).write_bytes(archive.read(member))
        _save('training_metrics.json',result)
        print('Training completed; adapter downloaded and hash-checked.',flush=True)
    else:
        outputs=result['outputs']
        if len(outputs)!=len(validation) or [r['index'] for r in outputs]!=list(range(len(validation))):
            raise ValueError('remote output indices differ from validation inputs')
        labels=[f['family'] for f in families]+['other']
        expected={row['page']:row['target'] for row in validation}
        predictions={row['page']:(INVALID if answer['at_token_limit'] else parse_answer(answer['text'],labels))
                     for row,answer in zip(validation,outputs,strict=True)}
        result['predictions']=[{'page':row['page'],'expected':row['target'],
                                'predicted':predictions[row['page']],**answer}
                               for row,answer in zip(validation,outputs,strict=True)]
        _save(f'{stage}_predictions.json',result)
        metrics=score(expected,predictions,labels)
        _save(f'{stage}_metrics.json',metrics)
        for comparator in ('spark_raw','spark_confirmed'):
            _save(f'{comparator}_metrics.json',score(expected,{r['page']:r[comparator] for r in validation},labels))
        print(json.dumps(metrics,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','baseline','train','trained'])
    args=parser.parse_args()
    run(args.stage)


if __name__=='__main__':
    main()
