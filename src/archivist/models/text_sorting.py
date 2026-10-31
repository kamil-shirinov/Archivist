"""The unchanged phase-2 text protocol, usable through the production model capability."""
from dataclasses import asdict

from archivist.models.base import SortFamily, SortRequest


def families_of(doc_types):
    return tuple(SortFamily(name, typ.template.identity.title, typ.description)
                 for name, typ in doc_types.items())


def payload(request: SortRequest):
    # Reuse, rather than reimplement, the frozen system/user prompt and excerpt rule.
    from archivist.glimmer.data import SYSTEM, prompt
    from archivist.glimmer.phase2 import decision_text
    families = [asdict(f) for f in request.families]
    return [{'system': SYSTEM, 'prompt': prompt(decision_text(text), families)}
            for text in request.texts]


def parse(raw, request):
    from archivist.glimmer.phase2 import parse_phase2
    from archivist.models.base import SortAnswer
    labels = [f.family for f in request.families] + ['other']
    if [r['index'] for r in raw] != list(range(len(request.texts))):
        raise ValueError('sort output cardinality/order differs from request')
    return tuple(SortAnswer(parse_phase2(r['text'], labels, at_token_limit=r['at_token_limit']),
        r['text'], r['input_tokens'], r['output_tokens'], r['at_token_limit']) for r in raw)
