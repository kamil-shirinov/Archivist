"""Cost projection from development timings; never reads or draws a held-out frame."""
from __future__ import annotations

import math

from archivist.models.glimmer_batch_backend import L4_RATE

POPULATION_UPPER_BOUND = 4569  # already published in PREREGISTRATION_REAL.md
FUNCTION_LIMIT_SECONDS = 14400
STARTUP_ALLOWANCE_SECONDS = 300
IDLE_ALLOWANCE_SECONDS = 5
THROUGHPUT_MARGIN = 1.5
RETAINED_CAP_USD = 24.31


def project(benchmark: dict, sample_pages: int) -> dict:
    if not isinstance(sample_pages, int) or not 0 < sample_pages <= POPULATION_UPPER_BOUND:
        raise ValueError('sample size must be a positive integer within the declared population')
    n = benchmark['pages']
    arms = benchmark['arm_results']
    paired_runtime = sum(arms[arm]['runtime_seconds'] for arm in ('untrained','trained'))
    if n <= 0 or not math.isfinite(paired_runtime) or paired_runtime <= 0:
        raise ValueError('valid completed development timings required')
    rate = benchmark.get('rate_per_second_usd', L4_RATE)
    limit = benchmark.get('prospective_function_limit_seconds', FUNCTION_LIMIT_SECONDS)
    startup = benchmark.get('startup_allowance_seconds', STARTUP_ALLOWANCE_SECONDS)
    idle = benchmark.get('idle_allowance_seconds', IDLE_ALLOWANCE_SECONDS)
    if not math.isfinite(rate) or rate <= 0 or limit <= 0:
        raise ValueError('positive measured hardware rate and runtime limit required')
    per_page = paired_runtime / n
    load_seconds = max(0, benchmark['runtime_seconds'] - paired_runtime)
    expected_function = load_seconds + per_page * sample_pages
    conservative_function = load_seconds + THROUGHPUT_MARGIN * per_page * sample_pages
    return {
        'sample_pages': sample_pages, 'measured_seconds_per_paired_page': per_page,
        'observed_load_seconds': load_seconds,
        'expected_function_seconds': expected_function,
        'conservative_function_seconds': conservative_function,
        'expected_cost_usd': (expected_function + startup + idle) * rate,
        'conservative_cost_usd': (conservative_function + startup + idle) * rate,
        'gpu_job_ceiling_usd': (limit + startup + idle) * rate,
        'fits_runtime_limit': conservative_function <= limit,
        'rate_per_second_usd': rate, 'function_limit_seconds': limit,
        'selected_gpu': benchmark.get('selected_gpu', 'L4'),
        'note': 'development timing extrapolation, not held-out timing or a sample draw',
    }


def require_budget_fit(benchmark: dict, sample_pages: int, retained_before_phase2_usd: float) -> dict:
    estimate = project(benchmark, sample_pages)
    if not estimate['fits_runtime_limit']:
        raise ValueError('forecast exceeds declared runtime limit: stop before OCR or GPU; do not shrink sample')
    if not math.isfinite(retained_before_phase2_usd) or retained_before_phase2_usd < 0:
        raise ValueError('invalid retained budget')
    if retained_before_phase2_usd + estimate['gpu_job_ceiling_usd'] > RETAINED_CAP_USD:
        raise ValueError('combined reservations exceed the $24.31 retained cap')
    return estimate
