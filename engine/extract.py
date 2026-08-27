"""Turn a source document into clean pages of text, with its metadata.

The engine only ever reads documents you already hold: files you have
downloaded from an official register, or text you have pasted. It does no
fetching of its own. That is a deliberate boundary, not a missing feature:
the registers set terms on automated access, and asking is the path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import profiles, textclean


@dataclass
class Document:
    """One source document, extracted and cleaned but not yet parsed."""

    path: str
    title: str
    pages: list[str]
    profile_key: str
    jurisdiction: str
    year: int | None = None
    act_number: str | None = None
    currency: str | None = None          # "as at" date printed on the source
    source_note: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.pages)


# A short title runs from a capital to a year: "Privacy Act 1988",
# "Residential Tenancies and Rooming Accommodation Act 2008". Interior
# words may be lowercase ("and", "of"), which is what distinguishes a real
# title from the tail of a wrapped one.
_TITLE_LINE = re.compile(
    r"^([A-Z][\w'()&,\-]*(?:\s+[\w'()&,\-]+){0,12}\s+"
    r"(?:Act|Regulations?|Code|Rules|Ordinance)"
    r"(?:\s+\(\w{2,3}\))?\s+(?:1[89]\d{2}|20\d{2}))\s*$")
# A few acts carry no year in the short title at all: the Commonwealth of
# Australia Constitution Act is the one every Australian has heard of.
_TITLE_LINE_NO_YEAR = re.compile(
    r"^([A-Z][\w'()&,\-]*(?:\s+[\w'()&,\-]+){2,12}\s+"
    r"(?:Act|Regulations?|Code|Rules|Ordinance))\s*$")
# Pages carry the title beside a page number, on either side of it, and
# front matter numbers its pages in roman. Stripping both sides at once
# would eat the year off the end of a title, so each side is tried alone.
_LEADING_PAGE_NUMBER = re.compile(r"^\s*(?:\d{1,4}|[ivxlc]{1,6})\s+", re.I)
_TRAILING_PAGE_NUMBER = re.compile(r"\s+(?:\d{1,4}|[ivxlc]{1,6})\s*$", re.I)
_ACT_NUMBER = re.compile(r"\bAct\s+No\.\s*(\d+)\s+of\s+(\d{4})\b", re.I)
_CURRENCY_PATTERNS = (
    re.compile(r"This compilation was prepared on\s+(\d{1,2}\s+\w+\s+\d{4})", re.I),
    re.compile(r"Compilation date:\s*(\d{1,2}\s+\w+\s+\d{4})", re.I),
    re.compile(r"Reprint\s+\d+[A-Z]?\s+effective\s+(\d{1,2}\s+\w+\s+\d{4})", re.I),
    re.compile(r"Reprinted as in force on\s+(\d{1,2}\s+\w+\s+\d{4})", re.I),
    re.compile(r"Current as at\s+(\d{1,2}\s+\w+\s+\d{4})", re.I),
    re.compile(r"in force (?:on|at)\s+(\d{1,2}\s+\w+\s+\d{4})", re.I),
)
_YEAR_IN_TITLE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
# Some reprints say so on their own cover. If a source disclaims its own
# authority, every answer drawn from it inherits that.
_NOT_AUTHORISED = re.compile(
    r"(not an authoris(?:ed|ing) copy|unauthorised version|"
    r"this reprint is not)", re.I)
_LEADER = re.compile(r"\.{4,}|(?:\.\s){4,}")


def _read_pdf(path: Path) -> list[str]:
    try:
        import pypdf
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "Reading PDFs needs pypdf. Install it with: pip install pypdf"
        ) from exc

    reader = pypdf.PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # a damaged page should not lose the document
            pages.append("")
    return pages


def _read_text(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # Form feed is the conventional page break in text dumps.
    return raw.split("\f") if "\f" in raw else [raw]


def _strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        html = html.replace(entity, char)
    return html


def _guess_title(pages: list[str], fallback: str) -> str:
    """Take the act's name from its own running header.

    Both drafting offices repeat the short title on nearly every page. A
    cover page may wrap it across three lines, so the most frequent
    single-line match across the document beats the first one found.
    """
    # Count the pages a candidate appears on, not the times it appears. The
    # amendment history at the back of a compilation names dozens of other
    # acts, sometimes repeatedly; only the act's own title runs the length
    # of the document.
    pages_seen: dict[tuple[str, bool], set[int]] = {}
    scanned = pages[:500]
    for number, page in enumerate(scanned):
        for line in page.splitlines():
            line = line.strip()
            if _LEADER.search(line):
                continue
            for candidate_line in (
                line,
                _LEADING_PAGE_NUMBER.sub("", line).strip(),
                _TRAILING_PAGE_NUMBER.sub("", line).strip(),
            ):
                match = _TITLE_LINE.match(candidate_line)
                dated = True
                if not match:
                    match = _TITLE_LINE_NO_YEAR.match(candidate_line)
                    dated = False
                if not match:
                    continue
                title = " ".join(match.group(1).split())
                if title.count("(") != title.count(")"):
                    continue
                pages_seen.setdefault((title, dated), set()).add(number)
                break

    if pages_seen:
        # Only a title that runs through the document is the act's own; a
        # heading in the amendment notes reaches a handful of pages at most.
        floor = max(3, len(scanned) // 12)
        reaching = {key: seen for key, seen in pages_seen.items()
                    if len(seen) >= floor}
        if reaching:
            # Widest reach wins, then a dated title over an undated one,
            # then the longer and more specific.
            (title, _), _ = max(
                reaching.items(),
                key=lambda kv: (len(kv[1]), kv[0][1], len(kv[0][0])))
            return title

    name = re.sub(r"[_-]+", " ", fallback)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _find(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def load(path: str | Path, profile_key: str | None = None) -> Document:
    """Extract, clean and describe one document on disk."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raw_pages = _read_pdf(path)
    elif suffix in {".html", ".htm", ".xhtml"}:
        raw_pages = [_strip_tags(path.read_text(encoding="utf-8", errors="replace"))]
    else:
        raw_pages = _read_text(path)

    pages = [textclean.clean(page) for page in raw_pages]

    # Some reprints extract with words split by stray spaces ("eviden ce").
    # The document's own vocabulary is the evidence for putting them back.
    vocabulary = textclean.build_vocabulary("\n".join(pages))
    repaired = [textclean.rejoin_split_words(page, vocabulary) for page in pages]
    rejoined = sum(1 for before, after in zip(pages, repaired) if before != after)
    pages = repaired

    head = "\n".join(pages[:3])

    profile = (profiles.get(profile_key) if profile_key
               else profiles.detect(head, path.name))

    warnings: list[str] = []
    if rejoined:
        warnings.append(
            f"Words split by stray spaces were rejoined on {rejoined} page(s), "
            "using words the document itself uses elsewhere. The wording is "
            "otherwise untouched.")
    if not any(page.strip() for page in pages):
        warnings.append(
            "No text could be extracted. The source is probably a scan; it "
            "would need optical character recognition before the engine can "
            "read it."
        )
    if profile.key == "generic":
        warnings.append(
            "Drafting office not recognised, so the generic layout profile is "
            "in use. Page furniture removal is conservative and some running "
            "headers may survive into the text."
        )

    number = None
    year = None
    number_match = _ACT_NUMBER.search(head)
    if number_match:
        number = number_match.group(1)
        year = int(number_match.group(2))

    title = _guess_title(pages, path.stem)
    if year is None:
        year_match = _YEAR_IN_TITLE.search(title)
        if year_match:
            year = int(year_match.group(1))

    # The currency line lives on the cover for Queensland and in the
    # compilation note for the Commonwealth, and running headers repeat it
    # later, so the search widens past the front matter before giving up.
    currency = _find(_CURRENCY_PATTERNS, head)
    if currency is None:
        currency = _find(_CURRENCY_PATTERNS, "\n".join(pages[:60]))
    if _NOT_AUTHORISED.search(head):
        warnings.append(
            "The source says on its own cover that it is not an authorised "
            "copy. Check the register before relying on any wording from it."
        )
    if currency is None:
        warnings.append(
            "No currency date found on the source. The engine cannot tell you "
            "how current this text is, so every answer drawn from it carries "
            "that gap."
        )

    return Document(
        path=str(path),
        title=title,
        pages=pages,
        profile_key=profile.key,
        jurisdiction=profile.jurisdiction,
        year=year,
        act_number=number,
        currency=currency,
        source_note=f"Read from {path.name}",
        warnings=warnings,
    )
