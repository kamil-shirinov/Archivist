"""Text-only batched inference for the prospective phase-2 configuration."""
from __future__ import annotations

import gc
import time

from archivist.models.glimmer_runtime import REMOTE, load_model, messages

BATCH_SIZE = 8
MAX_NEW_TOKENS = 512


def batch_generate(model, tokenizer, items):
    import torch
    model.eval()
    tokenizer.padding_side = 'left'
    lengths = []
    rendered = []
    for item in items:
        text = tokenizer.apply_chat_template(messages(item), tokenize=False,
                    add_generation_prompt=True, reasoning_strength='low')
        ids = tokenizer(text, add_special_tokens=False)['input_ids']
        if len(ids) + MAX_NEW_TOKENS > 4096:
            raise ValueError('phase-2 context overflow; never silently truncate')
        lengths.append(len(ids))
        rendered.append(text)
    ordered = sorted(range(len(items)), key=lambda i: (lengths[i], i))
    outputs = []
    eos = model.generation_config.eos_token_id
    end_ids = set(eos if isinstance(eos, (list, tuple)) else [eos])
    for start in range(0, len(ordered), BATCH_SIZE):
        indices = ordered[start:start + BATCH_SIZE]
        inputs = tokenizer([rendered[i] for i in indices], padding=True,
                           add_special_tokens=False, return_tensors='pt').to(model.device)
        width = inputs.input_ids.shape[-1]
        begin = time.monotonic()
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                       pad_token_id=tokenizer.pad_token_id)
        seconds = time.monotonic() - begin
        for ref, sequence in zip(indices, generated[:, width:], strict=True):
            ids = sequence.tolist()
            end = next((i + 1 for i, token in enumerate(ids) if token in end_ids), None)
            answer_ids = ids[:end] if end is not None else ids
            outputs.append({
                'index': ref, 'text': tokenizer.decode(answer_ids, skip_special_tokens=False),
                'input_tokens': lengths[ref], 'output_tokens': len(answer_ids),
                'at_token_limit': end is None and len(answer_ids) >= MAX_NEW_TOKENS,
                'batch_seconds': seconds, 'batch_size': len(indices),
            })
        del generated, inputs
        print(f'Batch {start // BATCH_SIZE + 1}: {len(indices)} pages complete', flush=True)
    return sorted(outputs, key=lambda row: row['index'])


def benchmark(payload):
    """One load, both arms, development inputs only as attested by the checked local driver."""
    import torch
    from peft import PeftModel
    if payload.get('development_only') is not True:
        raise ValueError('this entrypoint accepts development benchmarking only')
    start = time.monotonic()
    model, tokenizer = load_model()
    if next(model.parameters()).device.type != 'cuda':
        raise ValueError('CPU offload is not an allowed phase-2 configuration')
    result = {
        'gpu': torch.cuda.get_device_name(0), 'gpu_total_bytes': torch.cuda.get_device_properties(0).total_memory,
        'model_footprint_bytes': model.get_memory_footprint(),
        'batch_size': BATCH_SIZE, 'max_new_tokens': MAX_NEW_TOKENS,
        'arm_results': {},
    }
    for arm in ('untrained', 'trained'):
        if arm == 'trained':
            gc.collect()
            torch.cuda.empty_cache()
            model = PeftModel.from_pretrained(model, REMOTE / 'adapters' / payload['dataset_id'],
                                              is_trainable=False)
        torch.cuda.reset_peak_memory_stats()
        begin = time.monotonic()
        outputs = batch_generate(model, tokenizer, payload['items'])
        result['arm_results'][arm] = {
            'outputs': outputs, 'runtime_seconds': time.monotonic() - begin,
            'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
            'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
        }
    result['runtime_seconds'] = time.monotonic() - start
    return result
