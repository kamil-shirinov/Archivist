"""Archivist turns scanned financial archives into a verified database.

`uv run archivist` prints the main commands (COMMANDS). Everything is run from the repository root.
This module stays light: every other module imports the package, so it imports nothing of its own.
"""

# What each main command does, in plain English, then the command. tests/test_cli.py holds the
# list to the modules that exist, so it cannot name a command that is gone.
COMMANDS: tuple[tuple[str, str], ...] = (
    (
        "Check the published numbers, charts and exports against what is committed. "
        "Needs no key, saved model answers or scans.",
        "uv run python -m archivist.verify",
    ),
    (
        "Read a page live on your own machine, with every model call shown. "
        "Development pages only; Live calls need your own keys and spend.",
        "uv run --group glimmer python -m archivist.live",
    ),
    (
        "Replay every committed run from the saved answers. Spends nothing; "
        "needs the cache/ folder, which is not in the repository.",
        "uv run python -m archivist.replay",
    ),
    (
        "Export a run for the review app (data/bundles/<run>/bundle.json).",
        "uv run python -m archivist.export.bundle --run <run>",
    ),
    (
        "Export a run as a database (exports/<run>/: SQLite and one CSV per table).",
        "uv run python -m archivist.export.database --run <run>",
    ),
)


def text() -> str:
    """The list of main commands, as printed."""
    lines = [
        "Archivist turns scanned financial archives into a verified database.",
        "",
        "The main commands, run from the repository root:",
    ]
    for says, command in COMMANDS:
        lines += ["", f"  {says}", f"    {command}"]
    lines += ["", "The README has the rest, including how to open the review app."]
    return "\n".join(lines)


def main() -> None:
    print(text())
