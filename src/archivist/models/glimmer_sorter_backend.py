"""Untrained Glimmer text sorter: private Modal lookup, behind cache/cap/ledger."""
from __future__ import annotations

import json
from pathlib import Path

from archivist.models.base import SortResponse, Usage
from archivist.models.glimmer_access import MODEL, REVISION
from archivist.models.glimmer_allocation import wait_for_call
from archivist.models.text_sorting import payload, parse

APP_NAME = 'archivist-glimmer-sorter-p37'
MODEL_ID = f'{MODEL}@{REVISION}/untrained-sorter-v1'
RATE = .000222 + 4*.0000131 + 32*.00000222
EXECUTION_SECONDS = 900
STARTUP_SECONDS = 300
EXTRA_SECONDS = 17  # two idle + fifteen transport/shutdown
MAX_CALL_USD = (EXECUTION_SECONDS + STARTUP_SECONDS + EXTRA_SECONDS) * RATE


class SortRefused(ValueError):
    submitted = False


def check_sources(request, root=Path('data')):
    from archivist.glimmer.data import checked_ref
    for ref in request.source_refs:
        try:
            source, _, _ = checked_ref(ref, root)
        except Exception as error:
            raise SortRefused('text sorter accepts only development Treasury sources') from error
        if source != 'real':
            raise SortRefused('the fixed five-family sorter accepts Treasury sources only')


def remote_sort(app_name):
    import modal
    return modal.Cls.from_name(app_name, 'GlimmerSorter')().infer


class GlimmerSorter:
    name = 'modal_glimmer_sorter'

    def __init__(self, model_id=MODEL_ID, *, app_name=APP_NAME, price=None):
        if model_id != MODEL_ID:
            raise ValueError('the sorter is pinned to the untrained phase-2 base revision')
        if price is None or price.per_request_usd < MAX_CALL_USD:
            raise ValueError('sort price must reserve the full hard GPU request ceiling')
        self.model_id, self.app_name = model_id, app_name
        self.settings = {'app_name':app_name, 'precision':'NF4_double_quant_bf16_compute_storage_load',
            'ocr_chars':1024, 'parser':'native-assistant-header-v1', 'batch_size':8,
            'max_new_tokens':512, 'reasoning':'low', 'greedy':True, 'adapter':False}

    def sort(self, request):
        check_sources(request)  # before endpoint lookup, page access or any GPU request
        # The fixed scheme uses the exact enabled template descriptions from phase 2.
        from dataclasses import asdict
        expected = json.loads(Path('config/glimmer_families.json').read_text())
        if [asdict(f) for f in request.families] != expected:
            raise SortRefused('enabled families/descriptions differ from the phase-2 scheme')
        events = []
        result = wait_for_call(remote_sort(self.app_name),
            {'development_only':True, 'items':payload(request)},
            allocation_seconds=900, execution_seconds=EXECUTION_SECONDS, event=events.append)
        answers = parse(result['outputs'], request)
        # Charge every request for a full cold start and shutdown, even if warm. This
        # deliberately overstates billing and bounds startup/idle as well as inference.
        charge = (min(EXECUTION_SECONDS, result['runtime_seconds']) + STARTUP_SECONDS + EXTRA_SECONDS) * RATE
        return SortResponse(answers, Usage(sum(a.input_tokens for a in answers),
            sum(a.output_tokens for a in answers), charge), self.name, self.model_id,
            details={'precision':result.get('precision'), 'inference_seconds':result['runtime_seconds'],
                     'events':events, 'maximum_usd':MAX_CALL_USD, 'app_name':self.app_name,
                     'cost_basis':'conservative inference + full startup/shutdown allowance'})
