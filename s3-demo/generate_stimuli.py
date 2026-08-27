"""Generise sintetican materijal za demonstrator Scenarija 3: firme, nacrte
ugovora (stavke za proveru) i unapred izracunate sugestije modela.

Sve je deterministicko za dati --seed. Pokretanje:

    python generate_stimuli.py --seed 20260825 --participants 40

Izlazi u data/: companies.json, items_S3a.json, items_S3b.json,
suggestions.json. contract_template.html se ne generise, pise se rucno.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

# --------------------------------------------------------------------------
# Parametri koji se podesavaju u pilotu (drzati na jednom mestu, sekcija 5).
# --------------------------------------------------------------------------

ITEMS_PER_BLOCK = 30          # dovoljno da pokrije BLOCK_DURATION_MS=180000
PRACTICE_ITEMS = 8
PRACTICE_N = 3

SUGGESTION_QUOTAS = {
    # udeo od SVIH polja u S3b bloku, sekcija 5
    "true_positive": 0.10,
    "true_negative": 0.65,
    "missed_error": 0.15,
    "false_alarm": 0.10,
}
WARM_UP_FIELDS = 8             # prvih 8 polja po sesiji: samo TP/TN (sekcija 5)

MISMATCH_RATE = 0.25           # udeo polja sa odstupanjem, sekcija 4

N_LEVELS = (3, 5, 7)

# --------------------------------------------------------------------------
# Klase tezine i sastav stavki (sekcija 3.3, 3.4).
#
# Napomena o odstupanju od tabele u uputstvu: originalna tabela u 3.3 spaja
# "street" i "street_number" u jedno polje srednje tezine, sto ostavlja samo
# dva polja niske tezine (city, contact_person) -- nedovoljno za N=7, koje
# trazi tri polja niske tezine. Sekcija 4 ionako vec tretira street i
# street_number kao dva odvojena polja sa odvojenim pravilima odstupanja, pa
# su ovde razdvojena i u klasifikaciji: street ostaje srednje, street_number
# prelazi u nisku tezinu. Time se dobija 3/3/3 raspored koji tacno pokriva
# N=7 bez uvodjenja ijednog novog polja. Videti README.md.
# --------------------------------------------------------------------------

FIELD_WEIGHT = {
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

WEIGHT_POOLS = {
    "high": ["contract_number", "pib", "registration_number"],
    "medium": ["company_name", "street", "monthly_fee_per_package"],
    "low": ["city", "contact_person", "street_number"],
}

COMPOSITION = {
    3: {"high": 1, "medium": 1, "low": 1},
    5: {"high": 1, "medium": 2, "low": 2},
    7: {"high": 1, "medium": 3, "low": 3},
}

# Redosled prikaza polja na ugovoru (sta god je izabrano za stavku, filtrira
# se ovim redosledom -- odgovara rasporedu u contract_template.html).
FIELD_DISPLAY_ORDER = [
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

CONTEXT_FIELDS = [
    "employee_count",
    "package_count",
    "contract_months",
    "total_monthly_fee",
    "start_date",
    "contact_phone",
]

# --------------------------------------------------------------------------
# Fiksne liste za sintetičku bazu firmi (sekcija 3.1).
# --------------------------------------------------------------------------

COMPANY_ROOTS = [
    "Vega", "Panonija", "Delta", "Morava", "Kolubara",
    "Zenit", "Sirmium", "Timok", "Avala", "Karpat",
]
COMPANY_NOUNS = [
    "Logistika", "Trejd", "Komerc", "Grupa", "Sistemi",
    "Inzenjering", "Distribucija", "Konsalting", "Tehnologije",
    "Promet", "Agrar", "Trans",
]
LEGAL_FORMS = ["d.o.o.", "a.d.", "o.d."]

CITIES = [
    "Beograd", "Novi Sad", "Nis", "Kragujevac", "Subotica", "Zrenjanin",
    "Pancevo", "Cacak", "Kraljevo", "Novi Pazar", "Smederevo", "Leskovac",
    "Valjevo", "Krusevac", "Vranje", "Sabac", "Sombor", "Pozarevac",
    "Pirot", "Zajecar",
]

STREETS = [
    "Kneza Milosa", "Kralja Petra I", "Cara Dusana", "Njegoseva",
    "Balkanska", "Vojvode Stepe", "Bulevar Oslobodjenja",
    "Ilije Garasanina", "Save Kovacevica", "Zmaj Jovina", "Dunavska",
    "Moravska", "Rade Koncara", "Djure Jaksica", "Branka Radicevica",
    "Vuka Karadzica", "Milosa Obilica", "Cvijiceva", "Gunduliceva",
    "Studentski trg", "Takovska", "Kosovska", "Nemanjina", "Resavska",
    "Bulevar Kralja Aleksandra", "Ustanicka", "Vojislava Ilica",
    "Mije Kovacevica", "Patrijarha Dimitrija", "Radoja Dakica",
    "Milentija Popovica", "Jurija Gagarina", "Kraljice Marije",
    "Despota Stefana", "Karadjordjeva", "Svetogorska", "Makedonska",
    "Kosovke Devojke", "Vojvode Misica", "Bulevar Evrope",
]

FIRST_NAMES = [
    "Marko", "Nikola", "Stefan", "Aleksandar", "Milos", "Petar",
    "Nemanja", "Vladimir", "Dusan", "Ivan", "Jovana", "Ana", "Milica",
    "Jelena", "Tamara", "Marija", "Sofija", "Katarina", "Teodora",
    "Ivana", "Sara", "Natasa", "Dragana", "Snezana", "Bojan",
]
SURNAMES = [
    "Jovanovic", "Petrovic", "Nikolic", "Markovic", "Djordjevic",
    "Stojanovic", "Ilic", "Stankovic", "Pavlovic", "Milosevic",
    "Todorovic", "Ristic", "Simic", "Kovacevic", "Popovic", "Kostic",
    "Vasic", "Djuric", "Mitrovic", "Radovanovic", "Lukic", "Savic",
    "Antic", "Obradovic", "Vukovic",
]

OPERATOR = {
    "name": "Interlink Telekom d.o.o.",
    "city": "Beograd",
    "street": "Bulevar Zorana Djindjica",
    "street_number": "105",
    "pib": "104778213",
    "registration_number": "20447719",
}


# --------------------------------------------------------------------------
# Kontrolne cifre, ISO 7064 MOD 11,10 (cist sistem).
# --------------------------------------------------------------------------

def mod_11_10_check_digit(base_digits: str) -> int:
    p = 10
    for ch in base_digits:
        d = int(ch)
        s = (d + p) % 10
        if s == 0:
            s = 10
        p = (s * 2) % 11
    return (11 - p) % 10


def make_checked_number(rng: random.Random, base_len: int) -> str:
    base = "".join(str(rng.randint(0, 9)) for _ in range(base_len))
    if base[0] == "0":
        base = str(rng.randint(1, 9)) + base[1:]
    check = mod_11_10_check_digit(base)
    return base + str(check)


def validate_checked_number(full_digits: str) -> bool:
    base, check = full_digits[:-1], full_digits[-1]
    return mod_11_10_check_digit(base) == int(check)


def seeded_rng(*parts) -> random.Random:
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return random.Random(digest)


# --------------------------------------------------------------------------
# Sekcija 3.1 / 3.2: firme.
# --------------------------------------------------------------------------

def gen_companies(seed: int, count: int = 200) -> list[dict]:
    rng = seeded_rng(seed, "companies")

    name_combos = [
        f"{root} {noun} {form}"
        for root in COMPANY_ROOTS
        for noun in COMPANY_NOUNS
        for form in LEGAL_FORMS
    ]
    rng.shuffle(name_combos)
    if count > len(name_combos):
        raise ValueError("nedovoljno kombinacija za jedinstvena imena firmi")
    names = name_combos[:count]

    person_combos = [f"{fn} {sn}" for fn in FIRST_NAMES for sn in SURNAMES]
    rng.shuffle(person_combos)

    used_pib = set()
    used_reg = set()
    used_contract_no = set()

    companies = []
    for i in range(count):
        company_id = f"C{i + 1:03d}"

        pib = make_checked_number(rng, 8)
        while pib in used_pib:
            pib = make_checked_number(rng, 8)
        used_pib.add(pib)

        reg = make_checked_number(rng, 7)
        while reg in used_reg:
            reg = make_checked_number(rng, 7)
        used_reg.add(reg)

        contract_tail = f"{rng.randint(0, 99999):05d}"
        while contract_tail in used_contract_no:
            contract_tail = f"{rng.randint(0, 99999):05d}"
        used_contract_no.add(contract_tail)
        contract_number = f"TK-2026-{contract_tail}"

        city = rng.choice(CITIES)
        street = rng.choice(STREETS)
        street_number = str(rng.randint(1, 150))

        contact_person = person_combos[i % len(person_combos)]
        contact_phone = (
            f"06{rng.randint(0, 9)}"
            f"{rng.randint(0, 999):03d}"
            f"{rng.randint(0, 9999):04d}"
        )

        employee_count = rng.randint(8, 240)
        package_factor = rng.uniform(0.8, 1.2)
        package_count = max(1, round(employee_count * package_factor))
        monthly_fee_per_package = rng.randint(16, 48) * 50  # 800..2400 / 50
        contract_months = rng.choice([12, 24, 36])
        total_monthly_fee = package_count * monthly_fee_per_package
        start_month = rng.randint(1, 12)
        start_day = rng.randint(1, 28)
        start_date = f"2026-{start_month:02d}-{start_day:02d}"

        companies.append({
            "company_id": company_id,
            "company_name": names[i],
            "pib": pib,
            "registration_number": reg,
            "city": city,
            "street": street,
            "street_number": street_number,
            "contact_person": contact_person,
            "contact_phone": contact_phone,
            "employee_count": employee_count,
            "contract_number": contract_number,
            "package_count": package_count,
            "monthly_fee_per_package": monthly_fee_per_package,
            "contract_months": contract_months,
            "total_monthly_fee": total_monthly_fee,
            "start_date": start_date,
        })

    return companies


# --------------------------------------------------------------------------
# Sekcija 4: pravila odstupanja po polju. Svaka funkcija vraca vrednost
# razlicitu od one koja joj je data.
# --------------------------------------------------------------------------

def _swap_adjacent_digits(rng: random.Random, digits: str) -> str:
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


def distort_contract_number(rng: random.Random, value: str, _company, _all) -> str:
    # Prikaz (sekcija 3.5) skraćuje broj ugovora na poslednje 4 cifre --
    # prva cifra petocifrenog dela se nikad ne prikazuje. Odstupanje mora
    # da pogodi jednu od te 4 vidljive cifre, inace bi izmena bila nevidljiva
    # na ekranu iako je logicki "mismatch" u pozadini.
    prefix, year, tail = value.split("-")
    head, visible = tail[0], tail[1:]
    for _ in range(20):
        mode = rng.choice(["digit", "swap"])
        if mode == "digit":
            pos = rng.randrange(len(visible))
            new_digit = str(rng.randint(0, 9))
            new_visible = visible[:pos] + new_digit + visible[pos + 1:]
        else:
            new_visible = _swap_adjacent_digits(rng, visible)
        if new_visible != visible:
            return f"{prefix}-{year}-{head}{new_visible}"
    raise RuntimeError("ne mogu da generisem odstupanje za contract_number")


def distort_digit_pair_swap(rng: random.Random, value: str, _company, _all) -> str:
    for _ in range(20):
        new_value = _swap_adjacent_digits(rng, value)
        if new_value != value:
            return new_value
    raise RuntimeError("ne mogu da generisem odstupanje za brojcano polje")


def distort_company_name(rng: random.Random, value: str, _company, _all) -> str:
    parts = value.split(" ", 1)
    rest = parts[1] if len(parts) > 1 else ""
    other_roots = [r for r in COMPANY_ROOTS if not value.startswith(r + " ")]
    new_root = rng.choice(other_roots)
    return f"{new_root} {rest}".strip()


def distort_street(rng: random.Random, value: str, _company, _all) -> str:
    other = [s for s in STREETS if s != value]
    return rng.choice(other)


def distort_street_number(rng: random.Random, value: str, _company, _all, forbidden=frozenset()) -> str:
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


def distort_city(rng: random.Random, value: str, _company, _all) -> str:
    other = [c for c in CITIES if c != value]
    return rng.choice(other)


def distort_contact_person(rng: random.Random, value: str, _company, all_companies) -> str:
    others = [c["contact_person"] for c in all_companies if c["contact_person"] != value]
    if not others:
        fn = rng.choice(FIRST_NAMES)
        sn = rng.choice(SURNAMES)
        return f"{fn} {sn}"
    return rng.choice(others)


def distort_fee(rng: random.Random, value: int, _company, _all, forbidden=frozenset()) -> int:
    step = 50
    lo, hi = 800, 2400
    # standardno: jedan korak od 50 dinara (sekcija 4). Ako oba jednokoracna
    # kandidata upadnu u zabranjeni skup (redak granicni slucaj blizu 800
    # ili 2400 RSD kada je isti korak vec iskoriscen za displayed_value),
    # sirimo pretragu na visestruke korake, i dalje unutar opsega.
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


DISTORTERS = {
    "contract_number": distort_contract_number,
    "pib": distort_digit_pair_swap,
    "registration_number": distort_digit_pair_swap,
    "company_name": distort_company_name,
    "street": distort_street,
    "street_number": distort_street_number,
    "city": distort_city,
    "contact_person": distort_contact_person,
    "monthly_fee_per_package": distort_fee,
}


def make_distinct_distortion(rng, field_name, true_value, company, all_companies, forbidden):
    if field_name == "monthly_fee_per_package":
        return distort_fee(rng, true_value, company, all_companies, forbidden=forbidden)
    if field_name == "street_number":
        return distort_street_number(rng, true_value, company, all_companies, forbidden=forbidden)
    for _ in range(50):
        candidate = DISTORTERS[field_name](rng, true_value, company, all_companies)
        if candidate not in forbidden:
            return candidate
    raise RuntimeError(f"ne mogu da generisem distinct odstupanje za {field_name}")


# --------------------------------------------------------------------------
# Sekcija 3.4 / 4: konstrukcija jedne stavke.
# --------------------------------------------------------------------------

def choose_fields_for_item(rng: random.Random, n: int) -> list[str]:
    comp = COMPOSITION[n]
    chosen = []
    for weight, count in comp.items():
        pool = WEIGHT_POOLS[weight]
        chosen.extend(rng.sample(pool, count))
    # poredjaj po rasporedu prikaza na ugovoru
    order_index = {f: i for i, f in enumerate(FIELD_DISPLAY_ORDER)}
    chosen.sort(key=lambda f: order_index[f])
    return chosen


def build_item(rng: random.Random, item_id: str, company: dict,
                all_companies: list[dict], n: int) -> dict:
    field_names = choose_fields_for_item(rng, n)

    printed = dict(company)  # pocinje kao tacna kopija referentnog zapisa
    fields = []

    for order, field_name in enumerate(field_names):
        true_value = company[field_name]
        is_mismatch = rng.random() < MISMATCH_RATE

        if is_mismatch:
            displayed_value = make_distinct_distortion(
                rng, field_name, true_value, company, all_companies,
                forbidden={true_value},
            )
        else:
            displayed_value = true_value

        distractor_value = make_distinct_distortion(
            rng, field_name, true_value, company, all_companies,
            forbidden={true_value, displayed_value},
        )

        printed[field_name] = displayed_value
        if field_name == "monthly_fee_per_package":
            # total_monthly_fee mora ostati interno konzistentan sa onim sto
            # je odstampano na ugovoru, inace bi se odstupanje moglo otkriti
            # deljenjem total_monthly_fee / package_count umesto pamcenjem.
            printed["total_monthly_fee"] = printed["package_count"] * displayed_value

        fields.append({
            "field_name": field_name,
            "weight_class": FIELD_WEIGHT[field_name],
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


def gen_items_for_participant(seed, participant_id, variant, companies, n_items=ITEMS_PER_BLOCK):
    result = {}
    for n in N_LEVELS:
        rng = seeded_rng(seed, participant_id, variant, n)
        block_companies = rng.sample(companies, min(n_items, len(companies)))
        if n_items > len(companies):
            extra = [rng.choice(companies) for _ in range(n_items - len(companies))]
            block_companies.extend(extra)
        items = []
        for i, company in enumerate(block_companies):
            item_id = f"{participant_id}_{variant}_{n}_{i + 1:03d}"
            items.append(build_item(rng, item_id, company, companies, n))
        result[str(n)] = items
    return result


def gen_practice_items(seed, companies):
    rng = seeded_rng(seed, "practice")
    block_companies = rng.sample(companies, PRACTICE_ITEMS)
    items = []
    for i, company in enumerate(block_companies):
        item_id = f"PRACTICE_{i + 1:03d}"
        items.append(build_item(rng, item_id, company, companies, PRACTICE_N))
    return {"n_fields": PRACTICE_N, "items": items}


# --------------------------------------------------------------------------
# Sekcija 5: sugestije modela za S3b.
# --------------------------------------------------------------------------

SUGGESTION_TEXT = {
    "confirm": "Vrednost odgovara referenci.",
    "flag": "Vrednost odstupa od reference. Predlog: {value}",
    "uncertain": "Vrednost izgleda neobicno. Proverite.",
}


def outcome_for_status(true_status: str, is_flag: bool) -> str:
    if true_status == "mismatch":
        return "true_positive" if is_flag else "missed_error"
    return "false_alarm" if is_flag else "true_negative"


def assign_outcomes(rng: random.Random, statuses: list[str]) -> list[str]:
    """statuses: 'match'/'mismatch' po redosledu polja u bloku (svi item-i
    nadovezani). Prvih WARM_UP_FIELDS su prisilno confirm/tacan flag
    (true_positive ili true_negative). Ostatak se raspodeljuje da pogodi
    ciljane udele iz SUGGESTION_QUOTAS koliko je moguce sa celobrojnim
    brojem polja."""
    outcomes = [None] * len(statuses)

    warm_up = min(WARM_UP_FIELDS, len(statuses))
    for i in range(warm_up):
        outcomes[i] = "true_negative" if statuses[i] == "match" else "true_positive"

    rest_idx = list(range(warm_up, len(statuses)))
    match_idx = [i for i in rest_idx if statuses[i] == "match"]
    mismatch_idx = [i for i in rest_idx if statuses[i] == "mismatch"]

    fa_share = SUGGESTION_QUOTAS["false_alarm"] / (
        SUGGESTION_QUOTAS["false_alarm"] + SUGGESTION_QUOTAS["true_negative"]
    )
    missed_share = SUGGESTION_QUOTAS["missed_error"] / (
        SUGGESTION_QUOTAS["missed_error"] + SUGGESTION_QUOTAS["true_positive"]
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


def build_suggestions_for_block(rng: random.Random, items: list[dict]) -> list[dict]:
    flat_fields = [(item, field) for item in items for field in item["fields"]]
    statuses = [f["true_status"] for _, f in flat_fields]
    outcomes = assign_outcomes(rng, statuses)

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

        text = SUGGESTION_TEXT[suggestion_type]
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


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--participants", type=int, required=True)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    companies = gen_companies(args.seed, count=200)

    # provera kontrolnih cifara pre pisanja bilo cega
    for c in companies:
        assert validate_checked_number(c["pib"]), c
        assert validate_checked_number(c["registration_number"]), c

    (args.out / "companies.json").write_text(
        json.dumps({"seed": args.seed, "companies": companies}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # "DEMO" je dodatni, uvek prisutan ucesnik (pored P01..PNN) -- URL rezim
    # ?participant=DEMO&demo=1 (sekcija 9) i podrazumevane vrednosti u
    # samostalnoj verziji (build_standalone.py) oslanjaju se na njega.
    participant_ids = ["DEMO"] + [f"P{i + 1:02d}" for i in range(args.participants)]

    for variant in ("S3a", "S3b"):
        payload = {
            "variant": variant,
            "seed": args.seed,
            "field_pools": WEIGHT_POOLS,
            "composition": COMPOSITION,
            "practice": gen_practice_items(args.seed, companies),
            "participants": {},
        }
        for pid in participant_ids:
            payload["participants"][pid] = gen_items_for_participant(
                args.seed, pid, variant, companies,
            )
        (args.out / f"items_{variant}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
        )

    # sugestije se racunaju samo za S3b, iz njegovih items
    items_s3b = json.loads((args.out / "items_S3b.json").read_text(encoding="utf-8"))
    suggestions_payload = {
        "variant": "S3b",
        "seed": args.seed,
        "quotas": SUGGESTION_QUOTAS,
        "warm_up_fields": WARM_UP_FIELDS,
        "model": {
            "source": "template",
            "note": "Tekst sugestija generisan iz sablona (sekcija 5), bez poziva modela.",
        },
        "participants": {},
    }
    for pid in participant_ids:
        rng = seeded_rng(args.seed, pid, "suggestions")
        suggestions_payload["participants"][pid] = {}
        for n in N_LEVELS:
            items = items_s3b["participants"][pid][str(n)]
            suggestions_payload["participants"][pid][str(n)] = build_suggestions_for_block(rng, items)

    (args.out / "suggestions.json").write_text(
        json.dumps(suggestions_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
    )

    print(f"OK: {len(companies)} firmi, {len(participant_ids)} ispitanika, seed={args.seed}")
    print(f"Upisano u: {args.out}")


if __name__ == "__main__":
    main()
