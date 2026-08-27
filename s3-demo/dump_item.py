"""Ispisuje stavke jednog ucesnika u citljivoj tabeli, za rucnu proveru
generisanog materijala (sekcija 12, korak 2 uputstva: "rucno pregledati
20 nasumicnih stavki").

Kolone: redni broj stavke, polje, klasa tezine, referentna vrednost,
vrednost na ugovoru, status (match/mismatch), klasa ishoda sugestije
(samo za S3b, iz suggestions.json -- za S3a je "-").

Vrednosti su sirove, kao u items_*.json/logu (bez segmentacije/formatiranja
iz sekcije 3.5 -- to je iskljucivo prikaz u app/task.js).

Upotreba:
    python dump_item.py --participant DEMO --items 1 2
    python dump_item.py --participant <SIFRA> --variant S3a --n 3 --items 5 12 30
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent

COLUMNS = ["Stavka", "Polje", "Tezina", "Referentna", "Na ugovoru", "Status", "Sugestija"]


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_suggestion_index(suggestions_data, participant: str, n: int):
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
    ap.add_argument("--variant", choices=["S3a", "S3b"], default="S3b")
    ap.add_argument("--n", type=int, choices=[3, 5, 7], default=5)
    ap.add_argument("--items", type=int, nargs="+", required=True,
                     help="redni brojevi stavki u bloku, 1-zasnovano (npr. 1 2 30)")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    items_path = args.data / f"items_{args.variant}.json"
    items_data = load_json(items_path)
    if items_data is None:
        raise SystemExit(f"ne postoji {items_path} -- pokreni prvo generate_stimuli.py")

    try:
        block = items_data["participants"][args.participant][str(args.n)]
    except KeyError:
        raise SystemExit(
            f"nema podataka za participant={args.participant!r} variant={args.variant} n={args.n} "
            f"u {items_path}"
        )

    suggestions_data = load_json(args.data / "suggestions.json") if args.variant == "S3b" else None
    suggestion_index = build_suggestion_index(suggestions_data, args.participant, args.n)

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
    print(format_table(rows))


if __name__ == "__main__":
    main()
