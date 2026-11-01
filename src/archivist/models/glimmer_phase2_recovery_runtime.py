"""Resume only missing raw batches. All model/input/generation settings stay frozen."""
from __future__ import annotations

import gc
import hashlib
import json
import re
import time

from archivist.models.glimmer_runtime import REMOTE,load_model
from archivist.models.glimmer_batch import batch_generate,precision_record
from archivist.models.glimmer_checkpoints import run_arm


def recover(payload):
    import torch
    from peft import PeftModel
    from archivist.models.glimmer_image import volume
    if payload.get('owner_authorised_recovery') is not True or len(payload['items'])!=791:
        raise ValueError('only the authorised frozen phase-2 recovery')
    if not re.fullmatch('[0-9a-f]{64}',payload['sample_sha256']):
        raise ValueError('invalid frozen sample identity')
    adapter=REMOTE/'adapters'/payload['dataset_id']
    if hashlib.sha256((adapter/'adapter_model.safetensors').read_bytes()).hexdigest()!=payload['adapter_sha256']:
        raise ValueError('adapter differs from phase 1')
    output=REMOTE/'phase2_recovery'/payload['sample_sha256']
    output.mkdir(parents=True,exist_ok=True)
    identity={key:payload[key] for key in ('sample_sha256','input_sha256','adapter_sha256','recovery_code_id')}
    start=time.monotonic()
    model,tokenizer=load_model()
    result={'gpu':torch.cuda.get_device_name(0),'gpu_total_bytes':torch.cuda.get_device_properties(0).total_memory,
        'model_footprint_bytes':model.get_memory_footprint(),'sample_sha256':payload['sample_sha256'],
        'input_sha256':payload['input_sha256'],'batch_size':8,'ocr_prefix_chars':1024,
        'max_new_tokens':512,'arm_results':{}}
    for arm in ('untrained','trained'):
        if arm=='trained':
            gc.collect()
            torch.cuda.empty_cache()
            model=PeftModel.from_pretrained(model,adapter,is_trainable=False)
        precision=precision_record(model)
        torch.cuda.reset_peak_memory_stats()
        begin=time.monotonic()
        print(f'Starting recovery arm {arm}',flush=True)
        answers,checkpoint_counts=run_arm(payload['items'],tokenizer,model,output/arm,
            {**identity,'arm':arm},generate=batch_generate,persist=volume.commit)
        record={'outputs':answers,'runtime_seconds':time.monotonic()-begin,
            'precision':precision,'checkpoint_counts':checkpoint_counts,
            'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
            'peak_reserved_bytes':torch.cuda.max_memory_reserved(),
            'free_and_total_memory_bytes':list(torch.cuda.mem_get_info())}
        result['arm_results'][arm]=record
        (output/f'{arm}_raw.json').write_text(json.dumps(record,indent=2)+'\n')
        volume.commit()
    result['runtime_seconds']=time.monotonic()-start
    (output/'paired_raw.json').write_text(json.dumps(result,indent=2)+'\n')
    volume.commit()
    return result
