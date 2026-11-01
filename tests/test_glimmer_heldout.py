"""Offline phase-2 gates and aggregate metrics; invented frames, development OCR only."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from archivist.glimmer.heldout_frame import read_frame,validate_frame
from archivist.glimmer.heldout_ocr import sampled_text
from archivist.glimmer.compare_phase2 import summarise,require_pushed_raw


def invented_frame():
    assignments={'1940-01_p001':'family','1940-01_p002':'family','1940-01_p003':'unsupported'}
    titles=[{'page':ref,'classified_as':'family','pattern':'title' if ref.endswith('001') else None}
            for ref in list(assignments)[:2]]
    summary={'side':'held_out','issues':['1940-01'],'pages':3,'classified':3,'failed':[],
        'by_family':{'family':{'classified':2,'confirmed':1,'type_unconfirmed':1}},
        'assigned':{r['page']:{'classified_as':'family',
            'counts_for':'family' if r['pattern'] else None,
            'set_aside_by':None if r['pattern'] else 'title'} for r in titles},
        'set_aside_by_classifier':1,'type_unconfirmed':1}
    sweep=[{'page':ref,'classified_as':value} for ref,value in assignments.items()]
    split={'development':['1939-01'],'held_out':['1940-01']}
    return summary,sweep,titles,split,['family']


def test_frame_requires_owner_counts_before_a_draw_is_possible():
    data=invented_frame()
    with pytest.raises(ValueError,match='owner-declared counts'):
        validate_frame(*data)
    assignments,titles,record=validate_frame(*data,expected={
        'named':2,'confirmed':1,'title_rejected':1,'sample':3})
    assert len(assignments)==3 and len(titles)==2
    assert record['status']=='validated_before_draw'


@pytest.mark.parametrize('fault',['title_missing','wrong_title_family','wrong_issue','wrong_summary','conflict'])
def test_frame_cross_checks_records_before_sampling(fault):
    summary,sweep,titles,split,families=invented_frame()
    if fault=='title_missing': titles.pop()
    if fault=='wrong_title_family': titles[0]['classified_as']='other_family'
    if fault=='wrong_issue': sweep[0]['page']='1939-01_p001'
    if fault=='wrong_summary': summary['by_family']['family']['confirmed']=2
    if fault=='conflict': sweep.append({'page':sweep[0]['page'],'classified_as':'unsupported'})
    with pytest.raises(ValueError):
        validate_frame(summary,sweep,titles,split,families)


def test_source_reader_refuses_before_any_file_access_without_go(tmp_path):
    with pytest.raises(PermissionError,match='go'):
        read_frame(tmp_path/'not-existing',tmp_path/'split.json',['family'])


def test_ocr_rejects_unsampled_and_wrong_issue_before_pdf_access(tmp_path):
    with pytest.raises(PermissionError):
        sampled_text('1940-01_p001',set(),{'1940-01'},tmp_path/'missing.pdf',100,100)
    with pytest.raises(PermissionError):
        sampled_text('1939-01_p001',{'1939-01_p001'},{'1940-01'},tmp_path/'missing.pdf',100,100)


def test_text_only_ocr_matches_all_40_frozen_development_inputs():
    from archivist.glimmer.data import load_frozen
    from archivist.ingest.fraser import pdf_name
    _,rows,_=load_frozen()
    split=json.loads(Path('data/real/split.json').read_text())
    dev=set(split['development'])
    manifest=json.loads(Path('data/real/manifest.json').read_text())
    metadata={(r['issue'],r['page']):(r['width'],r['height']) for r in manifest['pages'] if r['issue'] in dev}
    # Both allow sets deliberately contain DEVELOPMENT references for this equivalence test.
    for row in rows:
        ref=row['page']
        issue,number=ref.rsplit('_p',1)
        assert issue in dev and issue not in split['held_out']
        text=sampled_text(ref,{ref},dev,Path('data/real/pdf')/pdf_name(issue),*metadata[issue,int(number)])
        assert text[:12000]==row['ocr']


def test_comparison_is_aggregate_only_and_retains_failures_and_design_weights():
    summary,sweep,title_rows,split,families=invented_frame()
    assignments={r['page']:r['classified_as'] for r in sweep}
    titles={r['page']:r for r in title_rows}
    refs=list(assignments)
    sample=[{'page':ref,'weight':8 if i==2 else 1} for i,ref in enumerate(refs)]
    result=summarise(sample,assignments,titles,{
        'untrained':{refs[0]:'family',refs[1]:'family',refs[2]:'family'},
        'trained':{refs[0]:'family',refs[1]:'other',refs[2]:'invalid'}},['family','other'])
    untrained=result['arms']['untrained']
    assert untrained['sample']['per_family']['family']['precision']==1/3
    assert untrained['design_weighted']['per_family']['family']['precision']==1/10
    trained=result['arms']['trained']
    assert trained['sample']['invalid']==1
    assert trained['strata']['title_rejected']['predicted_other']==1
    assert trained['strata']['classifier_set_aside']['invalid_or_missing']==1
    assert result['arms']['spark_raw']['sample']['accuracy']==2/3
    assert result['arms']['spark_title_confirmed']['sample']['accuracy']==1
    # The report contains counts, never page-level predictions/errors.
    assert all(ref not in json.dumps(result) for ref in refs)


def test_raw_comparison_requires_pushed_identical_bytes_and_a_commit_id(tmp_path):
    raw=tmp_path/'raw.json'
    raw.write_bytes(b'raw answers\n')
    commit='a'*40
    def git(*args):
        if args[0]=='merge-base': return SimpleNamespace(returncode=1)
        raise AssertionError('must not read committed raw before push proof')
    with pytest.raises(PermissionError,match='pushed'):
        require_pushed_raw(commit,[raw],git=git)
    with pytest.raises(ValueError,match='commit ID'):
        require_pushed_raw('some-tag',[raw],git=git)
    def git(*args):
        return SimpleNamespace(returncode=0,stdout=b'different' if args[0]=='show' else b'')
    with pytest.raises(PermissionError,match='bytes differ'):
        require_pushed_raw(commit,[raw],git=git)
    def git(*args):
        return SimpleNamespace(returncode=0,stdout=raw.read_bytes())
    require_pushed_raw(commit,[raw],git=git)
