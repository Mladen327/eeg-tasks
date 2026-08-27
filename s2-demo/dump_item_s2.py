"""Ispisuje stavke jednog ucesnika u citljivoj tabeli, za rucnu proveru
generisanog materijala (sekcija 12, korak 1 uputstva S2: "pregledati 20
nasumicnih stavki").

Kolone: redni broj stavke, polje, klasa tezine, vrednost koju treba preneti
(reference_value -- ista vrednost je i na dokumentu i ono sto se ocekuje u
tabeli, S2 nema mismatch/distractor mehaniku kao S3).

Vrednosti su sirove, kao u items_S2.json/logu (bez segmentacije/formatiranja
iz sekcije 3.3 -- to je iskljucivo prikaz u app/task.js).

Upotreba:
    python dump_item_s2.py --participant DEMO --items 1 2
    python dump_item_s2.py --participant <SIFRA> --n 7 --items 5 12 30
    python dump_item_s2.py --participant DEMO --n 5 --random 20 --seed 1
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).parent

COLUMNS = ["Stavka", "Firma", "Polje", "Tezina", "Vrednost"]


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def format_table(rows: list[list[str]]) -> str:
    widths = [len(h) for h in COLUMNS]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(COLUMNS), fmt_row(["-" * w for w in widths])]
    lines.extend(fmt_row(row) for row in rows)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--participant", required=True, help='npr. "DEMO", ili stvarna sifra iz participant_codes.json')
    ap.add_argument("--n", type=int, choices=[3, 5, 7], default=5)
    ap.add_argument("--items", type=int, nargs="+", help="redni brojevi stavki u bloku, 1-zasnovano")
    ap.add_argument("--random", type=int, help="umesto --items, izaberi ovoliko nasumicnih stavki")
    ap.add_argument("--seed", type=int, default=0, help="seed za --random (samo za ovaj alat, ne za studiju)")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    if not args.items and not args.random:
        raise SystemExit("navesti --items ili --random")

    items_path = args.data / "items_S2.json"
    items_data = load_json(items_path)
    if items_data is None:
        raise SystemExit(f"ne postoji {items_path} -- pokreni prvo generate_stimuli_s2.py")

    try:
        block = items_data["participants"][args.participant][str(args.n)]
    except KeyError:
        raise SystemExit(
            f"nema podataka za participant={args.participant!r} n={args.n} u {items_path}"
        )

    companies = {c["company_id"]: c for c in load_json(args.data / "companies.json")["companies"]}

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
    print(format_table(rows))

    # brza provera sastava: koliko polja svake klase po stavci
    print("\nProvera sastava (broj polja po klasi, po stavci):")
    for item_no in item_nos:
        item = block[item_no - 1]
        counts = {"high": 0, "medium": 0, "low": 0}
        for f in item["fields"]:
            counts[f["weight_class"]] += 1
        print(f"  Stavka {item_no}: high={counts['high']} medium={counts['medium']} low={counts['low']} "
              f"(n_fields={item['n_fields']})")


if __name__ == "__main__":
    main()
