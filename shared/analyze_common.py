"""Zajednicko jezgro alata za proveru materijala i logova (S1/S2/S3),
uputstvo za spajanje jezgra, korak 7.

Premesteno bez izmene ponasanja iz s2-demo/analyze_log_s2.py i
s3-demo/analyze_log.py (dump_item_s2.py/dump_item.py dele load_json i
format_table). Svaka funkcija ispod je bila bajt-identicna (ili, kod
percentile, algoritamski identicna do na jednu odbrambenu proveru koja se
u praksi nikad nije ni pozivala na praznoj listi -- videti napomenu) u
originalima. Sto NIJE ovde: verify_hashes_or_die (S3 mora da razlikuje
variant S3a/S3b/practice, S2 ima samo jedan items fajl -- strukturno
razlicito, ostaje po scenariju), normalizacija/tipologija gresaka (samo
S2, tacnost se ne beleze u S3 logu jer S3 vec racuna correct u
pregledacu), analiza ishoda sugestije (samo S3b). To ostaje u
analyze_log.py, odvojeno po scenariju.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path


def sha256_of_file(path: Path) -> str:
    """Isti format kao app/task.js (bufToHashHex): 'sha256:' + hex, nad
    sirovim bajtovima fajla."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_events(paths):
    """Vraca listu (path, session_header, events)."""
    blocks = []
    for path in paths:
        session = None
        events = []
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"UPOZORENJE: {path}:{line_no} neispravan JSON ({e})", file=sys.stderr)
                    continue
                if obj.get("type") == "session":
                    session = obj
                else:
                    events.append(obj)
        blocks.append((path, session, events))
    return blocks


def pct(n, d):
    return f"{(100 * n / d):.1f}%" if d else "n/a"


def percentile(sorted_vals, p):
    """Linearna interpolacija (numpy-stil). Prazna lista -> nan (S3-ov
    original nije imao ovu proveru, ali je nikad nije ni pozivao na
    praznoj listi -- svaki poziv u oba originala je vec bio uslovljen sa
    `if vals:`/`if decision_vals:` -- pa dodavanje ovde ne menja nijedan
    stvaran ishod, samo cini funkciju bezbednom za buduce pozivaoce."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def format_table(columns: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in columns]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(columns), fmt_row(["-" * w for w in widths])]
    lines.extend(fmt_row(row) for row in rows)
    return "\n".join(lines)
