"""Bounded Modal GPU functions. Launch only via archivist.glimmer.run."""
import modal

from archivist.models.glimmer_access import MODEL, REVISION

app=modal.App('archivist-glimmer-p31')
from archivist.models.glimmer_image import COMMON, volume


@app.function(**COMMON,gpu='H100!',timeout=1800,startup_timeout=300)
def baseline(payload):
    from archivist.models.glimmer_runtime import run
    return run('baseline',payload)


@app.function(**COMMON,gpu='H100!',timeout=7200,startup_timeout=300)
def train(payload):
    from archivist.models.glimmer_runtime import run
    result=run('train',payload)
    volume.commit()
    return result


@app.function(**COMMON,gpu='H100!',timeout=1800,startup_timeout=300)
def trained(payload):
    from archivist.models.glimmer_runtime import run
    return run('trained',payload)
