"""Registry-backed recovery, or result collection from this task's existing call."""
import json

from archivist.models.base import LLMResponse,Usage
from archivist.models.glimmer_allocation import wait_for_call
from archivist.models.glimmer_batch_backend import L4_RATE


class RecoveryBackend:
    name='modal_glimmer_phase2_recovery'
    def __init__(self,model_id,*,code_id,event,remote=None,existing_call_id=None,price=None):
        self.model_id,self.remote,self.event=model_id,remote,event
        self.existing_call_id=existing_call_id
        self.settings={'code_id':code_id,'gpu':'L4','ocr_chars':1024,'batch_size':8,
                       'execution_timeout':10825,'checkpointing':'atomic_original_batches_v1'}
    def complete(self,request):
        if request.images: raise ValueError('frozen OCR only')
        if self.existing_call_id:
            import modal
            call=modal.FunctionCall.from_id(self.existing_call_id)
            # Collection never starts or cancels a GPU call.
            while True:
                try:
                    result=call.get(timeout=10)
                    break
                except TimeoutError as error:
                    if type(error).__name__!='TimeoutError': raise
        else:
            result=wait_for_call(self.remote,json.loads(request.prompt),execution_seconds=10825,
                                 event=self.event)
        rows=[r for arm in result['arm_results'].values() for r in arm['outputs']]
        return LLMResponse(json.dumps(result),Usage(sum(r['input_tokens'] for r in rows),
            sum(r['output_tokens'] for r in rows),result['runtime_seconds']*L4_RATE),
            self.name,self.model_id)
