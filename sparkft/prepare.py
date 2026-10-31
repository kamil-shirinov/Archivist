"""Prepare agreed, OCR-backed answers without hosted calls or validation page access."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from archivist.doctypes import from_config
from archivist.templates.ocr import CONFUSIONS, words
from archivist.templates.pages import resolve
from sparkft.boxes import HOSTS, OUT, PAGES, P33_REVISION, blob, gate


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def number(text: str | None, *, ocr: bool = False) -> str | None:
    if text is None:
        return None
    if ocr:
        for wrong, right in CONFUSIONS:
            text = text.replace(wrong, right)
    # Unsigned, unambiguous numeric tokens only; no guessed signs/footnotes.
    if (not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?', text)
            or len(re.sub(r'\D', '', text)) < 3):
        return None
    value = Decimal(text.replace(',', ''))
    return format(value.normalize(), 'f') if value else '0'


def validation_pages(evidence: dict[str, list[str]], split: dict) -> dict[str, str]:
    result = {}
    for family, refs in sorted(evidence.items()):
        for ref in refs:
            gate(ref, split)
        if not refs:
            raise ValueError('No development evidence for ' + family)
        result[family] = max(refs)
    return result


def agreed_answers(left: dict, right: dict, layer, figure_fields: frozenset[str]) -> list[dict]:
    a = {v['field_id']: v for v in left['values']}
    b = {v['field_id']: v for v in right['values']}
    by_number = defaultdict(list)
    for word in layer:
        numeric = number(word.text, ocr=True)
        if numeric is not None:
            by_number[numeric].append(word)
    claimed = [Counter(number(v['value']) for v in host.values()
                       if not v['abstained'] and v['field_id'].rsplit(':', 1)[1] in figure_fields)
               for host in (a, b)]
    out = []
    for key in sorted(a.keys() & b.keys()):
        x, y = a[key], b[key]
        numeric = number(x['value'])
        if (key.rsplit(':', 1)[1] not in figure_fields or x['abstained'] or y['abstained']
                or numeric is None or numeric != number(y['value'])
                or len(by_number[numeric]) != 1 or any(c[numeric] != 1 for c in claimed)):
            continue
        word = by_number[numeric][0]
        out.append({'field_id': key, 'value': x['value'], 'canonical_value': numeric,
                    'teacher_values': {HOSTS[0]: x['value'], HOSTS[1]: y['value']},
                    'ocr_text': word.text, 'ocr_box': word.box.model_dump()})
    return out


def main() -> None:
    split_bytes = Path('data/real/split.json').read_bytes()
    split = json.loads(split_bytes)
    types = from_config(Path('config/real_test.toml'))
    evidence, hashes = {}, {}
    for family in types:
        path = Path('templates') / (family + '.evidence.json')
        raw = path.read_bytes()
        hashes[str(path)] = sha(raw)
        evidence[family] = [p['ref'] for p in json.loads(raw)['pages']]
    validation = validation_pages(evidence, split)
    manifest_bytes = Path('data/real/manifest.json').read_bytes()
    metadata = json.loads(manifest_bytes)
    image_hashes = {f"{p['issue']}_p{p['page']:03d}": p['sha256'] for p in metadata['pages']}
    if len({image_hashes[p] for p in validation.values()}) != len(validation):
        raise ValueError('Duplicate validation image')
    revision = P33_REVISION
    diagnostic = json.loads((OUT / 'boxes.json').read_text())
    if revision != diagnostic['source_revision']:
        raise ValueError('P33 branch moved after geometry audit')
    reads, excluded = {}, []
    for ref in PAGES:
        gate(ref, split)
        if ref in validation.values():
            continue
        pair = []
        for host in HOSTS:
            path = f'results/openw_measure/reads/{host}/{ref}.json'
            raw = blob(revision, path)
            hashes[path] = sha(raw)
            data = json.loads(raw)
            if data['host'] != host or data['ref'] != ref:
                raise ValueError('Source identity mismatch')
            pair.append(data)
        if all(d['ok'] for d in pair):
            if pair[0]['family'] != pair[1]['family']:
                raise ValueError('Teacher family mismatch')
            reads[ref] = pair
        else:
            excluded.append({'page': ref, 'reason': 'No successful pair of P33 page reads'})
    if {image_hashes[p] for p in reads} & {image_hashes[p] for p in validation.values()}:
        raise ValueError('Duplicate image across training/validation')
    answers, per_page = [], []
    for ref, pair in sorted(reads.items()):
        gate(ref, split)
        resolve(ref)  # Hash-check development image before PDF access.
        family = pair[0]['family']
        selected = agreed_answers(*pair, words(ref), types[family].money_fields)
        for answer in selected:
            answer['page'] = ref
            answer['family'] = family
        answers.extend(selected)
        per_page.append({'page': ref, 'family': family, 'answers': len(selected),
                         'image_sha256': image_hashes[ref], 'image_opened': True})
    encoded = ''.join(json.dumps(r, sort_keys=True) + '\n' for r in answers).encode()
    (OUT / 'training_answers.jsonl').write_bytes(encoded)
    result = {
        'status': 'prepared_only_budget_stop_no_training',
        'page_rule': 'PLAN.md', 'source_revision': revision, 'source_hashes': hashes,
        'split_sha256': sha(split_bytes), 'manifest_sha256': sha(manifest_bytes),
        'training': per_page,
        'validation': [{'page': ref, 'family': family, 'image_sha256': image_hashes[ref],
                        'image_opened': False, 'ocr_opened': False}
                       for family, ref in sorted(validation.items())],
        'excluded': excluded, 'training_answers': len(answers),
        'training_answers_sha256': sha(encoded), 'new_model_calls': 0,
        'teacher_independence': 'Separate hosted reads of the same model; correlated pseudo-labels',
    }
    (OUT / 'data_manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'training': per_page, 'validation': result['validation'],
                      'answers': len(answers)}, indent=2))


if __name__ == '__main__':
    main()
