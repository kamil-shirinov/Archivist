"""Atomic batch checkpoints around the unchanged Glimmer generator; no answer parsing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from archivist.models.glimmer_runtime import messages


def digest(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def batch_plan(items,tokenizer):
    lengths=[]
    for item in items:
        rendered=tokenizer.apply_chat_template(messages(item),tokenize=False,
            add_generation_prompt=True,reasoning_strength='low')
        length=len(tokenizer(rendered,add_special_tokens=False)['input_ids'])
        if length+512>4096:
            raise ValueError('frozen context exceeds original limit')
        lengths.append(length)
    ordered=sorted(range(len(items)),key=lambda i:(lengths[i],i))
    return [ordered[start:start+8] for start in range(0,len(ordered),8)],lengths


def read_batch(path,identity,indices,lengths):
    record=json.loads(path.read_text())
    checksum=record.pop('sha256')
    if digest(record)!=checksum or record['identity']!=identity or record['indices']!=indices:
        raise ValueError('checkpoint integrity, inputs or original batch membership differs')
    outputs=record['outputs']
    if sorted(r['index'] for r in outputs)!=sorted(indices):
        raise ValueError('checkpoint is not a complete original batch')
    for row in outputs:
        if row['input_tokens']!=lengths[row['index']]:
            raise ValueError('checkpoint tokenization differs from the frozen setup')
    return outputs


def run_arm(items,tokenizer,model,directory:Path,identity,*,generate,persist=lambda:None):
    """Reuse complete original batches; generate only absent batches, at their old boundaries.

    A new subset is supplied in ascending ORIGINAL index order. The unchanged generator
    sorts it by token length and relative index, yielding the exact same padded tensor
    order and width as its group in the original full-sample invocation.
    """
    batches,lengths=batch_plan(items,tokenizer)
    directory.mkdir(parents=True,exist_ok=True)
    outputs=[]
    reused=generated=0
    # Validate every saved batch before the first new generation call.
    saved={}
    for number,indices in enumerate(batches):
        path=directory/f'batch_{number:03d}.json'
        if path.exists():
            saved[number]=read_batch(path,identity,indices,lengths)
    for number,indices in enumerate(batches):
        if number in saved:
            outputs.extend(saved[number])
            reused+=1
            continue
        original_indices=sorted(indices)
        answers=generate(model,tokenizer,[items[i] for i in original_indices])
        if sorted(r['index'] for r in answers)!=list(range(len(original_indices))):
            raise ValueError('generator returned an incomplete batch')
        mapped=[{**row,'index':original_indices[row['index']]} for row in answers]
        record={'identity':identity,'indices':indices,'outputs':mapped}
        record['sha256']=digest(record)
        path=directory/f'batch_{number:03d}.json'
        if path.exists():
            raise ValueError('refusing to overwrite a completed batch')
        temporary=path.with_suffix('.partial')
        temporary.write_text(json.dumps(record,indent=2)+'\n')
        temporary.replace(path)
        persist()  # Publish the full atomic batch to Modal Volume before proceeding.
        outputs.extend(mapped)
        generated+=1
        print(f'Checkpointed batch {number+1}/{len(batches)}: {len(mapped)} raw answers',flush=True)
    return sorted(outputs,key=lambda r:r['index']),{'reused_batches':reused,'new_batches':generated,
        'complete_batches':len(batches)}
