"""Prospective phase-2 rules; actual page IDs are used only from phase-1 development files."""
import hashlib
import json
import random
from pathlib import Path

import pytest

from archivist.glimmer.phase2 import (
    INVALID, OCR_PREFIX_CHARS, decision_text, draw_sample, parse_phase2, weighted_score,
)


def test_phase2_parser_accepts_both_models_saved_development_outputs_without_rewriting_them():
    root = Path('results/glimmer')
    labels = [row['family'] for row in json.loads((root/'families.json').read_text())] + ['other']
    checksums = json.loads((root/'artifact_manifest.json').read_text())['strict_scores_sha256']
    for arm in ('baseline', 'trained'):
        saved = json.loads((root/f'{arm}_predictions.json').read_text())['predictions']
        assert len(saved) == 40
        assert all(parse_phase2(row['text'], labels, at_token_limit=row['at_token_limit']) in labels
                   for row in saved)
    for name, checksum in checksums.items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == checksum
    assert json.loads((root/'trained_metrics.json').read_text())['accuracy'] == 0
    diagnostic = json.loads((root/'trained_native_framing_metrics.json').read_text())
    assert diagnostic['accuracy'] == 1
    assert diagnostic['status'] == 'post_hoc_protocol_framing_diagnostic_not_preregistered_primary'


def test_parser_rejects_reasoning_unknown_answers_prose_and_exhausted_output():
    labels = ['family', 'other']
    for text in (' to=self<|message|>family<|eot|>',
                 ' to=user<|message|>Probably family<|eot|>',
                 ' to=tool<|message|>family<|eot|>',
                 ' to=user<|message|>unknown<|eot|>'):
        assert parse_phase2(text, labels) == INVALID
    assert parse_phase2(' to=user<|message|>family<|eot|>', labels, at_token_limit=True) == INVALID
    assert parse_phase2('family', labels) == 'family'
    assert parse_phase2(' to=self<|message|>other<|eom|><|start|>assistant to=user<|message|>family<|eot|>',labels) == 'family'


def test_ocr_selection_is_a_fixed_label_independent_prefix():
    text = 'header ' + 'x' * 2000
    assert decision_text(text) == text[:OCR_PREFIX_CHARS]
    assert decision_text('') == ''


def test_sample_refuses_to_examine_a_frame_before_go():
    class Unreadable:
        def __iter__(self):
            raise AssertionError('no frame may be inspected')
        def items(self):
            raise AssertionError('no frame may be inspected')
    with pytest.raises(PermissionError):
        draw_sample(Unreadable(), Unreadable(), Unreadable())


def test_sample_has_all_family_assignments_and_500_unique_set_aside_pages():
    # All references below are invented; no held-out file or real frame is read.
    named = {'1940-01_p001':'family', '1940-01_p002':'family', '1940-01_p003':'family'}
    pool = [f'1940-02_p{n:03d}' for n in range(1, 601)]
    frame = named | {ref:'unsupported' for ref in pool}
    sample = draw_sample(frame, ['family'], ['1940-01','1940-02'], go=True)
    reverse = draw_sample(dict(reversed(list(frame.items()))), ['family'], ['1940-01','1940-02'], go=True)
    assert sample == reverse
    assert len(sample) == len({row.page for row in sample}) == 503
    assert set(named) <= {row.page for row in sample}
    chosen = {row.page for row in sample if row.stratum == 'classifier_set_aside'}
    assert chosen == set(random.Random(4005).sample(sorted(pool), 500))
    for row in sample:
        if row.page in named:
            assert row.inclusion_probability == row.weight == 1
        else:
            assert row.inclusion_probability == 500/600
            assert row.weight == 600/500


def test_sample_small_pool_census_and_failures_are_not_relabelled_other():
    sample = draw_sample({'1940-01_p001':'unsupported'}, ['family'], ['1940-01'], go=True)
    assert len(sample) == 1 and sample[0].weight == 1
    for frame in ({'1939-12_p001':'family'}, {'frb-1940-01_p001':'family'},
                  {'1940-01_p001':'failed'}):
        with pytest.raises(ValueError):
            draw_sample(frame, ['family'], ['1940-01'], go=True)


def test_weighted_proxy_precision_accounts_for_subsampled_other_pages_and_failures():
    result = weighted_score({'a':'family','b':'other','c':'family'},
                            {'a':'family','b':'family'}, ['family','other'], {'a':1,'b':8,'c':1})
    family = result['per_family']['family']
    assert family['tp'] == 1 and family['fp'] == 8 and family['fn'] == 1
    assert family['precision'] == 1/9 and family['recall'] == .5
    assert result['weighted_population'] == 10
    assert result['per_family']['other']['precision'] is None
    with pytest.raises(ValueError):
        weighted_score({'a':'family'}, {}, ['family'], {'a':float('nan')})


def test_cost_projection_is_paired_margin_adjusted_and_stops_before_an_oversized_job():
    from archivist.glimmer.phase2_cost import project, require_budget_fit
    benchmark = {'pages':40,'runtime_seconds':240,
                 'arm_results':{'untrained':{'runtime_seconds':160},'trained':{'runtime_seconds':40}}}
    estimate = project(benchmark,500)
    assert estimate['measured_seconds_per_paired_page'] == 5
    assert estimate['expected_function_seconds'] == 2540
    assert estimate['conservative_function_seconds'] == 3790
    assert estimate['expected_cost_usd'] < estimate['conservative_cost_usd']
    assert require_budget_fit(benchmark,500,18)['fits_runtime_limit']
    with pytest.raises(ValueError,match='runtime limit'):
        require_budget_fit(benchmark,4569,18)
    with pytest.raises(ValueError,match='cap'):
        require_budget_fit(benchmark,500,24)
