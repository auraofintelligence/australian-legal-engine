"""Repair the text that comes out of statute PDFs.

PDF extraction mangles the things legal text cares about most: the smart
quotes inside defined terms, the dashes that introduce a list, the
ligatures in ordinary words, and the line breaks that split a section
number from its heading. Everything downstream (the parser, the index,
the citations) reads the output of this module, so it runs first and it
never guesses: each repair below is a known, reversible substitution.
"""

from __future__ import annotations

import re
import unicodedata

# Characters that PDF extraction commonly produces in place of the real one.
# The replacement character U+FFFD turns up wherever the source used a
# non-Latin-1 punctuation mark, which in Australian drafting is nearly
# always a curly apostrophe or an em dash.
_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
}

_PUNCTUATION = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",
    "…": "...",
    "­": "",          # soft hyphen
}

# U+FFFD sitting between two word characters is an apostrophe
# ("person�s place"); at the end of a clause it is a dash
# ("other than�").
_FFFD_APOSTROPHE = re.compile(r"(?<=\w)�(?=\w)")
_FFFD_DASH = re.compile(r"�")

# A word split across a line break by a hyphen: "sub-\nsection".
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")

# Runs of spaces or tabs, but never newlines: line structure is meaningful
# to the parser and must survive.
_HORIZONTAL_SPACE = re.compile(r"[ \t]+")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")
_BLANK_RUN = re.compile(r"\n{3,}")


def clean(text: str) -> str:
    """Normalise extracted statute text without touching its line structure."""
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)

    for bad, good in _LIGATURES.items():
        text = text.replace(bad, good)

    text = _FFFD_APOSTROPHE.sub("'", text)
    text = _FFFD_DASH.sub("-", text)

    for bad, good in _PUNCTUATION.items():
        text = text.replace(bad, good)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = _TRAILING_SPACE.sub("\n", text)
    text = _BLANK_RUN.sub("\n\n", text)

    return text.strip()


def collapse(text: str) -> str:
    """Flatten a provision to one line, for indexing and display.

    The parser keeps line structure because it carries meaning. Once a
    provision has been identified, its internal line breaks are an artefact
    of the page width and only get in the way of search.
    """
    return " ".join(clean(text).split())


def is_mostly_upper(line: str) -> bool:
    """True for lines that are shouting, which in statute PDFs means a banner."""
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.8
