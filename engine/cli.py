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

    index = build(paths, profile_key=args.profile, on_progress=progress)
    out = Path(args.out)
    index.save(out)
    stats = index.stats()
    print(f"\nIndexed {stats['provisions']} provisions from {stats['acts']} act(s).")
    print(f"Written to {out} ({out.stat().st_size / 1_000_000:.1f} MB).")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    index = _load_index(Path(args.index))
    packet = answer_module.ask(
        index, args.question, limit=args.limit,
        jurisdiction=args.jurisdiction, act=args.act)

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

    check_parser = subparsers.add_parser(
        "check", help="report the limits of the current index")
    check_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    check_parser.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
