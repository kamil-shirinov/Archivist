"""Pinned image and volume shared by separate CPU and GPU apps."""
import modal

volume=modal.Volume.from_name('archivist-glimmer-p31',create_if_missing=True)
image=(modal.Image.debian_slim(python_version='3.12')
       .pip_install('torch==2.15.0','transformers==5.22.1','peft==0.21.2',
                    'bitsandbytes==0.50.2','accelerate==1.15.0','safetensors==0.8.0',
                    'pydantic==2.14.1','openai==3.38.0','python-dotenv==1.2.4',
                    'meta-sam-parser==0.1.0','pillow==13.0.0')
       .env({'HF_HOME':'/archivist/results/glimmer/remote/hf',
             'HF_HUB_DISABLE_TELEMETRY':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1',
             'DO_NOT_TRACK':'1','WANDB_DISABLED':'true','TOKENIZERS_PARALLELISM':'false'})
       .add_local_python_source('archivist.models','archivist.schema'))
COMMON=dict(image=image,volumes={'/archivist/results/glimmer/remote':volume},
            retries=0,max_containers=1,scaledown_window=2,cpu=(4,4),memory=(65536,65536))
