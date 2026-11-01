"""Attention-only LoRA on the pinned BF16 base; imported inside the bounded GPU job."""
from __future__ import annotations
import hashlib
import io
import json
import random
import time
from pathlib import Path

MODEL='unsloth/Muse-Spark-Open-816B-A42B'
REVISION='49cade7b0c6ed297f0434229ac67eea5f9ae1220'
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


PROJECT_AGENT='archivist-hackathon/0.1 (+https://github.com/kamil-shirinov/Archivist); file_type/kernel'


def project_agent(request):
    request.headers['User-Agent']=PROJECT_AGENT


def configure_hub_requests():
    from huggingface_hub.utils._http import default_client_factory,set_client_factory
    def factory():
        client=default_client_factory()
        client.event_hooks['request'].append(project_agent)
        return client
    set_client_factory(factory)


def load_kernel():
    import re
    from kernels import get_kernel
    from transformers.integrations import hub_kernels
    configure_hub_requests()
    repo='kernels-community/finegrained-kernels'
    module=get_kernel(repo,revision='6ad75fc2a174a02bc1df3db98fe71768e0c8e682',
                      trust_remote_code=[repo],user_agent=PROJECT_AGENT)
    hub_kernels._KERNEL_MODULE_MAPPING['finegrained-kernels']=module
    file=Path(module.__file__)
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    found=re.search(r'/snapshots/([0-9a-f]{40})/',str(file))
    return {'repo':repo,'version':0,'entrypoint_sha256':digest,
            'revision':'6ad75fc2a174a02bc1df3db98fe71768e0c8e682'}


def kernel_gradient(config):
    fingerprint=load_kernel()
    import copy
    import torch
    from transformers.integrations.finegrained.core import FineGrainedExperts
    tiny=copy.deepcopy(config.text_config)
    tiny.moe_hidden_size=4096;tiny.moe_intermediate_size=4096;tiny.num_local_experts=4
    tiny._experts_implementation='eager'
    test=FineGrainedExperts(tiny,weight_format='nvfp4',activation_format='bf16').to('cuda:0')
    test.requires_grad_(False)
    with torch.no_grad():
        for name,p in test.named_parameters():
            p.fill_(0x22 if p.dtype==torch.int8 else 1)
    x=(torch.randn(16,4096,dtype=torch.bfloat16,device='cuda:0')*.01).requires_grad_(True)
    ids=torch.tensor([[0,1]]*16,device='cuda:0')
    weights=torch.full((16,2),.5,dtype=torch.bfloat16,device='cuda:0')
    y=test(x,ids,weights)
    y.float().sum().backward()
    if x.grad is None or not torch.isfinite(x.grad).all() or not x.grad.abs().max()>0:
        raise RuntimeError('Frozen NVFP4 experts do not propagate usable input gradients')
    return {'passed':True,'kernel':fingerprint,'max_input_gradient':float(x.grad.abs().max()),
            'method':'Synthetic input-gradient check; no archive target and no optimizer update'}


def bf16_gradient(config):
    import copy
    import torch
    from transformers.models.muse_spark.modeling_muse_spark import MuseSparkExperts
    tiny=copy.deepcopy(config.text_config)
    tiny.moe_hidden_size=128;tiny.moe_intermediate_size=128;tiny.num_local_experts=4
    tiny._experts_implementation='grouped_mm'
    test=MuseSparkExperts(tiny).to(device='cuda:0',dtype=torch.bfloat16)
    test.requires_grad_(False)
    with torch.no_grad():
        for p in test.parameters():p.normal_(0,.02)
    x=torch.randn(16,128,device='cuda:0',dtype=torch.bfloat16,requires_grad=True)
    ids=torch.tensor([[0,1]]*16,device='cuda:0')
    weights=torch.full((16,2),.5,device='cuda:0',dtype=torch.bfloat16)
    test(x,ids,weights).float().sum().backward()
    if x.grad is None or not torch.isfinite(x.grad).all() or not x.grad.abs().max()>0:
        raise ValueError('BF16 frozen expert input-gradient preflight failed')
    return {'passed':True,'method':'native BF16 grouped_mm expert input-gradient test',
            'max_input_gradient':float(x.grad.abs().max())}


def check_deadline(deadline):
    if deadline is not None and time.time()>=deadline:
        raise RuntimeError('Original experiment budget deadline reached; preserve committed checkpoints')


def generate(model,processor,items,images,path=None,commit=lambda:None,deadline=None):
    import torch
    model.eval();model.config.use_cache=True
    results=json.loads(path.read_text()) if path is not None and path.exists() else []
    for item in items[len(results) :]:
        check_deadline(deadline)
        batch=inputs(processor,item,images[item['image_index']])
        count=batch['input_ids'].shape[-1]
        if count+MAX_NEW>MAX_CONTEXT:
            raise ValueError('Validation prompt exceeds frozen context; do not truncate')
        batch=batch.to('cuda:0',dtype=torch.bfloat16)
        start=time.monotonic()
        with torch.inference_mode():
            generated=model.generate(**batch,max_new_tokens=MAX_NEW,do_sample=False)
        tokens=generated[0,count:]
        results.append({'text':processor.decode(tokens,skip_special_tokens=False),
                        'input_tokens':count,'output_tokens':len(tokens),
                        'seconds':time.monotonic()-start,'at_token_limit':len(tokens)==MAX_NEW})
        if path is not None:save(path,results);commit()
        print('Sparkft validation page',len(results),'of',len(items),flush=True)
    return results


def run(payload,images,PathRoot,commit=lambda:None):
    import torch
    from transformers import AutoConfig,AutoModelForMultimodalLM,AutoProcessor
    from peft import LoraConfig,PeftModel,get_peft_model
    from huggingface_hub import snapshot_download
    deadline=payload['budget_deadline_epoch'];check_deadline(deadline)
    started=time.monotonic();root=Path(PathRoot);directory=root/'experiment-v1'
    directory.mkdir(exist_ok=True)
    identity=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    manifest=directory/'identity.json'
    if manifest.exists() and json.loads(manifest.read_text())['sha256']!=identity:
        raise ValueError('Cannot resume a different frozen experiment')
    save(manifest,{'sha256':identity});commit()
    latest=directory/'latest.json'
    checkpoint=directory/json.loads(latest.read_text())['checkpoint'] if latest.exists() else None
    torch.manual_seed(3401)
    config=AutoConfig.from_pretrained(MODEL,revision=REVISION,local_files_only=True,token=False)
    diagnostic=bf16_gradient(config)
    save(directory/'gradient_preflight.json',diagnostic)
    processor=AutoProcessor.from_pretrained(MODEL,revision=REVISION,local_files_only=True,token=False)
    device_map={'':0,'lm_head':7,'model.language_model.norm':7}
    for layer in range(config.text_config.num_hidden_layers):
        device_map[f'model.language_model.layers.{layer}']=min(layer//8,7)
    model=AutoModelForMultimodalLM.from_pretrained(
        MODEL,revision=REVISION,local_files_only=True,token=False,dtype=torch.bfloat16,
        config=config,device_map=device_map,attn_implementation='sdpa',experts_implementation='grouped_mm')
    model.requires_grad_(False)
    from collections import Counter
    if any(p.device.type!='cuda' for p in model.parameters()):
        raise ValueError('Unexpected CPU or disk base-weight offload')
    save(directory/'loaded.json',{'actual_parameter_devices':dict(Counter(str(p.device) for p in model.parameters())),
         'actual_parameter_dtypes':dict(Counter(str(p.dtype) for p in model.parameters())),
         'quantized_module_classes':dict(Counter(type(m).__name__ for m in model.modules() if 'FineGrained' in type(m).__name__)),
         'model':MODEL,'revision':REVISION,'device_map':device_map,
         'gpu_names':[torch.cuda.get_device_name(i) for i in range(8)],
         'memory_allocated':[torch.cuda.memory_allocated(i) for i in range(8)]})
    base=generate(model,processor,payload['validation'],images,directory/'base_predictions.json',commit,deadline)
    save(directory/'base_predictions.json',base)
    train=[];excluded=[]
    for index,item in enumerate(payload['train']):
        try:
            train.append(encoded(processor,item,images[item['image_index']]))
        except ValueError as error:
            excluded.append({'index':index,'reason':str(error)})
    save(directory/'training_coverage.json',{'encoded':len(train),'excluded':excluded})
    if not train or excluded:
        raise ValueError('Every frozen training conversation must fit')
    targets=[n for n,_ in model.named_modules() if '.language_model.layers.' in n and '.self_attn.' in n
             and n.rsplit('.',1)[-1] in ('q_proj','k_proj','v_proj','o_proj')]
    if not targets:
        raise ValueError('No language attention projections found')
    model=(PeftModel.from_pretrained(model,checkpoint/'adapter',is_trainable=True) if checkpoint else
           get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,
                                         target_modules=targets,task_type='CAUSAL_LM',bias='none')))
    if any(p.requires_grad and 'lora_' not in n for n,p in model.named_parameters()):
        raise ValueError('A base parameter became trainable')
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.enable_input_require_grads();model.config.use_cache=False
    parameters=[p for p in model.parameters() if p.requires_grad]
    save(directory/'trainable.json',[{'name':n,'dtype':str(p.dtype),'device':str(p.device),'parameters':p.numel()}
         for n,p in model.named_parameters() if p.requires_grad])
    optimizer=torch.optim.AdamW(parameters,lr=.0002,weight_decay=0)
    log=[];rng=random.Random(3401);orders=[]
    for _ in range(1):
        order=list(range(len(train)));rng.shuffle(order);orders.append(order)
    if checkpoint:
        state=torch.load(checkpoint/'state.pt',weights_only=False,map_location='cpu')
        if state['identity']!=identity:raise ValueError('Checkpoint identity mismatch')
        optimizer.load_state_dict(state['optimizer']);log=state['log']
        torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state_all(state['cuda_rng'])
    completed=len(log);position=0
    for epoch,order in enumerate(orders):
        model.train()
        for name,module in model.named_modules():
            if name.rsplit('.',1)[-1] in ('vision_tower','audio_tower','vision_adapter','vision_projection'):
                module.eval()
        for start in range(0,len(order),8):
            position+=1
            if position<=completed:continue
            group=order[start:start+8];optimizer.zero_grad(set_to_none=True);losses=[]
            for index in group:
                check_deadline(deadline)
                batch={k:(v.to('cuda:0',dtype=torch.bfloat16) if v.is_floating_point() else v.to('cuda:0'))
                       for k,v in train[index].items()}
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
            step=directory/f'checkpoint-{len(log):03d}'
            step.mkdir(exist_ok=True)
            model.save_pretrained(step/'adapter',safe_serialization=True)
            torch.save({'identity':identity,'optimizer':optimizer.state_dict(),'log':log,
                        'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),
                        'orders':orders,'next_group':position},step/'state.pt')
            save(directory/'latest.pending.json',{'checkpoint':step.name,'completed_steps':len(log),
                                                 'identity':identity})
            (directory/'latest.pending.json').replace(latest)
            save(directory/'training_progress.json',log);commit()
            print('Sparkft optimizer step',len(log),'loss',log[-1]['mean_loss'],flush=True)
    model.save_pretrained(directory/'adapter',safe_serialization=True);commit()
    save(directory/'training_metrics.json',{'steps':log,'conversations':len(train),'target_modules':targets,
         'trainable_parameters':sum(p.numel() for p in parameters),'excluded':excluded})
    del optimizer
    model=model.unload()
    model=PeftModel.from_pretrained(model,directory/'adapter',is_trainable=False)
    tuned=generate(model,processor,payload['validation'],images,directory/'trained_predictions.json',commit,deadline)
    save(directory/'trained_predictions.json',tuned)
    artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (directory/'adapter').iterdir() if p.is_file()}
    result={'base':base,'trained':tuned,'adapter_files':artifacts,'gradient_preflight':diagnostic,
            'training':{'steps':len(log),'conversations':len(train),'excluded':excluded},
            'runtime_seconds':time.monotonic()-started,
            'peak_allocated_bytes':[torch.cuda.max_memory_allocated(i) for i in range(8)]}
    save(directory/'result.json',result)
    return result
