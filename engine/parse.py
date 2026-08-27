"""Read an act as the tree it actually is.

Legislation is not prose with headings. It is a tree: an act divides into
chapters and parts, parts into sections, sections into subsections and
paragraphs, and the meaning of a line depends on where it sits. Cut that
tree into fixed-size blocks and you sever a definition from the term it
defines, or an exception from the rule it softens.

So this module walks the cleaned text and rebuilds the tree, giving every
provision an address (act, part, section, subsection) that travels with
it. The address is what makes a citation possible later, and a citation
the engine cannot produce is an answer it will not give.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import profiles, textclean
from .extract import Document

# Sections whose numbering restarts inside a schedule are addressed with the
# schedule prefix so two "section 5"s never collide.
_ROMAN = re.compile(r"^[ivxlc]+$", re.I)


@dataclass
class Provision:
    """One addressable unit of law, with its place in the tree."""

    kind: str                      # section, subsection, paragraph, definition...
    number: str                    # "12", "3A", "a", "ii"
    heading: str
    text: str
    act: str
    jurisdiction: str
    chapter: str = ""
    part: str = ""
    division: str = ""
    subdivision: str = ""
    schedule: str = ""
    section: str = ""
    subsection: str = ""
    paragraph: str = ""
    page: int | None = None
    currency: str | None = None
    children: list["Provision"] = field(default_factory=list)

    @property
    def address(self) -> str:
        """A citation a person can take to the register and check."""
        bits: list[str] = []
        if self.schedule:
            bits.append(f"Schedule {self.schedule}")
        if self.section:
            ref = f"s {self.section}"
            if self.subsection:
                ref += f"({self.subsection})"
            if self.paragraph:
                ref += f"({self.paragraph})"
            if self.kind == "subparagraph" and self.number:
                ref += f"({self.number})"
            bits.append(ref)
        elif self.kind == "definition":
            bits.append(f"definition of '{self.number}'")
        label = ", ".join(bits) if bits else self.kind
        return f"{self.act} {label}".strip()

    @property
    def context(self) -> str:
        """Where this provision sits, in words, for a reader."""
        bits = []
        if self.chapter:
            bits.append(f"Chapter {self.chapter}")
        if self.part:
            bits.append(f"Part {self.part}")
        if self.division:
            bits.append(f"Division {self.division}")
        if self.subdivision:
            bits.append(f"Subdivision {self.subdivision}")
        if self.schedule:
            bits.append(f"Schedule {self.schedule}")
        return " > ".join(bits)

    def full_text(self, limit: int = 1800) -> str:
        """The provision as a person reads it: itself, then what sits under it.

        Many sections carry no words of their own; the rule lives in the
        subsections beneath. Returning the bare heading for those would
        hand a reader, or a model, a label instead of a rule.
        """
        parts: list[str] = []
        if self.text.strip():
            parts.append(self.text.strip())

        def walk(node: "Provision") -> None:
            for child in node.children:
                body = child.text.strip()
                if body:
                    parts.append(f"({child.number}) {body}")
                walk(child)

        walk(self)
        out = " ".join(parts).strip()
        if len(out) > limit:
            out = out[:limit].rsplit(" ", 1)[0] + " [...]"
        return out

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "number": self.number,
            "heading": self.heading,
            "text": self.text,
            "act": self.act,
            "jurisdiction": self.jurisdiction,
            "chapter": self.chapter,
            "part": self.part,
            "division": self.division,
            "subdivision": self.subdivision,
            "schedule": self.schedule,
            "section": self.section,
            "subsection": self.subsection,
            "paragraph": self.paragraph,
            "page": self.page,
            "currency": self.currency,
            "address": self.address,
            "context": self.context,
        }


@dataclass
class ParsedAct:
    """An act, as a flat list of provisions plus the tree of sections."""

    title: str
    jurisdiction: str
    currency: str | None
    profile_key: str
    sections: list[Provision]
    definitions: list[Provision]
    warnings: list[str] = field(default_factory=list)
    front_matter: str = ""

    @property
    def provisions(self) -> list[Provision]:
        """Every addressable provision, parents before children."""
        out: list[Provision] = []

        def walk(node: Provision) -> None:
            out.append(node)
            for child in node.children:
                walk(child)

        for section in self.sections:
            walk(section)
        out.extend(self.definitions)
        return out

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        for provision in self.provisions:
            kinds[provision.kind] = kinds.get(provision.kind, 0) + 1
        return {
            "title": self.title,
            "jurisdiction": self.jurisdiction,
            "currency": self.currency,
            "profile": self.profile_key,
            "sections": len(self.sections),
            "provisions": len(self.provisions),
            "by_kind": kinds,
            "warnings": len(self.warnings),
        }


# A contents entry runs the heading out to a page number with a leader of
# dots, either solid (Commonwealth) or spaced (Queensland). Legislative text
# itself never contains a run of four dots, which makes this a reliable tell.
_LEADER = re.compile(r"\.{4,}|(?:\.\s){4,}")

# The heading of a contents entry ends in the page number it points at,
# even where the leader itself was lost in extraction.
_TRAILING_PAGE = re.compile(r"\s\d{1,4}$")

_CONTENTS_HEADING = re.compile(r"^\s*(Contents|Table of (Contents|Provisions))\s*$", re.I)


def _is_contents_line(line: str) -> bool:
    return bool(_LEADER.search(line))


def _is_furniture(line: str, profile: profiles.Profile,
                  banners: frozenset[str] = frozenset()) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # The act's own short title, alone on a line, is the running header
    # every drafting office prints. It is never operative text, and left in
    # it both pollutes provisions and pulls every search towards the acts
    # with the most pages.
    if stripped.casefold().strip(" .,") in banners:
        return True
    for pattern in profile.furniture:
        if pattern.match(stripped):
            return True
    return False


# State and territory names stand alone on Queensland-style cover pages.
_JURISDICTION_BANNERS = frozenset({
    "queensland", "new south wales", "victoria", "western australia",
    "south australia", "tasmania", "australian capital territory",
    "northern territory", "commonwealth of australia", "australia",
    "contents", "notes", "endnotes", "table of provisions",
})


def parse(document: Document) -> ParsedAct:
    """Rebuild the structure of one extracted document."""
    profile = profiles.get(document.profile_key)
    warnings = list(document.warnings)

    # Lines that are page furniture for this particular document: its own
    # title, and the jurisdiction banners that sit on a cover page.
    banners = set(_JURISDICTION_BANNERS)
    title = document.title.casefold().strip(" .,")
    if len(title) > 6:
        banners.add(title)
        # Compilations print the title with its act number beside it.
        if document.act_number:
            banners.add(f"{title} act no. {document.act_number}".strip())
    banners = frozenset(banners)

    sections: list[Provision] = []
    definitions: list[Provision] = []

    chapter = part = division = subdivision = schedule = ""
    current_section: Provision | None = None
    current_subsection: Provision | None = None
    current_paragraph: Provision | None = None
    buffer: list[str] = []
    front_matter: list[str] = []
    in_toc = False

    def flush() -> None:
        """Attach the buffered lines to the deepest open provision."""
        nonlocal buffer
        if not buffer:
            return
        chunk = textclean.collapse("\n".join(buffer))
        buffer = []
        if not chunk:
            return
        target = current_paragraph or current_subsection or current_section
        if target is None:
            front_matter.append(chunk)
        else:
            target.text = (target.text + " " + chunk).strip()

    def new_section(number: str, heading: str, page: int) -> Provision:
        return Provision(
            kind="section", number=number, heading=heading.strip(), text="",
            act=document.title, jurisdiction=document.jurisdiction,
            chapter=chapter, part=part, division=division,
            subdivision=subdivision, schedule=schedule,
            section=number, page=page, currency=document.currency,
        )

    for page_number, page in enumerate(document.pages, start=1):
        lines = page.split("\n")
        for i, raw_line in enumerate(lines):
            line = raw_line.rstrip()
            if not line.strip():
                continue
            if _is_furniture(line, profile, banners):
                continue

            # A table of contents repeats every heading in the act. Parsing it
            # would double every section, so contents entries are dropped and
            # the block they sit in is skipped until real text resumes.
            if _CONTENTS_HEADING.match(line):
                in_toc = True
                continue
            if _is_contents_line(line):
                in_toc = True
                continue
            if in_toc:
                # A contents block ends at the first line that reads like law:
                # a sentence, or a numbered provision with real text after it.
                if line.rstrip().endswith((".", ";", ":")) and len(line.strip()) > 40:
                    in_toc = False
                else:
                    continue

            stripped = line.strip()

            match = profile.schedule.match(stripped)
            if match and len(stripped) < 90:
                flush()
                schedule = match.group(1)
                chapter = part = division = subdivision = ""
                current_section = current_subsection = current_paragraph = None
                continue

            match = profile.chapter.match(stripped)
            if match and len(stripped) < 90:
                flush()
                chapter = match.group(1)
                part = division = subdivision = ""
                continue

            match = profile.part.match(stripped)
            if match and len(stripped) < 90:
                flush()
                part = match.group(1)
                division = subdivision = ""
                continue

            match = profile.division.match(stripped)
            if match and len(stripped) < 90:
                flush()
                division = match.group(1)
                subdivision = ""
                continue

            match = profile.subdivision.match(stripped)
            if match and len(stripped) < 90:
                flush()
                subdivision = match.group(1)
                continue

            match = profile.section_start.match(line)
            if (match and not textclean.is_mostly_upper(match.group(2))
                    and not _TRAILING_PAGE.search(match.group(2))):
                flush()
                current_section = new_section(match.group(1), match.group(2),
                                              page_number)
                current_subsection = current_paragraph = None
                sections.append(current_section)
                continue

            if current_section is not None:
                match = profile.subsection.match(line)
                if match:
                    flush()
                    current_subsection = Provision(
                        kind="subsection", number=match.group(1), heading="",
                        text="", act=document.title,
                        jurisdiction=document.jurisdiction,
                        chapter=chapter, part=part, division=division,
                        subdivision=subdivision, schedule=schedule,
                        section=current_section.number,
                        subsection=match.group(1),
                        page=page_number, currency=document.currency,
                    )
                    current_paragraph = None
                    current_section.children.append(current_subsection)
                    buffer.append(match.group(2))
                    continue

                match = profile.subparagraph.match(line)
                if match and _ROMAN.match(match.group(1)) and current_paragraph:
                    flush()
                    node = Provision(
                        kind="subparagraph", number=match.group(1), heading="",
                        text="", act=document.title,
                        jurisdiction=document.jurisdiction,
                        chapter=chapter, part=part, division=division,
                        subdivision=subdivision, schedule=schedule,
                        section=current_section.number,
                        subsection=current_subsection.number if current_subsection else "",
                        paragraph=current_paragraph.number,
                        page=page_number, currency=document.currency,
                    )
                    current_paragraph.children.append(node)
                    buffer.append(match.group(2))
                    continue

                match = profile.paragraph.match(line)
                if match:
                    flush()
                    parent = current_subsection or current_section
                    current_paragraph = Provision(
                        kind="paragraph", number=match.group(1), heading="",
                        text="", act=document.title,
                        jurisdiction=document.jurisdiction,
                        chapter=chapter, part=part, division=division,
                        subdivision=subdivision, schedule=schedule,
                        section=current_section.number,
                        subsection=current_subsection.number if current_subsection else "",
                        paragraph=match.group(1),
                        page=page_number, currency=document.currency,
                    )
                    parent.children.append(current_paragraph)
                    buffer.append(match.group(2))
                    continue

                match = profile.definition.match(stripped)
                if match and current_paragraph is None:
                    flush()
                    definitions.append(Provision(
                        kind="definition", number=match.group(1).strip(),
                        heading=match.group(1).strip(), text=stripped,
                        act=document.title,
                        jurisdiction=document.jurisdiction,
                        chapter=chapter, part=part, division=division,
                        subdivision=subdivision, schedule=schedule,
                        section=current_section.number,
                        subsection=current_subsection.number if current_subsection else "",
                        page=page_number, currency=document.currency,
                    ))
                    continue

            buffer.append(stripped)

    flush()

    if not sections:
        warnings.append(
            "No sections were found. Either the source is a scan with no text "
            "layer, or its layout does not match any profile the engine knows. "
            "Check the extracted text before relying on anything here."
        )

    empty = [s for s in sections if not s.text and not s.children]
    if len(empty) > len(sections) * 0.3 and sections:
        warnings.append(
            f"{len(empty)} of {len(sections)} sections came out with no text. "
            "That usually means the layout profile is wrong for this source."
        )

    return ParsedAct(
        title=document.title,
        jurisdiction=document.jurisdiction,
        currency=document.currency,
        profile_key=document.profile_key,
        sections=sections,
        definitions=definitions,
        warnings=warnings,
        front_matter=" ".join(front_matter[:20]),
    )
