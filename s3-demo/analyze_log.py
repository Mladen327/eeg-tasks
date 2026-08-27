"""Provera ispravnosti log datoteka za Scenario 3 (sekcija 10).

Cita jednu ili vise .jsonl datoteka (jedan blok po datoteci) i ispisuje
sumarne statistike potrebne za proveru da li je materijal i tajming
upotrebljiv za pilot/glavnu studiju.

Upotreba:
    python analyze_log.py logs/*.jsonl
    python analyze_log.py logs/<SIFRA>_S3b_5_20260825T101403Z.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics as stats
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent

TARGET_OUTCOME_QUOTAS = {
    "true_positive": 0.10,
    "true_negative": 0.65,
    "missed_error": 0.15,
    "false_alarm": 0.10,
}
TARGET_MISMATCH_RATE = 0.25
SUGGESTION_LATENCY_TARGET_MS = 1500
LATENCY_MAX_DEVIATION_WARN_MS = 50


def sha256_of_file(path: Path) -> str:
    """Isti format kao app/task.js (bufToHashHex): 'sha256:' + hex, nad
    sirovim bajtovima fajla."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hashes_or_die(blocks, data_dir: Path):
    """Pre bilo kakve analize: za svaki blok sa session zaglavljem, uporedi
    items_hash/companies_hash iz loga sa hesom fajlova koje bi ovaj log
    trebalo da odgovara (data/items_S3a.json ili items_S3b.json prema
    session['variant'], i data/companies.json). Prekida odmah na prvo
    neslaganje ili nedostajuce polje -- isti mehanizam kao u
    s2-demo/analyze_log_s2.py, radi uporedivosti."""
    companies_path = data_dir / "companies.json"
    items_paths = {
        "S3a": data_dir / "items_S3a.json",
        "S3b": data_dir / "items_S3b.json",
        "practice": data_dir / "items_S3a.json",  # vezba uvek koristi S3a stavke (app/task.js)
    }

    for path, session, events in blocks:
        if session is None:
            continue
        variant = session.get("variant")
        items_path = items_paths.get(variant)
        if items_path is None:
            sys.exit(f"PREKID: {path} -- nepoznata varijanta '{variant}' u zaglavlju sesije, "
                      f"ne mogu da odredim koji items_S3*.json fajl da proverim.")
        if not items_path.exists() or not companies_path.exists():
            print(f"UPOZORENJE: {items_path} ili {companies_path} ne postoji -- preskacem "
                  f"proveru heša za {path}.", file=sys.stderr)
            continue

        logged_items_hash = session.get("items_hash")
        logged_companies_hash = session.get("companies_hash")
        if logged_items_hash is None or logged_companies_hash is None:
            sys.exit(
                f"PREKID: {path} nema items_hash/companies_hash u zaglavlju sesije -- log je "
                f"verovatno snimljen pre uvodjenja provere integriteta, ili je zaglavlje "
                f"osteceno. Ne moze da se potvrdi da je ovaj log snimljen sa trenutnim "
                f"{items_path.name}/{companies_path.name}."
            )

        expected_items_hash = sha256_of_file(items_path)
        if logged_items_hash != expected_items_hash:
            sys.exit(
                f"PREKID: {path} -- items_hash iz loga ({logged_items_hash}) ne odgovara "
                f"trenutnom {items_path} ({expected_items_hash}). Log je verovatno snimljen sa "
                f"drugom generacijom stimulusa (drugi seed/broj ucesnika) -- rezultati poredjenja "
                f"bi bili besmisleni. Regenerisati stimuluse istim seedom kao pri snimanju, ili "
                f"ne mesati logove iz razlicitih generacija."
            )

        expected_companies_hash = sha256_of_file(companies_path)
        if logged_companies_hash != expected_companies_hash:
            sys.exit(
                f"PREKID: {path} -- companies_hash iz loga ({logged_companies_hash}) ne "
                f"odgovara trenutnom {companies_path} ({expected_companies_hash})."
            )


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
    """Linearna interpolacija (numpy-stil). sorted_vals mora biti neprazan i sortiran."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def analyze(blocks):
    all_events = []
    for path, session, events in blocks:
        for e in events:
            e["_path"] = str(path)
        all_events.extend(events)

    value_submitted = [e for e in all_events if e.get("event") == "value_submitted"]
    suggestion_shown = [e for e in all_events if e.get("event") == "suggestion_shown"]
    decisions = [e for e in all_events if e.get("event") == "decision"]
    field_active = [e for e in all_events if e.get("event") == "field_active"]
    peek_events = [e for e in all_events if e.get("event") in ("peek_start", "peek_end")]
    item_starts = [e for e in all_events if e.get("event") == "item_start"]

    n_items = len(item_starts)
    n_fields = len(value_submitted)

    print("=" * 72)
    print(f"Blokova: {len(blocks)}  Stavki: {n_items}  Polja (value_submitted): {n_fields}")
    print("=" * 72)

    # --- raspodela outcome klasa (samo S3b, iz suggestion_shown) ---
    if suggestion_shown:
        outcome_counts = Counter(e["outcome_class"] for e in suggestion_shown)
        total = sum(outcome_counts.values())
        print("\nRaspodela ishoda sugestije (ciljano vs stvarno):")
        for cls, target in TARGET_OUTCOME_QUOTAS.items():
            actual = outcome_counts.get(cls, 0) / total if total else 0
            print(f"  {cls:16s} ciljano {target*100:5.1f}%   stvarno {actual*100:5.1f}%  (n={outcome_counts.get(cls,0)})")

        # --- stopa prihvatanja sugestija po klasi ishoda ---
        decisions_by_key = {(d["item"], d["field"], d.get("_path")): d for d in decisions}
        print("\nStopa prihvatanja sugestije (accepted=true), po klasi ishoda:")
        by_class = defaultdict(list)
        for s in suggestion_shown:
            key = (s["item"], s["field"], s.get("_path"))
            d = decisions_by_key.get(key)
            if d is not None:
                by_class[s["outcome_class"]].append(d["accepted"])
        for cls in TARGET_OUTCOME_QUOTAS:
            vals = by_class.get(cls, [])
            rate = sum(vals) / len(vals) if vals else None
            print(f"  {cls:16s} {pct(sum(vals), len(vals)) if vals else 'n/a':>8s}  (n={len(vals)})")

        # --- stopa hvatanja propustenih gresaka ---
        vs_by_key = {(v["item"], v["field"], v.get("_path")): v for v in value_submitted}
        missed = [s for s in suggestion_shown if s["outcome_class"] == "missed_error"]
        caught = 0
        for s in missed:
            key = (s["item"], s["field"], s.get("_path"))
            v = vs_by_key.get(key)
            if v is not None and v.get("correct"):
                caught += 1
        print(f"\nStopa hvatanja propustenih gresaka (missed_error, ali ispitanik tacan): "
              f"{pct(caught, len(missed))}  ({caught}/{len(missed)})")

        # --- odstupanje latencije sugestije od 1500ms ---
        latencies = [s["latency_actual_ms"] for s in suggestion_shown if "latency_actual_ms" in s]
        if latencies:
            deviations = [abs(l - SUGGESTION_LATENCY_TARGET_MS) for l in latencies]
            max_dev = max(deviations)
            sd = stats.pstdev(latencies) if len(latencies) > 1 else 0.0
            print(f"\nLatencija sugestije: cilj {SUGGESTION_LATENCY_TARGET_MS} ms, "
                  f"srednje odstupanje {stats.mean(deviations):.1f} ms, "
                  f"max odstupanje {max_dev:.1f} ms, sd {sd:.1f} ms")
            if max_dev > LATENCY_MAX_DEVIATION_WARN_MS:
                print(f"  UPOZORENJE: max odstupanje > {LATENCY_MAX_DEVIATION_WARN_MS} ms -- "
                      f"tajming nije pouzdan za analizu po prozorima od 1 s (sekcija 10).")
    else:
        print("\n(Nema suggestion_shown dogadjaja -- verovatno S3a log, sekcija o sugestijama se preskace.)")

    # --- srednje vreme do odluke po klasi ishoda (koristi decision_ms iz value_submitted) ---
    print("\nSredje vreme do odluke (value_submitted.decision_ms), po true_status:")
    fa_by_status = defaultdict(list)
    field_meta_by_key = {(f["item"], f["field"], f.get("_path")): f for f in field_active}
    for v in value_submitted:
        key = (v["item"], v["field"], v.get("_path"))
        meta = field_meta_by_key.get(key)
        status = meta["true_status"] if meta else "?"
        fa_by_status[status].append(v.get("decision_ms", 0))
    for status, vals in fa_by_status.items():
        print(f"  {status:10s} srednje {stats.mean(vals):7.1f} ms  (n={len(vals)})")

    # --- raspodela decision_ms (medijana/p75/p90) i udeo preko praga ---
    # over_deadline je racunat u task.js u odnosu na DECISION_MS_PER_FIELD
    # koji je vazio u toj sesiji (upisan u session zaglavlju); ovde se samo
    # cita, ne racuna ponovo -- ako se blokovi mesaju iz razlicitih pragova
    # (razlicit decision_ms_per_field), to se dole eksplicitno prijavljuje.
    decision_vals = sorted(v["decision_ms"] for v in value_submitted if not v.get("timed_out") and "decision_ms" in v)
    if decision_vals:
        print(f"\nRaspodela decision_ms (bez timed_out): "
              f"medijana {stats.median(decision_vals):.0f} ms, "
              f"p75 {percentile(decision_vals, 75):.0f} ms, "
              f"p90 {percentile(decision_vals, 90):.0f} ms  (n={len(decision_vals)})")
        over_deadline_n = sum(1 for v in value_submitted if v.get("over_deadline"))
        thresholds = {s.get("decision_ms_per_field") for _, s, _ in blocks if s is not None}
        thresholds.discard(None)
        threshold_note = f"prag={sorted(thresholds)[0]} ms" if len(thresholds) == 1 else \
            (f"PRAGOVI SE RAZLIKUJU MEDJU BLOKOVIMA: {sorted(thresholds)} ms" if thresholds else "prag nepoznat (staro zaglavlje)")
        print(f"Udeo polja preko praga (over_deadline=true, {threshold_note}): "
              f"{pct(over_deadline_n, len(value_submitted))}  (n={over_deadline_n})")

    # --- raspodela polja po klasi tezine, po N ---
    print("\nRaspodela polja po klasi tezine, po N (field_active):")
    by_n = defaultdict(lambda: Counter())
    n_by_key = {}
    for path, session, events in blocks:
        if session is None:
            continue
        n_by_key[str(path)] = session.get("n_fields")
    for f in field_active:
        n = n_by_key.get(f.get("_path"), "?")
        by_n[n][f.get("weight_class", "?")] += 1
    for n, counter in sorted(by_n.items(), key=lambda x: str(x[0])):
        total = sum(counter.values())
        parts = ", ".join(f"{k}={pct(v,total)}" for k, v in counter.items())
        print(f"  N={n}: {parts}  (n polja={total})")

    # --- stopa otkrivanja (tacnost) po klasi tezine ---
    print("\nStopa otkrivanja (udeo correct=true), po klasi tezine:")
    detect_by_weight = defaultdict(list)
    for v in value_submitted:
        key = (v["item"], v["field"], v.get("_path"))
        meta = field_meta_by_key.get(key)
        weight = meta["weight_class"] if meta else "?"
        detect_by_weight[weight].append(v.get("correct", False))
    for weight in ("high", "medium", "low"):
        vals = detect_by_weight.get(weight, [])
        print(f"  {weight:8s} {pct(sum(vals), len(vals)) if vals else 'n/a':>8s}  (n={len(vals)})")

    # --- match/mismatch udeo, provera prema ciljanih 25% ---
    statuses = [f.get("true_status") for f in field_active]
    mismatch_rate = statuses.count("mismatch") / len(statuses) if statuses else 0
    print(f"\nUdeo mismatch polja: {mismatch_rate*100:.1f}% (cilj {TARGET_MISMATCH_RATE*100:.0f}%)")

    # --- broj ponovnih uvida po stavci, po N ---
    print("\nBroj ponovnih uvida (peek) po stavci, po N:")
    peek_starts_by_item = defaultdict(int)
    for e in all_events:
        if e.get("event") == "peek_start":
            peek_starts_by_item[(e.get("item"), e.get("_path"))] += 1
    peeks_by_n = defaultdict(list)
    item_n = {}
    for path, session, events in blocks:
        n = session.get("n_fields") if session else "?"
        for e in events:
            if e.get("event") == "item_start":
                item_n[(e["item"], str(path))] = n
    for item_start in item_starts:
        key = (item_start["item"], item_start.get("_path"))
        n = item_n.get(key, "?")
        peeks_by_n[n].append(peek_starts_by_item.get(key, 0))
    for n, vals in sorted(peeks_by_n.items(), key=lambda x: str(x[0])):
        print(f"  N={n}: prosek {stats.mean(vals):.2f} uvida po stavci  (stavki={len(vals)})")

    # --- raspodela chosen_role po N ---
    print("\nRaspodela chosen_role, po N:")
    role_by_n = defaultdict(Counter)
    for v in value_submitted:
        n = n_by_key.get(v.get("_path"), "?")
        role_by_n[n][v.get("chosen_role") or "timed_out"] += 1
    for n, counter in sorted(role_by_n.items(), key=lambda x: str(x[0])):
        total = sum(counter.values())
        parts = ", ".join(f"{k}={pct(v,total)}" for k, v in counter.items())
        print(f"  N={n}: {parts}")

    # --- znaci odustajanja ---
    print("\nZnaci odustajanja:")
    timed_out = [v for v in value_submitted if v.get("timed_out")]
    print(f"  Udeo polja resenih na isteku vremenskog limita (timed_out; smisleno samo kad je "
          f"enforce_decision_deadline=true u zaglavlju): {pct(len(timed_out), len(value_submitted))}")

    # trend tacnosti i vremena do odluke kroz blok (prva vs poslednja trecina stavki, po bloku)
    for path, session, events in blocks:
        block_vs = [e for e in events if e.get("event") == "value_submitted"]
        if len(block_vs) < 6:
            continue
        third = max(1, len(block_vs) // 3)
        first = block_vs[:third]
        last = block_vs[-third:]
        acc_first = sum(v.get("correct", False) for v in first) / len(first)
        acc_last = sum(v.get("correct", False) for v in last) / len(last)
        time_first = stats.mean(v.get("decision_ms", 0) for v in first)
        time_last = stats.mean(v.get("decision_ms", 0) for v in last)
        flag = ""
        if acc_last < acc_first - 0.1 and time_last > time_first * 1.1:
            flag = "  <- pad tacnosti + rast vremena: mozda odustajanje"
        print(f"  {path}: tacnost prva/poslednja trecina {acc_first*100:.0f}%/{acc_last*100:.0f}%, "
              f"vreme {time_first:.0f}/{time_last:.0f} ms{flag}")

    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logfiles", nargs="+", type=Path)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    blocks = load_events(args.logfiles)
    verify_hashes_or_die(blocks, args.data)
    analyze(blocks)


if __name__ == "__main__":
    main()
