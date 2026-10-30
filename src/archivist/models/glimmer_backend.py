"""Modal backend for the existing registry, cache and budget wrappers."""
from __future__ import annotations

import base64
import json

from archivist.models.base import LLMRequest, LLMResponse, Usage


class ModalGlimmer:
    name='modal_glimmer'

    def __init__(self,model_id,*,remote,stage,dataset_id,price=None,runtime_id="unspecified"):
        self.model_id=model_id
        self.remote=remote
        self.settings={'stage':stage,'dataset_id':dataset_id,'nf4':True,'bf16':True,'runtime_id':runtime_id}

    def complete(self,request: LLMRequest) -> LLMResponse:
        if request.images:
            raise ValueError('Glimmer experiment accepts text only')
        payload=json.loads(request.prompt)
        result=self.remote.remote(payload)
        if 'archive' in result:
            result['archive_base64']=base64.b64encode(result.pop('archive')).decode('ascii')
        # Aggregate actual GPU time is reconciled in the separate reservation ledger. Token
        # prices are zero because Modal bills hardware time, not tokens.
        from archivist.glimmer.cost import RATE
        usage=Usage(sum(r['input_tokens'] for r in result.get('outputs',[])),
                    sum(r['output_tokens'] for r in result.get('outputs',[])),
                    result['runtime_seconds']*RATE)
        return LLMResponse(json.dumps(result),usage,self.name,self.model_id)
