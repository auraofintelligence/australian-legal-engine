"""Command line for the engine.

    python -m engine index "C:/path/to/acts/*.pdf" --out data/index.json
    python -m engine ask "what notice must a lessor give to enter"
    python -m engine cite "Privacy Act" 13
    python -m engine sources
    python -m engine check

Every command reads files you already hold and writes files you own.
Nothing is uploaded and no network call is made.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from . import answer as answer_module
from .index import Index, build

DEFAULT_INDEX = Path("data/index.json")


def _expand(patterns: list[str]) -> list[str]:
    paths: list[str] = []
    for pattern in patterns:
        found = sorted(glob.glob(pattern))
        if found:
            paths.extend(found)
        elif Path(pattern).exists():
            paths.append(pattern)
        else:
            print(f"  no file matched: {pattern}", file=sys.stderr)
    return paths


def _load_index(path: Path) -> Index:
    if not path.exists():
        raise SystemExit(
            f"No index at {path}. Build one first:\n"
            f'  python -m engine index "path/to/acts/*.pdf"')
    return Index.load(path)


def cmd_index(args: argparse.Namespace) -> int:
    paths = _expand(args.paths)
    if not paths:
        raise SystemExit("Nothing to index.")

    print(f"Reading {len(paths)} document(s).")

    def progress(act, added: int) -> None:
        stamp = act.currency or "no date on source"
        print(f"  {act.title} [{act.jurisdiction}, as at {stamp}]: "
              f"{len(act.sections)} sections, {added} provisions indexed")
        for warning in act.warnings:
            print(f"    note: {warning}")

    def skipped(path: str, reason: str) -> None:
        print(f"  SKIPPED {Path(path).name}: {reason}")

    index = build(paths, profile_key=args.profile, on_progress=progress,
                  on_skip=skipped)
    out = Path(args.out)
    index.save(out)
    stats = index.stats()
    print(f"\nIndexed {stats['provisions']} provisions from {stats['acts']} act(s).")
    if index.skipped:
        print(f"Skipped {len(index.skipped)} document(s) that could not be read; "
              f"`engine check` lists them.")
    print(f"Written to {out} ({out.stat().st_size / 1_000_000:.1f} MB).")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    index = _load_index(Path(args.index))
    packet = answer_module.ask(
        index, args.question, limit=args.limit,
        jurisdiction=args.jurisdiction, act=args.act,
        bridge=not args.exact, wider=args.wider)

    if args.json:
        print(json.dumps(packet.to_dict(), indent=2))
        return 0 if packet.found else 1
    if args.prompt:
        if not packet.found:
            print(packet.as_text())
            return 1
        print(packet.as_prompt())
        return 0

    print(packet.as_text())
    return 0 if packet.found else 1


def cmd_cite(args: argparse.Namespace) -> int:
    index = _load_index(Path(args.index))
    packet = answer_module.cite(index, args.act, args.section, args.subsection or "")
    if args.json:
        print(json.dumps(packet.to_dict(), indent=2))
    else:
        print(packet.as_text())
    return 0 if packet.found else 1


def cmd_sources(args: argparse.Namespace) -> int:
    index = _load_index(Path(args.index))
    print(f"Index built {index.built or 'at an unrecorded time'}\n")
    for source in index.sources:
        stamp = source.get("currency") or "no date on source"
        print(f"{source['act']}")
        print(f"  {source['jurisdiction']} | as at {stamp} | "
              f"profile {source['profile']}")
        print(f"  {source['sections']} sections, {source['indexed']} provisions")
        print(f"  from {source['path']}")
        for warning in source.get("warnings", []):
            print(f"  note: {warning}")
        print()
    stats = index.stats()
    print(f"Total: {stats['provisions']} provisions, "
          f"{stats['distinct_terms']} distinct terms, {stats['acts']} act(s).")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Report what the index can and cannot support, before you rely on it."""
    index = _load_index(Path(args.index))
    stats = index.stats()
    problems: list[str] = []

    undated = [source for source in index.sources if not source.get("currency")]
    for source in undated:
        problems.append(f"{source['act']}: no currency date on the source.")
    for source in index.sources:
        for warning in source.get("warnings", []):
            problems.append(f"{source['act']}: {warning}")
    for entry in index.skipped:
        problems.append(
            f"{Path(entry['path']).name}: not read at all, because "
            f"{entry['reason']}. Nothing from this document is searchable.")

    print(f"Provisions indexed: {stats['provisions']}")
    print(f"Acts indexed:       {stats['acts']}")
    print(f"Kinds:              {json.dumps(stats['by_kind'])}")
    print()
    if problems:
        print("Things that limit what this index can support:")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("Every source carries a currency date and parsed cleanly.")
    print()
    print("What this index is: the text of the documents listed under "
          "`sources`, as they stood on the dates shown, cut into provisions "
          "and searchable offline.")
    print("What it is not: current law, a complete corpus, or legal advice. "
          "Check the register before relying on any provision.")
    return 0


def cmd_threads(args: argparse.Namespace) -> int:
    from . import threads as threads_module

    index = _load_index(Path(args.index))
    thread_map = threads_module.build(index)
    stats = thread_map.stats()

    if args.json:
        print(json.dumps({
            "stats": stats,
            "act_links": [{"from": a, "to": b, "count": n}
                          for (a, b), n in sorted(thread_map.act_links().items(),
                                                  key=lambda kv: -kv[1])],
            "reading_list": [{"act": act, "referenced": count,
                              "referenced_from": examples}
                             for act, count, examples in thread_map.reading_list()],
        }, indent=2))
        return 0

    print(f"{stats['threads']} threads found across {stats['acts_in_index']} act(s).")
    print(f"By kind: {json.dumps(stats['by_relation'])}\n")

    links = sorted(thread_map.act_links().items(), key=lambda kv: -kv[1])
    if links:
        print("Which act leans on which:")
        for (source, target), count in links[:args.limit]:
            print(f"  {count:4d}  {source[:40]:42s} -> {target}")
        print()

    reading = thread_map.reading_list()
    if reading:
        print("Acts your sources point at but do not contain.")
        print("What the law leans on, not what you have missed. Whether any")
        print("of it touches your life is a question the counts cannot answer:")
        print()
        for act, count, examples in reading[:args.limit]:
            print(f"  {count:4d} reference(s)  {act}")
            print(f"        first seen at: {examples[0]}")
        print()
        print(f"{len(reading)} act(s) in total. Each is free to read on its "
              f"jurisdiction's register.")
        print("A high count means the law refers to it often. It does not")
        print("mean you need it.")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    from . import threads as threads_module

    index = _load_index(Path(args.index))
    thread_map = threads_module.build(index)
    trail = threads_module.trace(index, thread_map, args.act, args.section,
                                 depth=args.depth)

    if args.json:
        print(json.dumps([{"depth": depth, **edge.to_dict()}
                          for depth, edge in trail], indent=2))
        return 0 if trail else 1

    if not trail:
        print(f"No threads run out of {args.act} section {args.section} in "
              f"this index. Either the provision points nowhere, or it is "
              f"not indexed.")
        return 1

    print(f"Threads out of {args.act} section {args.section}, "
          f"{args.depth} step(s) deep:\n")
    for depth, edge in trail[:args.limit]:
        indent = "  " * depth
        print(f"{indent}{edge.source_address}")
        print(f"{indent}  --{edge.relation}--> {edge.target_label}")
        print(f"{indent}  \"{edge.quote[:120]}\"")
        print()
    if len(trail) > args.limit:
        print(f"({len(trail) - args.limit} more threads not shown; "
              f"raise --limit to see them.)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="engine",
        description="An offline, citation-first reader for Australian statute "
                    "law. Reads documents you already hold; makes no network "
                    "calls; gives legal information, never legal advice.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("index", help="parse and index documents")
    build_parser.add_argument("paths", nargs="+", help="files or glob patterns")
    build_parser.add_argument("--out", default=str(DEFAULT_INDEX))
    build_parser.add_argument("--profile", default=None,
                              help="force a layout profile: cth, qld, generic")
    build_parser.set_defaults(func=cmd_index)

    ask_parser = subparsers.add_parser("ask", help="find the provisions on a question")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    ask_parser.add_argument("--limit", type=int, default=5)
    ask_parser.add_argument("--jurisdiction", default=None)
    ask_parser.add_argument("--act", default=None)
    ask_parser.add_argument("--prompt", action="store_true",
                            help="print a grounded prompt for an AI assistant")
    ask_parser.add_argument("--exact", action="store_true",
                            help="search your words only, with no bridge from "
                                 "everyday words to drafting words")
    ask_parser.add_argument("--wider", action="store_true",
                            help="also search terms that keep the same company "
                                 "in your sources")
    ask_parser.add_argument("--json", action="store_true")
    ask_parser.set_defaults(func=cmd_ask)

    cite_parser = subparsers.add_parser("cite", help="fetch a provision by address")
    cite_parser.add_argument("act")
    cite_parser.add_argument("section")
    cite_parser.add_argument("subsection", nargs="?", default="")
    cite_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    cite_parser.add_argument("--json", action="store_true")
    cite_parser.set_defaults(func=cmd_cite)

    sources_parser = subparsers.add_parser("sources", help="list what is indexed")
    sources_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    sources_parser.set_defaults(func=cmd_sources)

    threads_parser = subparsers.add_parser(
        "threads", help="map the references between provisions and acts")
    threads_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    threads_parser.add_argument("--limit", type=int, default=15)
    threads_parser.add_argument("--json", action="store_true")
    threads_parser.set_defaults(func=cmd_threads)

    trace_parser = subparsers.add_parser(
        "trace", help="follow the threads out of one provision")
    trace_parser.add_argument("act")
    trace_parser.add_argument("section")
    trace_parser.add_argument("--depth", type=int, default=2)
    trace_parser.add_argument("--limit", type=int, default=20)
    trace_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    trace_parser.add_argument("--json", action="store_true")
    trace_parser.set_defaults(func=cmd_trace)

    check_parser = subparsers.add_parser(
        "check", help="report the limits of the current index")
    check_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    check_parser.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
