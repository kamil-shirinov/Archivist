"""Declared L4 / timed L40S fallback, development inputs only."""
import modal

from archivist.models.glimmer_image import COMMON

app = modal.App('archivist-glimmer-development-checks')
SETTINGS = {**COMMON, 'memory': (32768, 32768), 'timeout': 900, 'startup_timeout': 300}


@app.function(**SETTINGS, gpu='L4')
def primary(payload):
    from archivist.models.glimmer_batch import benchmark
    return benchmark(payload)


@app.function(**SETTINGS, gpu='L40S')
def fallback(payload):
    from archivist.models.glimmer_batch import benchmark
    return benchmark(payload)
