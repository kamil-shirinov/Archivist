"""Time-priced batch backend using the normal registry/cache/budget path."""
import json

from archivist.models.base import LLMRequest, LLMResponse, Usage

L4_RATE = .000222 + 4 * .0000131 + 32 * .00000222


class GlimmerBatchBackend:
    name = 'modal_glimmer_batch'

    def __init__(self, model_id, *, remote, price=None, code_sha256=''):
        self.model_id = model_id
        self.remote = remote
        self.settings = {'gpu': 'L4', 'batch_size': 8, 'ocr_chars': 1024,
                         'code_sha256': code_sha256}

    def complete(self, request: LLMRequest) -> LLMResponse:
        if request.images:
            raise ValueError('phase-2 preparation uses OCR text only')
        result = self.remote.remote(json.loads(request.prompt))
        rows = [row for arm in result['arm_results'].values() for row in arm['outputs']]
        usage = Usage(sum(r['input_tokens'] for r in rows), sum(r['output_tokens'] for r in rows),
                      result['runtime_seconds'] * L4_RATE)
        return LLMResponse(json.dumps(result), usage, self.name, self.model_id)
