"""Poredi dva .jsonl loga (pre/posle refaktora) red-po-red, ignorišući
polja koja su MERENE (a ne planirane) vremenske vrednosti -- ta polja se
neizbežno razlikuju između dva pokretanja čak i sa identičnim skriptovanim
radnjama (jitter u rasporedjivanju requestAnimationFrame/setTimeout).
Sve ostalo (redosled dogadjaja, imena polja, planirane/izvedene vrednosti
kao duration_ms, brojevi ponavljanja, itd.) mora biti IDENTIČNO.

Upotreba:
    python compare_logs.py pre.jsonl posle.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Merene (ne planirane) vremenske vrednosti -- neizbezno se razlikuju
# izmedju dva pokretanja.
IGNORE_FIELDS = {
    "t", "t_wall", "t0_wall", "t0_perf",
    "delay_actual_ms", "encoding_actual_ms", "document_stay_ms",
    "first_keystroke_ms", "last_keystroke_ms",
    "decision_ms", "decision_time_ms", "latency_actual_ms",
    "elapsed_ms",
}

# "scenario" je JEDINO sankcionisano dodavanje polja u log format ovim
# refaktorom (uputstvo, sekcija 8) -- bazne linije iz koraka 1 (pre ove
# izmene) ga nemaju, pa se namerno ignorise ovde da ne bi svaki session red
# ubuduce prijavljivao ocekivanu, odobrenu razliku.
IGNORE_FIELDS.add("scenario")


def load(path: Path) -> list[dict]:
    events = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}:{line_no} neispravan JSON ({e})")
    return events


def strip_ignored(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k not in IGNORE_FIELDS}


def compare(path_before: Path, path_after: Path) -> list[str]:
    before = load(path_before)
    after = load(path_after)
    diffs = []
    if len(before) != len(after):
        diffs.append(f"BROJ REDOVA: pre={len(before)} posle={len(after)}")
    for i, (b, a) in enumerate(zip(before, after)):
        b2, a2 = strip_ignored(b), strip_ignored(a)
        if b2 != a2:
            only_b = {k: v for k, v in b2.items() if k not in a2 or a2[k] != v}
            only_a = {k: v for k, v in a2.items() if k not in b2 or b2[k] != v}
            diffs.append(f"red {i} ({b.get('event') or b.get('type')}):\n  samo pre:   {only_b}\n  samo posle: {only_a}")
    return diffs


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    diffs = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    if diffs:
        print(f"NADJENO {len(diffs)} razlika (van ignorisanih vremenskih polja):")
        for d in diffs:
            print(" ", d)
        sys.exit(1)
    print(f"IDENTICNI ({sys.argv[1]} vs {sys.argv[2]}) osim ignorisanih vremenskih polja.")


if __name__ == "__main__":
    main()
