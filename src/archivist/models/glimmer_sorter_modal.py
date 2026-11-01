"""Scale-to-zero untrained phase-2 Glimmer. Deploying creates no warm GPU."""
import time
import modal
from archivist.models.glimmer_image import COMMON
from archivist.models.glimmer_sorter_backend import APP_NAME

app = modal.App(APP_NAME)


@app.cls(**{**COMMON, 'gpu':'L4', 'memory':(32768,32768), 'min_containers':0,
            'max_containers':1, 'scaledown_window':2, 'timeout':900, 'startup_timeout':300})
class GlimmerSorter:
    @modal.enter()
    def load(self):
        from archivist.models.glimmer_runtime import load_model
        from archivist.models.glimmer_batch import precision_record
        self.model, self.tokenizer = load_model()
        self.precision = precision_record(self.model)
        # No adapter is ever loaded by this service.

    @modal.method()
    def infer(self, request):
        from archivist.models.glimmer_batch import batch_generate
        if request.get('development_only') is not True or not 1 <= len(request['items']) <= 16:
            raise ValueError('development text batches only')
        began = time.monotonic()
        outputs = batch_generate(self.model, self.tokenizer, request['items'])
        return {'outputs':outputs, 'runtime_seconds':time.monotonic()-began,
                'precision':self.precision}
