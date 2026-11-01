"""Remote model implementation for P31; imported only inside a bounded Modal job."""
from __future__ import annotations

import gc
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

from archivist.models.glimmer_access import MODEL, REVISION

REMOTE = Path('/archivist/results/glimmer/remote')


def load_model():
    import torch
    from transformers import AutoModelForMultimodalLM, AutoTokenizer, BitsAndBytesConfig
    model = AutoModelForMultimodalLM.from_pretrained(
        MODEL, revision=REVISION, token=False, local_files_only=True,
        dtype=torch.bfloat16, device_map={'':0}, attn_implementation='sdpa',
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_storage=torch.bfloat16),
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, token=False, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return model, tokenizer


def messages(item):
    return [{'role':'system','content':item['system']}, {'role':'user','content':item['prompt']}]


def generate(model, tokenizer, items):
    import torch
    model.eval()
    outputs=[]
    for i,item in enumerate(items):
        rendered=tokenizer.apply_chat_template(messages(item),tokenize=False,
                    add_generation_prompt=True,reasoning_strength='low')
        inputs=tokenizer(rendered,return_tensors='pt',add_special_tokens=False).to(model.device)
        if inputs.input_ids.shape[-1] + 512 > 4096:
            raise ValueError('frozen OCR prompt exceeds 4096-token context; do not truncate silently')
        started=time.monotonic()
        with torch.inference_mode():
            output=model.generate(**inputs,max_new_tokens=512,do_sample=False,
                                  pad_token_id=tokenizer.pad_token_id)
        generated=output[0,inputs.input_ids.shape[-1]:]
        outputs.append({'index':i,'text':tokenizer.decode(generated,skip_special_tokens=False),
                        'input_tokens':inputs.input_ids.shape[-1], 'output_tokens':len(generated),
                        'seconds':time.monotonic()-started, 'at_token_limit':len(generated)==512})
        print(f'Inference {i+1}/{len(items)} completed',flush=True)
    return outputs


def encode_training(tokenizer, items):
    encoded=[]
    for item in items:
        turns=messages(item)
        prefix=tokenizer.apply_chat_template(turns,tokenize=False,add_generation_prompt=True,
                                             reasoning_strength='low')
        complete=tokenizer.apply_chat_template(turns+[{'role':'assistant','content':item['target']}],
                                               tokenize=False,add_generation_prompt=False,
                                               reasoning_strength='low')
        prefix_ids=tokenizer(prefix,add_special_tokens=False)['input_ids']
        ids=tokenizer(complete,add_special_tokens=False)['input_ids']
        if ids[:len(prefix_ids)] != prefix_ids:
            raise ValueError('chat template does not preserve the generation prefix')
        if len(ids)>4096 or len(ids)<=len(prefix_ids):
            raise ValueError('training target missing or example longer than 4096 tokens')
        encoded.append({'input_ids':ids,'attention_mask':[1]*len(ids),
                        'labels':[-100]*len(prefix_ids)+ids[len(prefix_ids):]})
    return encoded


def train_adapter(model,tokenizer,items,dataset_id):
    import torch
    from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training
    from transformers import Trainer,TrainingArguments,default_data_collator,set_seed
    set_seed(3101)
    encoded=encode_training(tokenizer,items)
    model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True)
    model.config.use_cache=False
    targets=[name for name,_ in model.named_modules()
             if name.rsplit('.',1)[-1] in ('q_proj','k_proj','v_proj','o_proj')
             and not any(part in name.lower() for part in ('vision','visual','projector'))]
    if not targets:
        raise ValueError('no language attention projections found')
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,
                         target_modules=targets,task_type='CAUSAL_LM',bias='none'))
    if any(p.requires_grad for n,p in model.named_parameters() if 'lora_' not in n):
        raise ValueError('a non-adapter parameter is trainable')
    directory=REMOTE/'adapters'/dataset_id
    if directory.exists():
        raise ValueError('adapter already exists; refusing to train again')
    trainer=Trainer(model=model,train_dataset=encoded,data_collator=default_data_collator,
        args=TrainingArguments(output_dir=str(REMOTE/'training'/dataset_id),
            num_train_epochs=3,per_device_train_batch_size=1,gradient_accumulation_steps=8,
            learning_rate=2e-4,bf16=True,seed=3101,data_seed=3101,logging_steps=5,
            save_strategy='no',eval_strategy='no',report_to='none',gradient_checkpointing=True,
            optim='adamw_torch',dataloader_num_workers=0))
    result=trainer.train()
    for name, parameter in model.named_parameters():
        if "lora_" in name:
            parameter.data = parameter.data.to(torch.bfloat16)
    model.save_pretrained(directory,safe_serialization=True)
    # Tokenizer remains pinned at the base revision; do not redistribute base weights.
    metrics={**result.metrics,'target_modules':targets,
             'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),
             'encoded_examples':len(encoded),'max_training_tokens':max(len(r['input_ids']) for r in encoded)}
    (directory/'training_metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    del trainer, model
    gc.collect()
    torch.cuda.empty_cache()
    return directory,metrics


def adapter_archive(directory):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(directory.iterdir()):
            if file.is_file():
                archive.writestr(file.name,file.read_bytes())
    data=buffer.getvalue()
    return {'archive':data,'sha256':hashlib.sha256(data).hexdigest()}


def run(stage,payload):
    start=time.monotonic()
    import torch
    from peft import PeftModel
    model,tokenizer=load_model()
    result={'stage':stage,'model':MODEL,'revision':REVISION,'gpu':torch.cuda.get_device_name(0)}
    if stage=='train':
        directory,metrics=train_adapter(model,tokenizer,payload['items'],payload['dataset_id'])
        result.update(training=metrics,**adapter_archive(directory))
    else:
        if stage=='trained':
            directory=REMOTE/'adapters'/payload['dataset_id']
            model=PeftModel.from_pretrained(model,directory,is_trainable=False)
            result['adapter_config_sha256']=hashlib.sha256((directory/'adapter_config.json').read_bytes()).hexdigest()
        result['outputs']=generate(model,tokenizer,payload['items'])
    result['runtime_seconds']=time.monotonic()-start
    result['peak_allocated_bytes']=torch.cuda.max_memory_allocated()
    return result
