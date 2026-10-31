"""P37: one registered, capped RPC on ten frozen development pages; never reads a sweep."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from archivist.doctypes import from_config
from archivist.doctypes.titles import title_match
from archivist.glimmer.data import checked_ref, digest, load_frozen
from archivist.models import SortRequest, load_roles
from archivist.models.glimmer_sorter_backend import APP_NAME, MAX_CALL_USD, MODEL_ID, RATE
from archivist.models.text_sorting import families_of, payload

OUT = Path('results/glimmer/sorter')
CONFIG = Path('config/archive_glimmer.toml')


def select():
    train, validation, _ = load_frozen()
    rows = sorted([r for r in validation if r['target'] != 'other'] +
                  [r for r in train + validation if r['stratum'] == 'title_other'],
                  key=lambda r: r['page'])
    if len(rows) != 10 or len({r['page'] for r in rows}) != 10:
        raise ValueError('expected five fixed validation positives and five title rejections')
    for row in rows:
        if checked_ref(row['page'], Path('data'))[0] != 'real':
            raise ValueError('Treasury development pages only')
    return rows


def prepare():
    rows = select()
    request = SortRequest('sorter', tuple(r['ocr'] for r in rows),
                          families_of(from_config(CONFIG)), tuple(r['page'] for r in rows))
    record = {'pages': list(request.source_refs), 'model_id': MODEL_ID, 'app_name': APP_NAME,
              'selection': 'five frozen validation positives plus all five frozen title_other pages',
              'data_manifest_sha256': digest(Path('results/glimmer/data_manifest.json').read_bytes()),
              'config_sha256': digest(CONFIG.read_bytes()),
              'request_sha256': digest(json.dumps(payload(request), sort_keys=True).encode()),
              'estimated_gpu_maximum_usd': MAX_CALL_USD, 'rate_usd_per_second': RATE,
              'deployment_storage_allowance_usd': .10, 'live_check_limit_usd': 2,
              'task_limit_usd': 10, 'no_training': True, 'ocr_chars': 1024}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / 'live-check-plan.json'
    if manifest.exists() and json.loads(manifest.read_text()) != record:
        raise ValueError('refusing a different live-check plan')
    manifest.write_text(json.dumps(record, indent=2) + '\n')
    return rows, request


def run():
    rows, request = prepare()
    if (OUT / 'live-check.json').exists():
        raise ValueError('live check already recorded; refusing to overwrite')
    # The live check has a tighter cap than the deployed sorter's $10 task cap.
    os.environ['GLIMMER_CAP_USD'] = '2'
    roles = load_roles(CONFIG)
    response = roles['sorter'].sort(request)
    raw = {'timestamp': datetime.now(UTC).isoformat(), 'response': asdict(response)}
    # Save the model's exact output before deriving a comparison.
    (OUT / 'live-check-raw.json').write_text(json.dumps(raw, indent=2) + '\n')
    replay = roles['sorter'].sort(request)
    if not replay.cached or replay.answers != response.answers:
        raise ValueError('immediate cache replay differed')
    types = from_config(CONFIG)
    comparisons = []
    for row, answer in zip(rows, response.answers, strict=True):
        if answer.family not in {*types, 'other'}:
            raise ValueError('invalid model answer; no fallback or repair permitted')
        pattern = title_match(types[answer.family], row['ocr']) if answer.family in types else None
        confirmed = answer.family if pattern is not None else 'other'
        comparisons.append({'page': row['page'], 'spark_raw': row['spark_raw'],
            'spark_confirmed': row['spark_confirmed'], 'glimmer_raw': answer.family,
            'glimmer_confirmed': confirmed, 'title_pattern': pattern,
            'raw_agrees': answer.family == row['spark_raw'],
            'confirmed_agrees': confirmed == row['spark_confirmed']})
    result = {'pages': len(rows), 'raw_agreement': sum(r['raw_agrees'] for r in comparisons),
              'confirmed_agreement': sum(r['confirmed_agrees'] for r in comparisons),
              'positive_recall': sum(r['glimmer_raw'] == r['spark_confirmed'] for r in comparisons
                                     if r['spark_confirmed'] != 'other'),
              'positive_pages': 5, 'cache_replay_verified': True,
              'ledger_reserved_charge_usd': response.usage.cost_usd,
              'comparisons': comparisons}
    (OUT / 'live-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'comparisons'}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', help='freeze the ten pages without a model call')
    args = parser.parse_args()
    if args.prepare:
        prepare()
        print('Frozen ten development pages; no model call.')
    else:
        run()


if __name__ == '__main__':
    main()
