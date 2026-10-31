"""Offline: what a version of the code would send and parse for each of version 1's five families,
hashed. Run once with the tag's tree and once with main's and compare the two files (P33, step 8):

    T=<scratch dir outside the repo>; for f in $(git ls-tree -r --name-only run-real-treasury -- \
        src config templates pyproject.toml uv.lock); do mkdir -p $T/$(dirname $f); \
        git show run-real-treasury:$f > $T/$f; done
    (cd $T && <this checkout>/.venv/bin/python -I -c "import sys; sys.path.insert(0, '$T/src'); \
        sys.argv = ['x', 'tag.json']; exec(open('<this checkout>/openw/equivalence.py').read())")
    (cd <this checkout> && .venv/bin/python -I -c "import sys; sys.path.insert(0, 'src'); \
        sys.argv = ['x', 'main.json']; exec(open('openw/equivalence.py').read())")

It calls no model and opens no page: prompts, schemas, field ids, re-read prompts, a canned answer
parsed, the checks run on it, the output allowances and the templates' hashes.
"""
import hashlib, json, sys
from pathlib import Path
import archivist
from archivist.doctypes import from_config, recorded
from archivist.schema import PageExtraction
from archivist.templates import test as arithmetic

def h(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()

VALUES = ["1,234", "", "-", "56", "7.5", "12, 345", "(8)"]
def fake(schema, state):
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "null")
    if t == "object":
        return {k: fake(v, state) for k, v in schema["properties"].items()}
    if t == "array":
        return [fake(schema["items"], state) for _ in range(schema.get("minItems", 1))]
    if t == "string":
        state[0] += 1
        return VALUES[state[0] % len(VALUES)]
    return 10 * (state[0] % 7 + 1)

out = {"archivist_from": str(Path(archivist.__file__).resolve().parent), "families": {}}
types = from_config(Path("config/real_test.toml"))
out["recorded"] = recorded(types)
for name, t in types.items():
    page_id = "1939-01_p051"
    ids = t.field_ids(page_id)
    schema = t.extraction_schema()
    data = fake(schema, [0])
    values = t.parse(page_id, data, 2000, 3000)
    page = PageExtraction(page_id=page_id, doc_type=name, values=values)
    flags = t.checks([page])
    out["families"][name] = {
        "cells": len(ids),
        "prompt": h(t.extraction_prompt(grounding=False)),
        "prompt_grounded": h(t.extraction_prompt(grounding=True)),
        "schema": h(schema),
        "output_tokens": arithmetic.output_tokens(t),
        "field_ids": h(ids),
        "reread_prompts": h([t.reread_prompt(f) for f in ids]),
        "parsed": h([v.model_dump() for v in values]),
        "canonical": h([t.canonical(v.field_id, v.value or "") for v in values]),
        "instances": len(list(t.instances([page]))),
        "flags": h([f.model_dump() for f in flags]),
        "money_fields": sorted(t.money_fields),
        "citations": t.citations,
    }
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True))
print("wrote", sys.argv[1], "from", out["archivist_from"])
