"""The cache key of every re-read the held-out deep check asks, in the order verify asks them.

Read-only: uses the frozen code's own functions, calls no model, writes only the output file.
Run from archivist/: uv run python <this> <out.jsonl>
"""

import io
import json
import sys

from PIL import Image

from archivist.models import LLMRequest
from archivist.models.cache import cache_key
from archivist.models.registry import load_roles
from archivist.pipeline import extract, reread, verify
from archivist.templates import real_test as rt

out = rt.OUT_DIR / "held_out"
roles = load_roles(rt.CONFIG)
llm = roles[reread.ROLE]
doc_types = rt._types(rt.CONFIG)
pages = sorted(extract.load_predictions(out / "predictions.jsonl"), key=lambda p: p.page_id)

with open(sys.argv[1], "w") as sink:
    index = 0
    for page in pages:
        image = Image.open(io.BytesIO(rt.resolve(page.page_id, "held_out").path.read_bytes()))
        plugin = doc_types.get(page.doc_type)
        for value in page.values:
            if value.citation is None or not verify.needs_reread(value):
                continue
            picture = reread.crop(image, reread.region(value.citation))
            prompt = plugin.reread_prompt(value.field_id)
            keys = [
                cache_key(
                    llm.name,
                    llm.model_id,
                    LLMRequest(
                        role=reread.ROLE,
                        prompt=attempt,
                        images=(picture,),
                        json_schema=reread.SCHEMA,
                        max_output_tokens=reread.REREAD_TOKENS,
                    ),
                    llm.settings,
                )
                for attempt in (prompt, prompt + reread.RETRY_NOTE)
            ]
            line = {"index": index, "page": page.page_id, "field": value.field_id,
                    "key": keys[0], "retry_key": keys[1]}
            sink.write(json.dumps(line) + "\n")
            index += 1
print(index, "re-reads")
