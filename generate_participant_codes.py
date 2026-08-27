"""Generise sifre ispitanika za fizicke kartice -- alternativa numerisanju
ucesnika, da aplikacija nikad ne veze sifru za identitet (uputstvo:
"Sifra ispitanika se ne generise u aplikaciji"). Uz svaku sifru dodeljuje i
KONTRABALANSIRAN redosled tri zadatka (integracija sesije, tacka 4: "cita
se iz dodele, ne bira rucno").

Sifra: 4 znaka, velika slova i cifre, BEZ znakova koji se lako mesaju pri
citanju sa odstampane kartice: O/0, I/1/L, S/5. Preostali skup (29 znakova):
    slova:  A B C D E F G H J K M N P Q R T U V W X Y Z
    cifre:  2 3 4 6 7 8 9

"DEMO" je namerno rezervisano i van ovog skupa (sadrzi "O") -- ne moze da se
izgeneriše kao prava sifra, pa nema sudara sa posebnom probnom sifrom
(core/intro.js je uvek prihvata bez provere liste, i DEMO/vezba zadrzavaju
slobodan izbor redosleda -- ne prolaze kroz dodelu ovde).

Redosled zadataka: ciklicno se dodeljuje jedna od 6 permutacija (S1,S2,S3)
po SORTIRANOM redosledu sifri -- svaka permutacija se pojavljuje podjednako
cesto (do zaokruzivanja na 6), determinicki iz --seed (ista dodela pri
ponovnom pokretanju sa istim seedom/brojem sifri).

Izlaz:
    data/participant_codes.json  -- {"codes": [...], "assignments": {sifra: [S?,S?,S?]}, "seed": N, "count": N}
    data/codes_printable.html    -- za stampu, jedna sifra po kartici

Pokretanje:
    python generate_participant_codes.py --count 60 --seed 20260825
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path

ROOT = Path(__file__).parent

LETTERS = "ABCDEFGHJKMNPQRTUVWXYZ"  # bez O, I, L, S
DIGITS = "2346789"  # bez 0, 1, 5
ALPHABET = LETTERS + DIGITS
CODE_LENGTH = 4

RESERVED = {"DEMO"}  # nikad ne sme da se izgeneriše kao prava sifra (i ne moze -- sadrzi "O")

TASKS = ("S1", "S2", "S3")
TASK_ORDER_PERMUTATIONS = list(itertools.permutations(TASKS))  # 6 permutacija


def gen_codes(count: int, rng: random.Random) -> list[str]:
    codes: set[str] = set()
    while len(codes) < count:
        code = "".join(rng.choice(ALPHABET) for _ in range(CODE_LENGTH))
        if code in RESERVED:
            continue
        codes.add(code)
    return sorted(codes)


def gen_task_order_assignment(codes: list[str], rng: random.Random) -> dict[str, list[str]]:
    """Kontrabalansiran redosled: SVIH 6 permutacija se izmesa jednom
    (rng.shuffle), pa se ciklicno dodeljuje sortiranim siframa -- svaka
    permutacija se pojavi podjednako cesto, redosled dodele je jos i
    nepredvidiv (ne uvek "prva sifra dobija S1,S2,S3")."""
    shuffled_perms = TASK_ORDER_PERMUTATIONS[:]
    rng.shuffle(shuffled_perms)
    return {code: list(shuffled_perms[i % len(shuffled_perms)]) for i, code in enumerate(codes)}


def build_printable_html(codes: list[str]) -> str:
    cards = "\n".join(f'      <div class="card"><span class="code">{c}</span></div>' for c in codes)
    return f"""<!doctype html>
<html lang="sr">
<head>
<meta charset="utf-8">
<title>Sifre ispitanika -- kartice za stampu</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; }}
  .sheet {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    padding: 12px;
  }}
  .card {{
    border: 1px dashed #999;
    border-radius: 6px;
    padding: 18px 8px;
    text-align: center;
    break-inside: avoid;
  }}
  .code {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 28px;
    font-weight: bold;
    letter-spacing: 0.15em;
  }}
  @media print {{
    .card {{ border-color: #ccc; }}
  }}
</style>
</head>
<body>
  <div class="sheet">
{cards}
  </div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, required=True, help="Broj sifri (= broj planiranih ispitanika).")
    ap.add_argument("--seed", type=int, required=True, help="Za reproduktivnost -- ista lista pri istom seedu.")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "participant_codes.json")
    ap.add_argument("--html-out", type=Path, default=ROOT / "data" / "codes_printable.html")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    codes = gen_codes(args.count, rng)
    assignments = gen_task_order_assignment(codes, rng)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"codes": codes, "assignments": assignments, "seed": args.seed, "count": len(codes)},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    args.html_out.parent.mkdir(parents=True, exist_ok=True)
    args.html_out.write_text(build_printable_html(codes), encoding="utf-8")

    print(f"OK: {len(codes)} sifri -> {args.out}")
    print(f"OK: kartice za stampu -> {args.html_out}")


if __name__ == "__main__":
    main()
