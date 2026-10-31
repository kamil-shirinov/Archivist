"""Read-only integrity check of this task's public model-cache links."""
import json
from pathlib import Path
from decimal import Decimal
from sparkft.modal_app import app,COMMON,ROOT,volume
from sparkft.cloud import OUT,append_event,require_owned,wait


@app.function(**COMMON,cpu=(1,1),memory=(2048,2048),timeout=120,startup_timeout=60)
def probe():
    import os
    root=Path(ROOT,'hf/hub/models--unsloth--Muse-Spark-Open-816B-A42B/blobs')
    rows=[]
    for path in root.iterdir():
        resolved=path.resolve()
        rows.append({'name':path.name,'symlink':path.is_symlink(),
                     'target':os.readlink(path) if path.is_symlink() else None,
                     'exists':resolved.exists(),'bytes':resolved.stat().st_size if resolved.exists() else None})
    return {'entries':rows,'resolved_bytes':sum(r['bytes'] or 0 for r in rows),
            'large_files':sum((r['bytes'] or 0)>10**9 for r in rows)}


def main():
    path=OUT/'budget.json';data=json.loads(path.read_text())
    amount=Decimal('0.00342030')
    if sum(Decimal(x['ceiling_usd']) for x in data['cpu_attempts'])+amount>4:
        raise ValueError('CPU preparation subcap exhausted')
    if any(x['stage']=='cache_integrity' for x in data['cpu_attempts']):
        raise ValueError('Cache integrity probe already reserved')
    data['cpu_attempts'].append({'stage':'cache_integrity','ceiling_usd':str(amount),'retained':True})
    path.write_text(json.dumps(data,indent=2)+'\n')
    with app.run(name='archivist-sparkft-p34-cache-integrity',detach=True):
        append_event({'event':'started','app_id':app.app_id,'stage':'cache_integrity'})
        call=probe.spawn()
        result=wait(call,'cache integrity')
        (OUT/'cache_integrity.json').write_text(json.dumps(result,indent=2)+'\n')
        require_owned(app.app_id)
        append_event({'event':'run_context_exiting','app_id':app.app_id,'stage':'cache_integrity'})
        print('Resolved cache:',result['large_files'],'large files;',result['resolved_bytes'],'bytes',flush=True)


if __name__=='__main__':main()
