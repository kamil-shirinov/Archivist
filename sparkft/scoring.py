"""Strict native response framing and OCR-proxy metrics, fixed before inference."""
import json
import math
import re
from sparkft.prepare import number


def final_body(raw):
    if raw.startswith(' to=user<|message|>') or raw.startswith(' to=self<|message|>'):
        raw='<|start|>assistant'+raw
    marker='<|start|>assistant to=user<|message|>'
    if marker in raw:
        raw=raw.rsplit(marker,1)[1]
    elif '<|start|>' in raw or '<|message|>' in raw:
        raise ValueError('No final assistant-to-user channel')
    for end in ('<|eot|>','<|eom|>','</s>'):
        if raw.rstrip().endswith(end):
            raw=raw.rstrip()[:-len(end)]
    return raw.strip()


def parse(raw, expected, at_limit=False):
    if at_limit:
        raise ValueError('Output exhausted its token allowance')
    data=json.loads(final_body(raw))
    if not isinstance(data,dict) or set(data)!=set(expected):
        raise ValueError('Missing or additional requested cells')
    for value in data.values():
        if not isinstance(value,dict) or set(value)!= {'value','box'}:
            raise ValueError('Unexpected cell schema')
        if value['value'] is not None and not isinstance(value['value'],str):
            raise ValueError('Value must be printed text or null')
        b=value['box']
        if b is not None and (not isinstance(b,list) or len(b)!=4 or
            any(type(x) is not int or not 0<=x<=1000 for x in b) or b[2]<=b[0] or b[3]<=b[1]):
            raise ValueError('Invalid grid box')
    return data


def score(records, references):
    per_page=[]
    for record, ref in zip(records,references,strict=True):
        expected=ref['target']; w,h=ref['size']
        try:
            data=parse(record['text'],expected,record['at_token_limit'])
            error=None
        except (ValueError,TypeError) as exc:
            data={};error=str(exc)
        correct=boxed=joint=0;details=[]
        for i,(key,target) in enumerate(expected.items()):
            pred=data.get(key,{})
            good=number(pred.get('value')) is not None and number(pred.get('value'))==number(target['value'])
            box=pred.get('box'); real=ref['ocr_boxes'][i]
            contains=False;area_ratio=None
            if box is not None:
                x0,y0,x1,y1=box
                pixel=[math.floor(x0*w/1000),math.floor(y0*h/1000),
                       math.ceil(x1*w/1000),math.ceil(y1*h/1000)]
                contains=(pixel[0]<=real['x0'] and pixel[1]<=real['y0'] and
                          pixel[2]>=real['x1'] and pixel[3]>=real['y1'])
                area_ratio=(pixel[2]-pixel[0])*(pixel[3]-pixel[1])/((real['x1']-real['x0'])*(real['y1']-real['y0']))
            correct+=good;boxed+=contains;joint+=good and contains
            details.append({'field':ref['fields'][i],'value_correct':good,
                            'figure_contained':contains,'area_ratio':area_ratio})
        per_page.append({'page':ref['page'],'n':len(expected),'value_correct':correct,
                         'figure_contained':boxed,'joint_correct':joint,'error':error,'cells':details})
    n=sum(p['n'] for p in per_page)
    def rate(key):return sum(p[key] for p in per_page)/n if n else None
    return {'n':n,'value_accuracy':rate('value_correct'),'box_containment':rate('figure_contained'),
            'joint_accuracy':rate('joint_correct'),'invalid_pages':sum(p['error'] is not None for p in per_page),
            'per_page':per_page}


def adoption(base,trained):
    return bool(base['n']>0 and base['n']==trained['n'] and
                trained['value_accuracy']>base['value_accuracy'] and
                trained['box_containment']>base['box_containment'])
