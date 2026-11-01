"""Complete development-only title offsets in the exact OCR string used by Glimmer."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from archivist.doctypes import from_config
from archivist.ingest.fraser import pdf_name
from archivist.templates import ocr
from archivist.templates.pages import REAL, resolve
from archivist.templates.real_test import _FOLD, fold, fold_pattern


def folded_offsets(text: str) -> tuple[str, list[int]]:
    characters, offsets = [], []
    for index, char in enumerate(text):
        for folded in char.lower().translate(_FOLD).replace('-', ' '):
            if folded.isspace():
                if characters and characters[-1] != ' ':
                    characters.append(' ')
                    offsets.append(index)
            else:
                characters.append(folded)
                offsets.append(index)
    if characters and characters[-1] == ' ':
        characters.pop()
        offsets.pop()
    result = ''.join(characters)
    if result != fold(text):
        raise ValueError('offset folding differs from the approved title check')
    return result, offsets


def locate_titles(text: str, patterns: list[str]) -> list[dict]:
    folded, offsets = folded_offsets(text)
    matches = {}
    for pattern in patterns:
        for match in re.finditer(fold_pattern(pattern), folded, re.IGNORECASE):
            if match.start() == match.end():
                raise ValueError('empty approved title pattern')
            start, end = offsets[match.start()], offsets[match.end()-1] + 1
            matches[start, end] = {
                'start_char_1based': start + 1, 'end_char_1based': end,
                'starts_after_1024': start >= 1024,
                'start_chars_past_1024': max(0, start + 1 - 1024),
                'full_title_not_retained_at_1024': end > 1024,
                'context': text[max(0, start-120):min(len(text), end+180)],
            }
    return [matches[key] for key in sorted(matches)]


def development_records(root: Path) -> list[dict]:
    split = json.loads((root/'split.json').read_text())
    development, held_out = set(split['development']), set(split['held_out'])
    if development & held_out:
        raise ValueError('development and held-out issues overlap')
    manifest = json.loads((root/'manifest.json').read_text())
    # Inspect issue metadata first; never use held-out page text/hints or open its page/PDF.
    return [p for p in manifest['pages'] if p['issue'] in development]


def link_development_assets(source: Path, target: Path) -> None:
    """Expose only explicitly permitted development assets inside this worktree, read-only."""
    split = json.loads((target/'split.json').read_text())
    if split != json.loads((source/'split.json').read_text()):
        raise ValueError('source split differs from worktree split')
    for issue in split['development']:
        if issue in split['held_out']:
            raise ValueError('issue is not exclusively development')
        for relative in (Path('pdf')/pdf_name(issue), Path('pages')/issue):
            dest, origin = target/relative, source/relative
            if not origin.exists():
                raise FileNotFoundError(f'missing development asset: {relative}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.symlink_to(origin.resolve(), target_is_directory=origin.is_dir())


def audit(root: Path, output: Path) -> dict:
    types = from_config(Path('config/real_test.toml'))
    rows, page_lengths, candidates = [], [], []
    records = development_records(root)
    for i, record in enumerate(records):
        ref = f"{record['issue']}_p{record['page']:03d}"
        match = REAL.fullmatch(ref)
        # resolve gates the development split and hashes the image before its PDF opens.
        page = resolve(ref, root=root)
        text = ' '.join(w.text for w in ocr.layer(root/'pdf'/pdf_name(match['issue']),
                                               int(match['page']), page.path))
        page_lengths.append({'page': ref, 'full_ocr_chars': len(text)})
        broad = {
            'short_term_foreign_liabilities_as': 'Short-Term Foreign Liab',
            'security_transactions_as_reported_by': 'Security Transactions',
            'outstanding_forward_exchange_contracts': 'Outstanding Forward Exchange',
            'receipts_and_expenditures_under_railroad': 'Receipts and Expenditures',
            'total_claims_by_country': 'Total Claims by Country',
        }
        for family, anchor in broad.items():
            for position in locate_titles(text, [anchor]):
                candidates.append({'page': ref, 'candidate_family': family, **position})
        for family, typ in types.items():
            positions = locate_titles(text, typ.template.identity.title_patterns)
            if positions:
                rows.append({'page': ref, 'family': family, 'full_ocr_chars': len(text),
                             'matches': positions})
        if (i+1) % 100 == 0:
            print(f'Full development OCR audit: {i+1}/{len(records)} pages', flush=True)
    by_family = {}
    for family in types:
        found = [r for r in rows if r['family'] == family]
        occurrences = [m for row in found for m in row['matches']]
        by_family[family] = {
            'pages_with_title_pattern': len(found), 'title_pattern_occurrences': len(occurrences),
            'pages_first_title_starts_after_1024': sum(r['matches'][0]['starts_after_1024'] for r in found),
            'occurrences_starting_after_1024': sum(m['starts_after_1024'] for m in occurrences),
            'pages_first_title_not_fully_retained': sum(r['matches'][0]['full_title_not_retained_at_1024'] for r in found),
            'maximum_title_start_1based': max((m['start_char_1based'] for m in occurrences), default=None),
            'maximum_title_end_1based': max((m['end_char_1based'] for m in occurrences), default=None),
        }
    result = {
        'status': 'complete_Treasury_development_OCR_pattern_audit',
        'pages_examined': len(records), 'issues': sorted({p['issue'] for p in records}),
        'offset_basis': '1-based Unicode characters in full OCR words joined by one space; no 12000-character truncation',
        'interpretation': 'approved-title-pattern occurrences; references/contents entries need separate adjudication',
        'by_family': by_family, 'matches': rows,
        'broad_anchor_candidates': candidates,
        'broad_anchor_late_candidates': [r for r in candidates if r['starts_after_1024']],
        'late_occurrences': [{'page': r['page'], 'family': r['family'], **m}
                             for r in rows for m in r['matches'] if m['starts_after_1024']],
        'page_lengths': page_lengths,
    }
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'pages_examined': len(records), 'by_family': by_family}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('../..')/'data/real')
    parser.add_argument('--root', type=Path, default=Path('data/real'))
    parser.add_argument('--output', type=Path, default=Path('.tmp/glimmer-title-audit.json'))
    args = parser.parse_args()
    link_development_assets(args.source, args.root)
    audit(args.root, args.output)


if __name__ == '__main__':
    main()
