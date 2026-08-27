"""Layout profiles, one per drafting office.

Australia's nine parliaments publish through nine drafting offices, and
each one lays out a page its own way. A Commonwealth compilation puts the
part name and the section number in a running header and the page number
beside the act's short title. Queensland puts a marker like "[s 35]" at
the top of the page, then the act, chapter and part, then a reprint line.

A parser that ignores this reads page furniture as if it were law. So the
layout knowledge lives here, declared per office, and the parser stays
general. Adding a jurisdiction means adding a profile, not editing the
parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Pattern


@dataclass(frozen=True)
class Profile:
    """How one drafting office lays out a page and numbers a provision."""

    key: str
    label: str
    jurisdiction: str

    # Lines that are page furniture rather than law.
    furniture: tuple[Pattern[str], ...] = field(default_factory=tuple)

    # A section beginning: "35 Rental purchase plan agreements" or
    # "6  Interpretation". Group 1 is the number, group 2 the heading.
    section_start: Pattern[str] = re.compile(
        r"^\s{0,4}(\d+[A-Z]{0,3})\s{1,6}([A-Z][^\n]{2,120})$"
    )

    # Structural headings above the section level.
    chapter: Pattern[str] = re.compile(r"^\s*Chapter\s+(\w+)\b\s*(.*)$", re.I)
    part: Pattern[str] = re.compile(r"^\s*Part\s+([\dIVXLC]+[A-Z]*)\b\s*(.*)$", re.I)
    division: Pattern[str] = re.compile(r"^\s*Division\s+(\w+)\b\s*(.*)$", re.I)
    subdivision: Pattern[str] = re.compile(r"^\s*Subdivision\s+(\w+)\b\s*(.*)$", re.I)
    schedule: Pattern[str] = re.compile(r"^\s*Schedule\s+(\w+)\b\s*(.*)$", re.I)

    # Numbering inside a section.
    subsection: Pattern[str] = re.compile(r"^\s{0,6}\((\d+[A-Z]{0,3})\)\s+(.*)$")
    paragraph: Pattern[str] = re.compile(r"^\s{0,10}\(([a-z]{1,3})\)\s+(.*)$")
    subparagraph: Pattern[str] = re.compile(r"^\s{0,14}\(([ivxlc]{1,6})\)\s+(.*)$")

    # A defined term introduced in an interpretation section:
    # "Norfolk Island agency means:".
    definition: Pattern[str] = re.compile(
        r"^\s*([a-z][A-Za-z'\- ]{2,60})\s+(means|includes)\b"
    )

    notes: str = ""


def _p(pattern: str, flags: int = 0) -> Pattern[str]:
    return re.compile(pattern, flags)


COMMONWEALTH = Profile(
    key="cth",
    label="Commonwealth, Office of Parliamentary Counsel",
    jurisdiction="Commonwealth",
    furniture=(
        # "16            Privacy Act 1988        " and its mirror.
        _p(r"^\s*\d{1,4}\s+[A-Z][\w'\-() ]{3,80}\s*$"),
        _p(r"^\s*[A-Z][\w'\-() ]{3,80}\s+\d{1,4}\s*$"),
        # Running headers naming the current structural unit.
        _p(r"^\s*(Part|Division|Subdivision|Chapter|Schedule)\s+[\dIVXLCA-Z]+\s"),
        _p(r"^\s*Section\s+\d+[A-Z]{0,3}\s*$"),
        _p(r"^\s*ComLaw Authoritative Act\b"),
        _p(r"^\s*Authorised Version\b"),
        _p(r"^\s*Federal Register of Legislation\b"),
        _p(r"^\s*Compilation No\.", re.I),
        _p(r"^\s*Registered:", re.I),
        _p(r"^\s*Prepared by the Office of Parliamentary Counsel\b", re.I),
        _p(r"^\s*This compilation was prepared\b", re.I),
    ),
    # OPC indents subsection numbers by a space: " (3) For the purposes...".
    subsection=_p(r"^\s{0,8}\((\d+[A-Z]{0,3})\)\s+(.*)$"),
    section_start=_p(r"^\s{0,4}(\d+[A-Z]{0,3})\s{1,8}([A-Z][^\n]{2,120})$"),
    notes="Compilations carry a preparation date and an amendment ceiling on "
          "the title page; both are captured as currency metadata.",
)

QUEENSLAND = Profile(
    key="qld",
    label="Queensland, Office of the Queensland Parliamentary Counsel",
    jurisdiction="Queensland",
    furniture=(
        # The section marker OQPC prints at the top of every page.
        _p(r"^\s*\[s\s*\d+[A-Z]{0,3}\]\s*$"),
        _p(r"^\s*Reprint\s+\d+[A-Z]?\s+effective\b", re.I),
        _p(r"^\s*Current as at\b", re.I),
        # The footer sometimes extracts as one line, the page
        # number and reprint note together.
        _p(r"^\s*Page\s+\d+\s+Reprint\b", re.I),
        _p(r"^\s*Page\s+\d+\s*$", re.I),
        _p(r"^\s*(Chapter|Part|Division|Subdivision|Schedule)\s+[\dIVXLCA-Z]+\s"),
        _p(r"^\s*Authorised by the Parliamentary Counsel\b", re.I),
    ),
    # OQPC starts numbering hard against the left margin.
    subsection=_p(r"^\s{0,4}\((\d+[A-Z]{0,3})\)\s*(.*)$"),
    paragraph=_p(r"^\s{0,6}\(([a-z]{1,3})\)\s*(.*)$"),
    subparagraph=_p(r"^\s{0,8}\(([ivxlc]{1,6})\)\s*(.*)$"),
    section_start=_p(r"^\s{0,2}(\d+[A-Z]{0,3})\s{1,4}([A-Z][^\n]{2,120})$"),
    notes="Reprints carry an effective date; the [s N] page marker is a "
          "reliable cross-check on the parsed section boundaries.",
)

GENERIC = Profile(
    key="generic",
    label="Generic Australian statute layout",
    jurisdiction="Unknown",
    furniture=(
        _p(r"^\s*Page\s+\d+\s*(of\s+\d+)?\s*$", re.I),
        _p(r"^\s*\d{1,4}\s*$"),
        _p(r"^\s*(Part|Division|Subdivision|Chapter|Schedule)\s+[\dIVXLCA-Z]+\s"),
    ),
    notes="Used when the source jurisdiction is unknown. Structure detection "
          "still runs; page furniture removal is conservative.",
)

PROFILES: dict[str, Profile] = {
    "cth": COMMONWEALTH,
    "qld": QUEENSLAND,
    "generic": GENERIC,
}


def get(key: str | None) -> Profile:
    """Return a profile by key, falling back to the generic layout."""
    if not key:
        return GENERIC
    return PROFILES.get(key.lower(), GENERIC)


def detect(sample_text: str, filename: str = "") -> Profile:
    """Guess the drafting office from a page of text and the file name.

    Detection is evidence-based and deliberately narrow: a marker that only
    one office uses. Where nothing matches, the generic profile applies and
    the caller can override.
    """
    name = filename.lower()
    if name.startswith("qld") or " qld " in name or "queensland" in name:
        return QUEENSLAND

    text = sample_text or ""
    if re.search(r"\[s\s*\d+[A-Z]{0,3}\]", text) or re.search(
        r"Reprint\s+\d+[A-Z]?\s+effective", text, re.I
    ):
        return QUEENSLAND
    if re.search(r"ComLaw|Office of Parliamentary Counsel, Canberra|"
                 r"Federal Register of Legislation", text, re.I):
        return COMMONWEALTH
    if re.search(r"\bAct No\.\s*\d+\s*of\s*\d{4}\b", text) and re.search(
        r"This compilation was prepared", text, re.I
    ):
        return COMMONWEALTH

    return GENERIC
