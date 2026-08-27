"""Follow the threads between provisions.

The 2013 read worked by following threads: one act defines a term, another
borrows it, a third amends them both. Doing that by hand is what turned a
folder of PDFs into an understanding, and it is also what made it take a
summer.

This module does the same walk mechanically. It reads every provision for
the references a drafter writes, builds a graph of them, and lets you
start anywhere and see what a provision leans on, what leans on it, and
where a chain of references leads.

Every edge is evidence-backed: it exists because a specific provision
contains specific words, and the words are kept so a person can check the
claim rather than trust the graph.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .index import Index, Record

# "section 12", "s 12", "ss 12 and 13", "sections 12 to 15"
_SECTION_REF = re.compile(
    r"\b(?:section|sections|s|ss)\s*(\d+[A-Z]{0,3})"
    r"(?:\s*\((\d+[A-Z]{0,3})\))?", re.I)

# "the Privacy Act 1988", "the Freedom of Information Act 1982", "the
# Retirement Villages Act 1999". Interior words may be lowercase, which is
# what makes "Freedom of Information" one title rather than two fragments,
# but only a short list of connectives is allowed so the match cannot run
# away backwards through a sentence.
_ACT_REF = re.compile(
    r"\b([A-Z][\w'&\-]*"
    r"(?:\s+(?:of|and|the|for|in|on|to|a|an)|\s+[A-Z][\w'&\-]*){0,10}"
    r"\s+(?:Act|Regulations?|Code|Rules|Ordinance)"
    r"(?:\s+\(\w{2,3}\))?\s+(?:1[89]\d{2}|20\d{2}))")

_LEADING_THE = re.compile(r"^the\s+", re.I)


def _normalise_act(name: str) -> str:
    return " ".join(_LEADING_THE.sub("", name).split())


def _same_act(one: str, two: str) -> bool:
    """True when two names refer to the same act.

    A reference may carry the act's full name, or the tail of it where the
    title wrapped across a line in the source.
    """
    first = _normalise_act(one).casefold()
    second = _normalise_act(two).casefold()
    if not first or not second:
        return False
    return first == second or first.endswith(second) or second.endswith(first)

# Words a drafter uses to point at another provision, which say what kind
# of thread this is.
_RELATIONS = (
    ("defines", re.compile(r"\b(means|includes|has the meaning given)\b", re.I)),
    ("applies", re.compile(r"\b(applies to|apply to|application of)\b", re.I)),
    ("subject to", re.compile(r"\bsubject to\b", re.I)),
    ("despite", re.compile(r"\b(despite|notwithstanding)\b", re.I)),
    ("amends", re.compile(r"\b(amend(?:s|ed|ment)?|inserted|repealed|omitted)\b", re.I)),
    ("penalty", re.compile(r"\b(penalt(?:y|ies)|offence|guilty of)\b", re.I)),
)


@dataclass
class Edge:
    """One thread: a provision pointing at something else, with the words."""

    source_address: str
    source_act: str
    target_act: str
    target_section: str
    target_subsection: str
    relation: str
    quote: str

    @property
    def target_label(self) -> str:
        label = self.target_act
        if self.target_section:
            label += f" s {self.target_section}"
            if self.target_subsection:
                label += f"({self.target_subsection})"
        return label

    def to_dict(self) -> dict:
        data = self.__dict__.copy()
        data["target_label"] = self.target_label
        return data


def _relation_for(text: str) -> str:
    for name, pattern in _RELATIONS:
        if pattern.search(text):
            return name
    return "refers to"


def _quote_around(text: str, position: int, width: int = 130) -> str:
    start = max(0, position - width // 2)
    end = min(len(text), position + width // 2)
    fragment = text[start:end].strip()
    if start > 0:
        fragment = "[...] " + fragment
    if end < len(text):
        fragment = fragment + " [...]"
    return fragment


def extract_edges(record: Record, known_acts: set[str]) -> list[Edge]:
    """Read one provision for the threads it contains."""
    edges: list[Edge] = []
    text = record.text
    if not text:
        return edges

    # An act named in the text redirects any section reference that follows
    # it, which is how a drafter writes "section 5 of the Retirement
    # Villages Act 1999".
    named_acts: list[tuple[int, str]] = [
        (match.start(), _normalise_act(match.group(1)))
        for match in _ACT_REF.finditer(text)
    ]

    for match in _SECTION_REF.finditer(text):
        position = match.start()
        # The nearest act named just after the reference wins, then the
        # nearest named before it, then the act the provision sits in.
        target_act = record.act
        following = [name for start, name in named_acts
                     if 0 <= start - match.end() <= 40]
        preceding = [name for start, name in named_acts if start < position]
        if following:
            target_act = following[0]
        elif preceding:
            target_act = preceding[-1]

        section = match.group(1)
        subsection = match.group(2) or ""
        # Where the reference names the act this provision already sits in,
        # record it under the act's full title rather than the fragment the
        # drafter or the page break happened to leave.
        if _same_act(target_act, record.act):
            target_act = record.act
        # A provision pointing at itself is not a thread.
        if target_act == record.act and section == record.section:
            continue

        edges.append(Edge(
            source_address=record.address,
            source_act=record.act,
            target_act=target_act,
            target_section=section,
            target_subsection=subsection,
            relation=_relation_for(_quote_around(text, position)),
            quote=_quote_around(text, position),
        ))

    # An act named with no section beside it is still a thread worth having.
    for start, name in named_acts:
        if _same_act(name, record.act):
            continue
        nearby = any(abs(start - match.start()) < 60
                     for match in _SECTION_REF.finditer(text))
        if nearby:
            continue
        edges.append(Edge(
            source_address=record.address,
            source_act=record.act,
            target_act=name,
            target_section="",
            target_subsection="",
            relation=_relation_for(_quote_around(text, start)),
            quote=_quote_around(text, start),
        ))

    return edges


@dataclass
class ThreadMap:
    """Every thread found in an index, indexed both ways."""

    edges: list[Edge] = field(default_factory=list)
    out_by_address: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    in_by_target: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    acts: set[str] = field(default_factory=set)

    def add(self, edge: Edge) -> None:
        self.edges.append(edge)
        self.out_by_address[edge.source_address].append(edge)
        self.in_by_target[_key(edge.target_act, edge.target_section)].append(edge)

    def outbound(self, address: str) -> list[Edge]:
        return self.out_by_address.get(address, [])

    def inbound(self, act: str, section: str = "") -> list[Edge]:
        return self.in_by_target.get(_key(act, section), [])

    def act_links(self) -> dict[tuple[str, str], int]:
        """How many times one act points at another."""
        counts: dict[tuple[str, str], int] = {}
        for edge in self.edges:
            if edge.source_act == edge.target_act:
                continue
            key = (edge.source_act, edge.target_act)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def stats(self) -> dict:
        relations: dict[str, int] = {}
        for edge in self.edges:
            relations[edge.relation] = relations.get(edge.relation, 0) + 1
        external = {edge.target_act for edge in self.edges
                    if edge.target_act not in self.acts}
        return {
            "threads": len(self.edges),
            "by_relation": relations,
            "acts_in_index": len(self.acts),
            "acts_pointed_at_but_not_indexed": len(external),
        }


    def reading_list(self) -> list[tuple[str, int, list[str]]]:
        """Acts your sources point at but do not contain.

        This is the 2013 thread-following turned into a next step: the
        cabinet you have tells you which acts it leans on, so the gaps in
        it are named by the law itself rather than guessed at.
        """
        counts: dict[str, int] = {}
        examples: dict[str, list[str]] = {}
        for edge in self.edges:
            if any(_same_act(edge.target_act, act) for act in self.acts):
                continue
            counts[edge.target_act] = counts.get(edge.target_act, 0) + 1
            if len(examples.setdefault(edge.target_act, [])) < 3:
                examples[edge.target_act].append(edge.source_address)
        return sorted(
            ((act, count, examples[act]) for act, count in counts.items()),
            key=lambda item: item[1], reverse=True)


def _key(act: str, section: str) -> str:
    return f"{act.casefold()}|{section}"


def build(index: Index, limit: int | None = None) -> ThreadMap:
    """Read every indexed provision for the threads it contains."""
    known = {source["act"] for source in index.sources}
    thread_map = ThreadMap(acts=set(known))
    records = index.records if limit is None else index.records[:limit]
    for record in records:
        # Sections are indexed with their subsections folded in, so reading
        # only the leaf provisions would count the same reference twice.
        if record.kind == "section":
            continue
        for edge in extract_edges(record, known):
            thread_map.add(edge)
    return thread_map


def trace(index: Index, thread_map: ThreadMap, act_fragment: str,
          section: str, depth: int = 2) -> list[tuple[int, Edge]]:
    """Walk outward from one provision, following what it points at."""
    seen: set[str] = set()
    trail: list[tuple[int, Edge]] = []

    def walk(current_act: str, current_section: str, level: int) -> None:
        if level > depth:
            return
        for record in index.by_citation(current_act, current_section):
            for edge in thread_map.outbound(record.address):
                key = f"{edge.target_act}|{edge.target_section}|{edge.source_address}"
                if key in seen:
                    continue
                seen.add(key)
                trail.append((level, edge))
                if edge.target_section:
                    walk(edge.target_act, edge.target_section, level + 1)

    walk(act_fragment, section, 1)
    return trail
