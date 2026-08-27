"""Bridge the words people use to the words parliaments use.

Someone with a rent problem searches for "landlord". Across the whole
2012 corpus, 101,370 provisions, "landlord" appears once and "lessor"
appears 672 times. Someone sacked from a job searches "sacked", which
appears in no act at all. The law is searchable, and the words most
people would search it with are not the words it uses.

Two things close that gap, and they are kept apart on purpose because
they are different kinds of claim:

1. A short, hand-written list of everyday words and their drafting
   equivalents. This is a judgement by a person, visible in the source,
   meant to be argued with and edited.
2. Terms the indexed text itself uses in the same way, worked out from
   which provisions they appear in. This is arithmetic over your own
   sources, and it changes when they change.

Whatever gets added to a query is reported back, so a search never
quietly becomes a different search.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .index import Index, content_tokens

# ---------------------------------------------------------------------
# 1. The hand-written bridge.
#
# Everyday word to the words Australian drafters actually use. Kept short
# and plain. Each entry is a judgement, not a finding, and a wrong one
# shows up as odd search results rather than as a wrong statement about
# the law: the engine still only ever quotes what the act says.
# ---------------------------------------------------------------------

PLAIN_TO_DRAFTING: dict[str, tuple[str, ...]] = {
    # renting
    "landlord": ("lessor",),
    "landlords": ("lessor",),
    "renter": ("tenant",),
    "renters": ("tenant",),
    "renting": ("tenancy", "tenant"),
    "flatmate": ("cotenant", "resident"),
    "eviction": ("termination", "notice to leave"),
    "evicted": ("terminated", "notice to leave"),
    "inspection": ("entry", "enter"),
    # work
    "sacked": ("dismissed", "dismissal", "termination"),
    "fired": ("dismissed", "dismissal", "termination"),
    "boss": ("employer",),
    "wage": ("remuneration", "pay"),
    "wages": ("remuneration", "pay"),
    "sickie": ("personal leave", "sick leave"),
    # police and offences
    "cop": ("police officer",),
    "cops": ("police officer",),
    "copper": ("police officer",),
    "arrested": ("arrest", "apprehend"),
    "fine": ("penalty", "infringement"),
    "fines": ("penalty", "infringement"),
    "breathalyser": ("breath test", "breath analysis"),
    "speeding": ("speed", "speed limit"),
    # money and government
    "centrelink": ("social security", "benefit", "pension"),
    "dole": ("benefit", "allowance"),
    "welfare": ("social security", "benefit"),
    "loan": ("credit", "credit contract"),
    "debt": ("liability", "amount owing"),
    # information
    "data": ("information", "record"),
    "foi": ("freedom of information", "access"),
    # people and places
    "judge": ("magistrate", "justice"),
    "lawyer": ("legal practitioner", "solicitor"),
    "kid": ("child", "minor"),
    "kids": ("child", "children"),
    "house": ("premises", "dwelling"),
    "home": ("premises", "dwelling", "residence"),
    "car": ("motor vehicle", "vehicle"),
    "boat": ("vessel", "ship"),
}


@dataclass
class Expansion:
    """What a query became, and why."""

    original: str
    added: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.added)

    def describe(self) -> str:
        if not self.added:
            return ""
        parts = [f"{term} ({self.reasons.get(term, 'related')})"
                 for term in self.added]
        return "Also searched: " + ", ".join(parts)

    def as_query(self) -> str:
        return " ".join([self.original, *self.added])


def _postings(index: Index, token: str) -> set[int]:
    return set(index.postings.get(token, ()))


def _context_profile(index: Index, positions: set[int],
                     sample: int = 300) -> Counter:
    """The words that keep company with a set of provisions."""
    profile: Counter = Counter()
    for position in list(positions)[:sample]:
        record = index.records[position]
        profile.update(set(content_tokens(record.text)))
    return profile


def _cosine(one: Counter, two: Counter) -> float:
    if not one or not two:
        return 0.0
    shared = set(one) & set(two)
    if not shared:
        return 0.0
    dot = sum(one[key] * two[key] for key in shared)
    norm_one = math.sqrt(sum(value * value for value in one.values()))
    norm_two = math.sqrt(sum(value * value for value in two.values()))
    if not norm_one or not norm_two:
        return 0.0
    return dot / (norm_one * norm_two)


def related_terms(index: Index, token: str, limit: int = 4,
                  min_provisions: int = 8, candidates: int = 30,
                  threshold: float = 0.5,
                  max_share: float = 0.05) -> list[tuple[str, float]]:
    """Words that keep the same company as this one in your sources.

    These are neighbours, not synonyms, and the difference matters. Ask
    for words like "premises" and you get lessor, tenant, accommodation;
    ask for "superannuation" and you get trustee, funds, member's. None
    of those means the same thing, but each one leads to provisions a
    reader of the first would want.

    Use it to widen a search, never to substitute one word for another.
    The tight ceiling on how many provisions a candidate may appear in is
    what keeps drafting boilerplate ("another", "following", "given") out
    of the results: a word spread across a quarter of the corpus keeps
    company with everything and so tells you nothing.
    """
    token = token.lower()
    positions = _postings(index, token)
    if len(positions) < min_provisions:
        return []

    profile = _context_profile(index, positions)
    profile.pop(token, None)
    if not profile:
        return []

    total = len(index.records) or 1
    scored: list[tuple[str, float]] = []
    for candidate, _ in profile.most_common(candidates):
        if candidate == token or len(candidate) < 4:
            continue
        other = _postings(index, candidate)
        if len(other) < min_provisions:
            continue
        # A word spread through the corpus keeps company with everything.
        if len(other) > total * max_share:
            continue
        # Years and section numbers are not terms.
        if candidate.isdigit():
            continue
        other_profile = _context_profile(index, other)
        other_profile.pop(candidate, None)
        score = _cosine(profile, other_profile)
        if score >= threshold:
            scored.append((candidate, round(score, 3)))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def expand(index: Index, query: str, use_corpus: bool = False,
           limit_per_term: int = 2) -> Expansion:
    """Widen a query with drafting words, reporting every addition.

    The hand-written bridge runs by default, because without it an
    ordinary question misses the law entirely: "landlord" finds one
    provision in the 2012 corpus and "lessor" finds 672.

    The corpus-derived neighbours are opt-in, because they broaden a
    search rather than sharpen it. Both report what they added.
    """
    expansion = Expansion(original=query)
    words = set(content_tokens(query))
    lowered = query.lower()

    for plain, drafting in PLAIN_TO_DRAFTING.items():
        if plain not in words:
            continue
        for term in drafting:
            key = term.lower()
            if key in lowered or term in expansion.added:
                continue
            # Only offer a word the indexed law actually uses.
            if index.postings.get(key.split()[0]):
                expansion.added.append(term)
                expansion.reasons[term] = f"the drafting word for '{plain}'"

    if use_corpus:
        for token in content_tokens(query):
            if token in PLAIN_TO_DRAFTING:
                continue
            for term, _ in related_terms(index, token, limit=limit_per_term):
                if term in words or term in expansion.added:
                    continue
                expansion.added.append(term)
                expansion.reasons[term] = (
                    f"keeps the same company as '{token}' here")

    return expansion
