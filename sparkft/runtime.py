"""Attention-only LoRA on the pinned NVFP4 base; imported inside the bounded GPU job."""
from __future__ import annotations
import hashlib
import io
import json
import random
import time
from pathlib import Path

MODEL='unsloth/Muse-Spark-Open-816B-A42B-NVFP4'
REVISION='fc6908f53c6882d4ec48fca5ba144e41d21e1f92'
MAX_CONTEXT=16384
MAX_NEW=4096


def save(path, data):
    path.write_text(json.dumps(data,indent=2)+'\n')


def inputs(processor,item,image,answer=False):
    from PIL import Image
    turns=[{'role':'system','content':item['system']},
           {'role':'user','content':[{'type':'image','image':Image.open(io.BytesIO(image)).convert('RGB')},
                                    {'type':'text','text':item['prompt']}]}]
    if answer:
        turns.append({'role':'assistant','content':json.dumps(item['target'],separators=(',',':'))})
    return processor.apply_chat_template(turns,reasoning_effort='low',add_generation_prompt=not answer,
                                         tokenize=True,return_dict=True,return_tensors='pt')


def encoded(processor,item,image):
    import torch
    prefix=inputs(processor,item,image)
    complete=inputs(processor,item,image,answer=True)
    count=prefix['input_ids'].shape[-1]
    ids=complete['input_ids']
    if ids.shape[-1]>MAX_CONTEXT or ids.shape[-1]<=count:
        raise ValueError('Training conversation exceeds frozen context or has no target')
    if not torch.equal(ids[:,:count],prefix['input_ids']):
        raise ValueError('Processor does not preserve the native generation prefix')
    labels=ids.clone();labels[:,:count]=-100
    complete['labels']=labels
    return complete


def kernel_gradient(config):
    import copy
    import torch
    from transformers.integrations.finegrained.core import FineGrainedExperts
    tiny=copy.deepcopy(config.text_config)
    tiny.moe_hidden_size=128;tiny.moe_intermediate_size=128;tiny.num_local_experts=4
    tiny._experts_implementation='eager'
    test=FineGrainedExperts(tiny,weight_format='nvfp4',activation_format='nvfp4').to('cuda:0')
    test.requires_grad_(False)
    with torch.no_grad():
        for name,p in test.named_parameters():
            p.fill_(0x22 if p.dtype==torch.int8 else 1)
    x=torch.randn(16,128,dtype=torch.bfloat16,device='cuda:0',requires_grad=True)
    ids=torch.tensor([[0,1]]*16,device='cuda:0')
    weights=torch.full((16,2),.5,dtype=torch.bfloat16,device='cuda:0')
    y=test(x,ids,weights)
    y.float().sum().backward()
    if x.grad is None or not torch.isfinite(x.grad).all() or not x.grad.abs().max()>0:
        raise RuntimeError('Frozen NVFP4 experts do not propagate usable input gradients')
    return {'passed':True,'max_input_gradient':float(x.grad.abs().max()),
            'method':'Synthetic input-gradient check; no archive target and no optimizer update'}


def generate(model,processor,items,images):
    import torch
    model.eval();model.config.use_cache=True
    results=[]
    for item in items:
        batch=inputs(processor,item,images[item['image_index']])
        count=batch['input_ids'].shape[-1]
        if count+MAX_NEW>MAX_CONTEXT:
            raise ValueError('Validation prompt exceeds frozen context; do not truncate')
        batch=batch.to('cuda:0')
        start=time.monotonic()
        with torch.inference_mode():
            generated=model.generate(**batch,max_new_tokens=MAX_NEW,do_sample=False)
        tokens=generated[0,count:]
        results.append({'text':processor.decode(tokens,skip_special_tokens=False),
                        'input_tokens':count,'output_tokens':len(tokens),
                        'seconds':time.monotonic()-start,'at_token_limit':len(tokens)==MAX_NEW})
    return results


def run(payload,images,PathRoot):
    import torch
    from transformers import AutoConfig,AutoModelForMultimodalLM,AutoProcessor
    from peft import LoraConfig,PeftModel,get_peft_model
    from huggingface_hub import snapshot_download
    started=time.monotonic();root=Path(PathRoot);directory=root/'experiment-v1'
    directory.mkdir(exist_ok=True)
    if (directory/'adapter').exists():
        raise ValueError('Adapter already exists; refuse another training run')
    torch.manual_seed(3401)
    config=AutoConfig.from_pretrained(MODEL,revision=REVISION,local_files_only=True,token=False)
    diagnostic=kernel_gradient(config)
    save(directory/'gradient_preflight.json',diagnostic)
    processor=AutoProcessor.from_pretrained(MODEL,revision=REVISION,local_files_only=True,token=False)
    device_map={'':0,'lm_head':3,'model.language_model.norm':3}
    for layer in range(config.text_config.num_hidden_layers):
        device_map[f'model.language_model.layers.{layer}']=min(layer//16,3)
    model=AutoModelForMultimodalLM.from_pretrained(
        MODEL,revision=REVISION,local_files_only=True,token=False,dtype=torch.bfloat16,
        device_map=device_map,attn_implementation='sdpa',experts_implementation='eager')
    model.requires_grad_(False)
    save(directory/'loaded.json',{'model':MODEL,'revision':REVISION,'device_map':device_map,
         'gpu_names':[torch.cuda.get_device_name(i) for i in range(4)],
         'memory_allocated':[torch.cuda.memory_allocated(i) for i in range(4)]})
    base=generate(model,processor,payload['validation'],images)
    save(directory/'base_predictions.json',base)
    train=[];excluded=[]
    for index,item in enumerate(payload['train']):
        try:
            train.append(encoded(processor,item,images[item['image_index']]))
        except ValueError as error:
            excluded.append({'index':index,'reason':str(error)})
    save(directory/'training_coverage.json',{'encoded':len(train),'excluded':excluded})
    if not train:
        raise ValueError('No training conversations fit')
    targets=[n for n,_ in model.named_modules() if '.language_model.layers.' in n and '.self_attn.' in n
             and n.rsplit('.',1)[-1] in ('q_proj','k_proj','v_proj','o_proj')]
    if not targets:
        raise ValueError('No language attention projections found')
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,
                                         target_modules=targets,task_type='CAUSAL_LM',bias='none'))
    if any(p.requires_grad and 'lora_' not in n for n,p in model.named_parameters()):
        raise ValueError('A base parameter became trainable')
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.enable_input_require_grads();model.config.use_cache=False
    parameters=[p for p in model.parameters() if p.requires_grad]
    optimizer=torch.optim.AdamW(parameters,lr=.0002,weight_decay=0)
    log=[];rng=random.Random(3401)
    for epoch in range(3):
        order=list(range(len(train)));rng.shuffle(order)
        model.train()
        for start in range(0,len(order),8):
            group=order[start:start+8];optimizer.zero_grad(set_to_none=True);losses=[]
            for index in group:
                batch={k:v.to('cuda:0') for k,v in train[index].items()}
                loss=model(**batch,use_cache=False).loss
                if not torch.isfinite(loss):
                    raise ValueError('Non-finite training loss')
                (loss/len(group)).backward();losses.append(float(loss.detach()))
            grads=[p.grad for p in parameters if p.grad is not None]
            if not grads or any(not torch.isfinite(g).all() for g in grads):
                raise ValueError('Missing or non-finite LoRA gradients')
            if not any(g.abs().max()>0 for g in grads):
                raise ValueError('All adapter gradients are zero')
            torch.nn.utils.clip_grad_norm_(parameters,1)
            optimizer.step()
            log.append({'epoch':epoch+1,'step':len(log)+1,'mean_loss':sum(losses)/len(losses),
                        'elapsed_s':time.monotonic()-started})
            save(directory/'training_progress.json',log)
            print('Sparkft optimizer step',len(log),'loss',log[-1]['mean_loss'],flush=True)
    model.save_pretrained(directory/'adapter',safe_serialization=True)
    save(directory/'training_metrics.json',{'steps':log,'conversations':len(train),'target_modules':targets,
         'trainable_parameters':sum(p.numel() for p in parameters),'excluded':excluded})
    del optimizer
    model=model.unload()
    model=PeftModel.from_pretrained(model,directory/'adapter',is_trainable=False)
    tuned=generate(model,processor,payload['validation'],images)
    save(directory/'trained_predictions.json',tuned)
    artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (directory/'adapter').iterdir() if p.is_file()}
    result={'base':base,'trained':tuned,'adapter_files':artifacts,'gradient_preflight':diagnostic,
            'training':{'steps':len(log),'conversations':len(train),'excluded':excluded},
            'runtime_seconds':time.monotonic()-started,
            'peak_allocated_bytes':[torch.cuda.max_memory_allocated(i) for i in range(4)]}
    save(directory/'result.json',result)
    return result
