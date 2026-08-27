"""Ispisuje stavke jednog ucesnika u citljivoj tabeli, za rucnu proveru
generisanog materijala (sekcija 12 uputstva S2/S3 + korak 7 uputstva za
spajanje jezgra: jedan alat sa --scenario, umesto dump_item_s2.py i
dump_item.py).

S2: kolone su redni broj stavke, firma, polje, klasa tezine, vrednost koju
treba preneti (reference_value -- ista vrednost je i na dokumentu i ono sto
se ocekuje u tabeli, S2 nema mismatch/distractor mehaniku kao S3).

S3: kolone su redni broj stavke, polje, klasa tezine, referentna vrednost,
vrednost na ugovoru, status (match/mismatch), klasa ishoda sugestije (samo
za S3b, iz suggestions.json -- za S3a je "-").

S1: kolone su redni broj stavke, redni broj recenice unutar stavke, klasa
duzine, poreklo (enron/constructed), da li je pitanje, tekst recenice.
Bez firme/polja -- S1 nema stavka-firma vezu (SPEC_S1_demo.md 3.3).

Vrednosti su sirove, kao u items_*.json/logu (bez segmentacije/formatiranja
iz prikaza u app/task.js).

Upotreba:
    python dump_item.py --scenario S2 --participant DEMO --items 1 2
    python dump_item.py --scenario S2 --participant DEMO --n 5 --random 20 --seed 1
    python dump_item.py --scenario S3 --participant <SIFRA> --variant S3a --n 3 --items 5 12 30
    python dump_item.py --scenario S1 --participant DEMO --n 7 --items 1 2
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from shared import analyze_common as ac

EEG_TASKS_ROOT = Path(__file__).parent

S2_COLUMNS = ["Stavka", "Firma", "Polje", "Tezina", "Vrednost"]
S3_COLUMNS = ["Stavka", "Polje", "Tezina", "Referentna", "Na ugovoru", "Status", "Sugestija"]
S1_COLUMNS = ["Stavka", "Redni broj", "Klasa duzine", "Poreklo", "Pitanje", "Tekst"]


# ==========================================================================
# Scenario S2 -- premesteno bez izmene ponasanja iz s2-demo/dump_item_s2.py.
# ==========================================================================

def run_s2(args):
    out = args.data or (EEG_TASKS_ROOT / "s2-demo" / "data")

    items_path = out / "items_S2.json"
    items_data = ac.load_json(items_path)
    if items_data is None:
        raise SystemExit(f"ne postoji {items_path} -- pokreni prvo generate_stimuli.py --scenario S2")

    try:
        block = items_data["participants"][args.participant][str(args.n)]
    except KeyError:
        raise SystemExit(
            f"nema podataka za participant={args.participant!r} n={args.n} u {items_path}"
        )

    companies = {c["company_id"]: c for c in ac.load_json(out / "companies.json")["companies"]}

    if args.random:
        rng = random.Random(args.seed)
        item_nos = sorted(rng.sample(range(1, len(block) + 1), min(args.random, len(block))))
    else:
        item_nos = args.items

    rows = []
    for item_no in item_nos:
        if not (1 <= item_no <= len(block)):
            raise SystemExit(f"stavka {item_no} ne postoji u bloku (ima ih {len(block)})")
        item = block[item_no - 1]
        company_name = companies.get(item["company_id"], {}).get("company_name", "?")
        fields = sorted(item["fields"], key=lambda f: f["order"])
        for f in fields:
            rows.append([
                str(item_no),
                company_name,
                f["field_name"],
                f["weight_class"],
                str(f["reference_value"]),
            ])

    print(f"participant={args.participant}  n={args.n}  stavki={len(item_nos)}\n")
    print(ac.format_table(S2_COLUMNS, rows))

    # brza provera sastava: koliko polja svake klase po stavci
    print("\nProvera sastava (broj polja po klasi, po stavci):")
    for item_no in item_nos:
        item = block[item_no - 1]
        counts = {"high": 0, "medium": 0, "low": 0}
        for f in item["fields"]:
            counts[f["weight_class"]] += 1
        print(f"  Stavka {item_no}: high={counts['high']} medium={counts['medium']} low={counts['low']} "
              f"(n_fields={item['n_fields']})")


# ==========================================================================
# Scenario S3 -- premesteno bez izmene ponasanja iz s3-demo/dump_item.py.
# ==========================================================================

def s3_build_suggestion_index(suggestions_data, participant: str, n: int):
    """(item_id, field_name) -> outcome_class"""
    if suggestions_data is None:
        return {}
    try:
        entries = suggestions_data["participants"][participant][str(n)]
    except KeyError:
        return {}
    index = {}
    for entry in entries:
        for f in entry["fields"]:
            index[(entry["item_id"], f["field_name"])] = f["outcome_class"]
    return index


def run_s3(args):
    out = args.data or (EEG_TASKS_ROOT / "s3-demo" / "data")

    items_path = out / f"items_{args.variant}.json"
    items_data = ac.load_json(items_path)
    if items_data is None:
        raise SystemExit(f"ne postoji {items_path} -- pokreni prvo generate_stimuli.py --scenario S3")

    try:
        block = items_data["participants"][args.participant][str(args.n)]
    except KeyError:
        raise SystemExit(
            f"nema podataka za participant={args.participant!r} variant={args.variant} n={args.n} "
            f"u {items_path}"
        )

    suggestions_data = ac.load_json(out / "suggestions.json") if args.variant == "S3b" else None
    suggestion_index = s3_build_suggestion_index(suggestions_data, args.participant, args.n)

    rows = []
    for item_no in args.items:
        if not (1 <= item_no <= len(block)):
            raise SystemExit(f"stavka {item_no} ne postoji u bloku (ima ih {len(block)})")
        item = block[item_no - 1]
        fields = sorted(item["fields"], key=lambda f: f["order"])
        for f in fields:
            outcome = suggestion_index.get((item["item_id"], f["field_name"]), "-")
            rows.append([
                str(item_no),
                f["field_name"],
                f["weight_class"],
                str(f["reference_value"]),
                str(f["displayed_value"]),
                f["true_status"],
                outcome,
            ])

    print(f"participant={args.participant}  variant={args.variant}  n={args.n}\n")
    print(ac.format_table(S3_COLUMNS, rows))


# ==========================================================================
# Scenario S1 -- SPEC_S1_demo.md, korak 3. Bez firme/polja po recenici --
# vidi napomenu uz S1_COLUMNS.
# ==========================================================================

def run_s1(args):
    out = args.data or (EEG_TASKS_ROOT / "data")

    items_path = out / "items_S1.json"
    items_data = ac.load_json(items_path)
    if items_data is None:
        raise SystemExit(f"ne postoji {items_path} -- pokreni prvo generate_stimuli.py --scenario S1")

    try:
        block = items_data["participants"][args.participant][str(args.n)]
    except KeyError:
        raise SystemExit(
            f"nema podataka za participant={args.participant!r} n={args.n} u {items_path}"
        )

    if args.random:
        rng = random.Random(args.seed)
        item_nos = sorted(rng.sample(range(1, len(block) + 1), min(args.random, len(block))))
    else:
        item_nos = args.items

    rows = []
    for item_no in item_nos:
        if not (1 <= item_no <= len(block)):
            raise SystemExit(f"stavka {item_no} ne postoji u bloku (ima ih {len(block)})")
        item = block[item_no - 1]
        for s in item["sentences"]:
            rows.append([
                str(item_no),
                str(s["sentence_index"]),
                s["length_class"],
                s["source"],
                "da" if s["is_question"] else "ne",
                s["text"],
            ])

    print(f"participant={args.participant}  n={args.n}  stavki={len(item_nos)}\n")
    print(ac.format_table(S1_COLUMNS, rows))

    # brza provera sastava: koliko recenica svake klase i porekla po stavci
    # (sekcija 3.2 sastav + tacka E balans porekla)
    print("\nProvera sastava (broj recenica po klasi i po poreklu, po stavci):")
    for item_no in item_nos:
        item = block[item_no - 1]
        counts = {"high": 0, "medium": 0, "low": 0}
        sources = {"enron": 0, "constructed": 0}
        for s in item["sentences"]:
            counts[s["length_class"]] += 1
            sources[s["source"]] += 1
        balance_flag = "  [UPOZORENJE: iskljucivo jednog porekla]" if min(sources.values()) == 0 else ""
        print(f"  Stavka {item_no}: high={counts['high']} medium={counts['medium']} low={counts['low']} "
              f"(n_sentences={item['n_sentences']})  enron={sources['enron']} "
              f"constructed={sources['constructed']}{balance_flag}")


# ==========================================================================
# main
# ==========================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=["S1", "S2", "S3"], required=True)
    ap.add_argument("--participant", required=True, help='npr. "DEMO", ili stvarna sifra iz participant_codes.json')
    ap.add_argument("--variant", choices=["S3a", "S3b"], default="S3b", help="samo za --scenario S3")
    ap.add_argument("--n", type=int, choices=[3, 5, 7], default=5)
    ap.add_argument("--items", type=int, nargs="+", help="redni brojevi stavki u bloku, 1-zasnovano")
    ap.add_argument("--random", type=int,
                     help="samo za --scenario S2/S1: umesto --items, izaberi ovoliko nasumicnih stavki")
    ap.add_argument("--seed", type=int, default=0, help="seed za --random (samo za ovaj alat, ne za studiju)")
    ap.add_argument("--data", type=Path,
                     help="Podrazumevano: data/ za S1 (zajednicko), s2-demo/data odn. "
                          "s3-demo/data za S2/S3, u odnosu na ovaj fajl.")
    args = ap.parse_args()

    if args.scenario == "S2":
        if not args.items and not args.random:
            ap.error("--scenario S2 zahteva --items ili --random")
        run_s2(args)
    elif args.scenario == "S3":
        if not args.items:
            ap.error("--scenario S3 zahteva --items")
        run_s3(args)
    else:
        if not args.items and not args.random:
            ap.error("--scenario S1 zahteva --items ili --random")
        run_s1(args)


if __name__ == "__main__":
    main()
