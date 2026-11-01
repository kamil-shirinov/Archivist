"""Explicit-go, metadata-only phase-2 frame checks; no page or forbidden result reader."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from archivist.templates.pages import REAL

ALLOWED_RECORDS = ('sweep.json', 'sweep.jsonl', 'titles.jsonl')
EXPECTED_COUNTS = {'named':291, 'confirmed':136, 'title_rejected':155, 'sample':791}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_frame(summary, sweep_rows, title_rows, split, families, *, expected=EXPECTED_COUNTS):
    """Validate the whole source collection before sampling. Inputs in tests are invented."""
    held, dev = set(split['held_out']), set(split['development'])
    if not held or held & dev or summary.get('side') != 'held_out':
        raise ValueError('invalid held-out split or sweep side')
    if set(summary.get('issues',[])) != held:
        raise ValueError('sweep does not cover exactly the held-out issues')
    families = set(families)
    def check_ref(ref):
        match = REAL.fullmatch(ref)
        if match is None or match['issue'] not in held or int(match['page']) < 1:
            raise ValueError('non-held-out Treasury reference in frame')
    assignments, failed_attempts = {}, 0
    for row in sweep_rows:
        ref = row['page']
        check_ref(ref)
        if 'classified_as' not in row:
            if 'failed' not in row:
                raise ValueError('neither classification nor recorded failure')
            failed_attempts += 1
            continue
        family = row['classified_as']
        if family not in families | {'unsupported'}:
            raise ValueError('unknown classification in frame')
        if ref in assignments and assignments[ref] != family:
            raise ValueError('conflicting successful classification records')
        assignments[ref] = family
    failed = summary.get('failed',[])
    if len(set(failed)) != len(failed):
        raise ValueError('duplicate unresolved failure')
    for ref in failed:
        check_ref(ref)
        if ref in assignments:
            raise ValueError('failed page also classified')
    seen = {row['page'] for row in sweep_rows}
    if seen != set(assignments) | set(failed):
        raise ValueError('unaccounted failure or page')
    if summary['classified'] != len(assignments) or summary['pages'] != len(seen):
        raise ValueError('sweep population count mismatch')
    titles = {}
    for row in title_rows:
        ref = row['page']
        check_ref(ref)
        if (ref not in assignments or assignments[ref] not in families
                or row['classified_as'] != assignments[ref]):
            raise ValueError('title record does not match a named-family assignment')
        if 'pattern' not in row or (row['pattern'] is not None and not isinstance(row['pattern'],str)):
            raise ValueError('missing/invalid title-check result')
        if ref in titles and titles[ref] != row:
            raise ValueError('conflicting title records')
        titles[ref] = row
    named = {ref for ref,family in assignments.items() if family in families}
    if set(titles) != named:
        raise ValueError('title coverage differs from the named-family census')
    by_family = {}
    for family in sorted(families):
        assigned = [ref for ref in named if assignments[ref] == family]
        confirmed = sum(titles[ref]['pattern'] is not None for ref in assigned)
        by_family[family] = {'classified':len(assigned), 'confirmed':confirmed,
                             'type_unconfirmed':len(assigned)-confirmed}
    if summary.get('by_family') != by_family:
        raise ValueError('per-family counts disagree with records')
    for ref in named:
        target = assignments[ref] if titles[ref]['pattern'] is not None else None
        actual = summary['assigned'].get(ref)
        if actual != {'classified_as':assignments[ref], 'counts_for':target,
                      'set_aside_by':None if target else 'title'}:
            raise ValueError('summary assignment differs from classification/title records')
    if set(summary['assigned']) != named:
        raise ValueError('summary named-page map coverage mismatch')
    unsupported = sum(f == 'unsupported' for f in assignments.values())
    confirmed = sum(r['confirmed'] for r in by_family.values())
    rejected = len(named)-confirmed
    counts = {'named':len(named), 'confirmed':confirmed, 'title_rejected':rejected,
              'sample':len(named)+min(500,unsupported)}
    if summary['set_aside_by_classifier'] != unsupported or summary['type_unconfirmed'] != rejected:
        raise ValueError('set-aside counts disagree with records')
    if counts != expected:
        raise ValueError(f'frame differs from owner-declared counts: {counts}; expected {expected}; no draw permitted')
    return assignments, titles, {'counts':counts, 'population_pages':len(seen),
        'successful_pages':len(assignments), 'classifier_set_aside':unsupported,
        'unresolved_failures':len(failed), 'failed_attempt_records':failed_attempts,
        'by_family':by_family, 'status':'validated_before_draw'}


def read_frame(directory: Path, split_path: Path, families, *, go=False):
    if not go:
        raise PermissionError('phase 2 requires explicit go before source access')
    if directory.name != 'held_out' or directory.parent.name != 'real_test':
        raise ValueError('only the explicitly permitted held-out sweep record location')
    split_bytes = split_path.read_bytes()
    split = json.loads(split_bytes)
    raw = {name:(directory/name).read_bytes() for name in ALLOWED_RECORDS}
    lines = lambda name:[json.loads(s) for s in raw[name].decode().splitlines() if s.strip()]
    assignments,titles,record = validate_frame(json.loads(raw['sweep.json']),
        lines('sweep.jsonl'),lines('titles.jsonl'),split,families)
    record['source_sha256'] = {name:digest(data) for name,data in raw.items()}
    record['split_sha256'] = digest(split_bytes)
    return assignments,titles,split,record
