"""Aggregate-only comparison, gated on raw artifacts already committed and pushed.

No human labels, images, OCR, original scorer or deep-check records are read here.
Metric definitions are frozen before inference and tested only on synthetic answers.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from archivist.glimmer.metrics import INVALID,score
from archivist.glimmer.phase2 import parse_phase2,weighted_score


def require_pushed_raw(commit, paths, *, git=None):
    if not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('use the full raw commit ID, never a tag or arbitrary ref')
    if git is None:
        def git(*args):
            return subprocess.run(['git',*args],capture_output=True,check=False)
    if git('merge-base','--is-ancestor',commit,'refs/remotes/origin/glimmer').returncode:
        raise PermissionError('raw commit is not on the pushed glimmer branch')
    for path in paths:
        saved=git('show',f'{commit}:{path}')
        if saved.returncode or saved.stdout != Path(path).read_bytes():
            raise PermissionError('raw/frozen bytes differ from the pushed commit')


def summarise(sample, assignments, titles, predictions, labels):
    """Aggregate pipeline-proxy comparisons only. No per-page answers or errors returned."""
    ids={r['page'] for r in sample}
    if len(ids)!=len(sample) or any(ref not in assignments for ref in ids):
        raise ValueError('sample IDs are duplicated or outside the frame')
    expected={ref:assignments[ref] if ref in titles and titles[ref]['pattern'] is not None
              else 'other' for ref in ids}
    weights={r['page']:r['weight'] for r in sample}
    groups={
        'confirmed':{ref for ref in ids if expected[ref]!='other'},
        'title_rejected':{ref for ref in ids if ref in titles and expected[ref]=='other'},
        'classifier_set_aside':{ref for ref in ids if assignments[ref]=='unsupported'},
    }
    all_predictions=dict(predictions)
    all_predictions['spark_raw']={ref:'other' if assignments[ref]=='unsupported' else assignments[ref]
                                  for ref in ids}
    all_predictions['spark_title_confirmed']=expected.copy()
    result={}
    for name,predicted in all_predictions.items():
        unweighted=score(expected,predicted,labels)
        weighted=weighted_score(expected,predicted,labels,weights)
        correct=sum(c['count'] for c in weighted['confusion'] if c['expected']==c['predicted'])
        weighted['accuracy']=correct/weighted['weighted_population']
        strata={}
        for group,refs in groups.items():
            counts=Counter(predicted.get(ref,INVALID) for ref in refs)
            strata[group]={'pages':len(refs),
                'correct':sum(predicted.get(ref)==expected[ref] for ref in refs),
                'predicted_other':counts['other'],
                'predicted_family':sum(n for label,n in counts.items() if label in labels and label!='other'),
                'invalid_or_missing':sum(n for label,n in counts.items() if label not in labels)}
        rejection_by_assigned_family={}
        for family in labels:
            if family=='other': continue
            refs={r for r in groups['title_rejected'] if assignments[r]==family}
            rejection_by_assigned_family[family]={
                'pages':len(refs),'predicted_other':sum(predicted.get(r)=='other' for r in refs),
                'kept_rejected_assignment':sum(predicted.get(r)==family for r in refs),
                'predicted_different_family':sum(predicted.get(r) in labels and predicted.get(r) not in ('other',family) for r in refs),
                'invalid_or_missing':sum(predicted.get(r) not in labels for r in refs)}
        result[name]={'sample':unweighted,'design_weighted':weighted,'strata':strata,
                      'title_rejections_by_original_assignment':rejection_by_assigned_family}
    return {'sample_pages':len(ids),'counts':{k:len(v) for k,v in groups.items()},'arms':result,
        'reference':'pipeline-confirmed family, else other; teacher-derived proxy, not human truth',
        'human_comparison':'deferred until separately authorised committed file on main; no labels read',
        'weighting':'named pages weight 1; sampled set-aside pages weight |U|/500',
        'spark_title_confirmed_note':'equals the proxy reference by construction, not independent accuracy'}


def compare(raw_commit):
    from archivist.glimmer.run_phase2 import OUT,frame,verify_frame,verify_freeze,write_once
    paths=[OUT/name for name in ('raw_response.json','sample.json','freeze.json','inputs_manifest.json',
                                'frame_check.json','reservation.json')]
    require_pushed_raw(raw_commit,paths)
    frozen=verify_freeze()
    assignments,titles,_,record=frame()
    verify_frame(record)
    sample=json.loads((OUT/'sample.json').read_text())['pages']
    raw=json.loads((OUT/'raw_response.json').read_text())
    if raw['sample_sha256']!=frozen['sample_sha256']:
        raise ValueError('raw output identifies another sample')
    if raw['input_sha256']!=json.loads((OUT/'inputs_manifest.json').read_text())['input_sha256']:
        raise ValueError('raw output identifies different input bytes')
    labels=[f['family'] for f in json.loads(Path('results/glimmer/families.json').read_text())]+['other']
    predictions={}
    for arm in ('untrained','trained'):
        outputs=raw['arm_results'][arm]['outputs']
        if [r['index'] for r in outputs]!=list(range(791)):
            raise ValueError('raw output order/completeness mismatch')
        predictions[arm]={row['page']:parse_phase2(answer['text'],labels,
            at_token_limit=answer['at_token_limit']) for row,answer in zip(sample,outputs,strict=True)}
    summary=summarise(sample,assignments,titles,predictions,labels)
    summary['raw_commit_already_pushed']=raw_commit
    write_once('summary.json',summary)
    print(json.dumps({'sample_pages':summary['sample_pages'],'counts':summary['counts'],
        'accuracies':{a:r['sample']['accuracy'] for a,r in summary['arms'].items()}},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-commit',required=True)
    args=parser.parse_args()
    compare(args.raw_commit)


if __name__=='__main__': main()
