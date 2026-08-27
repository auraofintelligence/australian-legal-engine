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


_SPLIT_CANDIDATE = re.compile(r"\b([A-Za-z]{2,})([ ])([A-Za-z]{1,2})\b")
_ALPHA = re.compile(r"[a-z]+")


def build_vocabulary(text: str) -> dict[str, int]:
    """Count the words a document uses, as its own reference dictionary."""
    counts: dict[str, int] = {}
    for token in _ALPHA.findall(text.lower()):
        counts[token] = counts.get(token, 0) + 1
    return counts


def rejoin_split_words(text: str, vocabulary: dict[str, int],
                       min_joined: int = 5, max_fragment: int = 2) -> str:
    """Repair words that extraction split apart, using the document's own words.

    Some reprints extract as "polic e officer" and "eviden ce", where
    kerning has been read as a space. Searching such a document for
    "police" then misses the very provisions that matter.

    No dictionary is needed to fix this, because the document is its own
    dictionary: if "eviden" appears twice in 200,000 words while "evidence"
    appears hundreds of times, the two-word reading is the broken one. Both
    tests must pass before anything is joined, so ordinary pairs like "may
    be" are never touched.
    """

    def repair(match: re.Match[str]) -> str:
        head, space, tail = match.group(1), match.group(2), match.group(3)
        joined = (head + tail).lower()
        if (vocabulary.get(joined, 0) >= min_joined
                and vocabulary.get(head.lower(), 0) <= max_fragment
                and len(tail) <= max_fragment):
            return head + tail
        return head + space + tail

    return _SPLIT_CANDIDATE.sub(repair, text)


def is_mostly_upper(line: str) -> bool:
    """True for lines that are shouting, which in statute PDFs means a banner."""
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.8
