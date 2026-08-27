<!--
  ██  BUILT BY LUKE × CLAUDE  ██
  This repository was created collaboratively by Luke Nathan Hayes and
  Claude (Anthropic, Fable 5) — NOT by Codex. See signature below.
-->

# Australian Legal Engine

> 🤝🔷 **A Luke × Claude build.** Created by **Luke Nathan Hayes** (`auraofintelligence`)
> and **Claude — Fable 5** (Anthropic) on **27 August 2026**. _Not a Codex build._

The robot lawyer, in code. It reads Australian acts, cuts them into provisions the way the drafter wrote them, indexes them offline, and answers a question by handing you the provisions themselves: quoted exactly, addressed precisely, dated to the source.

It runs on your own machine, makes no network calls, needs no account, no key and no subscription, and the index is a plain JSON file you own.

**Companion site:** https://auraofintelligence.github.io/australian-law-2012-lukes-relevance/ (the method, the story and the design this code implements)

## The one rule

**The engine never writes prose about the law.** It retrieves, quotes and cites. Language and judgement belong elsewhere: to you reading, or to a model working under the prompt the engine writes for it.

That split is the point. A citation produced by a parser is a fact about a file on your disk, checkable in seconds. A citation produced by a language model is a guess that usually happens to be right. Australian courts have already dealt with lawyers filing AI-invented citations, and in 2025 a lawyer was penalised for it. Only the first kind of citation can be checked mechanically, so only the first kind is what this emits.

This is legal information tooling. It is not legal advice, and it does not become legal advice by being accurate. For advice about your own situation, a qualified lawyer.

## What it does today

```bash
# Index acts you already hold, from any folder
python -m engine index "C:/path/to/acts/*.pdf"

# Ask a question in plain words
python -m engine ask "notice a lessor must give before entering"

# Fetch a provision by its address
python -m engine cite "Privacy Act" 13

# Hand the retrieved provisions to any AI assistant, on a leash
python -m engine ask "who can access my credit file" --prompt

# Follow the threads: what points at what, and what you have not read yet
python -m engine threads
python -m engine trace "Privacy Act" 13

# See what is indexed, and what limits it
python -m engine sources
python -m engine check
```

### Following the threads

The 2013 read worked by following threads: one act defines a term, another borrows it, a third amends them both. `threads` does that walk mechanically, and every edge keeps the words it came from, so you can check the claim rather than trust the graph.

```
642 threads found across 2 acts.
By kind: {"refers to": 529, "defines": 37, "applies": 35, "penalty": 14, "amends": 14, ...}

Which act leans on which:
    17  Privacy Act 1988      -> Acts Interpretation Act 1901
    13  Privacy Act 1988      -> Freedom of Information Act 1982
     8  Privacy Act 1988      -> Anti-Money Laundering and Counter-Terrorism Financing Act 2006

Acts your sources point at but do not contain.
This is your reading list, named by the law itself:
    17 reference(s)  Acts Interpretation Act 1901
        first seen at: Privacy Act 1988 s 5B(10)(a)
```

That last part is the useful one. The gaps in your own reading get named by the law itself, with the exact provision that points at each one, rather than guessed at.

`trace` walks outward from a single provision and resolves references in context, including the awkward ones: "see section 35L of that Act" resolves to whichever act the sentence last named.

A real run over three acts from the 2012 corpus:

```
Privacy Act 1988 [Commonwealth, as at 11 December 2012]: 122 sections, 1724 provisions
Residential Tenancies and Rooming Accommodation Act 2008 [Queensland, as at
  17 September 2012]: 557 sections, 3476 provisions
  note: The source says on its own cover that it is not an authorised copy.
Freedom of Information Act 1982 [Commonwealth, as at 13 December 2012]: 138 sections, 1556 provisions

Indexed 6756 provisions from 3 acts. Written to data/index.json (4.8 MB).
```

## How it works

| Stage | Module | What it does |
| --- | --- | --- |
| Clean | `engine/textclean.py` | Repairs what PDF extraction mangles: apostrophes inside defined terms, dashes that introduce a list, words split across a line break. |
| Profile | `engine/profiles.py` | One layout profile per drafting office. Queensland prints `[s 35]` at the top of a page; the Commonwealth puts the part name and section in a running header. Page furniture is not law. |
| Extract | `engine/extract.py` | Reads PDF, HTML or text you already hold. Finds the act's real short title from its own running header, its currency date, and whether the source disclaims its own authority. |
| Parse | `engine/parse.py` | Rebuilds the tree: chapters, parts, divisions, sections, subsections, paragraphs, subparagraphs, definitions. Every provision gets an address that travels with it. Contents pages are dropped, not indexed. |
| Index | `engine/index.py` | BM25 over provisions, plus exact-phrase and citation matching and a heading boost. Plain JSON, offline, portable. |
| Answer | `engine/answer.py` | Assembles a packet: the provisions, their addresses, their currency dates, the register to check them at, and a prompt that forbids a model from inventing a citation. |
| Threads | `engine/threads.py` | Reads every provision for the references a drafter writes, builds a graph of them, and turns the acts your sources point at but do not contain into a reading list. |

Adding a jurisdiction means adding a profile, not editing the parser.

## Status

**Built and tested:** everything above, verified by 44 tests including a golden set that asserts real citations against the real 2012 acts (`python tests/test_engine.py`).

Run over the whole 2012 corpus, 61 documents in one command, it indexed **101,370 provisions from 41 acts**. One encrypted PDF was skipped and named; the forms, Magna Carta and the Universal Declaration reported no sections found rather than pretending, because they are not Australian statutes.

**Not built:** semantic search (the design keeps a slot for Australian legal embeddings, but the core stays dependency-light on purpose), amendment awareness beyond a compilation's printed date, and any automated acquisition of law. The engine reads documents you already hold; it does no fetching of its own. That boundary is deliberate: the registers set terms on automated access, and asking is the path.

**Not a corpus.** This ships code, not law. What the engine knows is whatever you indexed, as it stood on the dates printed on those sources. `python -m engine check` prints exactly that, including every gap.

## Requirements

Python 3.10 or newer. `pypdf` for reading PDFs (`pip install pypdf`); everything else is the standard library.

## Where the law actually lives

Commonwealth [legislation.gov.au](https://www.legislation.gov.au/) ·
NSW [legislation.nsw.gov.au](https://legislation.nsw.gov.au/) ·
Victoria [legislation.vic.gov.au](https://www.legislation.vic.gov.au/) ·
Queensland [legislation.qld.gov.au](https://www.legislation.qld.gov.au/) ·
WA [legislation.wa.gov.au](https://www.legislation.wa.gov.au/) ·
SA [legislation.sa.gov.au](https://www.legislation.sa.gov.au/) ·
Tasmania [legislation.tas.gov.au](https://www.legislation.tas.gov.au/) ·
ACT [legislation.act.gov.au](https://www.legislation.act.gov.au/) ·
NT [legislation.nt.gov.au](https://legislation.nt.gov.au/) ·
[AustLII](https://www.austlii.edu.au/)

## Neighbouring rooms

- **Australian Law: Luke's Relevance** — the method and the design: https://auraofintelligence.github.io/australian-law-2012-lukes-relevance/
- **Legal Memory Workbench** — map your own side of the table: https://auraofintelligence.github.io/legal-memory-workbench/
- **P4A** — the civic campaign workbench, forms first: https://p4a.xyz/pages/site-map.html
- **Strange But True** — https://auraofintelligence.github.io/strange-but-true/
- **Aura of Intelligence** — https://auraofintelligence.github.io/

## Licence

Strange But True Public Source Licence: free for personal, educational, artistic, research and community use with attribution; all commercial and corporate rights reserved to Luke Nathan Hayes. See [LICENCE.md](LICENCE.md).

---

<sub>

### 🔷 Signature
**Made by Luke × Claude (Fable 5).** Not Codex.
Every commit is co-signed `Co-Authored-By: Claude Fable 5` — check `git log` to confirm lineage.
Repo initialised 2026-08-27. Minjerribah, Quandamooka Country.

</sub>
