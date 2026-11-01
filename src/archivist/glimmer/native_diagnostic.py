"""Post hoc native-framing diagnostic; never replaces pre-registered strict metrics.

The tokenizer generation prompt ends with <|start|>assistant. A direct final answer
continues that open header, whereas reasoning followed by a final answer emits another
full header. Reattach only the known, fixed open header before the unchanged strict parser.
"""
from __future__ import annotations

import json
from pathlib import Path

from archivist.glimmer.data import OUT
from archivist.glimmer.metrics import INVALID, parse_answer, score


ENDING_HEADER = '<|start|>assistant'


def decode_native_continuation(text: str, labels: list[str]) -> str:
    if text.startswith((' to=user<|message|>', ' to=self<|message|>')):
        text = ENDING_HEADER + text
    return parse_answer(text, labels)


def main() -> None:
    families=json.loads((OUT/'families.json').read_text())
    labels=[f['family'] for f in families]+['other']
    for stage in ('baseline','trained'):
        rows=json.loads((OUT/f'{stage}_predictions.json').read_text())['predictions']
        expected={row['page']:row['expected'] for row in rows}
        predicted={row['page']:(INVALID if row['at_token_limit'] else
                   decode_native_continuation(row['text'],labels)) for row in rows}
        record=score(expected,predicted,labels)
        record['status']='post_hoc_protocol_framing_diagnostic_not_preregistered_primary'
        record['method']='Reattach the fixed assistant header already present in the generation prompt; reuse unchanged strict label parser and scoring formulas.'
        (OUT/f'{stage}_native_framing_metrics.json').write_text(json.dumps(record,indent=2)+'\n')
        print(stage,record['accuracy'],record['invalid'])


if __name__=='__main__':
    main()
