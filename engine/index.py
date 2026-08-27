"""Build a searchable index of parsed provisions, on your own machine.

The index is a plain JSON file. No database to run, no service to sign up
to, no key to keep, and nothing leaves the machine it was built on. It can
be copied to a USB stick, read in a text editor, and rebuilt from the same
sources by anyone who has them.

Search is BM25 over the provision text, which is the standard ranking
function behind most keyword search, with two additions that legal text
needs: a phrase check, so "reasonable steps" beats two loose words, and a
citation check, so "section 13" finds section 13 rather than every
provision that mentions the word section.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .parse import ParsedAct, Provision

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

# Words carried by nearly every provision. Dropping them from the index
# keeps the file smaller and the ranking sharper, but they are kept for
# phrase matching, where "of" and "the" still do real work.
_STOPWORDS = frozenset("""
a an and are as at be been by for from has have if in into is it its may must
no not of on or shall such that the their there this to under upon was were
will with within would
""".split())


def tokenise(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    return [token for token in tokenise(text) if token not in _STOPWORDS]


@dataclass
class Record:
    """One indexed provision: its text, its address and its metadata."""

    uid: str
    text: str
    address: str
    act: str
    jurisdiction: str
    kind: str
    section: str
    subsection: str
    paragraph: str
    context: str
    heading: str
    currency: str | None
    page: int | None
    source: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "Record":
        return cls(**data)


@dataclass
class Index:
    """An on-disk, offline index of provisions."""

    records: list[Record] = field(default_factory=list)
    postings: dict[str, list[int]] = field(default_factory=dict)
    lengths: list[int] = field(default_factory=list)
    built: str = ""
    sources: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    # ---- building -------------------------------------------------------

    def add_act(self, act: ParsedAct, source_path: str = "") -> int:
        """Index every provision of one act that carries text of its own."""
        added = 0
        for provision in act.provisions:
            if provision.kind == "section":
                # A section is indexed whole: its own words plus the
                # subsections beneath it, which is where the rule usually
                # lives. Each subsection is still indexed separately, so a
                # precise query can land on the precise provision.
                text = provision.full_text()
            else:
                text = provision.text.strip()
            if not text or len(text) < 12:
                continue
            self._add(provision, act, source_path, text=text)
            added += 1

        self.sources.append({
            "act": act.title,
            "jurisdiction": act.jurisdiction,
            "currency": act.currency,
            "profile": act.profile_key,
            "path": source_path,
            "sections": len(act.sections),
            "indexed": added,
            "warnings": act.warnings,
        })
        return added

    def _add(self, provision: Provision, act: ParsedAct, source_path: str,
             text: str | None = None) -> None:
        uid = f"{len(self.records)}"
        body = (text if text is not None else provision.text).strip()
        searchable = f"{provision.heading} {body}".strip()
        record = Record(
            uid=uid,
            text=body or provision.heading,
            address=provision.address,
            act=act.title,
            jurisdiction=act.jurisdiction,
            kind=provision.kind,
            section=provision.section,
            subsection=provision.subsection,
            paragraph=provision.paragraph,
            context=provision.context,
            heading=provision.heading,
            currency=provision.currency,
            page=provision.page,
            source=source_path,
        )
        position = len(self.records)
        self.records.append(record)

        tokens = content_tokens(searchable)
        self.lengths.append(len(tokens))
        for token in set(tokens):
            self.postings.setdefault(token, []).append(position)

    # ---- persistence ----------------------------------------------------

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "australian-legal-engine/index/1",
            "built": self.built,
            "sources": self.sources,
            "skipped": self.skipped,
            "records": [record.to_dict() for record in self.records],
            "lengths": self.lengths,
            "postings": self.postings,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Index":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            records=[Record.from_dict(item) for item in payload["records"]],
            postings=payload["postings"],
            lengths=payload["lengths"],
            built=payload.get("built", ""),
            sources=payload.get("sources", []),
            skipped=payload.get("skipped", []),
        )

    # ---- search ---------------------------------------------------------

    def _bm25(self, query_tokens: list[str], k1: float = 1.5,
              b: float = 0.75) -> dict[int, float]:
        total = len(self.records)
        if not total:
            return {}
        average = sum(self.lengths) / total
        scores: dict[int, float] = {}
        counted = Counter(query_tokens)

        for token, query_count in counted.items():
            postings = self.postings.get(token)
            if not postings:
                continue
            # Inverse document frequency: a word in every provision tells
            # you nothing; a word in three provisions tells you a lot.
            idf = math.log(1 + (total - len(postings) + 0.5) / (len(postings) + 0.5))
            for position in postings:
                length = self.lengths[position] or 1
                # Term frequency is recomputed from the record rather than
                # stored, keeping the index file small enough to read.
                record = self.records[position]
                frequency = (record.text.lower().count(token)
                             + record.heading.lower().count(token) + 1)
                numerator = frequency * (k1 + 1)
                denominator = frequency + k1 * (1 - b + b * length / average)
                scores[position] = scores.get(position, 0.0) + (
                    idf * numerator / denominator * min(query_count, 3))
        return scores

    def search(self, query: str, limit: int = 8,
               jurisdiction: str | None = None,
               act: str | None = None,
               kind: str | None = None) -> list[tuple[Record, float, list[str]]]:
        """Rank provisions against a query, with the reasons for each hit."""
        tokens = content_tokens(query)
        scores = self._bm25(tokens)

        phrases = [phrase.lower() for phrase in re.findall(r'"([^"]{3,80})"', query)]
        loose = " ".join(tokens)
        citation = _citation_in(query)

        results: list[tuple[Record, float, list[str]]] = []
        for position, score in scores.items():
            record = self.records[position]
            if jurisdiction and record.jurisdiction.lower() != jurisdiction.lower():
                continue
            if act and act.lower() not in record.act.lower():
                continue
            if kind and record.kind != kind:
                continue

            reasons: list[str] = []
            lowered = record.text.lower()

            for phrase in phrases:
                if phrase in lowered:
                    score *= 2.5
                    reasons.append(f'exact phrase "{phrase}"')
            if len(tokens) > 1 and loose in lowered:
                score *= 1.6
                reasons.append("all query words together")
            if citation and _matches_citation(record, citation):
                score *= 4.0
                reasons.append(f"cited as {citation[0]} {citation[1]}")
            # A drafter names a section after what it does, so a query that
            # lands on the heading has usually found the right door.
            if record.heading:
                heading_words = set(content_tokens(record.heading))
                overlap = heading_words & set(tokens)
                if overlap and len(overlap) >= min(2, len(tokens)):
                    score *= 1.0 + 0.6 * len(overlap)
                    reasons.append("heading: " + record.heading[:50])

            if record.kind == "definition":
                for token in tokens:
                    if token and token in record.heading.lower():
                        score *= 1.8
                        reasons.append(f"defines '{record.heading}'")
                        break
            if not reasons:
                hits = [token for token in tokens if token in lowered]
                if hits:
                    reasons.append("words: " + ", ".join(sorted(set(hits))[:5]))

            results.append((record, score, reasons))

        results.sort(key=lambda item: item[1], reverse=True)
        return results[:limit]

    def by_citation(self, act_fragment: str, section: str,
                    subsection: str = "") -> list[Record]:
        """Look a provision up by its address, the way a lawyer would."""
        out = []
        for record in self.records:
            if act_fragment.lower() not in record.act.lower():
                continue
            if record.section != section:
                continue
            if subsection and record.subsection != subsection:
                continue
            out.append(record)
        return out

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        acts: dict[str, int] = {}
        for record in self.records:
            kinds[record.kind] = kinds.get(record.kind, 0) + 1
            acts[record.act] = acts.get(record.act, 0) + 1
        return {
            "provisions": len(self.records),
            "distinct_terms": len(self.postings),
            "acts": len(acts),
            "by_kind": kinds,
            "by_act": acts,
            "built": self.built,
        }


_CITATION = re.compile(
    r"\b(?:s|section|ss|sections)\s*(\d+[A-Z]{0,3})(?:\((\d+[A-Z]{0,3})\))?", re.I)


def _citation_in(query: str) -> tuple[str, str] | None:
    match = _CITATION.search(query)
    if not match:
        return None
    return ("section", match.group(1))


def _matches_citation(record: Record, citation: tuple[str, str]) -> bool:
    return record.section == citation[1]


def build(paths: list[str], profile_key: str | None = None,
          on_progress=None, on_skip=None) -> Index:
    """Extract, parse and index a list of documents.

    A document that cannot be read is recorded and skipped, never fatal.
    Encrypted PDFs, scans with no text layer and damaged files all turn up
    in a real folder of law, and losing the other sixty because of one of
    them would be the wrong trade.
    """
    from datetime import datetime, timezone

    from . import extract, parse as parse_module

    index = Index(built=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    for path in paths:
        try:
            document = extract.load(path, profile_key)
            act = parse_module.parse(document)
            added = index.add_act(act, source_path=str(path))
        except Exception as error:
            reason = str(error) or error.__class__.__name__
            if "cryptography" in reason:
                reason = ("the file is encrypted; pypdf needs the "
                          "'cryptography' package to open it")
            index.skipped.append({"path": str(path), "reason": reason})
            if on_skip:
                on_skip(str(path), reason)
            continue
        if on_progress:
            on_progress(act, added)
    return index
