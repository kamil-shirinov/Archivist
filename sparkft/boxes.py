"""Offline P33 geometry audit; no model client or cache scan is used."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from archivist.doctypes import from_config
from archivist.templates.ocr import words
from archivist.templates.pages import PageRefused, resolve

OUT = Path('results/sparkft')
PAGES = ('1939-01_p051', '1939-01_p055', '1939-01_p061', '1939-08_p043', '1982-06_p094')
HOSTS = ('baseten', 'fireworks')
P33_REVISION = '633cdffc7797fecc1f8a9adf5ac38ef1d6b28fc9'


def gate(ref: str, split: dict) -> None:
    match = re.fullmatch(r'(\d{4}-\d{2})_p\d{3}', ref)
    if match is None or match[1] not in split['development'] or match[1] in split['held_out']:
        raise PageRefused('Not an allowed Treasury development page: ' + ref)


def blob(revision: str, path: str) -> bytes:
    return subprocess.check_output(['git', 'show', revision + ':' + path])


def centre(box):
    return (np.asarray(box[:2], dtype=float) + box[2:]) / 2


def contains(box, target) -> bool:
    return all(box[i] <= target[i] for i in (0, 1)) and all(box[i] >= target[i] for i in (2, 3))


def metrics(pairs: list[dict], transform) -> dict:
    if not pairs:
        return {'n': 0, 'contains': None, 'centre_contains': None, 'median_error_px': None}
    errors, offsets = [], []
    full = point = 0
    for pair in pairs:
        predicted, target = transform(pair), pair['ocr_box']
        full += contains(predicted, target)
        c = centre(target)
        point += contains(predicted, [*c, *c])
        offset = centre(predicted) - c
        offsets.append(offset)
        errors.append(np.linalg.norm(offset))
    return {
        'n': len(pairs), 'contains': full, 'containment': full / len(pairs),
        'centre_contains': point, 'centre_containment': point / len(pairs),
        'median_error_px': float(np.median(errors)),
        'median_offset_xy_px': np.median(offsets, axis=0).tolist(),
    }


def affine_fit(pairs: list[dict], shift_only: bool = False) -> list[float]:
    source = np.array([centre(p['model_box']) / p['size'] for p in pairs])
    target = np.array([centre(p['ocr_box']) / p['size'] for p in pairs])
    if shift_only:
        return [1., 1., *np.median(target - source, axis=0).tolist()]
    result = []
    for axis in (0, 1):
        design = np.column_stack([source[:, axis], np.ones(len(pairs))])
        a, b = np.linalg.lstsq(design, target[:, axis], rcond=None)[0]
        result.append((float(a), float(b)))
    return [result[0][0], result[1][0], result[0][1], result[1][1]]


def apply(pair: dict, params: list[float]) -> list[float]:
    box = np.array(pair['model_box'], dtype=float).reshape(2, 2)
    size = np.array(pair['size'])
    changed = (box / size * params[:2] + params[2:]) * size
    return [*np.minimum(changed[0], changed[1]), *np.maximum(changed[0], changed[1])]


def fixed(pair: dict, name: str) -> list[float]:
    w, h = pair['size']
    choices = {
        'identity': [1, 1, 0, 0],
        'undo_grid_conversion': [1000 / w, 1000 / h, 0, 0],
        'extra_grid_conversion': [w / 1000, h / 1000, 0, 0],
        'pdf_points_to_pixels': [200 / 72, 200 / 72, 0, 0],
        'vertical_reflection': [1, -1, 0, 1],
    }
    if name == 'swapped_axes':
        x0, y0, x1, y1 = pair['model_box']
        return [y0 * w / h, x0 * h / w, y1 * w / h, x1 * h / w]
    return apply(pair, choices[name])


def main() -> None:
    revision = P33_REVISION
    current = subprocess.check_output(['git', 'rev-parse', 'openw-measure'], text=True).strip()
    if current != revision:
        raise ValueError('P33 branch moved; review inputs before regenerating')
    split = json.loads(Path('data/real/split.json').read_text())
    types = from_config(Path('config/real_test.toml'))
    pairs, inputs, rows = [], {}, []
    missing = []
    for ref in PAGES:
        gate(ref, split)  # Must precede cached response, image and PDF access.
        page = resolve(ref)
        with Image.open(page.path) as image:
            size = list(image.size)
        layer = words(ref)
        by_digits = defaultdict(list)
        for word in layer:
            if len(word.digits) >= 3:
                by_digits[word.digits].append(word)
        for host in HOSTS:
            path = f'results/openw_measure/reads/{host}/{ref}.json'
            raw = blob(revision, path)
            inputs[path] = hashlib.sha256(raw).hexdigest()
            read = json.loads(raw)
            if not read['ok']:
                missing.append({'host': host, 'page': ref, 'reason': 'P33 read failed'})
                continue
            assert read['ref'] == ref and read['host'] == host
            plugin = types[read['family']]
            eligible = [v for v in read['values'] if not v['abstained'] and v['value']
                        and v['field_id'].rsplit(':', 1)[1] in plugin.money_fields]
            counts = Counter(re.sub(r'\D', '', v['value']) for v in eligible)
            page_pairs = []
            for value in eligible:
                digits = re.sub(r'\D', '', value['value'])
                if (len(digits) < 3 or counts[digits] != 1 or len(by_digits[digits]) != 1
                        or value['citation'] is None):
                    continue
                assert value['citation']['page_id'] == ref
                word = by_digits[digits][0]
                pair = {
                    'host': host, 'page': ref, 'field_id': value['field_id'],
                    'value': value['value'], 'ocr_text': word.text, 'size': size,
                    'model_box': [value['citation']['bbox'][k] for k in ('x0','y0','x1','y1')],
                    'ocr_box': [getattr(word.box, k) for k in ('x0','y0','x1','y1')],
                }
                page_pairs.append(pair)
            pairs.extend(page_pairs)
            rows.append({'host': host, 'page': ref, 'size': size,
                         'figure_values': len(eligible), 'anchors': len(page_pairs)})
    names = ('identity', 'undo_grid_conversion', 'extra_grid_conversion',
             'pdf_points_to_pixels', 'vertical_reflection', 'swapped_axes')
    scores = []
    for row in rows:
        own = [p for p in pairs if p['host'] == row['host'] and p['page'] == row['page']]
        other = [p for p in pairs if p['host'] == row['host'] and p['page'] != row['page']]
        measured = {name: metrics(own, lambda p, n=name: fixed(p, n)) for name in names}
        params = {}
        for name, shift in [('other_pages_shift', True), ('other_pages_affine', False)]:
            params[name] = affine_fit(other, shift)
            measured[name] = metrics(own, lambda p, n=name: apply(p, params[n]))
        ordered = sorted(own, key=lambda p: hashlib.sha256(
            ('sparkft-box:' + p['field_id']).encode()).hexdigest())
        cut = int(len(ordered) * .8)
        train, test = ordered[:cut], ordered[cut:]
        if len(train) >= 4:
            params['within_page_affine'] = affine_fit(train)
            measured['within_page_affine'] = metrics(test, lambda p: apply(p, params['within_page_affine']))
            measured['within_page_identity'] = metrics(test, lambda p: p['model_box'])
        scores.append({**row, 'transforms': params, 'metrics': measured})
    pooled = {}
    for name in (*names, 'other_pages_shift', 'other_pages_affine'):
        subset = [r['metrics'][name] for r in scores]
        n = sum(r['n'] for r in subset)
        full = sum(r['contains'] or 0 for r in subset)
        pooled[name] = {'n': n, 'contains': full, 'containment': full / n,
                        'qualifies': all(r['n'] >= 10 and r['containment'] >= .9 for r in subset)
                        and full > sum(r['metrics']['identity']['contains'] or 0 for r in scores)}
    output = {
        'source_revision': revision, 'source_hashes': inputs,
        'split_sha256': hashlib.sha256(Path('data/real/split.json').read_bytes()).hexdigest(),
        'rule': 'BOX_PLAN.md', 'missing_reads': missing, 'scores': scores, 'pooled': pooled,
        'reusable_conversion_found': any(r['qualifies'] for r in pooled.values()),
        'new_model_calls': 0, 'cost_usd': 0,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / 'boxes.json').write_text(json.dumps(output, indent=2) + '\n')
    (OUT / 'box_anchors.jsonl').write_text(''.join(json.dumps(p) + '\n' for p in pairs))
    print(json.dumps({'pooled': pooled, 'pages': rows}, indent=2))


if __name__ == '__main__':
    main()
