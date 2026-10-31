"""Task-owned, bounded Modal resources. Import never launches a job."""
import modal

MODEL = 'unsloth/Muse-Spark-Open-816B-A42B'
REVISION = '49cade7b0c6ed297f0434229ac67eea5f9ae1220'
TRANSFORMERS = '585946e8dbfc114a5f45e62b41e35a468e9e85b9'
VOLUME_NAME = 'archivist-sparkft-p34-v1'
UA = 'archivist-hackathon/0.1 (+https://github.com/kamil-shirinov/Archivist)'
ROOT = '/sparkft-store'

app = modal.App('archivist-sparkft-p34-runtime')
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (modal.Image.debian_slim(python_version='3.12')
    .apt_install('git')
    .pip_install('torch==2.15.0', 'torchvision==0.29.2', 'peft==0.21.2', 'accelerate==1.15.0',
                 'safetensors==0.8.0', 'pillow==13.0.0', 'kernels==0.17.2',
                 'huggingface_hub==2.4.0',
                 'git+https://github.com/huggingface/transformers.git@' + TRANSFORMERS)
    .env({'HF_HOME': ROOT + '/hf', 'HF_HUB_DISABLE_TELEMETRY': '1',
          'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1', 'DO_NOT_TRACK': '1',
          'TOKENIZERS_PARALLELISM': 'false', 'WANDB_DISABLED': 'true',
          'TRANSFORMERS_DISABLE_DEEPGEMM_LINEAR': '1'})
    .add_local_python_source('sparkft'))
COMMON = dict(image=image, volumes={ROOT: volume}, retries=0, max_containers=1,
              min_containers=0, scaledown_window=5)


@app.function(**COMMON, cpu=(8,8), memory=(65536,65536), timeout=1800, startup_timeout=60)
def prepare(download_weights=False):
    import hashlib
    import importlib.metadata
    import json
    import time
    from pathlib import Path
    from huggingface_hub import hf_hub_download, snapshot_download
    from transformers import AutoConfig, AutoProcessor
    start = time.monotonic()
    path = snapshot_download(MODEL, revision=REVISION, token=False,
                             allow_patterns=['*.json','*.jinja','l4_200k_base','tokenizer*',
                                             'LICENSE.md','USE_POLICY.md'],
                             headers={'User-Agent': UA})
    config = AutoConfig.from_pretrained(path, local_files_only=True)
    processor = AutoProcessor.from_pretrained(path, local_files_only=True)
    licence = (Path(path)/'LICENSE.md').read_text()
    if 'fine-tune' not in licence or 'MUSE MODEL LICENSE' not in licence:
        raise ValueError('Unexpected mirror licence; do not download weights')
    from transformers.integrations.finegrained.core import FineGrainedExperts
    result = {'model': MODEL, 'revision': REVISION,
              'architecture': config.architectures, 'processor':type(processor).__name__,
              'expert_class': FineGrainedExperts.__name__,
              'licence_sha256':hashlib.sha256(licence.encode()).hexdigest(),
              'versions':{p:importlib.metadata.version(p) for p in
                          ['torch','transformers','peft','accelerate','kernels','huggingface_hub']},
              'download_weights':download_weights}
    if download_weights:
        path = snapshot_download(MODEL, revision=REVISION, token=False,
                                 headers={'User-Agent': UA}, max_workers=16)
        result['weight_shards'] = len(list(Path(path).glob('*.safetensors')))
    result['runtime_seconds'] = time.monotonic()-start
    Path(ROOT,'preparation.json').write_text(json.dumps(result,indent=2)+'\n')
    volume.commit()
    return result


@app.function(**COMMON, gpu='B300:8', cpu=(16,16), memory=(262144,262144),
              timeout=4700, startup_timeout=300)
def experiment(payload, images):
    from sparkft.runtime import run
    try:
        return run(payload, images, PathRoot=ROOT, commit=volume.commit)
    finally:
        volume.commit()


@app.function(**COMMON, cpu=(1,1), memory=(2048,2048), timeout=120, startup_timeout=60)
def cleanup_base():
    import shutil
    from pathlib import Path
    shutil.rmtree(Path(ROOT,'hf'), ignore_errors=True)
    volume.commit()
    return {'base_cache_removed': not Path(ROOT,'hf').exists(), 'adapter_preserved':True}


@app.function(**COMMON, cpu=(8,8), memory=(65536,65536), timeout=900, startup_timeout=60)
def tokenize(payload, images):
    from transformers import AutoProcessor
    from sparkft.runtime import MODEL,REVISION,encoded,inputs,MAX_CONTEXT,MAX_NEW
    processor=AutoProcessor.from_pretrained(MODEL,revision=REVISION,token=False,local_files_only=True)
    train=[]
    for item in payload['train']:
        batch=encoded(processor,item,images[item['image_index']])
        train.append(int(batch['input_ids'].shape[-1]))
    val=[]
    for item in payload['validation']:
        batch=inputs(processor,item,images[item['image_index']])
        length=int(batch['input_ids'].shape[-1])
        if length+MAX_NEW>MAX_CONTEXT:
            raise ValueError('Validation exceeds prospective context; no silent truncation')
        val.append(length)
    result={'training_lengths':train,'validation_lengths':val,
            'processor':type(processor).__name__,'max_context':MAX_CONTEXT,'max_new_tokens':MAX_NEW}
    return result


@app.function(**COMMON, gpu='B300', cpu=(4,4), memory=(16384,16384),
              timeout=600, startup_timeout=60)
def gradient_probe(config_dict):
    from transformers import AutoConfig
    from sparkft.runtime import kernel_gradient
    config_dict=dict(config_dict)
    model_type=config_dict.pop('model_type')
    config=AutoConfig.for_model(model_type,**config_dict)
    return kernel_gradient(config)



@app.function(**COMMON, cpu=(1,1), memory=(2048,2048), timeout=120, startup_timeout=60)
def kernel_transport():
    from sparkft.runtime import configure_hub_requests,PROJECT_AGENT
    from kernels import get_kernel
    configure_hub_requests()
    try:
        module=get_kernel('kernels-community/finegrained-kernels',version=0,backend='cpu',
                          check_arch=False,trust_remote_code=['kernels-community/finegrained-kernels'],
                          user_agent=PROJECT_AGENT)
        return {'status':'loaded','module':module.__name__}
    except Exception as error:
        return {'status':'exception','type':type(error).__name__,'message':str(error)}
