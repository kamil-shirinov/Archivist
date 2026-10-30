"""Render strict phase-1 results and the explicitly post hoc framing diagnostic."""
from __future__ import annotations

import json
from pathlib import Path

from archivist.glimmer.data import OUT


def _read(out: Path, name: str) -> dict:
    return json.loads((out/name).read_text())


def _percent(value) -> str:
    return 'undefined' if value is None else f'{value:.1%}'


def build(out: Path = OUT) -> str:
    data=_read(out,'data_manifest.json')
    arms={name:_read(out,f'{name}_metrics.json') for name in
          ('baseline','trained','spark_raw','spark_confirmed')}
    native={name:_read(out,f'{name}_native_framing_metrics.json') for name in ('baseline','trained')}
    billing=_read(out,'billing.json')
    cost=_read(out,'cost.json')
    training=_read(out,'training_metrics.json')['training']
    lines=['# P31 — phase 1 completed','',
           '**Frozen strict result:** untrained 39/40 (97.5%); trained 0/40, with 40 framing-invalid answers.',
           '**Post hoc native-framing diagnostic:** untrained 39/40; trained 40/40 (100%).',
           'These are separate results. The diagnostic is not a pre-registered improvement claim.','',
           'The trained model directly continues the open `assistant` header with `to=user`; the frozen',
           'parser only recognised a final answer after a new complete assistant-turn header.',
           'Reattaching the already-open header decodes those saved responses. The original strict',
           'metrics, scorer and raw outputs are retained unchanged; no inference or training was repeated.',
           'The diagnostic was tested on synthetic native frames before applying it to the saved answers.',
           '[Native protocol reference](https://dev.meta.ai/docs/muse-glimmer/prompting).','',
           '| Arm | Frozen strict accuracy | Invalid / missing | Native-framing diagnostic |',
           '|---|---:|---:|---:|']
    for name in arms:
        m=arms[name]
        d=_percent(native[name]['accuracy']) if name in native else 'not applicable'
        lines.append(f"| {name} | {m['accuracy']:.1%} | {m['invalid']} / {m['missing']} | {d} |")
    lines+=['','Muse Spark is `muse-spark-1.3-contributor` from the existing image-based development sweep.',
            'Its title-confirmed assignments define the proxy labels, so 100% confirmed agreement is a',
            'teacher-agreement ceiling. The Glimmer arms see only OCR text.','',
            '## Per-family validation precision / recall','',
            '| Family | Support | Untrained P / R | Trained strict P / R | Trained native diagnostic P / R |',
            '|---|---:|---:|---:|---:|']
    for family,row in arms['baseline']['per_family'].items():
        b=arms['trained']['per_family'][family]
        d=native['trained']['per_family'][family]
        lines.append(f"| {family} | {row['support']} | {_percent(row['precision'])} / {_percent(row['recall'])} | {_percent(b['precision'])} / {_percent(b['recall'])} | {_percent(d['precision'])} / {_percent(d['recall'])} |")
    lines+=['','All TP/FP/FN counts, confusion matrices and Spark family metrics are in the adjacent JSON files.',
            'Undefined precision has no predicted positives; it is not a perfect score.','',
            '## Data and training','',
            f"Frozen data: {data['train_pages']} unique training pages; {data['validation_pages']} validation pages.",
            'Training has two approved development positives per family and 105 `other` pages.',
            'Validation has one positive per family and 35 `other` pages. These are proxy labels, not human truth.',
            f"Removed {data['duplicate_ocr_removed_from_training']} training pages whose OCR duplicated validation inputs.",
            f"QLoRA: three epochs, {training['encoded_examples']} expanded examples, 57 optimizer steps,",
            f"{training['trainable_parameters']:,} adapter parameters across 208 language attention projections; vision frozen.",
            f"Training runtime {training['train_runtime']:.2f}s; final aggregate training loss {training['train_loss']:.6f}.",
            'Base revision, hyperparameters, prompt, input hashes and splits are in PLAN.md and the manifests.',
            'One positive per family is too little evidence for a generalisation claim.','',
            '## Failures and recovery','',
            'Training completed and saved the adapter, then a return-wrapper NameError discarded its response.',
            'The existing 58.8 MB adapter was recovered and SHA256-verified on CPU; training ran once.',
            'Only the return wrapper and CPU recovery support were corrected; inference-function ASTs and',
            'the model runtime, prompt, scorer and training settings were unchanged. See recovery.json and',
            'training_return_failure.json. The failed GPU job retains its full worst-case reservation.',
            'The native-framing issue is a separate measurement limitation, reported above, with original scores preserved.',
            'Metadata whitespace normalisation for pre-commit does not change adapter tensors or JSON meaning.','',
            '## Cost','',
            f"Modal reported resource charges so far: **${billing['total_usd']:.6f}** (billing may lag; before any credits).",
            '| GPU job | Reported app cost, including CPU/memory/egress | Worst-case reservation |',
            '|---|---:|---:|']
    for job in cost:
        lines.append(f"| {job['stage']} | ${job['reported_cost_usd']:.6f} | ${job['maximum_usd']:.4f} |")
    overhead=billing['total_usd']-sum(job['reported_cost_usd'] for job in cost)
    lines+=['',f"Other setup/build/recovery charges: ${overhead:.6f}.",
            f"All GPU reservations plus the $2.50 overhead reserve: ${sum(job['maximum_usd'] for job in cost)+2.5:.4f}, below $25.",
            'The experiment ledger is reconciled to the reported app charges and mirrored in the canonical branch ledger.',
            'All experiment Modal apps are stopped; no service is left running.','',
            '## Checks','',
            'Run `uv run pytest -q && uv run python -m archivist.replay`; final check records are in CHECKS.md.',
            'The sparse checkout excludes tests/test_labelling.py and tests/test_score.py because they import',
            'the prohibited labelling/scorer code. Every other discovered test runs. No held-out page/result,',
            'labelling code, original scorer or git tag was opened.','',
            '## Phase 2 remains closed','',
            'Needs explicit owner permission after freezing the adapter, inference code, prompt and configuration.',
            'Resolve and pre-register native response framing before phase-2 measurement.',
            'Then compare untrained, trained and Muse Spark sorting on Treasury held-out pages with pipeline-confirmed',
            'types, title-check rejections and the owner\'s 50-page hand check where available. Report per-family',
            'precision/recall against proxy labels, human agreement separately and total cost. The 50-page check',
            'cannot measure recall outside pipeline-confirmed pages.','',
            'A new budget estimate is required: extrapolating the current sequential validation runtimes to the',
            '4,569 held-out pages specified by PREREGISTRATION_REAL.md gives roughly $76 for both Glimmer arms.',
            'That exceeds the remaining $25 cap; a budget-compliant serving plan or an explicitly raised cap is needed',
            'before any held-out GPU job. This is an extrapolation from development timings, not a held-out run.',
            'No original pre-registration, scorer, labelling record or tag was changed.','']
    return '\n'.join(lines)


def main():
    text=build()
    (OUT/'REPORT.md').write_text(text)
    print(text)


if __name__=='__main__':
    main()
