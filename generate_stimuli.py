"""Generise sintetican materijal za demonstratore Scenarija 1/2/3.

Uputstvo za spajanje jezgra, korak 7: umesto tri para skripti (ranije
s2-demo/generate_stimuli_s2.py i s3-demo/generate_stimuli.py), jedan ulaz
sa --scenario. Ovo je premestanje koda, ne izmena ponasanja -- za dati
--seed/--participants izlazni fajlovi su bajt-identicni onome sto su
odvojene skripte proizvodile pre refaktora (videti refactor_tools/).

Pokretanje (S3 se generise PRVI, uvek bez iskljucivanja -- isto kao pre
refaktora; zatim se napravi jednokratan snimak njegovih dodela i S2 se
generise iskljucujuci ih, sekcija 3 dopune S2 uputstva):

    python generate_stimuli.py --scenario S3 --seed 20260825 --participants 40
    python generate_stimuli.py --scenario S2 --snapshot-exclusions s3-demo/data/items_S3b.json
    python generate_stimuli.py --scenario S2 --seed 20260825 --participants 40

Podrazumevani --out je i dalje PO PROJEKTU za S2/S3 (s2-demo/data,
s3-demo/data) -- konsolidacija NJIHOVOG izlaza u jedinstven eeg-tasks/data/
NIJE deo ovog koraka (zahtevala bi i izmenu fetch putanja u app/task.js oba
scenarija, sto prevazilazi "Python stranu" kako je korak 7 opisan
uputstvom; ostaje odvojen, kasnije eksplicitno zatrazen korak). S1 NEMA
sopstveni projekat (SPEC_refaktor_jezgro.md: "Scenario 1 nije zaseban
projekat") -- podrazumevani --out za njega je vec zajednicki eeg-tasks/data/.

    python generate_stimuli.py --scenario S1 --seed 20260825 --participants 40

S1 ucitava data/sentences.json (build_sentences.py) i deli ga po
length_class; sastav stavke je iz SPEC_S1_demo.md 3.2 (composition[n],
kljucevi "high"/"medium"/"low" = 7/6/5 reci); disjunktnost je PO RECENICI
(ista recenica se ne ponavlja istom ispitaniku unutar sesije), NE po firmi
-- items_S1.json namerno ne sadrzi company_id nigde. Firma-disjunktnost
izmedju S1 i S2/S3 je resena na nivou baze (companies.json
s1_only_roots/s2_s3_roots), ne po stavci.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from shared import generate_common as gc

EEG_TASKS_ROOT = Path(__file__).parent
N_LEVELS = (3, 5, 7)


def load_participant_codes(count: int) -> list[str]:
    """Sifre ispitanika se NE generisu ovde (ni bilo gde u aplikaciji) --
    dolaze iz generate_participant_codes.py, odstampane na kartice.
    items_*.json mora koristiti ISTE sifre koje ce ispitanik uneti na
    pocetnom ekranu (core/intro.js proverava unos protiv tog istog fajla),
    inace se sifra ne moze povezati ni sa jednom stavkom."""
    codes_path = EEG_TASKS_ROOT / "data" / "participant_codes.json"
    if not codes_path.exists():
        raise SystemExit(
            f"PREKID: {codes_path} ne postoji. Sifre se generisu unapred, van aplikacije -- "
            f"pokreni prvo: python generate_participant_codes.py --count {count} --seed <seed>"
        )
    data = json.loads(codes_path.read_text(encoding="utf-8"))
    codes = data["codes"]
    if len(codes) < count:
        raise SystemExit(
            f"PREKID: trazeno je --participants {count}, ali {codes_path} sadrzi samo "
            f"{len(codes)} sifri. Ponovo pokreni generate_participant_codes.py sa vecim --count."
        )
    return codes[:count]


# ==========================================================================
# Scenario S2 -- premesteno bez izmene ponasanja iz
# s2-demo/generate_stimuli_s2.py.
# ==========================================================================

S2_ITEMS_PER_BLOCK = 30
S2_PRACTICE_ITEMS = 5
S2_PRACTICE_N = 3

# Napomena o odstupanju od tabele u uputstvu 3.1 -- isto obrazlozenje kao
# u S3 delu nize (street/street_number razdvojeni na medium/low da bi
# niska tezina imala 3 polja, dovoljno za N=7).
S2_FIELD_WEIGHT = {
    "pib": "high",
    "registration_number": "high",
    "company_name": "medium",
    "street": "medium",
    "contact_phone": "medium",
    "city": "low",
    "contact_person": "low",
    "street_number": "low",
}

S2_WEIGHT_POOLS = {
    "high": ["pib", "registration_number"],
    "medium": ["company_name", "street", "contact_phone"],
    "low": ["city", "contact_person", "street_number"],
}

# Redosled prikaza polja na dokumentu (odgovara rasporedu u
# document_template.html).
S2_FIELD_DISPLAY_ORDER = [
    "company_name",
    "pib",
    "registration_number",
    "city",
    "street",
    "street_number",
    "contact_person",
    "contact_phone",
]


def s2_view(company: dict) -> dict:
    """Podskup polja koja S2 stvarno koristi, u S2_FIELD_DISPLAY_ORDER."""
    return {k: company[k] for k in S2_FIELD_DISPLAY_ORDER}


def s2_build_item(rng: random.Random, item_id: str, company: dict, n: int) -> dict:
    field_names = gc.choose_fields_for_item(rng, n, gc.COMPOSITION, S2_WEIGHT_POOLS, S2_FIELD_DISPLAY_ORDER)
    document = s2_view(company)

    fields = []
    for order, field_name in enumerate(field_names):
        fields.append({
            "field_name": field_name,
            "weight_class": S2_FIELD_WEIGHT[field_name],
            "order": order,
            "reference_value": company[field_name],
        })

    return {
        "item_id": item_id,
        "company_id": company["company_id"],
        "n_fields": n,
        "document": document,
        "fields": fields,
    }


def s2_gen_items_for_participant(seed, participant_id, companies, forbidden_ids, n_items=S2_ITEMS_PER_BLOCK):
    result = {}
    available = [c for c in companies if c["company_id"] not in forbidden_ids]
    for n in N_LEVELS:
        rng = gc.seeded_rng(seed, participant_id, "S2", n)
        pool = available if available else companies  # fallback ako je iskljucivanje obrisalo sve
        block_companies = rng.sample(pool, min(n_items, len(pool)))
        if n_items > len(pool):
            extra = [rng.choice(pool) for _ in range(n_items - len(pool))]
            block_companies.extend(extra)
        items = []
        for i, company in enumerate(block_companies):
            item_id = f"{participant_id}_S2_{n}_{i + 1:03d}"
            items.append(s2_build_item(rng, item_id, company, n))
        result[str(n)] = items
    return result


def s2_gen_practice_items(seed, companies):
    rng = gc.seeded_rng(seed, "practice_s2")
    block_companies = rng.sample(companies, S2_PRACTICE_ITEMS)
    items = []
    for i, company in enumerate(block_companies):
        item_id = f"PRACTICE_S2_{i + 1:03d}"
        items.append(s2_build_item(rng, item_id, company, S2_PRACTICE_N))
    return {"n_fields": S2_PRACTICE_N, "items": items}


def run_s2(args):
    out = args.out or (EEG_TASKS_ROOT / "s2-demo" / "data")
    out.mkdir(parents=True, exist_ok=True)

    if args.snapshot_exclusions:
        gc.make_exclusions_snapshot(args.snapshot_exclusions, out)
        return

    if args.seed is None or args.participants is None:
        raise SystemExit("--seed i --participants su obavezni za --scenario S2 (osim uz --snapshot-exclusions)")

    hint = "python generate_stimuli.py --scenario S2 --snapshot-exclusions <putanja-do-items_S3b.json>"
    forbidden_by_participant = gc.load_exclusions_or_die(out, hint)

    companies = gc.gen_companies(args.seed, count=200)
    for c in companies:
        assert gc.validate_checked_number(c["pib"]), c
        assert gc.validate_checked_number(c["registration_number"]), c

    # Firme sa korenom iz S1_ONLY_ROOTS se NIKAD ne dodeljuju ispitaniku u
    # S2 -- rezervisane su iskljucivo za pominjanje u tekstu S1 recenica
    # (shared/generate_common.py, S1_ONLY_ROOTS). companies.json i dalje
    # sadrzi svih 200 (radi PIB/registration_number konteksta i buduce
    # upotrebe), samo se pool za UZORKOVANJE ovde suzava.
    assignable_companies = [c for c in companies if c["company_name"].split()[0] in gc.S2_S3_ROOTS]

    (out / "companies.json").write_text(
        json.dumps({
            "seed": args.seed,
            "s1_only_roots": gc.S1_ONLY_ROOTS,
            "s2_s3_roots": gc.S2_S3_ROOTS,
            "companies": companies,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    participant_ids = ["DEMO"] + load_participant_codes(args.participants)

    payload = {
        "variant": "S2",
        "seed": args.seed,
        "field_pools": S2_WEIGHT_POOLS,
        "composition": gc.COMPOSITION,
        "practice": s2_gen_practice_items(args.seed, assignable_companies),
        "participants": {},
    }
    total_excluded_reports = []
    for pid in participant_ids:
        forbidden_ids = forbidden_by_participant.get(pid, set())
        if forbidden_ids:
            total_excluded_reports.append((pid, len(forbidden_ids)))
        payload["participants"][pid] = s2_gen_items_for_participant(
            args.seed, pid, assignable_companies, forbidden_ids,
        )

    (out / "items_S2.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
    )

    print(f"OK: {len(companies)} firmi, {len(participant_ids)} ucesnika, seed={args.seed}")
    print(f"Upisano u: {out}")
    if total_excluded_reports:
        n_pid = len(total_excluded_reports)
        avg = sum(c for _, c in total_excluded_reports) / n_pid
        print(f"Iskljucivanje po ucesniku primenjeno za {n_pid} ucesnika "
              f"(prosek {avg:.1f} firmi iskljuceno po ucesniku, iz {out / 'excluded_companies.json'}).")
    else:
        print(f"Iskljucivanje: {out / 'excluded_companies.json'} ucitan, ali nema poklapajucih "
              f"participant_id (S3 i S2 ucesnici se ne poklapaju po imenu?).")


# ==========================================================================
# Scenario S3 -- premesteno bez izmene ponasanja iz
# s3-demo/generate_stimuli.py.
# ==========================================================================

S3_ITEMS_PER_BLOCK = 30
S3_PRACTICE_ITEMS = 8
S3_PRACTICE_N = 3

S3_SUGGESTION_QUOTAS = {
    "true_positive": 0.10,
    "true_negative": 0.65,
    "missed_error": 0.15,
    "false_alarm": 0.10,
}
S3_WARM_UP_FIELDS = 8

S3_MISMATCH_RATE = 0.25

S3_FIELD_WEIGHT = {
    "contract_number": "high",
    "pib": "high",
    "registration_number": "high",
    "company_name": "medium",
    "street": "medium",
    "monthly_fee_per_package": "medium",
    "city": "low",
    "contact_person": "low",
    "street_number": "low",
}

S3_WEIGHT_POOLS = {
    "high": ["contract_number", "pib", "registration_number"],
    "medium": ["company_name", "street", "monthly_fee_per_package"],
    "low": ["city", "contact_person", "street_number"],
}

# Redosled prikaza polja na ugovoru (odgovara rasporedu u
# contract_template.html).
S3_FIELD_DISPLAY_ORDER = [
    "contract_number",
    "company_name",
    "pib",
    "registration_number",
    "city",
    "street",
    "street_number",
    "monthly_fee_per_package",
    "contact_person",
]

S3_CONTEXT_FIELDS = [
    "employee_count",
    "package_count",
    "contract_months",
    "total_monthly_fee",
    "start_date",
    "contact_phone",
]

S3_OPERATOR = {
    "name": "Interlink Telekom d.o.o.",
    "city": "Beograd",
    "street": "Bulevar Zorana Djindjica",
    "street_number": "105",
    "pib": "104778213",
    "registration_number": "20447719",
}


# --------------------------------------------------------------------------
# Sekcija 4: pravila odstupanja po polju. Svaka funkcija vraca vrednost
# razlicitu od one koja joj je data.
# --------------------------------------------------------------------------

def _s3_swap_adjacent_digits(rng: random.Random, digits: str) -> str:
    digits = list(digits)
    positions = list(range(len(digits) - 1))
    rng.shuffle(positions)
    for i in positions:
        if digits[i] != digits[i + 1]:
            digits[i], digits[i + 1] = digits[i + 1], digits[i]
            return "".join(digits)
    # sve cifre iste (degenerisan slucaj): promeni jednu cifru za 1
    digits[0] = str((int(digits[0]) + 1) % 10)
    return "".join(digits)


def s3_distort_contract_number(rng: random.Random, value: str, _company, _all) -> str:
    prefix, year, tail = value.split("-")
    head, visible = tail[0], tail[1:]
    for _ in range(20):
        mode = rng.choice(["digit", "swap"])
        if mode == "digit":
            pos = rng.randrange(len(visible))
            new_digit = str(rng.randint(0, 9))
            new_visible = visible[:pos] + new_digit + visible[pos + 1:]
        else:
            new_visible = _s3_swap_adjacent_digits(rng, visible)
        if new_visible != visible:
            return f"{prefix}-{year}-{head}{new_visible}"
    raise RuntimeError("ne mogu da generisem odstupanje za contract_number")


def s3_distort_digit_pair_swap(rng: random.Random, value: str, _company, _all) -> str:
    for _ in range(20):
        new_value = _s3_swap_adjacent_digits(rng, value)
        if new_value != value:
            return new_value
    raise RuntimeError("ne mogu da generisem odstupanje za brojcano polje")


def s3_distort_company_name(rng: random.Random, value: str, _company, _all) -> str:
    parts = value.split(" ", 1)
    rest = parts[1] if len(parts) > 1 else ""
    other_roots = [r for r in gc.COMPANY_ROOTS if not value.startswith(r + " ")]
    new_root = rng.choice(other_roots)
    return f"{new_root} {rest}".strip()


def s3_distort_street(rng: random.Random, value: str, _company, _all) -> str:
    other = [s for s in gc.STREETS if s != value]
    return rng.choice(other)


def s3_distort_street_number(rng: random.Random, value: str, _company, _all, forbidden=frozenset()) -> str:
    n = int(value)
    candidates = []
    if len(value) >= 2:
        reversed_digits = value[::-1].lstrip("0") or "0"
        candidates.append(int(reversed_digits))
    for delta in (-1, 1, -2, 2, -3, 3):
        candidates.append(n + delta)
    valid = [c for c in candidates if 1 <= c <= 300 and c != n and str(c) not in forbidden]
    if not valid:
        raise RuntimeError("ne mogu da generisem odstupanje za street_number")
    return str(rng.choice(valid))


def s3_distort_city(rng: random.Random, value: str, _company, _all) -> str:
    other = [c for c in gc.CITIES if c != value]
    return rng.choice(other)


def s3_distort_contact_person(rng: random.Random, value: str, _company, all_companies) -> str:
    others = [c["contact_person"] for c in all_companies if c["contact_person"] != value]
    if not others:
        fn = rng.choice(gc.FIRST_NAMES)
        sn = rng.choice(gc.SURNAMES)
        return f"{fn} {sn}"
    return rng.choice(others)


def s3_distort_fee(rng: random.Random, value: int, _company, _all, forbidden=frozenset()) -> int:
    step = 50
    lo, hi = 800, 2400
    for multiplier in range(1, (hi - lo) // step + 1):
        options = []
        down, up = value - step * multiplier, value + step * multiplier
        if down >= lo and down not in forbidden:
            options.append(down)
        if up <= hi and up not in forbidden:
            options.append(up)
        if options:
            return rng.choice(options)
    raise RuntimeError("ne mogu da generisem odstupanje za monthly_fee_per_package")


S3_DISTORTERS = {
    "contract_number": s3_distort_contract_number,
    "pib": s3_distort_digit_pair_swap,
    "registration_number": s3_distort_digit_pair_swap,
    "company_name": s3_distort_company_name,
    "street": s3_distort_street,
    "street_number": s3_distort_street_number,
    "city": s3_distort_city,
    "contact_person": s3_distort_contact_person,
    "monthly_fee_per_package": s3_distort_fee,
}


def s3_make_distinct_distortion(rng, field_name, true_value, company, all_companies, forbidden):
    if field_name == "monthly_fee_per_package":
        return s3_distort_fee(rng, true_value, company, all_companies, forbidden=forbidden)
    if field_name == "street_number":
        return s3_distort_street_number(rng, true_value, company, all_companies, forbidden=forbidden)
    for _ in range(50):
        candidate = S3_DISTORTERS[field_name](rng, true_value, company, all_companies)
        if candidate not in forbidden:
            return candidate
    raise RuntimeError(f"ne mogu da generisem distinct odstupanje za {field_name}")


def s3_build_item(rng: random.Random, item_id: str, company: dict,
                   all_companies: list[dict], n: int) -> dict:
    field_names = gc.choose_fields_for_item(rng, n, gc.COMPOSITION, S3_WEIGHT_POOLS, S3_FIELD_DISPLAY_ORDER)

    printed = dict(company)  # pocinje kao tacna kopija referentnog zapisa
    fields = []

    for order, field_name in enumerate(field_names):
        true_value = company[field_name]
        is_mismatch = rng.random() < S3_MISMATCH_RATE

        if is_mismatch:
            displayed_value = s3_make_distinct_distortion(
                rng, field_name, true_value, company, all_companies,
                forbidden={true_value},
            )
        else:
            displayed_value = true_value

        distractor_value = s3_make_distinct_distortion(
            rng, field_name, true_value, company, all_companies,
            forbidden={true_value, displayed_value},
        )

        printed[field_name] = displayed_value
        if field_name == "monthly_fee_per_package":
            printed["total_monthly_fee"] = printed["package_count"] * displayed_value

        fields.append({
            "field_name": field_name,
            "weight_class": S3_FIELD_WEIGHT[field_name],
            "order": order,
            "true_status": "mismatch" if is_mismatch else "match",
            "reference_value": true_value,
            "displayed_value": displayed_value,
            "distractor_value": distractor_value,
        })

    return {
        "item_id": item_id,
        "company_id": company["company_id"],
        "n_fields": n,
        "printed": printed,
        "reference": dict(company),
        "fields": fields,
    }


def s3_gen_items_for_participant(seed, participant_id, variant, companies, n_items=S3_ITEMS_PER_BLOCK):
    result = {}
    for n in N_LEVELS:
        rng = gc.seeded_rng(seed, participant_id, variant, n)
        block_companies = rng.sample(companies, min(n_items, len(companies)))
        if n_items > len(companies):
            extra = [rng.choice(companies) for _ in range(n_items - len(companies))]
            block_companies.extend(extra)
        items = []
        for i, company in enumerate(block_companies):
            item_id = f"{participant_id}_{variant}_{n}_{i + 1:03d}"
            items.append(s3_build_item(rng, item_id, company, companies, n))
        result[str(n)] = items
    return result


def s3_gen_practice_items(seed, companies):
    rng = gc.seeded_rng(seed, "practice")
    block_companies = rng.sample(companies, S3_PRACTICE_ITEMS)
    items = []
    for i, company in enumerate(block_companies):
        item_id = f"PRACTICE_{i + 1:03d}"
        items.append(s3_build_item(rng, item_id, company, companies, S3_PRACTICE_N))
    return {"n_fields": S3_PRACTICE_N, "items": items}


# --------------------------------------------------------------------------
# Sekcija 5: sugestije modela za S3b.
# --------------------------------------------------------------------------

S3_SUGGESTION_TEXT = {
    "confirm": "Vrednost odgovara referenci.",
    "flag": "Vrednost odstupa od reference. Predlog: {value}",
    "uncertain": "Vrednost izgleda neobicno. Proverite.",
}


def s3_outcome_for_status(true_status: str, is_flag: bool) -> str:
    if true_status == "mismatch":
        return "true_positive" if is_flag else "missed_error"
    return "false_alarm" if is_flag else "true_negative"


def s3_assign_outcomes(rng: random.Random, statuses: list[str]) -> list[str]:
    outcomes = [None] * len(statuses)

    warm_up = min(S3_WARM_UP_FIELDS, len(statuses))
    for i in range(warm_up):
        outcomes[i] = "true_negative" if statuses[i] == "match" else "true_positive"

    rest_idx = list(range(warm_up, len(statuses)))
    match_idx = [i for i in rest_idx if statuses[i] == "match"]
    mismatch_idx = [i for i in rest_idx if statuses[i] == "mismatch"]

    fa_share = S3_SUGGESTION_QUOTAS["false_alarm"] / (
        S3_SUGGESTION_QUOTAS["false_alarm"] + S3_SUGGESTION_QUOTAS["true_negative"]
    )
    missed_share = S3_SUGGESTION_QUOTAS["missed_error"] / (
        S3_SUGGESTION_QUOTAS["missed_error"] + S3_SUGGESTION_QUOTAS["true_positive"]
    )

    rng.shuffle(match_idx)
    n_fa = round(len(match_idx) * fa_share)
    for i in match_idx[:n_fa]:
        outcomes[i] = "false_alarm"
    for i in match_idx[n_fa:]:
        outcomes[i] = "true_negative"

    rng.shuffle(mismatch_idx)
    n_missed = round(len(mismatch_idx) * missed_share)
    for i in mismatch_idx[:n_missed]:
        outcomes[i] = "missed_error"
    for i in mismatch_idx[n_missed:]:
        outcomes[i] = "true_positive"

    return outcomes


def s3_build_suggestions_for_block(rng: random.Random, items: list[dict]) -> list[dict]:
    flat_fields = [(item, field) for item in items for field in item["fields"]]
    statuses = [f["true_status"] for _, f in flat_fields]
    outcomes = s3_assign_outcomes(rng, statuses)

    per_item = {item["item_id"]: [] for item in items}
    for (item, field), outcome in zip(flat_fields, outcomes):
        is_flag = outcome in ("true_positive", "false_alarm")
        suggestion_type = "flag" if is_flag else "confirm"

        if outcome == "true_positive":
            suggested_value = field["reference_value"]
        elif outcome == "false_alarm":
            suggested_value = field["distractor_value"]
        else:
            suggested_value = None

        text = S3_SUGGESTION_TEXT[suggestion_type]
        if suggestion_type == "flag":
            text = text.format(value=suggested_value)

        per_item[item["item_id"]].append({
            "field_name": field["field_name"],
            "order": field["order"],
            "suggestion_type": suggestion_type,
            "text": text,
            "suggested_value": suggested_value,
            "outcome_class": outcome,
        })

    return [
        {"item_id": item["item_id"], "fields": per_item[item["item_id"]]}
        for item in items
    ]


def run_s3(args):
    out = args.out or (EEG_TASKS_ROOT / "s3-demo" / "data")
    out.mkdir(parents=True, exist_ok=True)

    if args.seed is None or args.participants is None:
        raise SystemExit("--seed i --participants su obavezni za --scenario S3")

    companies = gc.gen_companies(args.seed, count=200)

    for c in companies:
        assert gc.validate_checked_number(c["pib"]), c
        assert gc.validate_checked_number(c["registration_number"]), c

    # Firme sa korenom iz S1_ONLY_ROOTS se NIKAD ne dodeljuju ispitaniku u
    # S3 -- rezervisane su iskljucivo za pominjanje u tekstu S1 recenica
    # (shared/generate_common.py, S1_ONLY_ROOTS). companies.json i dalje
    # sadrzi svih 200, samo se pool za UZORKOVANJE ovde suzava.
    assignable_companies = [c for c in companies if c["company_name"].split()[0] in gc.S2_S3_ROOTS]

    (out / "companies.json").write_text(
        json.dumps({
            "seed": args.seed,
            "s1_only_roots": gc.S1_ONLY_ROOTS,
            "s2_s3_roots": gc.S2_S3_ROOTS,
            "companies": companies,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # "DEMO" je dodatni, uvek prisutan ucesnik (pored stvarnih sifri iz
    # participant_codes.json, ucitanih ispod) -- URL rezim
    # ?participant=DEMO&demo=1 i podrazumevane vrednosti u samostalnoj
    # verziji oslanjaju se na njega.
    participant_ids = ["DEMO"] + load_participant_codes(args.participants)

    for variant in ("S3a", "S3b"):
        payload = {
            "variant": variant,
            "seed": args.seed,
            "field_pools": S3_WEIGHT_POOLS,
            "composition": gc.COMPOSITION,
            "practice": s3_gen_practice_items(args.seed, assignable_companies),
            "participants": {},
        }
        for pid in participant_ids:
            payload["participants"][pid] = s3_gen_items_for_participant(
                args.seed, pid, variant, assignable_companies,
            )
        (out / f"items_{variant}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
        )

    # sugestije se racunaju samo za S3b, iz njegovih items
    items_s3b = json.loads((out / "items_S3b.json").read_text(encoding="utf-8"))
    suggestions_payload = {
        "variant": "S3b",
        "seed": args.seed,
        "quotas": S3_SUGGESTION_QUOTAS,
        "warm_up_fields": S3_WARM_UP_FIELDS,
        "model": {
            "source": "template",
            "note": "Tekst sugestija generisan iz sablona (sekcija 5), bez poziva modela.",
        },
        "participants": {},
    }
    for pid in participant_ids:
        rng = gc.seeded_rng(args.seed, pid, "suggestions")
        suggestions_payload["participants"][pid] = {}
        for n in N_LEVELS:
            items = items_s3b["participants"][pid][str(n)]
            suggestions_payload["participants"][pid][str(n)] = s3_build_suggestions_for_block(rng, items)

    (out / "suggestions.json").write_text(
        json.dumps(suggestions_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
    )

    print(f"OK: {len(companies)} firmi, {len(participant_ids)} ispitanika, seed={args.seed}")
    print(f"Upisano u: {out}")


# ==========================================================================
# Scenario S1 -- SPEC_S1_demo.md, korak 2 (redosled izrade). Bez veze
# stavka-firma: items_S1.json ne sadrzi company_id nigde -- disjunktnost
# firmi je resena NA NIVOU BAZE (companies.json s1_only_roots/s2_s3_roots,
# vidi shared/generate_common.py), ne ovde.
# ==========================================================================

# ITEMS_PER_BLOCK ovde NIJE 30 kao u S2/S3: S1-ova stavka zahteva citanje pa
# kucanje N recenica (za razliku od jednog polja u S2/S3), pa realno traje
# znatno duze. Na N=7, sama faza kodiranja (ENCODING_BASE_MS+7*ENCODING_MS_PER_ITEM
# iz SPEC_S1_demo.md 4) je do 31s, plus kucanje sedam recenica -- jedna
# stavka moze trajati minut i vise. Deset stavki po bloku je izdasna
# rezerva za BLOCK_DURATION_MS=180000 (isti obrazac kao S2/S3: visak ne
# smeta, BLOCK_DURATION_MS ionako zaustavlja blok, ne broj generisanih
# stavki). Vrednost je i donja granica koju namece sam fond recenica: uz
# 41 ucesnika i sastav iz 3.2, PO UCESNIKU (nezavisno, ne deljeno sa
# drugima) treba 6*ITEMS_PER_BLOCK recenica niske i isto toliko srednje
# klase (zbir 1+2+3 preko N=3/5/7) -- pri 149 recenica niske klase u fondu,
# ITEMS_PER_BLOCK=10 (60 po ucesniku) ostaje daleko ispod granice; 30 bi je
# probilo (180 > 149).
S1_ITEMS_PER_BLOCK = 10
S1_PRACTICE_N = 3
S1_PRACTICE_ITEMS = 5


def s1_load_sentences_by_class(data_dir: Path) -> dict[str, list[dict]]:
    path = data_dir / "sentences.json"
    if not path.exists():
        raise SystemExit(f"NEDOSTAJE {path} -- pokreni prvo build_sentences.py.")
    records = json.loads(path.read_text(encoding="utf-8"))
    by_class: dict[str, list[dict]] = {"low": [], "medium": [], "high": []}
    for r in records:
        by_class[r["length_class"]].append(r)
    return by_class


def s1_choose_sentences_for_item(rng: random.Random, composition: dict, by_class: dict, used_ids: set) -> list[dict]:
    """Bira recenice za jednu stavku po sastavu iz 3.2 (kljucevi
    "high"/"medium"/"low" u composition[n] odgovaraju length_class), bez
    ijedne vec iskoriscene za ovog ispitanika (used_ids, deljen preko SVIH
    N nivoa te sesije -- 3.3 "unutar sesije", ne samo unutar jednog bloka).

    Balans porekla (uputstvo, tacka E): ako bi ceo izbor za stavku ispao
    iskljucivo jednog porekla (enron ili constructed), jedna recenica (iste
    duzinske klase, da sastav iz 3.2 ostane netaknut) se zamenjuje za
    recenicu suprotnog porekla."""
    chosen = []
    for length_class, count in composition.items():
        available = [s for s in by_class[length_class] if s["id"] not in used_ids]
        if len(available) < count:
            raise SystemExit(
                f"Fond recenica klase '{length_class}' iscrpljen za ovog ispitanika "
                f"(potrebno {count}, dostupno {len(available)}). Smanjiti "
                f"S1_ITEMS_PER_BLOCK ili prosiriti sentences.json."
            )
        chosen.extend(rng.sample(available, count))

    sources = {s["source"] for s in chosen}
    if len(sources) == 1:
        only = next(iter(sources))
        other = "constructed" if only == "enron" else "enron"
        chosen_ids = {s["id"] for s in chosen}
        for idx, s in enumerate(chosen):
            candidates = [
                x for x in by_class[s["length_class"]]
                if x["source"] == other and x["id"] not in used_ids and x["id"] not in chosen_ids
            ]
            if candidates:
                chosen[idx] = rng.choice(candidates)
                break
        # Ako ni jedna klasa nema dostupnu recenicu suprotnog porekla za ovog
        # ispitanika (fond te klase/porekla iscrpljen), stavka ostaje
        # jednog porekla -- ne sme da padne na manje recenica nego sto 3.2
        # trazi. Redak slucaj pri velikom broju vec iskoriscenih recenica;
        # ne prijavljuje se kao greska, samo se ne postize balans za TU stavku.

    for s in chosen:
        used_ids.add(s["id"])
    rng.shuffle(chosen)
    return chosen


def s1_build_item(item_id: str, sentences: list[dict], n: int) -> dict:
    return {
        "item_id": item_id,
        "n_sentences": n,
        "sentences": [
            {
                "sentence_index": i + 1,
                "sentence_id": s["id"],
                "text": s["text"],
                "length_class": s["length_class"],
                "source": s["source"],
                "is_question": s["is_question"],
            }
            for i, s in enumerate(sentences)
        ],
    }


def s1_gen_items_for_participant(seed, participant_id, by_class, n_items=S1_ITEMS_PER_BLOCK):
    result = {}
    used_ids: set = set()  # deljeno preko SVIH N nivoa -- 3.3, disjunktnost "unutar sesije"
    for n in N_LEVELS:
        rng = gc.seeded_rng(seed, participant_id, "S1", n)
        composition = gc.COMPOSITION[n]
        items = []
        for i in range(n_items):
            item_id = f"{participant_id}_S1_{n}_{i + 1:03d}"
            sentences = s1_choose_sentences_for_item(rng, composition, by_class, used_ids)
            items.append(s1_build_item(item_id, sentences, n))
        result[str(n)] = items
    return result


def s1_gen_practice_items(seed, by_class):
    rng = gc.seeded_rng(seed, "practice_s1")
    used_ids: set = set()
    composition = gc.COMPOSITION[S1_PRACTICE_N]
    items = []
    for i in range(S1_PRACTICE_ITEMS):
        item_id = f"PRACTICE_S1_{i + 1:03d}"
        sentences = s1_choose_sentences_for_item(rng, composition, by_class, used_ids)
        items.append(s1_build_item(item_id, sentences, S1_PRACTICE_N))
    return {"n_fields": S1_PRACTICE_N, "items": items}


def run_s1(args):
    out = args.out or (EEG_TASKS_ROOT / "data")
    out.mkdir(parents=True, exist_ok=True)

    if args.seed is None or args.participants is None:
        raise SystemExit("--seed i --participants su obavezni za --scenario S1")

    by_class = s1_load_sentences_by_class(out)
    for cls, items in by_class.items():
        print(f"  fond recenica '{cls}': {len(items)}")

    participant_ids = ["DEMO"] + load_participant_codes(args.participants)

    payload = {
        "variant": "S1",
        "seed": args.seed,
        "composition": gc.COMPOSITION,
        "practice": s1_gen_practice_items(args.seed, by_class),
        "participants": {},
    }
    for pid in participant_ids:
        payload["participants"][pid] = s1_gen_items_for_participant(args.seed, pid, by_class)

    (out / "items_S1.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
    )

    print(f"OK: {len(participant_ids)} ucesnika, seed={args.seed}")
    print(f"Upisano u: {out}")


# ==========================================================================
# main
# ==========================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=["S1", "S2", "S3"], required=True)
    ap.add_argument("--seed", type=int,
                     help="Za S2 MORA biti isti --seed kao za --scenario S3 da bi baza firmi "
                          "ostala identicna (ista gen_companies() nad istim seed-om). "
                          "Obavezno osim uz --snapshot-exclusions.")
    ap.add_argument("--participants", type=int,
                     help="Obavezno osim uz --snapshot-exclusions.")
    ap.add_argument("--out", type=Path,
                     help="Podrazumevano: data/ za S1 (zajednicko), s2-demo/data odn. "
                          "s3-demo/data za S2/S3, u odnosu na ovaj fajl.")
    ap.add_argument("--snapshot-exclusions", type=Path, nargs="+", metavar="ITEMS_JSON",
                     help="Samo za --scenario S2. Jednokratna radnja: procitaj jedan ili vise "
                          "items_*.json (vec generisanih scenarija) i upisi "
                          "data/excluded_companies.json, pa izadji BEZ generisanja items_S2.json.")
    args = ap.parse_args()

    if args.scenario == "S2":
        run_s2(args)
    elif args.scenario == "S3":
        run_s3(args)
    else:
        run_s1(args)


if __name__ == "__main__":
    main()
