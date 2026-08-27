"""Generise sintetican materijal za demonstrator Scenarija 2: firme i stavke
za prenosenje podataka izmedju dva prozora (dokument -> tabela, po secanju).

Sve je deterministicko za dati --seed. Pokretanje (posle jednokratnog
snimka iskljucivanja, videti nize):

    python generate_stimuli_s2.py --seed 20260825 --participants 40

Izlazi u data/: companies.json, items_S2.json.

Baza firmi je NAMERNO bajt-identicna bazi iz s3-demo (isti generator, iste
fiksne liste, isti --seed) -- videti gen_companies() nize i README.md,
odeljak "Zajednicka baza firmi sa Scenarijem 3". To je preduslov za
iskljucivanje po company_id: ima smisla samo ako "C047" oznacava istu
firmu u oba projekta. Baza se GENERISE ovde, iz istog seed-a -- ne cita se
iz s3-demo-a.

Iskljucivanje firmi vec vidjenih u S3 (sekcija 3) se NE racuna direktno iz
s3-demo-a na svakom pokretanju. Umesto toga, prvo se JEDNOM napravi lokalni
snimak:

    python generate_stimuli_s2.py --snapshot-exclusions ../s3-demo/data/items_S3b.json

Ovo upisuje data/excluded_companies.json i vise se ne dodiruje s3-demo.
Svaki naredni (normalan) poziv generate_stimuli_s2.py cita iskljucivo taj
lokalni snimak; ako ne postoji, skript prekida sa jasnom porukom umesto da
tiho generise bez iskljucivanja.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

# --------------------------------------------------------------------------
# Parametri koji se podesavaju u pilotu (drzati na jednom mestu, sekcija 7
# uputstva S2 + README).
# --------------------------------------------------------------------------

ITEMS_PER_BLOCK = 30    # generisano unapred po ucesniku/N; stvarno odradjenih
                        # po bloku je mnogo manje (vidi README -- stavke u S2
                        # traju znatno duze od S3 zbog kucanja i prebacivanja),
                        # ali visak ne smeta, samo osigurava da blok ne
                        # "ostane bez stavki" pre isteka BLOCK_DURATION_MS.
PRACTICE_ITEMS = 5
PRACTICE_N = 3

N_LEVELS = (3, 5, 7)

# --------------------------------------------------------------------------
# Klase tezine i sastav stavke (sekcija 3.1, 3.2 uputstva).
#
# Napomena o odstupanju od tabele u 3.1 -- isti problem i isto resenje kao u
# s3-demo/generate_stimuli.py (videti tamosnji README, odeljak
# "Odstupanja od uputstva"). Tabela u 3.1 spaja "street" i "street_number" u
# JEDNO polje srednje tezine. Sa time bi klasa niske tezine imala samo DVA
# polja (city, contact_person), sto nije dovoljno za sastav N=7 iz tabele
# 3.2, koja trazi TRI polja niske tezine. Zato je street_number ovde,
# identicno kao u s3-demo, izdvojen kao SVOJE polje niske tezine (broj bez
# znacenja, kratak, lako se pamti pogresno) dok street ostaje srednje
# (tekst). Rezultat: 2 visoka / 3 srednja / 3 niska polja, sto tacno
# pokriva N=3/5/7 (visoka je uvek tacno 1, pa je dovoljno da pool ima >=1).
# --------------------------------------------------------------------------

FIELD_WEIGHT = {
    "pib": "high",
    "registration_number": "high",
    "company_name": "medium",
    "street": "medium",
    "contact_phone": "medium",
    "city": "low",
    "contact_person": "low",
    "street_number": "low",
}

WEIGHT_POOLS = {
    "high": ["pib", "registration_number"],
    "medium": ["company_name", "street", "contact_phone"],
    "low": ["city", "contact_person", "street_number"],
}

COMPOSITION = {
    3: {"high": 1, "medium": 1, "low": 1},
    5: {"high": 1, "medium": 2, "low": 2},
    7: {"high": 1, "medium": 3, "low": 3},
}

# Redosled prikaza polja na dokumentu (sta god je izabrano za stavku,
# filtrira se ovim redosledom -- odgovara rasporedu u document_template.html).
FIELD_DISPLAY_ORDER = [
    "company_name",
    "pib",
    "registration_number",
    "city",
    "street",
    "street_number",
    "contact_person",
    "contact_phone",
]

# --------------------------------------------------------------------------
# Fiksne liste za sintetičku bazu firmi. Bajt-identicne s3-demo/generate_stimuli.py
# (isti nizovi, isti redosled) -- namerno, videti napomenu uz gen_companies().
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


# --------------------------------------------------------------------------
# Kontrolne cifre, ISO 7064 MOD 11,10 (cist sistem) -- identicno s3-demo.
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


def sha256_of_file(path: Path) -> str:
    """Isti format kao app/task.js (bufToHashHex): 'sha256:' + hex, nad
    sirovim bajtovima fajla."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Baza firmi. NAMERNO bajt-identicna funkcija kao gen_companies() u
# s3-demo/generate_stimuli.py -- ukljucujuci polja koja S2 uopste ne
# koristi (contract_number, employee_count, package_count,
# monthly_fee_per_package, contract_months, total_monthly_fee, start_date).
# Razlog: rng.* pozivi za ta polja se desavaju IZMEDJU poziva za polja koja
# S2 deli sa S3 (pib, registration_number, city, street, street_number,
# contact_phone...). Da su izbacena, redosled povlacenja iz rng bi se
# pomerio i firma "C047" vise ne bi bila ista u oba projekta za isti seed.
# Umesto da se ovo rizikuje suptilnom razlikom u redosledu, funkcija je
# ovde prepisana 1:1 i visak polja se posle prosto ignorise (S2 uzima samo
# FIELD_DISPLAY_ORDER podskup u build_item()).
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
        contract_number = f"TK-2026-{contract_tail}"  # neiskorisceno u S2, drzi rng redosled identicnim S3-u

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
        monthly_fee_per_package = rng.randint(16, 48) * 50
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
            # polja ispod ne koristi S2 -- drzana radi identicnog rng redosleda sa S3
            "employee_count": employee_count,
            "contract_number": contract_number,
            "package_count": package_count,
            "monthly_fee_per_package": monthly_fee_per_package,
            "contract_months": contract_months,
            "total_monthly_fee": total_monthly_fee,
            "start_date": start_date,
        })

    return companies


def s2_view(company: dict) -> dict:
    """Podskup polja koja S2 stvarno koristi, u FIELD_DISPLAY_ORDER."""
    return {k: company[k] for k in FIELD_DISPLAY_ORDER}


# --------------------------------------------------------------------------
# Sastav jedne stavke (sekcija 3.2).
# --------------------------------------------------------------------------

def choose_fields_for_item(rng: random.Random, n: int) -> list[str]:
    comp = COMPOSITION[n]
    chosen = []
    for weight, count in comp.items():
        pool = WEIGHT_POOLS[weight]
        chosen.extend(rng.sample(pool, count))
    order_index = {f: i for i, f in enumerate(FIELD_DISPLAY_ORDER)}
    chosen.sort(key=lambda f: order_index[f])
    return chosen


def build_item(rng: random.Random, item_id: str, company: dict, n: int) -> dict:
    field_names = choose_fields_for_item(rng, n)
    document = s2_view(company)

    fields = []
    for order, field_name in enumerate(field_names):
        fields.append({
            "field_name": field_name,
            "weight_class": FIELD_WEIGHT[field_name],
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


def gen_items_for_participant(seed, participant_id, companies, forbidden_ids, n_items=ITEMS_PER_BLOCK):
    result = {}
    available = [c for c in companies if c["company_id"] not in forbidden_ids]
    for n in N_LEVELS:
        rng = seeded_rng(seed, participant_id, "S2", n)
        pool = available if available else companies  # fallback ako je iskljucivanje obrisalo sve (ne bi trebalo da se desi na 200 firmi)
        block_companies = rng.sample(pool, min(n_items, len(pool)))
        if n_items > len(pool):
            extra = [rng.choice(pool) for _ in range(n_items - len(pool))]
            block_companies.extend(extra)
        items = []
        for i, company in enumerate(block_companies):
            item_id = f"{participant_id}_S2_{n}_{i + 1:03d}"
            items.append(build_item(rng, item_id, company, n))
        result[str(n)] = items
    return result


def gen_practice_items(seed, companies):
    rng = seeded_rng(seed, "practice_s2")
    block_companies = rng.sample(companies, PRACTICE_ITEMS)
    items = []
    for i, company in enumerate(block_companies):
        item_id = f"PRACTICE_S2_{i + 1:03d}"
        items.append(build_item(rng, item_id, company, PRACTICE_N))
    return {"n_fields": PRACTICE_N, "items": items}


# --------------------------------------------------------------------------
# Iskljucivanje firmi vec vidjenih u S3 (istom ucesniku), sekcija 3.
#
# Ovo je JEDINO mesto u ovom skriptu koje ikad dodiruje ../s3-demo, i to
# samo kad se eksplicitno pozove --snapshot-exclusions. Rezultat se upisuje
# JEDNOM u data/excluded_companies.json; svaki naredni (normalan) poziv
# generate_stimuli_s2.py cita ISKLJUCIVO taj fajl, unutar sopstvenog data/
# foldera -- nema vise runtime zavisnosti od drugog projekta.
# --------------------------------------------------------------------------

def build_exclusions_from_items_s3b(source_path: Path) -> dict:
    """Cita items_S3b.json i vraca payload za excluded_companies.json:
    {participant_id: [company_id, ...]}, unija preko sva tri N (S3b
    sempluje po N nezavisno, pa se firma moze ponoviti izmedju N=3/5/7
    istog ucesnika i u samom S3b)."""
    if not source_path.exists():
        raise SystemExit(f"NE POSTOJI {source_path} -- ne mogu da napravim snimak iskljucivanja.")
    data = json.loads(source_path.read_text(encoding="utf-8"))
    forbidden = {}
    for pid, by_n in data.get("participants", {}).items():
        ids = set()
        for n, items in by_n.items():
            for item in items:
                ids.add(item["company_id"])
        forbidden[pid] = sorted(ids)
    return {
        "source_file": str(source_path),
        "source_hash": sha256_of_file(source_path),
        "participants": forbidden,
    }


def make_exclusions_snapshot(source_path: Path, out_dir: Path) -> Path:
    payload = build_exclusions_from_items_s3b(source_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "excluded_companies.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    n_pid = len(payload["participants"])
    avg = sum(len(v) for v in payload["participants"].values()) / n_pid if n_pid else 0
    print(f"OK: {out_path} ({n_pid} ucesnika, prosek {avg:.1f} iskljucenih firmi po ucesniku)")
    print(f"Izvor: {source_path} ({payload['source_hash']})")
    return out_path


def load_exclusions_or_die(out_dir: Path) -> dict[str, set[str]]:
    """Cita data/excluded_companies.json IZ SOPSTVENOG foldera (nikad iz
    s3-demo). Ako fajl ne postoji, prekida sa jasnom porukom -- namerno se
    NE nastavlja tiho bez iskljucivanja (sekcija 3 dopune uputstva)."""
    path = out_dir / "excluded_companies.json"
    if not path.exists():
        raise SystemExit(
            f"NEDOSTAJE {path}.\n"
            f"Iskljucivanje po ucesniku (sekcija 3) je obavezno i ne moze tiho da se preskoci.\n"
            f"Pokreni prvo (jednom):\n"
            f"  python generate_stimuli_s2.py --snapshot-exclusions <putanja-do-items_S3b.json>\n"
            f"Posle toga ovaj poziv vise ne dodiruje s3-demo."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {pid: set(ids) for pid, ids in data.get("participants", {}).items()}


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int,
                     help="MORA biti isti --seed kao za s3-demo/generate_stimuli.py "
                          "da bi baza firmi ostala identicna (videti README). "
                          "Obavezno osim uz --snapshot-exclusions.")
    ap.add_argument("--participants", type=int,
                     help="Obavezno osim uz --snapshot-exclusions.")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    ap.add_argument("--snapshot-exclusions", type=Path, metavar="ITEMS_S3B_JSON",
                     help="Jednokratna radnja: procitaj ITEMS_S3B_JSON (iz s3-demo) i upisi "
                          "data/excluded_companies.json, pa izadji BEZ generisanja items_S2.json. "
                          "Ovo je jedino mesto u ovom skriptu koje ikad dodiruje s3-demo -- "
                          "svaki naredni, normalan poziv cita samo taj lokalni snimak.")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    if args.snapshot_exclusions:
        make_exclusions_snapshot(args.snapshot_exclusions, args.out)
        return

    if args.seed is None or args.participants is None:
        ap.error("--seed i --participants su obavezni (osim uz --snapshot-exclusions)")

    forbidden_by_participant = load_exclusions_or_die(args.out)

    companies = gen_companies(args.seed, count=200)

    for c in companies:
        assert validate_checked_number(c["pib"]), c
        assert validate_checked_number(c["registration_number"]), c

    (args.out / "companies.json").write_text(
        json.dumps({"seed": args.seed, "companies": companies}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    participant_ids = ["DEMO"] + [f"P{i + 1:02d}" for i in range(args.participants)]

    payload = {
        "variant": "S2",
        "seed": args.seed,
        "field_pools": WEIGHT_POOLS,
        "composition": COMPOSITION,
        "practice": gen_practice_items(args.seed, companies),
        "participants": {},
    }
    total_excluded_reports = []
    for pid in participant_ids:
        forbidden_ids = forbidden_by_participant.get(pid, set())
        if forbidden_ids:
            total_excluded_reports.append((pid, len(forbidden_ids)))
        payload["participants"][pid] = gen_items_for_participant(
            args.seed, pid, companies, forbidden_ids,
        )

    (args.out / "items_S2.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
    )

    print(f"OK: {len(companies)} firmi, {len(participant_ids)} ucesnika, seed={args.seed}")
    print(f"Upisano u: {args.out}")
    if total_excluded_reports:
        n_pid = len(total_excluded_reports)
        avg = sum(c for _, c in total_excluded_reports) / n_pid
        print(f"Iskljucivanje po ucesniku primenjeno za {n_pid} ucesnika "
              f"(prosek {avg:.1f} firmi iskljuceno po ucesniku, iz {args.out / 'excluded_companies.json'}).")
    else:
        print(f"Iskljucivanje: {args.out / 'excluded_companies.json'} ucitan, ali nema poklapajucih "
              f"participant_id (S3 i S2 ucesnici se ne poklapaju po imenu?).")


if __name__ == "__main__":
    main()
