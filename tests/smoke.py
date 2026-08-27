"""Run the parser over real acts from the 2012 corpus and report what it found.

Not a unit test: a look at the output with human eyes, which is how a
parser for a new layout gets trusted in the first place.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import extract, parse  # noqa: E402

CORPUS = r"C:\Users\sbt41\Downloads\Australian Law 2012 - Lukes Relevance"

FILES = [
    "Australian Privacy Act 1988.pdf",
    "QLD - Residential Tenancies and Rooming Accommodation Act 2008.pdf",
    "Australian Constitution Act 1900.pdf",
    "QLD - Electoral Act 1992.pdf",
    "Australian Freedom of Information Act 1982.pdf",
]


def main() -> None:
    for name in FILES:
        path = os.path.join(CORPUS, name)
        if not os.path.exists(path):
            print("missing:", name)
            continue
        document = extract.load(path)
        act = parse.parse(document)
        print("=" * 70)
        print(act.title, "|", act.jurisdiction, "| as at", act.currency,
              "| profile", act.profile_key)
        print("  ", json.dumps(act.stats()["by_kind"]))
        for section in act.sections[:3]:
            print("   *", section.address, "|", section.heading[:55])
            print("      ", (section.text or "(children only)")[:130])
            for child in section.children[:1]:
                print("        -", child.address, ":", child.text[:90])
        for warning in act.warnings[:2]:
            print("   WARN:", warning[:110])


if __name__ == "__main__":
    main()
