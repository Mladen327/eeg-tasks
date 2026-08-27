"""Zajednicko jezgro generatora stimulusa za S1/S2/S3 (uputstvo, odeljak 5).

Premesteno bez izmene ponasanja iz s2-demo/generate_stimuli_s2.py i
s3-demo/generate_stimuli.py -- te dve datoteke su ovaj deo sadrzale kao
bajt-identican (ili, kod choose_fields_for_item, algoritamski identican do
na modul-nivo globale koje je ovde zamenio eksplicitan parametar) duplirani
kod. Svaka funkcija/konstanta ispod je bila prisutna u OBA originala u
istom obliku -- videti komentare uz svaku za tacan izvor.

sto NIJE ovde: FIELD_WEIGHT/WEIGHT_POOLS/FIELD_DISPLAY_ORDER (razlicita
polja po scenariju), build_item (S3 ima mismatch/distractor logiku koju S2
nema), distortori i sugestije (iskljucivo S3b). To ostaje u generate_stimuli.py,
odvojeno po scenariju -- isti obrazac kao core/js: deli se MEHANIZAM, ne
scenario-specifican SADRZAJ.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

# --------------------------------------------------------------------------
# Kontrolne cifre, ISO 7064 MOD 11,10 (cist sistem). Bajt-identicno u oba
# originala.
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


# --------------------------------------------------------------------------
# Determinizam po seed-u. Bajt-identicno u oba originala.
# --------------------------------------------------------------------------


def seeded_rng(*parts) -> random.Random:
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return random.Random(digest)


def sha256_of_file(path: Path) -> str:
    """Isti format kao app/task.js (bufToHashHex): 'sha256:' + hex, nad
    sirovim bajtovima fajla. Prethodno postojala samo u S2 (jedini
    korisnik), ali je opsta -- ovde je i koristi build_exclusions_from_items."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Fiksne liste za sintetičku bazu firmi. Bajt-identicno u oba originala.
# --------------------------------------------------------------------------

COMPANY_ROOTS = [
    "Vega", "Panonija", "Delta", "Morava", "Kolubara",
    "Zenit", "Sirmium", "Timok", "Avala", "Karpat",
]

# --------------------------------------------------------------------------
# Podela firmi izmedju scenarija (S1 disjunktnost bez logike po ispitaniku).
#
# Umesto da se za svakog ispitanika prati koje mu je firme S2/S3 vec dodelio
# (sto S1 ne moze da radi -- recenice u sentences.json NEMAJU company_id,
# samo slobodan tekst koji USPUTNO pominje ime firme), koreni firmi su
# TRAJNO podeljeni na dva disjunktna skupa:
#   - S1_ONLY_ROOTS: iskljucivo za pominjanje u tekstu recenica Scenarija 1
#     (build_sentences.py NAME_MAP i CONSTRUCTED_SENTENCES).
#   - S2_S3_ROOTS: iskljucivo za stvarnu dodelu firme ispitaniku u S2/S3
#     (generate_stimuli.py filtrira pool pre uzorkovanja).
# Cim se koreni ne poklapaju, NIJEDNA konkretna firma (bez obzira na
# company_id) ne moze da se pojavi i kao S1-pominjana i kao S2/S3-dodeljena
# -- disjunktnost je zagarantovana samom podelom, ne runtime proverom.
#
# Granica: u name_map.json (build_sentences.py) je zatecen tacno 10 od 10
# mogucih korena (SVI); potrebno je da S2/S3 zadrzi bar 150 od 200 firmi.
# Dva najmanja korena u generisanoj bazi (seed 20260825): Delta (16) i
# Sirmium (17) = 33 firme za S1, 167 za S2/S3 -- bezbedno iznad minimuma,
# uz najmanji moguci gubitak raznovrsnosti za S2/S3.
S1_ONLY_ROOTS = ["Delta", "Sirmium"]
S2_S3_ROOTS = [r for r in COMPANY_ROOTS if r not in S1_ONLY_ROOTS]
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
# Baza firmi. Bajt-identicna funkcija u oba originala -- ukljucujuci polja
# koja S2 uopste ne koristi (contract_number, employee_count,
# package_count, monthly_fee_per_package, contract_months,
# total_monthly_fee, start_date). Namerno: rng.* pozivi za ta polja se
# desavaju IZMEDJU poziva za polja koja S2 deli sa S3 (pib,
# registration_number, city, street, street_number, contact_phone...). Da
# su izbacena, redosled povlacenja iz rng bi se pomerio i firma "C047" vise
# ne bi bila ista u oba projekta za isti seed -- sto je preduslov za
# iskljucivanje po company_id (ima smisla samo ako "C047" oznacava istu
# firmu u oba scenarija).
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
# Sastav stavke po nivou (N=3/5/7). Bajt-identican recnik u oba originala.
# --------------------------------------------------------------------------

COMPOSITION = {
    3: {"high": 1, "medium": 1, "low": 1},
    5: {"high": 1, "medium": 2, "low": 2},
    7: {"high": 1, "medium": 3, "low": 3},
}


def choose_fields_for_item(
    rng: random.Random,
    n: int,
    composition: dict,
    weight_pools: dict,
    field_display_order: list[str],
) -> list[str]:
    """Algoritamski identicno choose_fields_for_item() iz oba originala;
    jedina razlika je sto composition/weight_pools/field_display_order
    dolaze kao parametri umesto da se citaju iz modul-nivo globala S2-a
    odnosno S3-a (koje su medjusobno razlicite -- razlicita polja po
    scenariju)."""
    comp = composition[n]
    chosen = []
    for weight, count in comp.items():
        pool = weight_pools[weight]
        chosen.extend(rng.sample(pool, count))
    order_index = {f: i for i, f in enumerate(field_display_order)}
    chosen.sort(key=lambda f: order_index[f])
    return chosen


# --------------------------------------------------------------------------
# Iskljucivanje firmi vec vidjenih u drugom scenariju, za istog ucesnika
# (uputstvo, odeljak 3 dopune S2 + odeljak 7: "Generator mora obezbediti da
# isti ispitanik ni u jednom paru scenarija ne dobije istu firmu").
#
# Danas (S1 jos ne postoji) ovo se koristi samo jednosmerno: S3 se uvek
# generise prvi, bez ikakvog iskljucivanja (isto kao pre refaktora); zatim
# se napravi snimak njegovih items_S3b.json dodela i S2 se generise
# iskljucujuci ih. To vec daje potpunu parnu disjunktnost S2<->S3, uz uslov
# da se ispostuje taj redosled. Funkcije ispod primaju LISTU izvornih
# items_*.json fajlova (ne jedan), tako da kad S1 dobije svoj spec, moci ce
# da iskljuci UNIJU firmi iz VEC generisanih S2 i S3 snimaka bez ponovnog
# redizajna -- bez izmene ponasanja za danasnji, jednoizvorni S2 poziv (za
# jedan izvor je izlazni oblik bajt-identican prethodnom
# build_exclusions_from_items_s3b()).
# --------------------------------------------------------------------------


def build_exclusions_from_items(source_paths: list[Path]) -> dict:
    """Cita jedan ili vise items_*.json (ma kog scenarija) i vraca payload
    za excluded_companies.json: {participant_id: [company_id, ...]}, unija
    preko sva tri N i preko svih prosledjenih izvora."""
    for p in source_paths:
        if not p.exists():
            raise SystemExit(f"NE POSTOJI {p} -- ne mogu da napravim snimak iskljucivanja.")

    forbidden: dict[str, set[str]] = {}
    for p in source_paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        for pid, by_n in data.get("participants", {}).items():
            ids = forbidden.setdefault(pid, set())
            for n, items in by_n.items():
                for item in items:
                    ids.add(item["company_id"])

    participants = {pid: sorted(ids) for pid, ids in forbidden.items()}

    if len(source_paths) == 1:
        # Oblik identican prethodnom build_exclusions_from_items_s3b().
        return {
            "source_file": str(source_paths[0]),
            "source_hash": sha256_of_file(source_paths[0]),
            "participants": participants,
        }
    return {
        "source_files": [str(p) for p in source_paths],
        "source_hashes": [sha256_of_file(p) for p in source_paths],
        "participants": participants,
    }


def make_exclusions_snapshot(source_paths: list[Path], out_dir: Path) -> Path:
    payload = build_exclusions_from_items(source_paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "excluded_companies.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    n_pid = len(payload["participants"])
    avg = sum(len(v) for v in payload["participants"].values()) / n_pid if n_pid else 0
    print(f"OK: {out_path} ({n_pid} ucesnika, prosek {avg:.1f} iskljucenih firmi po ucesniku)")
    if "source_file" in payload:
        print(f"Izvor: {payload['source_file']} ({payload['source_hash']})")
    else:
        for f, h in zip(payload["source_files"], payload["source_hashes"]):
            print(f"Izvor: {f} ({h})")
    return out_path


def load_exclusions_or_die(out_dir: Path, snapshot_hint: str) -> dict[str, set[str]]:
    """Cita data/excluded_companies.json IZ SOPSTVENOG foldera. Ako fajl ne
    postoji, prekida sa jasnom porukom -- namerno se NE nastavlja tiho bez
    iskljucivanja (sekcija 3 dopune uputstva). snapshot_hint je tacna
    komanda koju treba pokrenuti prvo (razlicita po scenariju)."""
    path = out_dir / "excluded_companies.json"
    if not path.exists():
        raise SystemExit(
            f"NEDOSTAJE {path}.\n"
            f"Iskljucivanje po ucesniku (sekcija 3) je obavezno i ne moze tiho da se preskoci.\n"
            f"Pokreni prvo (jednom):\n"
            f"  {snapshot_hint}\n"
            f"Posle toga ovaj poziv vise ne dodiruje druge scenarije."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {pid: set(ids) for pid, ids in data.get("participants", {}).items()}
