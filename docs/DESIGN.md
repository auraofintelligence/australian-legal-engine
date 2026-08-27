# Design notes

Why the engine is shaped the way it is. Each decision below was a fork in
the road, and the reasoning matters more than the code, because the code
will be rewritten and the reasoning probably will not.

## 1. The engine retrieves and cites; it does not write about the law

A language model asked "what does the Privacy Act say about X" produces
fluent text with citations attached. The text is often right. The
citations are guesses, and a guessed section number looks exactly like a
real one until someone checks.

So the engine splits the job at the seam where checkability changes:

- **Retrieval and citation** come from a parser walking a file on your
  disk. The address `Privacy Act 1988 s 13(2)(a)` is a fact about that
  file, and the engine can show you the exact bytes it came from.
- **Language and judgement** happen after, done by a person or by a model
  reading the provisions the engine handed it under `--prompt`.

The engine is therefore not competing with a chat assistant. It is the
thing that makes one safe to use on law.

## 2. Structure before size

Legislation is a tree. An act divides into parts, parts into sections,
sections into subsections and paragraphs, and a line's meaning depends on
where it sits: subsection (3) is only intelligible under the heading of
section 12, inside Part 2.

Most document pipelines cut text into fixed-size blocks because it is
easy and it works for prose. Applied to an act it severs a definition
from the term it defines, or an exception from the rule it softens, and
the retrieved fragment can read as the opposite of the law.

So `parse.py` walks the structure and every provision carries its address
and its context. That address is what makes the citation possible, and a
citation the engine cannot produce is an answer it will not give.

## 3. One layout profile per drafting office

Nine parliaments publish through nine drafting offices, and each lays out
a page differently. Queensland prints `[s 35]` at the top of every page
and starts numbering hard against the left margin. The Commonwealth puts
the part name and the section number in a running header and the page
number beside the short title.

A parser that does not know this reads page furniture as law. Rather than
teach one parser every quirk, the layout knowledge lives in
`profiles.py`, declared per office. **Adding a jurisdiction means adding a
profile, not editing the parser.** The generic profile handles unknown
sources conservatively and says so in a warning.

## 4. Contents pages are the first trap

Every act repeats its full section list in a table of contents. Parse it
naively and every section appears twice, the second copy empty. The
reliable tell is the leader: a run of four or more dots, solid in
Commonwealth compilations and spaced in Queensland reprints. Legislative
text never contains one. That single signal, plus dropping headings that
end in a page number, removes the whole class of error.

The first parser run over the Privacy Act found 285 sections. The real
figure is 122. The difference was the contents pages.

## 5. Offline, dependency-light, and yours

The index is a plain JSON file. No database to run, no service to sign up
to, no key to keep, no vendor who can change the terms. It can be copied
to a USB stick, opened in a text editor, and rebuilt by anyone who holds
the same sources.

The core needs only the Python standard library plus `pypdf`. Semantic
search with Australian legal embeddings is a real improvement and there
is a slot for it, but making it a requirement would trade a tool that
runs on any machine for one that needs a few gigabytes of model weights
and, usually, someone else's server. For a tool meant to be picked up by
a person who wants to read their own law, that trade is the wrong way
round.

BM25 with exact-phrase matching, citation lookup and a heading boost
covers most of what legal search actually needs, because legal queries
are unusually literal: people search for the words the act uses.

## 6. The engine never fetches

It reads documents you already hold. It does not scrape a register, and
it has no network code at all.

This is not a missing feature. The registers publish terms on automated
access, Crown copyright applies to the reprints, and the path is to ask
each Parliamentary Counsel's office for sanctioned access rather than
work around them. A tool that quietly scraped would make its user the
one in breach.

## 7. Every gap is printed, not hidden

`engine check` reports what limits the current index: sources with no
currency date, sources that disclaim their own authority, layouts the
parser was unsure about, sections that came out empty. A warning that
only appears in a log is a warning nobody reads, so they surface at
index time, in `sources`, and in the notes attached to every answer.

## 8. The document is its own dictionary

Some Queensland reprints extract with words split by stray spaces:
"polic e officer", "eviden ce". Searching such a document for "police"
misses the very provisions that matter, and the acts affected here were
the ones about police powers and tenancy, which is to say the ones a
person is most likely to need.

Fixing it needs no dictionary, because the document is its own. If
"eviden" appears twice in 200,000 words while "evidence" appears
hundreds of times, the two-word reading is the broken one. Both tests
must pass before anything is joined, so an ordinary pair like "may be"
is never touched, and the repair is reported rather than done quietly.
This removed every detectable split across 227 pages of one act while
leaving the Commonwealth sources, which had none, untouched.

## 9. Threads are edges with evidence attached

`threads.py` reads each provision for the references a drafter writes and
builds a graph: which provision points at which, and what kind of pointing
it is (defines, applies, subject to, despite, amends, penalty).

Two things keep it honest. Every edge carries the words it came from, so a
claim can be checked rather than trusted. And a reference is resolved in
context the way a reader resolves it: "section 35L of that Act" belongs to
whichever act the sentence last named, not to the act you happen to be
reading.

The most useful output is the inverse: the acts your sources point at but
do not contain. That is a reading list named by the law itself, with the
exact provision that points at each gap. It is the 2013 thread-following
turned into a next step.

## What is not built

- **Semantic retrieval.** The slot exists; the dependency does not.
- **Amendment awareness.** The engine reads a compilation as at its
  printed date. It does not know what changed after that, and it says so
  rather than implying currency it cannot support.
- **Subordinate legislation and council local laws** as first-class
  citizens. They parse as generic documents today.
- **Any acquisition pipeline.** See point 6.
