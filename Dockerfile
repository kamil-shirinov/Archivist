# Archivist in one image, with nothing to set up. It does two things, and needs no key, no model
# call and no response cache for either:
#
#   docker build -t archivist .
#   docker run --rm -p 8000:8000 archivist                   # the review app, at http://localhost:8000/
#   docker run --rm archivist python -m archivist.verify     # the judge checks
#
# The review app is the published site (docs/make_site.py, what GitHub Pages serves) built once
# here: the static app over the committed runs, nothing held out. The checks are archivist.verify,
# which rebuilds the committed report, charts and exports and compares them with the originals.
# .dockerignore lets in only what these two read; the model cache, data/ beyond the committed
# bundles, scans and test split, and any .env stay out.

# Both base images are pinned by digest (multi-architecture indexes: amd64 and arm64).
FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# The locked dependencies first, from the lockfile alone, so a change to the code does not
# reinstall them. The dev and glimmer groups (pytest, pre-commit, Modal) are not needed here.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev \
    && python docs/make_site.py --out /site

# Run as an ordinary user: both commands only read /app and /site.
USER 10001

EXPOSE 8000
CMD ["python", "-m", "http.server", "8000", "--bind", "0.0.0.0", "--directory", "/site"]
