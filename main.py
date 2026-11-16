"""NLP_MachineTranslation - compare and evaluate machine translation services.

Usage:
    python main.py                                   # interactive: type a sentence
    python main.py --text "Hello" --source en --target es
    python main.py --tests test_cases.json           # run every test case
    python main.py --rate results/ratings.csv        # rate adequacy/fluency 1-5
    python main.py --report results/ratings.csv      # summary + best service
"""

import argparse
import csv
import difflib
import json
import os
import sys
import textwrap
from collections import Counter, defaultdict
from datetime import datetime

from translator import compare_translations, get_translators

RESULTS_DIR = "results"
WIDTH = 90

SCALE = {1: "poor", 2: "weak", 3: "acceptable", 4: "good", 5: "excellent"}

ERROR_CATEGORIES = [
    "none",
    "incorrect meaning",
    "awkward phrasing",
    "missing information",
    "incorrect pronoun handling",
    "idiom failure",
    "word order problem",
    "bias or stereotype issue",
    "wrong lexical choice",
    "other",
]

CSV_FIELDS = [
    "case_id", "category", "source_lang", "target_lang", "source_text",
    "reference", "service", "translation", "ref_similarity",
    "adequacy", "fluency", "errors", "notes",
]


# ---------------------------------------------------------------- helpers

def reference_similarity(translation, reference):
    """Rough character-level similarity (0-100) to the reference translation.

    This is only a quick sanity signal - the real evaluation is the human
    adequacy/fluency rating, since a correct translation can be worded
    differently from the reference.
    """
    if not translation or not reference:
        return ""
    ratio = difflib.SequenceMatcher(None, translation.lower(), reference.lower()).ratio()
    return round(ratio * 100)


def wrap(label, text, indent=14):
    body = textwrap.fill(
        text, width=WIDTH, initial_indent=" " * indent, subsequent_indent=" " * indent
    )
    return f"{label:<{indent}}" + body[indent:]


def print_comparison(case, results):
    """Display the source, reference and every service's output side by side."""
    print("=" * WIDTH)
    title = f"[{case.get('id', '-')}] {case.get('category', 'custom')}"
    print(f"{title}   ({case['source_lang']} -> {case['target_lang']})")
    if case.get("tests"):
        print(wrap("Tests:", case["tests"]))
    print("-" * WIDTH)
    print(wrap("Source:", case["text"]))
    if case.get("reference"):
        print(wrap("Reference:", case["reference"]))
    print("-" * WIDTH)
    for r in results:
        if r["error"]:
            print(wrap(f"{r['service']}:", f"ERROR - {r['error']}"))
        else:
            sim = reference_similarity(r["translation"], case.get("reference", ""))
            sim_text = f"   [ref sim {sim}%]" if sim != "" else ""
            print(wrap(f"{r['service']}:", r["translation"] + sim_text))
    print()


def require_translators():
    translators = get_translators()
    if not translators:
        sys.exit("No translation services configured. Copy .env.example to .env and add keys.")
    names = ", ".join(t.name for t in translators)
    print(f"Using services: {names}\n")
    if len(translators) < 2:
        print("Warning: the assignment requires at least two services.\n")
    return translators


def unique_path(path):
    """Avoid overwriting a file that may already hold your ratings."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    return f"{stem}_{datetime.now():%Y%m%d_%H%M%S}{ext}"


# ---------------------------------------------------------------- modes

def run_single(text, source, target):
    translators = require_translators()
    case = {"text": text, "source_lang": source, "target_lang": target}
    results = compare_translations(text, source, target, translators)
    print_comparison(case, results)


def run_interactive():
    print("Interactive mode - leave the text blank to quit.\n")
    translators = require_translators()
    source = input("Source language code (e.g. en): ").strip() or "en"
    target = input("Target language code (e.g. es): ").strip() or "es"
    while True:
        text = input("\nText to translate: ").strip()
        if not text:
            break
        case = {"text": text, "source_lang": source, "target_lang": target}
        print_comparison(case, compare_translations(text, source, target, translators))


def run_tests(path):
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    translators = require_translators()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    all_results = []
    rows = []
    for case in cases:
        results = compare_translations(
            case["text"], case["source_lang"], case["target_lang"], translators
        )
        print_comparison(case, results)
        all_results.append({**case, "results": results})
        for r in results:
            rows.append({
                "case_id": case["id"],
                "category": case["category"],
                "source_lang": case["source_lang"],
                "target_lang": case["target_lang"],
                "source_text": case["text"],
                "reference": case.get("reference", ""),
                "service": r["service"],
                "translation": r["translation"] or f"ERROR - {r['error']}",
                "ref_similarity": reference_similarity(r["translation"], case.get("reference", "")),
                "adequacy": "", "fluency": "", "errors": "", "notes": "",
            })

    json_path = os.path.join(RESULTS_DIR, f"translations_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    csv_path = unique_path(os.path.join(RESULTS_DIR, "ratings.csv"))
    write_csv(csv_path, rows)

    print("=" * WIDTH)
    print(f"Ran {len(cases)} test cases across {len(translators)} services.")
    print(f"Raw translations saved to: {json_path}")
    print(f"Rating sheet saved to:     {csv_path}")
    print(f"\nNext step: python main.py --rate {csv_path}")


def write_csv(path, rows):
    # utf-8-sig so Excel displays accented and Japanese characters correctly
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def ask_score(label):
    scale = "  ".join(f"{k}={v}" for k, v in SCALE.items())
    while True:
        answer = input(f"{label} ({scale}, q=quit): ").strip().lower()
        if answer == "q":
            return None
        if answer in {"1", "2", "3", "4", "5"}:
            return answer
        print("  Please enter a number from 1 to 5.")


def ask_errors():
    menu = "  ".join(f"{i}={c}" for i, c in enumerate(ERROR_CATEGORIES))
    print(textwrap.fill(f"Error categories: {menu}", width=WIDTH))
    while True:
        answer = input("Errors (comma-separated numbers, Enter = none): ").strip()
        if not answer:
            return "none"
        try:
            picks = [ERROR_CATEGORIES[int(x)] for x in answer.split(",")]
            return "; ".join(dict.fromkeys(picks))
        except (ValueError, IndexError):
            print("  Use numbers from the list, e.g. 1,5")


def run_rate(path):
    """Walk through each unrated translation and record the human ratings."""
    rows = read_csv(path)
    todo = [r for r in rows if not r["adequacy"] or not r["fluency"]]
    print(f"{len(todo)} of {len(rows)} translations still need ratings. Progress saves after each one.\n")

    for i, row in enumerate(todo, 1):
        print("=" * WIDTH)
        print(f"({i}/{len(todo)})  [{row['case_id']}] {row['category']}   service: {row['service']}")
        print(wrap("Source:", row["source_text"]))
        if row["reference"]:
            print(wrap("Reference:", row["reference"]))
        print(wrap("Output:", row["translation"]))
        print("-" * WIDTH)
        if row["translation"].startswith("ERROR"):
            row.update(adequacy="1", fluency="1", errors="missing information", notes="service returned an error")
            write_csv(path, rows)
            print("Service error - recorded as 1/1.\n")
            continue

        adequacy = ask_score("Adequacy - meaning preserved?")
        if adequacy is None:
            break
        fluency = ask_score("Fluency  - natural & grammatical?")
        if fluency is None:
            break
        errors = ask_errors()
        notes = input("Notes (why? optional): ").strip()

        row.update(adequacy=adequacy, fluency=fluency, errors=errors, notes=notes)
        write_csv(path, rows)
        print()

    print(f"Ratings saved to {path}. When finished: python main.py --report {path}")


def avg(values):
    return round(sum(values) / len(values), 2) if values else 0.0


def run_report(path):
    """Summarize ratings: averages per service, per category, and error counts."""
    rows = [r for r in read_csv(path) if r["adequacy"] and r["fluency"]]
    if not rows:
        sys.exit("No rated rows found. Run --rate first.")

    services = sorted({r["service"] for r in rows})
    categories = list(dict.fromkeys(r["category"] for r in rows))

    by_service = defaultdict(lambda: {"a": [], "f": []})
    by_cat = defaultdict(list)
    errors = defaultdict(Counter)
    for r in rows:
        a, f = int(r["adequacy"]), int(r["fluency"])
        by_service[r["service"]]["a"].append(a)
        by_service[r["service"]]["f"].append(f)
        by_cat[(r["category"], r["service"])].append((a + f) / 2)
        for e in r["errors"].split(";"):
            e = e.strip()
            if e and e != "none":
                errors[r["service"]][e] += 1

    lines = ["# Machine Translation Evaluation Report", ""]
    lines += [f"Rated translations: {len(rows)}  |  Services: {', '.join(services)}", ""]

    lines += ["## Overall scores (1-5)", "",
              "| Service | Avg adequacy | Avg fluency | Overall |",
              "|---|---|---|---|"]
    overall = {}
    for s in services:
        a, f = avg(by_service[s]["a"]), avg(by_service[s]["f"])
        overall[s] = round((a + f) / 2, 2)
        lines.append(f"| {s} | {a} | {f} | {overall[s]} |")
    best = max(overall, key=overall.get)
    lines += ["", f"**Best overall: {best}** ({overall[best]})", ""]

    lines += ["## Average score by test category", "",
              "| Category | " + " | ".join(services) + " | Best |",
              "|---|" + "---|" * (len(services) + 1)]
    for c in categories:
        scores = {s: avg(by_cat[(c, s)]) for s in services if by_cat[(c, s)]}
        top = max(scores.values())
        winners = ", ".join(s for s, v in scores.items() if v == top)
        cells = " | ".join(str(scores.get(s, "-")) for s in services)
        lines.append(f"| {c} | {cells} | {winners} |")
    lines.append("")

    lines += ["## Error counts by service", "",
              "| Error type | " + " | ".join(services) + " |",
              "|---|" + "---|" * len(services)]
    for e in ERROR_CATEGORIES[1:]:
        counts = [errors[s][e] for s in services]
        if any(counts):
            lines.append(f"| {e} | " + " | ".join(map(str, counts)) + " |")
    lines.append("")

    lines += ["## Translations with errors", ""]
    for r in rows:
        if r["errors"] and r["errors"] != "none":
            note = f" - {r['notes']}" if r["notes"] else ""
            lines.append(f"- **{r['case_id']} / {r['service']}** ({r['errors']}): "
                         f"\"{r['translation']}\"{note}")

    report = "\n".join(lines) + "\n"
    out = os.path.join(os.path.dirname(path) or ".", "report.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"Report saved to {out}")


# ---------------------------------------------------------------- entry

def main():
    parser = argparse.ArgumentParser(description="Compare and evaluate machine translation services.")
    parser.add_argument("--text", help="text to translate")
    parser.add_argument("--source", default="en", help="source language code (default: en)")
    parser.add_argument("--target", default="es", help="target language code (default: es)")
    parser.add_argument("--tests", metavar="JSON", help="run all test cases in a JSON file")
    parser.add_argument("--rate", metavar="CSV", help="rate translations in a ratings CSV")
    parser.add_argument("--report", metavar="CSV", help="summarize a rated CSV")
    args = parser.parse_args()

    if args.tests:
        run_tests(args.tests)
    elif args.rate:
        run_rate(args.rate)
    elif args.report:
        run_report(args.report)
    elif args.text:
        run_single(args.text, args.source, args.target)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
