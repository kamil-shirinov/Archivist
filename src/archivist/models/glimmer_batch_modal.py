"""Development-only L4 benchmark; no held-out reader, sampler or execution entrypoint."""
import modal

from archivist.models.glimmer_image import COMMON

app = modal.App('archivist-glimmer-phase2-preparation')


@app.function(**{**COMMON, 'memory': (32768, 32768)}, gpu='L4', timeout=1800, startup_timeout=300)
def benchmark_development(payload):
    from archivist.models.glimmer_batch import benchmark
    return benchmark(payload)
