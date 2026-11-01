"""Anonymous weight-access preflight; never downloads weights or loads a credential."""
from __future__ import annotations

import argparse
import hashlib
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

MODEL = "meta-models/Muse-Glimmer-30B"
REVISION = "a4e59da52a7bc87ae7251dd5545c0dd437c44b68"
USER_AGENT = "archivist-hackathon/0.1 (+https://github.com/kamil-shirinov/Archivist)"


def check_access() -> dict:
    files = {}
    for filename in ("config.json", "tokenizer_config.json", "model.safetensors.index.json"):
        request = Request(
            f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{filename}",
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
        except HTTPError as error:
            if error.code in (401, 403):
                raise SystemExit(
                    "Weight access requires authorization. Open "
                    f"https://huggingface.co/{MODEL}, accept any access terms, then create a "
                    "read-only Hugging Face token and install it as a Modal secret named "
                    "glimmer-hf with field HF_TOKEN. Do not paste it in chat."
                ) from None
            raise SystemExit(f"Weight preflight failed: HTTP {error.code} for {filename}") from None
        files[filename] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return {"model": MODEL, "revision": REVISION, "anonymous_access": True, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", action="store_true")
    args = parser.parse_args()
    if args.packages:
        versions = {}
        for name in ("torch", "transformers", "peft", "bitsandbytes", "accelerate", "safetensors"):
            req = Request(f"https://pypi.org/pypi/{name}/json", headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=30) as response:
                versions[name] = json.load(response)["info"]["version"]
        print(json.dumps(versions, indent=2))
    else:
        print(json.dumps(check_access(), indent=2))


if __name__ == "__main__":
    main()
