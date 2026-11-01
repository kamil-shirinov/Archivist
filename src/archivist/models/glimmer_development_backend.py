"""Registry backend with declared allocation waiting and hardware-time pricing."""
import json

from archivist.models.base import LLMRequest, LLMResponse, Usage
from archivist.models.glimmer_allocation import wait_for_call

RATES = {'L4': .000222 + 4*.0000131 + 32*.00000222,
         'L40S': .000542 + 4*.0000131 + 32*.00000222}


class DevelopmentBackend:
    name = 'modal_glimmer_development'

    def __init__(self, model_id, *, remote, gpu, event, code_id, price=None):
        self.model_id = model_id
        self.remote, self.gpu, self.event = remote, gpu, event
        self.settings = {'gpu': gpu, 'code_id': code_id, 'batch_size': 8, 'ocr_chars': 1024,
                         'precision': 'NF4_double_quant_bf16_compute_storage_load'}

    def complete(self, request: LLMRequest):
        if request.images:
            raise ValueError('development check accepts OCR text only')
        result = wait_for_call(self.remote, json.loads(request.prompt), event=self.event)
        result['selected_gpu'] = self.gpu
        result['rate_per_second_usd'] = RATES[self.gpu]
        rows = [r for arm in result['arm_results'].values() for r in arm['outputs']]
        return LLMResponse(json.dumps(result), Usage(sum(r['input_tokens'] for r in rows),
            sum(r['output_tokens'] for r in rows), result['runtime_seconds']*RATES[self.gpu]),
            self.name, self.model_id)
