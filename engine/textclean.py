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


_WORD_SPAN = re.compile(r"[A-Za-z]+")
_ALPHA = re.compile(r"[a-z]+")


def build_vocabulary(text: str) -> dict[str, int]:
    """Count the words a document uses, as its own reference dictionary."""
    counts: dict[str, int] = {}
    for token in _ALPHA.findall(text.lower()):
        counts[token] = counts.get(token, 0) + 1
    return counts


def rejoin_split_words(text: str, vocabulary: dict[str, int],
                       min_joined: int = 5, ratio: float = 4.0) -> str:
    """Repair words that extraction split apart, using the document's own words.

    Some reprints extract as "polic e officer" and "eviden ce", where
    kerning has been read as a space. Searching such a document for
    "police" then misses the very provisions that matter.

    No dictionary is needed, because the document is its own. The test is
    which reading dominates: in one tenancy act "fo" appears 41 times and
    "for" 1,681, so the split reading is the broken one. Ordinary pairs go
    the other way and are left alone, with a wide margin: "may" appears 554
    times and "maybe" never; "in" 952 times and "into" 85.

    Two earlier versions got this wrong in instructive ways. Asking whether
    the fragment was rare fails exactly where it matters, because a
    systematic fault makes its own fragments common. And sweeping with a
    regex let a rejected pair swallow the word after it: in "agent fo r",
    "agent fo" was tested, found meaningless, and consumed, so "fo r" never
    got its turn. Walking word by word gives every pair its own chance.
    """
    words = list(_WORD_SPAN.finditer(text))
    if not words:
        return text

    pieces: list[str] = []
    cursor = 0
    index = 0
    while index < len(words):
        current = words[index]
        following = words[index + 1] if index + 1 < len(words) else None
        merged = False

        if following is not None:
            head = current.group(0)
            tail = following.group(0)
            gap = text[current.end():following.start()]
            if (gap == " " and len(head) >= 2 and 1 <= len(tail) <= 2):
                joined_count = vocabulary.get((head + tail).lower(), 0)
                head_count = vocabulary.get(head.lower(), 0)
                if (joined_count >= min_joined
                        and joined_count >= ratio * max(head_count, 1)):
                    pieces.append(text[cursor:current.start()])
                    pieces.append(head + tail)
                    cursor = following.end()
                    index += 2
                    merged = True

        if not merged:
            index += 1

    pieces.append(text[cursor:])
    return "".join(pieces)


def is_mostly_upper(line: str) -> bool:
    """True for lines that are shouting, which in statute PDFs means a banner."""
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.8
