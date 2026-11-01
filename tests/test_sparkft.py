"""Offline geometry and pseudo-label checks on invented figures only."""
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from archivist.schema import BBox
from archivist.templates.pages import PageRefused
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sparkft import boxes
from sparkft.prepare import agreed_answers, number, validation_pages

SPLIT = {'development': ['1939-01', '1939-12'], 'held_out': ['1940-01']}


@pytest.mark.parametrize('ref', ['1940-01_p001', '../1939-01_p001', 'frb-1939-01_p001', 'test/x'])
def test_gate_rejects_other_pages(ref):
    with pytest.raises(PageRefused):
        boxes.gate(ref, SPLIT)


def test_geometry_refuses_before_source_response_or_page_access(monkeypatch):
    monkeypatch.setattr(boxes, 'PAGES', ('1940-01_p001',))

    def forbidden(*args):
        pytest.fail('A prohibited response/image/PDF was accessed')

    monkeypatch.setattr(boxes, 'blob', forbidden)
    monkeypatch.setattr(boxes, 'resolve', forbidden)
    monkeypatch.setattr(boxes, 'words', forbidden)
    with pytest.raises(PageRefused):
        boxes.main()


def test_validation_rule_uses_greatest_id_and_rejects_held_out():
    refs = {'a': ['1939-12_p003', '1939-01_p099'], 'b': ['1939-01_p002']}
    assert validation_pages(refs, SPLIT) == {'a': '1939-12_p003', 'b': '1939-01_p002'}
    with pytest.raises(PageRefused):
        validation_pages({'a': ['1940-01_p001']}, SPLIT)


def test_containment_distinguishes_centre_from_complete_figure():
    pairs = [{'model_box': [10, 10, 20, 20], 'ocr_box': [9, 9, 21, 21]}]
    result = boxes.metrics(pairs, lambda p: p['model_box'])
    assert result['contains'] == 0 and result['centre_contains'] == 1
    assert boxes.contains([0, 0, 10, 10], [0, 0, 10, 10])


def test_affine_learned_on_other_points_recovers_known_mapping():
    def pair(x, y):
        return {'model_box': [x, y, x + 10, y + 10],
                'ocr_box': [2*x + 7, .5*y - 3, 2*(x+10) + 7, .5*(y+10) - 3],
                'size': [1000, 2000]}

    params = boxes.affine_fit([pair(x, y) for x, y in [(50, 80), (300, 200), (600, 600)]])
    unseen = pair(450, 400)
    assert boxes.apply(unseen, params) == pytest.approx(unseen['ocr_box'])


@dataclass
class Word:
    text: str
    box: BBox


def read(values):
    return {'values': [{'field_id': 'T.x:1939-01_p001:' + field,
                        'value': value, 'abstained': False}
                       for field, value in values]}


def test_answers_need_host_agreement_unique_ocr_and_use_ocr_box():
    word = Word('1,234', BBox(x0=7, y0=8, x1=30, y1=20))
    a = read([('01:money', '1234')])
    b = read([('01:money', '1,234')])
    selected = agreed_answers(a, b, [word], frozenset({'money'}))
    assert len(selected) == 1 and selected[0]['ocr_box'] == word.box.model_dump()
    assert agreed_answers(a, read([('01:money', '1235')]), [word], frozenset({'money'})) == []
    assert agreed_answers(a, b, [word, word], frozenset({'money'})) == []
    duplicate_host = read([('01:money', '1234'), ('02:money', '1234')])
    assert agreed_answers(a, duplicate_host, [word], frozenset({'money'})) == []
    assert agreed_answers(duplicate_host, b, [word], frozenset({'money'})) == []
    assert agreed_answers(a, b, [word], frozenset({'label'})) == []


@pytest.mark.parametrize('text', ['-123', '(123)', '1e3', '12', '12,34', '123 footnote', None])
def test_ambiguous_or_short_tokens_are_excluded(text):
    assert number(text) is None


def test_numeric_agreement_preserves_decimal_place_value():
    assert number('123.40') == '123.4'
    assert number('12.34') != number('1234')
    assert number('1*23', ocr=True) == '423'
    assert number('1*23') is None
