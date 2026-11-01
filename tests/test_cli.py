"""The `archivist` command (P44): it lists the main commands, and every one it lists exists.

Nothing here runs a listed command; it only checks that the module each names can be found, so the
list cannot go on naming a command that has been renamed or removed.
"""

import importlib.util
import re
import tomllib
from pathlib import Path

import archivist

ROOT = Path(__file__).resolve().parents[1]


def module_of(command: str) -> str:
    found = re.search(r"python -m (\S+)", command)
    assert found, f"{command!r} does not run a module"
    return found.group(1)


def test_main_prints_every_command_with_its_description(capsys):
    archivist.main()
    shown = capsys.readouterr().out
    assert "Hello" not in shown
    for says, command in archivist.COMMANDS:
        assert command in shown
        assert says in shown


def test_the_list_names_verify_live_reading_replay_and_both_exports():
    modules = {module_of(command) for _, command in archivist.COMMANDS}
    assert modules == {
        "archivist.verify",
        "archivist.live",
        "archivist.replay",
        "archivist.export.bundle",
        "archivist.export.database",
    }


def test_every_listed_module_exists():
    for _, command in archivist.COMMANDS:
        name = module_of(command)
        assert importlib.util.find_spec(name) is not None, f"{name} is listed but not found"


def test_the_live_command_is_the_one_that_needs_the_glimmer_group():
    commands = {module_of(command): command for _, command in archivist.COMMANDS}
    assert "--group glimmer" in commands["archivist.live"]
    assert all("--group" not in c for name, c in commands.items() if name != "archivist.live")


def test_a_command_that_needs_a_run_says_so():
    for _, command in archivist.COMMANDS:
        if module_of(command).startswith("archivist.export."):
            assert command.endswith("--run <run>")


def test_the_console_script_is_this_function():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"]["archivist"] == "archivist:main"


def test_the_project_has_a_real_description():
    description = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "description"
    ]
    assert description and "Add your description" not in description
    assert len(description) < 120
