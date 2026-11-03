"""No "we", "our" or "us" in anything a reader sees (P57).

Archivist is a solo entry. What the author decided or found is written with "I" and "my", and what the system does with
"Archivist", so nothing a reader sees speaks for a group: the README (headings included), eval/README.md,
CONTRIBUTING.md, SECURITY.md, the landing page and the review app's on-screen text. This test fails if one comes back.

What it does not read: code, comments, file and test names, link targets, and CODE_OF_CONDUCT.md, which is the
Contributor Covenant's own text. "US" in capitals (the United States) is not "us".
"""

import importlib.util
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# we, our, ours, ourselves, us (any case but all capitals) and let's, with a straight or a curly apostrophe
FIRST_PERSON_PLURAL = re.compile(r"(?<![\w-])(?:[Ww]e|[Oo]urs?|[Oo]urselves|[Uu]s|[Ll]et[’']s)(?![\w-])")

MARKDOWN = ("README.md", "eval/README.md", "CONTRIBUTING.md", "SECURITY.md")
APP_PAGES = ["ui/index.html"]
APP_SCRIPTS = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "ui" / "js").rglob("*.js"))
LANDING_SCRIPT = "docs/landing/landing.js"

TEXT_ATTRIBUTES = {"alt", "aria-label", "aria-description", "placeholder", "title", "content"}


def found_in(text: str) -> list[str]:
    """Each first-person plural word in `text`, with a few words either side."""
    return [text[max(m.start() - 25, 0) : m.end() + 25].replace("\n", " ") for m in FIRST_PERSON_PLURAL.finditer(text)]


def prose(markdown: str) -> str:
    """The words of a Markdown file: no code, no HTML tags, no link or image targets."""
    text = re.sub(r"```.*?```|~~~.*?~~~", " ", markdown, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\]\([^)\s]*\)", "]", text)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"https?://\S+", " ", text)


class Words(HTMLParser):
    """The text of an HTML page that a reader sees or hears: its text, and the attributes that carry words."""

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        self.out += [v for k, v in attrs if k in TEXT_ATTRIBUTES and v]

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_words(html: str) -> str:
    parser = Words()
    parser.feed(html)
    return "\n".join(parser.out)


# A comment, or a string. Scanning left to right, a comment's quotes and a string's slashes are each swallowed whole.
JS_TOKEN = re.compile(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`", re.S)


def js_strings(source: str) -> str:
    """The string and template literals of a script, which is where a page's words are, without its code or comments."""
    return "\n".join(m.group(0)[1:-1] for m in JS_TOKEN.finditer(source) if m.group(0)[0] in "\"'`")


def landing_html() -> str:
    spec = importlib.util.spec_from_file_location("landing_for_voice", ROOT / "docs" / "landing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render(ROOT)


@pytest.mark.parametrize("name", MARKDOWN)
def test_the_markdown_a_reader_opens_has_no_we_our_or_us(name):
    text = prose((ROOT / name).read_text(encoding="utf-8"))
    assert found_in(text) == [], f"{name}: write it with I, my or Archivist"


def test_the_readmes_headings_speak_for_one_person():
    headings = re.findall(r"^#{1,6}\s+(.+?)\s*$", (ROOT / "README.md").read_text(encoding="utf-8"), re.M)
    assert "What I learned about Meta's models" in headings and "What I tried and dropped" in headings
    assert [h for h in headings if FIRST_PERSON_PLURAL.search(h)] == []


def test_the_landing_page_has_no_we_our_or_us():
    assert found_in(html_words(landing_html())) == []
    assert found_in(js_strings((ROOT / LANDING_SCRIPT).read_text(encoding="utf-8"))) == []


@pytest.mark.parametrize("name", APP_PAGES)
def test_the_review_apps_page_has_no_we_our_or_us(name):
    assert found_in(html_words((ROOT / name).read_text(encoding="utf-8"))) == [], name


@pytest.mark.parametrize("name", APP_SCRIPTS)
def test_the_review_apps_on_screen_text_has_no_we_our_or_us(name):
    assert found_in(js_strings((ROOT / name).read_text(encoding="utf-8"))) == [], name


# P58: the author is "I" or "me" in what a reader sees, never "the author"; the plans, DECISIONS.md and the records keep
# their own words
THE_AUTHOR = re.compile(r"\bthe author(?:['’]s)?\b", re.I)
VOICE = ("README.md", "eval/README.md")


@pytest.mark.parametrize("name", VOICE)
def test_the_readmes_say_i_not_the_author(name):
    text = prose((ROOT / name).read_text(encoding="utf-8"))
    assert THE_AUTHOR.findall(text) == [], f"{name}: write it with I or me"


def test_the_landing_page_and_the_app_say_i_not_the_author():
    assert THE_AUTHOR.findall(html_words(landing_html())) == []
    for name in APP_PAGES:
        assert THE_AUTHOR.findall(html_words((ROOT / name).read_text(encoding="utf-8"))) == [], name
    for name in APP_SCRIPTS + [LANDING_SCRIPT]:
        assert THE_AUTHOR.findall(js_strings((ROOT / name).read_text(encoding="utf-8"))) == [], name
    assert THE_AUTHOR.findall("labelled by the author") and THE_AUTHOR.findall("The author’s check"), "the check catches it"


def test_the_check_itself_catches_each_form_and_lets_the_united_states_through():
    for bad in ("We tried it", "what we learned", "our results", "Ours", "tell us", "Us too", "We’re sure", "we're sure", "Let’s look", "we put it back ourselves"):
        assert found_in(bad), bad
    for fine in ("US Treasury Bulletin", "the US Government", "a bus", "focus", "user", "Your own hardware", "well", "we-b", "ours_"):
        assert found_in(fine) == [], fine
    hits = found_in(js_strings('const ours = 1; // we put it back\nel.textContent = "We’re here";'))
    assert len(hits) == 1 and "We’re here" in hits[0], "a script's string is read, its identifiers and comments are not"
