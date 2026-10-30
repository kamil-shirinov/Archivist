"""Development-only phase-2 preparation. There is no held-out file reader or sample draw here."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from archivist.glimmer.data import SYSTEM, checked_ref, load_frozen, prompt
from archivist.glimmer.metrics import score
from archivist.glimmer.phase2 import BATCH_SIZE, OCR_PREFIX_CHARS, decision_text, parse_phase2
from archivist.models import LLMRequest, load_roles
from archivist.models.glimmer_access import MODEL, REVISION
from archivist.models.glimmer_batch_backend import L4_RATE, GlimmerBatchBackend
from archivist.models.registry import register_backend

OUT = Path('results/glimmer/phase2_preparation')
BENCHMARK_SECONDS = 1800
STARTUP_SECONDS = 300
SCALEDOWN_SECONDS = 5
PHASE2_SECONDS = 14400
OVERHEAD_RESERVE_USD = 2.50


def _write(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2) + '\n')


def development_payload():
    _, rows, families = load_frozen()
    for row in rows:
        source, _, _ = checked_ref(row['page'], Path('data'))
        if source != 'real':
            raise ValueError('benchmark accepts exclusively development Treasury references')
    return rows, families, {
        'development_only': True,
        'dataset_id': hashlib.sha256(Path('results/glimmer/data_manifest.json').read_bytes()).hexdigest(),
        'items': [{'system': SYSTEM, 'prompt': prompt(decision_text(row['ocr']), families)} for row in rows],
    }


def reserve_benchmark():
    path = OUT/'cost.json'
    if path.exists():
        raise ValueError('preparation job already reserved; no automatic GPU retries')
    prior = json.loads(Path('results/glimmer/cost.json').read_text())
    earlier_attempts = sum(json.loads(p.read_text())['maximum_usd'] for p in OUT.glob('cost_attempt*.json'))
    old_ceiling = sum(row['maximum_usd'] for row in prior) + OVERHEAD_RESERVE_USD + earlier_attempts
    maximum = (BENCHMARK_SECONDS + STARTUP_SECONDS + SCALEDOWN_SECONDS) * L4_RATE
    phase2_maximum = (PHASE2_SECONDS + STARTUP_SECONDS + SCALEDOWN_SECONDS) * L4_RATE
    if old_ceiling + maximum + phase2_maximum >= 25:
        raise ValueError('combined retained reservations reach the $25 project cap')
    record = {
        'stage': 'development_batched_L4_benchmark', 'state': 'reserved',
        'gpu': 'L4', 'physical_cpu_cores': 4, 'memory_gib': 32,
        'rate_per_second_usd': L4_RATE, 'maximum_usd': maximum,
        'timeout_seconds': BENCHMARK_SECONDS, 'startup_allowance_seconds': STARTUP_SECONDS,
        'prior_retained_ceiling_including_overhead_usd': old_ceiling,
        'planned_phase2_gpu_ceiling_usd': phase2_maximum,
        'combined_retained_ceiling_usd': old_ceiling + maximum + phase2_maximum,
        'reserved_at': datetime.now(UTC).isoformat(),
    }
    _write('cost.json', record)
    return record


def benchmark_development():
    from archivist.models import glimmer_batch_modal as remote
    OUT.mkdir(parents=True, exist_ok=True)
    rows, families, payload = development_payload()
    reservation = reserve_benchmark()
    print(f"L4 development benchmark: at most ${reservation['maximum_usd']:.4f}; "
          f"all retained reservations with future phase 2: ${reservation['combined_retained_ceiling_usd']:.4f}", flush=True)
    # Only the old phase-1 files are snapshotted. No held-out results tree is listed or opened.
    preserved = []
    for path in sorted(Path('results/glimmer').rglob('*')):
        if path.is_file() and OUT not in path.parents and path.name != 'PLAN.md':
            preserved.append({'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    _write('preserved_phase1.json', preserved)
    sources = [Path(__file__), Path('src/archivist/glimmer/phase2.py'),
               *sorted(Path('src/archivist/models').glob('glimmer_batch*.py')),
               Path('src/archivist/models/glimmer_runtime.py')]
    code_id = hashlib.sha256(b''.join(path.read_bytes() for path in sources)).hexdigest()
    model_id = f'{MODEL}@{REVISION}/phase2-development/{code_id}'
    register_backend('modal_glimmer_batch', 'llm',
                     lambda model_id, **settings: GlimmerBatchBackend(model_id,
                             remote=remote.benchmark_development, code_sha256=code_id, **settings), priced=True)
    config = OUT/'roles.toml'
    config.write_text(f'''[roles.benchmark]
kind = "llm"
backend = "modal_glimmer_batch"
model_id = "{model_id}"
[prices."{model_id}"]
input_per_mtok = 0.0
output_per_mtok = 0.0
''')
    os.environ['BUDGET_CAP_USD'] = '25'
    roles = load_roles(config, cache_dir=Path('cache/glimmer-phase2-preparation'),
                       ledger_path=OUT/'spend_ledger.jsonl')
    try:
        with remote.modal.enable_output(), remote.app.run():
            response = roles['benchmark'].complete(LLMRequest(role='glimmer_phase2_development',
                                                  prompt=json.dumps(payload), max_output_tokens=512))
        result = json.loads(response.text)
    except BaseException as error:
        reservation.update(state='failed', error=type(error).__name__)
        _write('cost.json', reservation)
        raise
    reservation.update(state='completed', runtime_seconds=result['runtime_seconds'],
                       estimated_compute_usd=result['runtime_seconds']*L4_RATE)
    _write('cost.json', reservation)
    labels = [f['family'] for f in families] + ['other']
    expected = {row['page']: row['target'] for row in rows}
    for arm, record in result['arm_results'].items():
        if [row['index'] for row in record['outputs']] != list(range(len(rows))):
            raise ValueError('batch output/input order differs')
        predictions = {ref['page']: parse_phase2(answer['text'], labels,
                          at_token_limit=answer['at_token_limit'])
                       for ref, answer in zip(rows, record['outputs'], strict=True)}
        record['development_metrics'] = score(expected, predictions, labels)
    result.update(pages=len(rows), batch_size=BATCH_SIZE, ocr_prefix_chars=OCR_PREFIX_CHARS,
                  input_page_ids=[row['page'] for row in rows],
                  status='development_preparation_only_not_a_phase2_result')
    _write('development_benchmark.json', result)
    for row in preserved:
        if hashlib.sha256(Path(row['file']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('a preserved phase-1 artifact changed')
    print('Development-only benchmark saved; phase-1 artifacts unchanged.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['benchmark-development'])
    parser.parse_args()
    benchmark_development()


if __name__ == '__main__':
    main()
