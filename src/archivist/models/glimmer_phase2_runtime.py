"""Frozen phase-2 paired inference; no reference labels or comparisons on the GPU."""
from __future__ import annotations

import gc
import hashlib
import json
import time

from archivist.models.glimmer_batch import batch_generate, precision_record
from archivist.models.glimmer_runtime import REMOTE, load_model


def paired_inference(payload):
    import torch
    from peft import PeftModel
    if payload.get('phase2_authorized') is not True or len(payload['items']) != 791:
        raise ValueError('only the explicitly authorised, frozen 791-input phase-2 run')
    adapter = REMOTE/'adapters'/payload['dataset_id']
    if hashlib.sha256((adapter/'adapter_model.safetensors').read_bytes()).hexdigest() != payload['adapter_sha256']:
        raise ValueError('saved adapter differs from phase 1')
    output = REMOTE/'phase2'/payload['sample_sha256']
    if output.exists():
        raise ValueError('phase-2 run already exists; no GPU retry')
    output.mkdir(parents=True)
    start = time.monotonic()
    model,tokenizer=load_model()
    result={'gpu':torch.cuda.get_device_name(0),
        'gpu_total_bytes':torch.cuda.get_device_properties(0).total_memory,
        'model_footprint_bytes':model.get_memory_footprint(),
        'sample_sha256':payload['sample_sha256'], 'input_sha256':payload['input_sha256'],
        'batch_size':8,'ocr_prefix_chars':1024,'max_new_tokens':512,
        'arm_results':{}}
    def persist(name,record):
        (output/name).write_text(json.dumps(record,indent=2)+'\n')
        from archivist.models.glimmer_image import volume
        volume.commit()
    for arm in ('untrained','trained'):
        if arm=='trained':
            gc.collect()
            torch.cuda.empty_cache()
            model=PeftModel.from_pretrained(model,adapter,is_trainable=False)
        before=precision_record(model)
        torch.cuda.reset_peak_memory_stats()
        begin=time.monotonic()
        print(f'Starting {arm} arm: 791 frozen inputs',flush=True)
        outputs=batch_generate(model,tokenizer,payload['items'])
        record={'outputs':outputs,'runtime_seconds':time.monotonic()-begin,
            'precision':before, 'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
            'peak_reserved_bytes':torch.cuda.max_memory_reserved(),
            'free_and_total_memory_bytes':list(torch.cuda.mem_get_info())}
        result['arm_results'][arm]=record
        persist(f'{arm}_raw.json',record)
        print(f'{arm} arm saved: {len(outputs)} raw answers; no comparison',flush=True)
    result['runtime_seconds']=time.monotonic()-start
    persist('paired_raw.json',result)
    return result
