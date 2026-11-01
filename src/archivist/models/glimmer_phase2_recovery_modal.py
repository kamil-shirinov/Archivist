"""A single detached recovery L4, with the original resource caps and hard timeouts."""
import modal
from archivist.models.glimmer_image import COMMON

app=modal.App('archivist-glimmer-phase2-recovery-20261031')


@app.function(**{**COMMON,'gpu':'L4','memory':(32768,32768),
                 'timeout':10825,'startup_timeout':300})
def infer(payload):
    from archivist.models.glimmer_phase2_recovery_runtime import recover
    return recover(payload)
