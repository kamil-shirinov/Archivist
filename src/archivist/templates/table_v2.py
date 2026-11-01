"""Opt-in S0+table-v2: page-local row/column anchors; S0+grid is unchanged.

Global unique figures seed columns and row consensus without model-box proximity.
Repeated stub labels map only with equal occurrence counts, in printed order.
Ink and ruled lines bound cells. Unresolved cells keep v1, explicitly sourced.
This module never opens a file or calls a model; callers enforce page access.
"""
from __future__ import annotations

import io
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Sequence

import numpy as np
from PIL import Image

from archivist.doctypes.template import NUMERIC, TemplateType
from archivist.schema import BBox, ExtractedValue
from archivist.templates import grid, ocr
from archivist.templates.ink import otsu

STRATEGY = 'S0+table-v2'


def _key(value):
    return value.field_id.rsplit(':', 2)[-2:]


def _centre(box):
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def _text(text):
    return re.sub(r'[^a-z0-9]', '', (text or '').lower().split('....')[0])


def _union(boxes):
    return BBox(x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
                x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes))


def assign(values: Sequence[ExtractedValue], doc_type: TemplateType, image: bytes,
           layer: Sequence[ocr.Word], check: grid.Check | None = None,
           *, fallback=None):
    """Return boxed values, per-cell sources and serializable page diagnostics.

    `fallback`, when supplied, is the existing grid.assign result on these inputs.
    It permits measuring v1 and v2 without repeating the v1 order guard.
    """
    old, old_sources, old_info = fallback if fallback is not None else grid.assign(
        values, doc_type, image, layer, check)
    sources = {f: 'v1:' + s for f, s in old_sources.items()}
    numeric = [c.key for c in doc_type.layout.columns if c.kind in NUMERIC]
    figures = [v for v in values if _key(v)[1] in numeric and not v.abstained and v.value]
    counts = Counter(re.sub(r'\D', '', v.value) for v in figures)
    tokens = defaultdict(list)
    for w in layer:
        if len(w.digits) >= 3:
            tokens[w.digits].append(w)
    anchors = []
    for v in figures:
        digits = re.sub(r'\D', '', v.value)
        if len(digits) >= 3 and counts[digits] == 1 and len(tokens[digits]) == 1:
            anchors.append((v, tokens[digits][0]))

    # Numeric columns are right-aligned; use their right edges rather than the
    # model's centres (or variable-width numbers' centres).
    column_edges = {}
    for c in numeric:
        hits = [w.box.x1 for v, w in anchors if _key(v)[1] == c]
        if len(hits) >= 2:
            median = statistics.median(hits)
            close = [x for x in hits if abs(x-median) <= 15]
            if len(close) >= 2 and len(close) >= len(hits) * .75:
                column_edges[c] = statistics.median(close)
    info = {'v1': old_info, 'anchors': len(anchors), 'columns': column_edges,
            'rows': {}, 'repeated_labels': {}, 'rejected_rows': [], 'rules': []}
    if not column_edges:
        return old, sources, info
    order = [c for c in numeric if c in column_edges]
    edges = [column_edges[c] for c in order]
    if any(b-a < 12 for a, b in zip(edges, edges[1:])):
        info['rejected_columns'] = 'non-monotone or overlapping OCR column anchors'
        return old, sources, info
    # Bound each column by the whitespace after the preceding right-aligned run.
    pitch = statistics.median((column_edges[b]-column_edges[a]) /
                              (numeric.index(b)-numeric.index(a))
                              for a,b in zip(order,order[1:])) if len(edges)>1 else 100
    columns = {}
    for c in order:
        index = numeric.index(c)
        previous = numeric[index-1] if index else None
        left = column_edges.get(previous, column_edges[c]-pitch) + 4
        columns[c] = (max(0, round(left)), round(column_edges[c]+5))

    valid_anchors = [(v,w) for v,w in anchors if _key(v)[1] in columns and
                     abs(w.box.x1-column_edges[_key(v)[1]]) <= 15]
    by_row = defaultdict(list)
    for v,w in valid_anchors:
        by_row[_key(v)[0]].append(w)
    # Estimate page shear only within rows, so vertical row spacing cannot enter.
    slopes = []
    for words in by_row.values():
        words = sorted(words, key=lambda w:w.box.x0)
        for a,b in zip(words,words[1:]):
            ax,ay = _centre(a.box); bx,by = _centre(b.box)
            if bx-ax >= 50 and abs((by-ay)/(bx-ax)) <= .03:
                slopes.append((by-ay)/(bx-ax))
    shear = statistics.median(slopes) if slopes else 0
    centre = Image.open(io.BytesIO(image)).width/2
    def deskew(b):
        x,y = _centre(b)
        return y-shear*(x-centre)

    row_y, row_source = {}, {}
    for row, words in by_row.items():
        ys = [deskew(w.box) for w in words]
        if len(ys) >= 2 and max(ys)-min(ys) <= 10:
            row_y[row] = statistics.median(ys)
            row_source[row] = 'figure-consensus'

    # Labels are matched across the entire stub, never near a model-provided y.
    # A repeated label requires the same count on both sides: missing/extra
    # occurrences cannot silently shift every later section.
    stub_right = min(a for a,b in columns.values())
    stub = [w for w in layer if w.box.x1 <= stub_right]
    label_lines = []
    for w in sorted(stub,key=lambda w:deskew(w.box)):
        y = deskew(w.box)
        if label_lines and abs(y-statistics.mean(deskew(t.box) for t in label_lines[-1])) <= 7:
            label_lines[-1].append(w)
        else:
            label_lines.append([w])
    lines = [(_text(' '.join(w.text for w in sorted(line,key=lambda w:w.box.x0))),
              statistics.mean(deskew(w.box) for w in line)) for line in label_lines]
    labels = [c.key for c in doc_type.layout.columns if c.kind == 'text']
    row_labels = {}
    by_id = {_key(v)[0]:v for v in values if labels and _key(v)[1] == labels[0]}
    fixed_labels = {r.key:r.printed for r in (doc_type.layout.rows if isinstance(doc_type.layout.rows,list) else [])}
    active = {r for r in doc_type.layout.row_keys if any(_key(v)[0] == r for v in figures)}
    for row in doc_type.layout.row_keys:
        label = by_id.get(row)
        text = _text(fixed_labels.get(row) or (label.value if label else ''))
        if text and row in active:
            row_labels[row] = text
    groups = defaultdict(list)
    for row,text in row_labels.items():
        groups[text].append(row)
    for text, rows in groups.items():
        matches = [y for name,y in lines if name == text or
                   (len(text)>=4 and name.startswith(text))]
        if len(rows)>1:
            info['repeated_labels'][text] = {'read':len(rows),'ocr':len(matches)}
        if len(matches) != len(rows):
            continue
        for row,y in zip(rows,matches):
            if row in row_y and abs(row_y[row]-y)>10:
                info['rejected_rows'].append(row)
                row_y.pop(row); row_source.pop(row)
            elif row not in info['rejected_rows']:
                row_y[row] = y if row not in row_y else row_y[row]
                row_source[row] = 'label-occurrence' if len(rows)>1 else 'label'

    # Refuse crossing row anchors. Do not shift an outlier into a neighbouring row.
    ordered = [r for r in doc_type.layout.row_keys if r in row_y]
    bad = set()
    for a,b in zip(ordered,ordered[1:]):
        if row_y[b]-row_y[a] < 8:
            bad.update((a,b))
    for r in bad:
        row_y.pop(r); row_source.pop(r); info['rejected_rows'].append(r)
    if not row_y:
        return old, sources, info

    gray = np.asarray(Image.open(io.BytesIO(image)).convert('L'))
    ink = gray <= otsu(gray)
    span = (max(0,min(a for a,b in columns.values())), min(gray.shape[1],max(b for a,b in columns.values())))
    rule_lines = grid.rules(ink,span,(0,gray.shape[0]),shear,centre)
    info['rules'] = rule_lines
    # Recover only exact-count gaps between fixed rows, using the page's ink bands.
    # Seed grid finding with OCR boxes, so its search never needs Open's positions.
    seeded = defaultdict(list)
    for v,w in valid_anchors:
        if v.citation:
            citation = v.citation.model_copy(update={'bbox':w.box,'raw_bbox':None})
            seeded[_key(v)[1]].append(v.model_copy(update={'citation':citation}))
    found = grid.find_grid(image,seeded,{v.field_id for v,w in valid_anchors},len(active)) if seeded else None
    if found and found.bands:
        band_ys = [((a+b)/2 + found.shear*(centre-found.centre)) for a,b in found.bands]
        ordered = [r for r in doc_type.layout.row_keys if r in row_y]
        row_order = [r for r in doc_type.layout.row_keys if r in active]
        for a,b in zip(ordered,ordered[1:]):
            if a not in row_order or b not in row_order:
                continue
            missing = row_order[row_order.index(a)+1:row_order.index(b)]
            between = [y for y in band_ys if row_y[a]+8 < y < row_y[b]-8]
            if missing and len(missing)==len(between):
                for r,y in zip(missing,between):
                    row_y[r] = y; row_source[r] = 'exact-grid-gap'
    info['rows'] = {r:{'y':y,'source':row_source[r]} for r,y in row_y.items()}
    info['shear'] = shear
    ys = sorted(row_y.values())
    gaps = [b-a for a,b in zip(ys,ys[1:]) if 8 < b-a < 60]
    row_pitch = statistics.median(gaps) if gaps else 20
    # Row windows stop before another row or a ruled separator. They never search
    # another row for the value that the first reader claimed.
    windows = {}
    for row,y in row_y.items():
        above = max([p for p in ys if p < y-1] + [y-row_pitch])
        below = min([p for p in ys if p > y+1] + [y+row_pitch])
        top = max((above+y)/2, y-row_pitch/2)
        bottom = min((below+y)/2, y+row_pitch/2)
        top = max([top]+[p+2 for p in rule_lines if top < p < y-3])
        bottom = min([bottom]+[p-2 for p in rule_lines if y+3 < p < bottom])
        windows[row] = top,bottom

    out = []
    for v in old:
        row,c = _key(v)
        if row not in windows or c not in columns or v.citation is None:
            out.append(v); continue
        top,bottom = windows[row]; left,right = columns[c]
        words = [w for w in layer if left <= _centre(w.box)[0] <= right and
                 top <= deskew(w.box) <= bottom and w.digits and
                 (re.fullmatch(r'[\d\s,.()\-+*†‡¹²³⁴ilIOoU|«»]+',w.text) or
                  len(re.findall(r'\d',w.text)) > len(re.findall(r'[A-Za-z]',w.text)))]
        if words:
            target = _union([w.box for w in words])
            source = 'table:ocr'
        else:
            # The layer may have labels but no figures. Use only ink within the
            # known cell, stripping full-length rules before taking its envelope.
            lift = shear*((left+right)/2-centre)
            y0=max(0,round(top+lift)); y1=min(gray.shape[0],round(bottom+lift))
            x0=max(0,left); x1=min(gray.shape[1],right)
            part=ink[y0:y1,x0:x1].copy()
            if part.size:
                part[:,part.sum(axis=0) >= .85*part.shape[0]]=False
                part[part.sum(axis=1) >= .85*part.shape[1],:]=False
            iy,ix=np.nonzero(part)
            if len(ix) < 3:
                out.append(v); continue
            target=BBox(x0=int(x0+ix.min()),y0=int(y0+iy.min()),
                        x1=int(x0+ix.max()+1),y1=int(y0+iy.max()+1))
            source='table:ink'
        # A little ink margin preserves the whole printed stroke and footnotes.
        target=BBox(x0=max(0,target.x0-2),y0=max(0,target.y0-2),
                    x1=min(gray.shape[1],target.x1+2),y1=min(gray.shape[0],target.y1+2))
        citation=v.citation.model_copy(update={'bbox':target,'raw_bbox':None})
        out.append(v.model_copy(update={'citation':citation}))
        sources[v.field_id]=source
    return out,sources,info
