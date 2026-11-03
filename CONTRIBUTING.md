# Contributing to Archivist

Thank you for looking. Archivist is open source under the [Apache License 2.0](LICENSE), and a change is welcome if it keeps the integrity rules below. To report a vulnerability, follow [SECURITY.md](SECURITY.md), not a public issue.

## Set up

You need Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/kamil-shirinov/Archivist.git
cd Archivist
uv sync --frozen
uv run pre-commit install
```

A clean clone passes the tests and the verify command with no key, response cache or scan. Docker alone also works: `docker build -t archivist .`, then `docker run --rm archivist python -m archivist.verify` ([Run it yourself](README.md#run-it-yourself)).

## The Check

Before you open a pull request, run both, unpiped, so that a failure stops you:

```bash
uv run pytest -q && uv run python -m archivist.replay
```

`archivist.replay` replays every committed run from the response cache, `cache/`, which is not committed, and it spends nothing. In a clean clone it stops for lack of the cache; run `uv run python -m archivist.verify` instead, which rebuilds the published numbers, charts and exports from what is committed and is what CI runs. Tests never touch the network, and some browser tests skip, with their reason, until the gitignored scans are fetched (`uv run python -m archivist.ingest.fraser`).

## The pull-request rule

One task, one short-lived branch, one pull request. Main moves only by a pull request whose CI has passed; the steps are in [`AGENTS.md`](AGENTS.md) (Branches).

1. Start from the latest main: `git fetch origin main`, then `git switch -c <short-name> origin/main`.
2. Commit on that branch only, after the Check passes and pre-commit is clean.
3. Push the branch and open a pull request into `main`. Never push to main, never force-push, never use `--no-verify`, and never move or delete a tag: `prereg-real-treasury`, `run-real-treasury`, `prereg-real-openw` and `run-real-openw` are records.
4. Wait for CI to pass, then merge with `gh pr merge --rebase --delete-branch`. Never bypass a failing check.

## Integrity rules every change must keep

These are what make the numbers believable, so a change that breaks one will not be merged however good it looks. They are stated in full in [`CLAUDE.md`](CLAUDE.md) (Hard rules).

- **No tuning on held-out pages.** Nothing runs on `data/test` except the pre-registered runs, and nothing on the held-out real issues except a pre-registered run by its own runner on its own tag. Choose settings on development pages.
- **Plans are registered before runs.** A run that will be reported needs its plan committed first, as [`PREREGISTRATION.md`](PREREGISTRATION.md), [`PREREGISTRATION_REAL.md`](PREREGISTRATION_REAL.md) and [`PREREGISTRATION_OPENW.md`](PREREGISTRATION_OPENW.md) were, and scoring rules are written and tested before any model output is scored.
- **Deviations are recorded before the results.** A plan changes only under its Deviations heading, and the entry is committed before the result it concerns is read.
- **Only synthetic or public-domain pages are sent to a model.** No real bank or customer data, ever. Every model call goes through `archivist.models` (registry, cache, budget, backend), and no HTTP call is made anywhere else.
- **No keys in the repository.** Never read, print or commit `.env` or any key; [`.env.example`](.env.example) lists the names, empty. Never put personal data (an email, a name or a local path) in a request, header or URL.
- **Numbers come from files.** A number you publish must be rebuilt from a committed result, and `archivist.verify` or a test must fail if it drifts.

## Where the reasons are

[`DECISIONS.md`](DECISIONS.md) records each decision in one line with its reason; read it before changing a design that looks odd, and add a line when you make a decision. [`eval/README.md`](eval/README.md) explains how every number was measured and how to reproduce it.

## Adding a table type

A table type is a template file, `templates/<family>.yaml` ([Document types in `CLAUDE.md`](CLAUDE.md#document-types), decision [D31](DECISIONS.md)). The flow is: Muse Spark drafts it from two or three development pages (`archivist.templates.draft`), an arithmetic test reads the pages twice and checks every rule (`archivist.templates.test`), and **only a person approves it**, with `archivist.templates.approve`, which records who, when and the evidence file's sha256. Never mark a template approved yourself, and never edit an approved template or its evidence file: it would no longer load. Approving a template changes no committed run; a run uses only the types its config names.
