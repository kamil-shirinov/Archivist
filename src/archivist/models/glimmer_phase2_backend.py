"""Phase-2 backend, always called through registry/cache/budget; only its own call is cancelled."""
import json

from archivist.models.base import LLMResponse, Usage
from archivist.models.glimmer_allocation import wait_for_call
from archivist.models.glimmer_batch_backend import L4_RATE


class Phase2Backend:
    name='modal_glimmer_phase2'
    def __init__(self,model_id,*,remote,event,code_id,price=None):
        self.model_id,self.remote,self.event=model_id,remote,event
        self.settings={'code_id':code_id,'gpu':'L4','batch_size':8,'ocr_chars':1024,
                       'timeout_seconds':10825,'scope':'authorised_791_page_paired_run'}
    def complete(self,request):
        if request.images:
            raise ValueError('OCR text only')
        result=wait_for_call(self.remote,json.loads(request.prompt),allocation_seconds=900,
                             execution_seconds=10825,event=self.event)
        rows=[r for arm in result['arm_results'].values() for r in arm['outputs']]
        return LLMResponse(json.dumps(result),Usage(sum(r['input_tokens'] for r in rows),
            sum(r['output_tokens'] for r in rows),result['runtime_seconds']*L4_RATE),
            self.name,self.model_id)
