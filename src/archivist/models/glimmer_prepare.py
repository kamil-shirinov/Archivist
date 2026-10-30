"""CPU-only checkpoint and tokenization checks; does not register any GPU functions."""
import modal
from archivist.models.glimmer_access import MODEL, REVISION
from archivist.models.glimmer_image import COMMON, volume

app = modal.App('archivist-glimmer-p31-prepare')

@app.function(**COMMON,timeout=1800)
def prepare_weights(payload):
    import importlib.metadata
    from huggingface_hub import snapshot_download
    from transformers import AutoConfig,AutoTokenizer,AutoModelForMultimodalLM
    snapshot_download(MODEL,revision=REVISION,token=False)
    config=AutoConfig.from_pretrained(MODEL,revision=REVISION,token=False,local_files_only=True)
    tokenizer=AutoTokenizer.from_pretrained(MODEL,revision=REVISION,token=False,local_files_only=True)
    # Check architecture support and the actual template without allocating a GPU.
    architecture=AutoModelForMultimodalLM._model_mapping[type(config)]
    rendered=tokenizer.apply_chat_template([{'role':'user','content':'Return other.'}],
                        tokenize=False,add_generation_prompt=True,reasoning_strength='low')
    from archivist.models.glimmer_runtime import encode_training, messages
    encoded = encode_training(tokenizer, payload['train'])
    validation_lengths = [len(tokenizer(tokenizer.apply_chat_template(messages(item), tokenize=False,
                          add_generation_prompt=True, reasoning_strength='low'),
                          add_special_tokens=False)['input_ids']) for item in payload['validation']]
    if max(validation_lengths) + 512 > 4096:
        raise ValueError('frozen validation prompt exceeds the pre-registered context limit')
    volume.commit()
    return {'model':MODEL,'revision':REVISION,'architecture':architecture.__name__,
            'template_works':bool(rendered),
            'max_training_tokens':max(len(item['input_ids']) for item in encoded),
            'max_validation_prompt_tokens':max(validation_lengths),'versions':{name:importlib.metadata.version(name)
            for name in ('torch','transformers','peft','bitsandbytes','accelerate')}}


@app.function(**COMMON, timeout=300)
def recover_adapter(dataset_id):
    import hashlib
    import json
    from archivist.models.glimmer_runtime import REMOTE, adapter_archive
    directory = REMOTE / 'adapters' / dataset_id
    result = adapter_archive(directory)
    result['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in directory.iterdir() if p.is_file()}
    result['training'] = json.loads((directory / 'training_metrics.json').read_text())
    return result
