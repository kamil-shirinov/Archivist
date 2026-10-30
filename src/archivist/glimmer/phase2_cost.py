"""Cost projection from development timings; never reads or draws a held-out frame."""
from __future__ import annotations

import math

from archivist.models.glimmer_batch_backend import L4_RATE

POPULATION_UPPER_BOUND = 4569  # already published in PREREGISTRATION_REAL.md
FUNCTION_LIMIT_SECONDS = 14400
STARTUP_ALLOWANCE_SECONDS = 300
IDLE_ALLOWANCE_SECONDS = 5
THROUGHPUT_MARGIN = 1.5


def project(benchmark: dict, sample_pages: int) -> dict:
    if not isinstance(sample_pages, int) or not 0 < sample_pages <= POPULATION_UPPER_BOUND:
        raise ValueError('sample size must be a positive integer within the declared population')
    n = benchmark['pages']
    arms = benchmark['arm_results']
    paired_runtime = sum(arms[arm]['runtime_seconds'] for arm in ('untrained','trained'))
    if n <= 0 or not math.isfinite(paired_runtime) or paired_runtime <= 0:
        raise ValueError('valid completed development timings required')
    per_page = paired_runtime / n
    load_seconds = max(0, benchmark['runtime_seconds'] - paired_runtime)
    expected_function = load_seconds + per_page * sample_pages
    conservative_function = load_seconds + THROUGHPUT_MARGIN * per_page * sample_pages
    return {
        'sample_pages': sample_pages, 'measured_seconds_per_paired_page': per_page,
        'observed_load_seconds': load_seconds,
        'expected_function_seconds': expected_function,
        'conservative_function_seconds': conservative_function,
        'expected_cost_usd': (expected_function + STARTUP_ALLOWANCE_SECONDS + IDLE_ALLOWANCE_SECONDS) * L4_RATE,
        'conservative_cost_usd': (conservative_function + STARTUP_ALLOWANCE_SECONDS + IDLE_ALLOWANCE_SECONDS) * L4_RATE,
        'gpu_job_ceiling_usd': (FUNCTION_LIMIT_SECONDS + STARTUP_ALLOWANCE_SECONDS + IDLE_ALLOWANCE_SECONDS) * L4_RATE,
        'fits_runtime_limit': conservative_function <= FUNCTION_LIMIT_SECONDS,
        'note': 'development timing extrapolation, not held-out timing or a sample draw',
    }


def require_budget_fit(benchmark: dict, sample_pages: int, retained_before_phase2_usd: float) -> dict:
    estimate = project(benchmark, sample_pages)
    if not estimate['fits_runtime_limit']:
        raise ValueError('forecast exceeds four hours: stop before OCR or GPU; do not shrink sample')
    if not math.isfinite(retained_before_phase2_usd) or retained_before_phase2_usd < 0:
        raise ValueError('invalid retained budget')
    if retained_before_phase2_usd + estimate['gpu_job_ceiling_usd'] >= 25:
        raise ValueError('combined reservations reach the $25 project cap')
    return estimate
