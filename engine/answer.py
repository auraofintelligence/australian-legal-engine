"""Assemble a grounded answer packet.

The engine does not write prose about the law. It finds provisions, quotes
them exactly, states where each one came from and how current it is, and
stops there. Language and judgement are someone else's job: a person
reading, or a model working under the prompt this module writes.

That split is the whole design. A citation produced by a parser is a fact
about the source file. A citation produced by a language model is a guess
that usually happens to be right. Only the first kind can be checked
mechanically, so only the first kind is what this engine emits.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from .index import Index, Record

REGISTERS = {
    "Commonwealth": "https://www.legislation.gov.au/",
    "New South Wales": "https://legislation.nsw.gov.au/",
    "Victoria": "https://www.legislation.vic.gov.au/",
    "Queensland": "https://www.legislation.qld.gov.au/",
    "Western Australia": "https://www.legislation.wa.gov.au/",
    "South Australia": "https://www.legislation.sa.gov.au/",
    "Tasmania": "https://www.legislation.tas.gov.au/",
    "Australian Capital Territory": "https://www.legislation.act.gov.au/",
    "Northern Territory": "https://legislation.nt.gov.au/",
}


@dataclass
class Extract:
    """One provision, ready to be quoted and checked."""

    address: str
    context: str
    heading: str
    text: str
    jurisdiction: str
    currency: str | None
    source: str
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def register(self) -> str:
        return REGISTERS.get(self.jurisdiction, "")

    def to_dict(self) -> dict:
        data = self.__dict__.copy()
        data["register"] = self.register
        return data


@dataclass
class Packet:
    """What the engine returns: extracts, provenance and a grounded prompt."""

    question: str
    extracts: list[Extract]
    notes: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.extracts)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "found": self.found,
            "extracts": [extract.to_dict() for extract in self.extracts],
            "notes": self.notes,
        }

    # ---- renderings -----------------------------------------------------

    def as_text(self, width: int = 78) -> str:
        """The packet as something readable in a terminal."""
        lines = [f"Question: {self.question}", ""]
        if not self.found:
            lines.append(
                "No provision in the index matches that. The engine will not "
                "answer without one.")
            lines.extend("- " + note for note in self.notes)
            return "\n".join(lines)

        for number, extract in enumerate(self.extracts, start=1):
            lines.append(f"[{number}] {extract.address}")
            if extract.heading:
                lines.append(f"    {extract.heading}")
            if extract.context:
                lines.append(f"    in {extract.context}")
            stamp = extract.currency or "no date printed on the source"
            lines.append(f"    as at {stamp} | {extract.jurisdiction}")
            if extract.reasons:
                lines.append(f"    matched on: {'; '.join(extract.reasons)}")
            lines.append("")
            lines.extend(textwrap.wrap(extract.text, width=width,
                                       initial_indent="    ",
                                       subsequent_indent="    "))
            lines.append("")

        if self.notes:
            lines.append("Notes")
            lines.extend("  - " + note for note in self.notes)
        return "\n".join(lines)

    def as_prompt(self) -> str:
        """A prompt that hands the extracts to any AI assistant, on a leash.

        The engine has already done the part a model is bad at: finding the
        right provisions and naming them exactly. The prompt exists so the
        model does the part it is good at, in plain words, without being
        given room to invent a section number.
        """
        blocks = []
        for number, extract in enumerate(self.extracts, start=1):
            stamp = extract.currency or "currency date not printed on the source"
            blocks.append(
                f"[{number}] {extract.address}\n"
                f"Heading: {extract.heading or '(none)'}\n"
                f"Position: {extract.context or '(top level)'}\n"
                f"Jurisdiction: {extract.jurisdiction}\n"
                f"Text as at {stamp}:\n\"{extract.text}\""
            )
        body = "\n\n".join(blocks)
        registers = sorted({extract.register for extract in self.extracts
                            if extract.register})
        register_line = " ".join(registers) if registers else "the official register"

        return (
            "Answer the question below using only the numbered provisions "
            "that follow. They were retrieved from Australian legislation "
            "and quoted exactly.\n\n"
            f"Question: {self.question}\n\n"
            f"Provisions:\n{body}\n\n"
            "Rules for your answer:\n"
            "1. Use only the text above. If it does not answer the question, "
            "say so plainly and stop.\n"
            "2. Cite the bracketed number and the address after every claim, "
            "for example: [1] " +
            (self.extracts[0].address if self.extracts else "Act s 1") + ".\n"
            "3. Do not name any section, subsection or act that does not "
            "appear above. Inventing a citation is the failure this whole "
            "system exists to prevent.\n"
            "4. Say which date the text is current to, and note that "
            "legislation changes.\n"
            "5. Write plainly, for someone who is not a lawyer. Gloss any "
            "legal term the first time you use it.\n"
            "6. This is legal information, not legal advice. For advice about "
            "a particular situation, say a qualified lawyer is needed.\n\n"
            f"The reader can check every provision above at: {register_line}"
        )


def _note_for(extracts: list[Extract]) -> list[str]:
    notes: list[str] = []
    undated = [extract for extract in extracts if not extract.currency]
    if undated:
        notes.append(
            f"{len(undated)} of {len(extracts)} extracts carry no currency "
            "date from their source, so how current they are is unknown.")
    stamps = {extract.currency for extract in extracts if extract.currency}
    if stamps:
        notes.append(
            "Text is as at " + "; ".join(sorted(stamps)) +
            ". Legislation changes: check the register for the current text.")
    jurisdictions = sorted({extract.jurisdiction for extract in extracts})
    if len(jurisdictions) > 1:
        notes.append(
            "Extracts span " + " and ".join(jurisdictions) +
            ". Provisions from different parliaments do not override one "
            "another simply by being quoted together.")
    notes.append(
        "Legal information, not legal advice. For advice about your own "
        "situation, a qualified lawyer.")
    return notes


def ask(index: Index, question: str, limit: int = 5,
        jurisdiction: str | None = None, act: str | None = None,
        bridge: bool = True, wider: bool = False) -> Packet:
    """Retrieve the provisions that bear on a question.

    By default the question is widened from everyday words to drafting
    words before searching, because otherwise an ordinary question misses
    the law: across the 2012 corpus "landlord" appears in one provision
    and "lessor" in 672. Anything added is reported in the notes.
    """
    searched = question
    expansion = None
    if bridge or wider:
        from . import vocab

        expansion = vocab.expand(index, question, use_corpus=wider)
        if expansion.changed:
            searched = expansion.as_query()

    hits = index.search(searched, limit=limit, jurisdiction=jurisdiction, act=act)
    extracts = [
        Extract(
            address=record.address,
            context=record.context,
            heading=record.heading,
            text=record.text,
            jurisdiction=record.jurisdiction,
            currency=record.currency,
            source=record.source,
            score=round(score, 3),
            reasons=reasons,
        )
        for record, score, reasons in hits
    ]

    notes = _note_for(extracts) if extracts else [
        "Nothing in the index matched. Either the relevant act has not been "
        "indexed, or the wording differs from the query. Try the words the "
        "act itself would use.",
        "Legal information, not legal advice.",
    ]
    if expansion is not None and expansion.changed:
        notes.insert(0, expansion.describe())
    return Packet(question=question, extracts=extracts, notes=notes)


def cite(index: Index, act_fragment: str, section: str,
         subsection: str = "") -> Packet:
    """Fetch a provision by address rather than by search."""
    records = index.by_citation(act_fragment, section, subsection)
    extracts = [
        Extract(
            address=record.address, context=record.context,
            heading=record.heading, text=record.text,
            jurisdiction=record.jurisdiction, currency=record.currency,
            source=record.source, score=1.0, reasons=["looked up by address"],
        )
        for record in records
    ]
    label = f"{act_fragment} section {section}"
    if subsection:
        label += f"({subsection})"
    notes = _note_for(extracts) if extracts else [
        f"No provision matching {label} is in the index.",
        "Legal information, not legal advice.",
    ]
    return Packet(question=label, extracts=extracts, notes=notes)
