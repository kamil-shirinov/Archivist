"""One isolated, bounded L4 job for the owner-authorised phase-2 run."""
import modal
from archivist.models.glimmer_image import COMMON

app=modal.App('archivist-glimmer-phase2-20261031')


@app.function(**{**COMMON,'gpu':'L4','memory':(32768,32768),
                 'timeout':10825,'startup_timeout':300})
def infer(payload):
    from archivist.models.glimmer_phase2_runtime import paired_inference
    return paired_inference(payload)
