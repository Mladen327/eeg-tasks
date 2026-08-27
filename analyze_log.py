"""Provera ispravnosti log datoteka za Scenario 2 i Scenario 3 (sekcija 10
uputstva S2/S3 + korak 7 uputstva za spajanje jezgra).

Cita jednu ili vise .jsonl datoteka (jedan blok po datoteci), PREPOZNAJE
scenario iz session zaglavlja svakog bloka (polje "scenario": "S2"/"S3a"/
"S3b" -- core/logger.js) i grana se na scenario-specificne mere. Blokovi iz
razlicitih scenarija mogu da se ucitaju u istom pozivu (retko u praksi,
logovi zive u odvojenim projektima) -- svaka grupa dobija sopstveni
izvestaj, kao da je pokrenuta zasebno.

Ovo je premestanje koda, ne izmena ponasanja: za homogen skup logova
(sve iz jednog scenarija -- jedini stvaran nacin upotrebe do sada) izvestaj
je identican onome sto su odvojene s2-demo/analyze_log_s2.py i
s3-demo/analyze_log.py ranije ispisivale.

Upotreba:
    python analyze_log.py s2-demo/logs/*.jsonl
    python analyze_log.py s3-demo/logs/*.jsonl --detail
    python analyze_log.py s3-demo/logs/P07_S3b_5_20260825T101403Z.jsonl
    python analyze_log.py --session 2CRD_20260827T143806Z

--session ucitava celu sesiju (integracija sesije, tacka 4/5 odobrenja):
skenira logs/, s2-demo/logs/ i s3-demo/logs/ (samo direktan sadrzaj, ne
practice/ ni demo/ poddirektorijume), pronalazi sve blokove sa zadatim
session_id, ispisuje zbirni pregled sva tri zadatka jedan pored drugog i
jasno prijavljuje nedostajuci zadatak kao ocekivano stanje (prekinuta
sesija), a zatim nastavlja sa punom postojecom analizom za svaki zadatak
koji jeste prisutan.
"""

from __future__ import annotations

import argparse
import math
import re
import statistics as stats
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from shared import analyze_common as ac

EEG_TASKS_ROOT = Path(__file__).parent

# Integracija sesije, tacka 4/5 odobrenja (core/intro.js sessionLogFields):
# tri zadatka jedne sesije zive kao tri odvojena .jsonl fajla, u tri
# odvojena projektna direktorijuma, povezana samo zajednickim session_id u
# svakom zaglavlju. --session skenira ova tri mesta (samo direktan sadrzaj,
# NE practice/ ni demo/ poddirektorijume -- orkestrirana sesija nikad ne
# pise u njih) i sastavlja ih nazad u jedan pregled.
SESSION_LOG_DIRS = [
    EEG_TASKS_ROOT / "logs",
    EEG_TASKS_ROOT / "s2-demo" / "logs",
    EEG_TASKS_ROOT / "s3-demo" / "logs",
]


# ==========================================================================
# Scenario S2 -- premesteno bez izmene ponasanja iz
# s2-demo/analyze_log_s2.py.
# ==========================================================================

S2_SWITCH_MAX_DEVIATION_WARN_MS = 50


def s2_verify_hashes_or_die(blocks, data_dir: Path):
    """Pre bilo kakve analize: za svaki blok sa session zaglavljem, uporedi
    items_hash/companies_hash iz loga sa hesom fajlova koje ovaj skript
    STVARNO cita (data/items_S2.json, data/companies.json). Prekida odmah
    na prvo neslaganje ili nedostajuce polje -- log snimljen sa drugim
    seedom/brojem ucesnika bi inace davao besmislene (tiho pogresne)
    rezultate poredjenja tacnosti."""
    items_path = data_dir / "items_S2.json"
    companies_path = data_dir / "companies.json"
    if not items_path.exists() or not companies_path.exists():
        return  # s2_load_items() dole vec ispisuje upozorenje i preskace tacnost
    expected_items_hash = ac.sha256_of_file(items_path)
    expected_companies_hash = ac.sha256_of_file(companies_path)

    for path, session, events in blocks:
        if session is None:
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
        if logged_items_hash != expected_items_hash:
            sys.exit(
                f"PREKID: {path} -- items_hash iz loga ({logged_items_hash}) ne odgovara "
                f"trenutnom {items_path} ({expected_items_hash}). Log je verovatno snimljen sa "
                f"drugom generacijom stimulusa (drugi seed/broj ucesnika) -- poredjenje tacnosti "
                f"protiv trenutnog items_S2.json bi bilo besmisleno. Regenerisati stimuluse "
                f"istim seedom kao pri snimanju, ili ne mesati logove iz razlicitih generacija."
            )
        if logged_companies_hash != expected_companies_hash:
            sys.exit(
                f"PREKID: {path} -- companies_hash iz loga ({logged_companies_hash}) ne "
                f"odgovara trenutnom {companies_path} ({expected_companies_hash})."
            )


# --------------------------------------------------------------------------
# Normalizacija pre poredjenja. Dve verzije, drzane na JEDNOM mestu svaka --
# posle pilota se ovde podesavaju, ne na vise mesta.
#
# STRICT (normalize_strict) je ono sto sad odredjuje correct=true (dopuna
# uputstva): DOSLOVNO poredjenje -- BEZ lowercase, BEZ uklanjanja
# dijakritike. Jedini izuzetak je razmak (svuda, uvek bezopasan) i, SAMO za
# polja ciju masku unosi interfejs a ne ispitanik (SPACING_FIELDS: PIB,
# maticni broj, telefon), tacka/kosa crta/crtica -- isti skup znakova kao
# spacing_only provera u classify_subclass() nize, namerno, da spacing_only
# detekcija i strict tacnost ostanu usaglaseni. Van SPACING_FIELDS (npr.
# company_name, gde je tacka semanticki deo pravnog oblika) tacka se NE
# uklanja.
#
# LENIENT (normalize_lenient) je STARO pravilo (pre ove izmene): lowercase +
# bez dijakritike + bez razmaka/kose crte/crtice (crtica dodata jer prikaz
# telefona, sekcija 3.3, ubacuje i kosu crtu I crticu -- "063/241-8870" --
# dok je sirova vrednost cist niz cifara; bukvalna primena "samo kosa crta"
# bi lazno oznacila ispravne telefone kao netacne). Lenient se VISE NE
# koristi za correct=true -- sluzi iskljucivo uporednoj "lenient" meri
# tacnosti u izvestaju (tacka 4 dopune uputstva), da se u pilotu vidi
# koliko je gresaka iskljucivo pravopisne prirode (velika/mala slova,
# dijakritika).
# --------------------------------------------------------------------------

_S2_DIACRITICS = str.maketrans({
    "č": "c", "ć": "c", "Č": "c", "Ć": "c",
    "ž": "z", "Ž": "z", "š": "s", "Š": "s",
    "đ": "dj", "Đ": "dj",
})

# Verzija koja CUVA velika/mala slova (Č -> C, ne c) -- normalize_lenient()
# ne sme da je koristi (vec radi na lowercase ulazu, gde bi ovo bilo bez
# efekta), ali classify_subclass() dole mora, jer poredi SIROVE (case-
# osetljive) vrednosti: bez ovoga bi "Čačak" (C sa kvacicom, veliko slovo)
# posle transliteracije ispalo "cacak" (malo c) i vise se ne bi poklopilo
# sa referencom "Cacak" (veliko C), lazno vracajuci None umesto
# diacritic_only.
_S2_DIACRITICS_CASE_PRESERVING = str.maketrans({
    "č": "c", "ć": "c", "Č": "C", "Ć": "C",
    "ž": "z", "Ž": "Z", "š": "s", "Š": "S",
    "đ": "dj", "Đ": "Dj",
})


def s2_normalize_strict(raw, field_name: str) -> str:
    s = str(raw).strip()
    if field_name in S2_SPACING_FIELDS:
        s = re.sub(r"[\s./\-]", "", s)
    else:
        s = re.sub(r"\s", "", s)
    return s


def s2_normalize_lenient(raw) -> str:
    s = str(raw).strip().lower()
    s = s.translate(_S2_DIACRITICS)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[\s/\-]", "", s)
    return s


# --------------------------------------------------------------------------
# Podklase gresaka (dopuna uputstva). Racunaju se na SIROVIM vrednostima
# (pre normalize_strict/normalize_lenient), PRE postojecih sest tipova
# ispod, i izvestavaju se ODVOJENO -- ne ulaze u raspodelu tipova. Provera
# je redosledna (prvo poklapanje pobedjuje); to retko ima efekat jer svako
# pravilo trazi da je SVE OSTALO identicno, pa se u praksi medjusobno ne
# preklapaju.
#
# Otkako je poredjenje za correct=true postalo doslovno (normalize_strict),
# svaka podklasa ima FIKSAN ishod (videti STRICT_SUBCLASS_VERDICT nize):
# case_only/diacritic_only/word_order su NETACNO (doslovno poredjenje ih
# vise ne oprasta), spacing_only ostaje TACNO (masku unosi interfejs, ne
# ispitanik -- normalize_strict i dalje uklanja razmak/tacku/kosu
# crtu/crticu za SPACING_FIELDS), legal_form_only ostaje NETACNO (u
# s2_analyze() eksplicitno forsirano, iako bi u praksi vec ispalo netacno i
# bez toga, jer normalize_strict ne uklanja tacke van SPACING_FIELDS).
# --------------------------------------------------------------------------

S2_LEGAL_FORMS = ["d.o.o.", "a.d.", "o.d."]
# Polja gde je razmak/tacka/kosa crta deo PRIKAZA (segmentacija, sekcija
# 3.3), ne sadrzaja -- spacing_only ima smisla samo za njih.
S2_SPACING_FIELDS = {"pib", "registration_number", "contact_phone"}


def _s2_strip_legal_form(s: str) -> tuple[str, str] | tuple[None, None]:
    for form in S2_LEGAL_FORMS:
        if s.endswith(form):
            return s[: -len(form)].rstrip(), form
    return None, None


def s2_classify_subclass(entered_raw: str, reference_raw: str, field_name: str) -> str | None:
    if not entered_raw or entered_raw == reference_raw:
        return None

    if entered_raw.lower() == reference_raw.lower():
        return "case_only"

    base_e, form_e = _s2_strip_legal_form(entered_raw)
    base_r, form_r = _s2_strip_legal_form(reference_raw)
    if base_e is not None and base_r is not None and base_e == base_r and form_e != form_r:
        return "legal_form_only"

    # case-preserving mapa (NE ista kao normalize_lenient, videti napomenu
    # uz _S2_DIACRITICS_CASE_PRESERVING) -- ovde nas zanima ISKLJUCIVO
    # dijakritika, ne i case/spacing (ti imaju svoje, prioritetnije provere
    # iznad).
    diac_e = entered_raw.translate(_S2_DIACRITICS_CASE_PRESERVING)
    diac_r = reference_raw.translate(_S2_DIACRITICS_CASE_PRESERVING)
    if diac_e == diac_r:
        return "diacritic_only"

    if field_name in S2_SPACING_FIELDS:
        # ukljucuje i crticu, ne samo razmak/tacku/kosu crtu -- isti skup
        # znakova kao normalize_strict za SPACING_FIELDS (telefon
        # "063/241-8870" ima i kosu crtu i crticu).
        stripped_e = re.sub(r"[\s./\-]", "", entered_raw)
        stripped_r = re.sub(r"[\s./\-]", "", reference_raw)
        if stripped_e == stripped_r:
            return "spacing_only"

    words_e = entered_raw.split()
    words_r = reference_raw.split()
    if len(words_e) > 1 and sorted(w.lower() for w in words_e) == sorted(w.lower() for w in words_r):
        return "word_order"

    return None


# --------------------------------------------------------------------------
# Tipologija gresaka (sekcija 6.3).
# --------------------------------------------------------------------------

def _s2_is_single_deletion(shorter: str, longer: str) -> bool:
    """Da li se `shorter` dobija brisanjem TACNO jednog znaka iz `longer`."""
    if len(longer) != len(shorter) + 1:
        return False
    i = j = 0
    skipped = False
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        else:
            if skipped:
                return False
            skipped = True
            j += 1
    return True


def s2_classify_error(entered: str, reference: str, other_refs: set[str]) -> str | None:
    """Vraca None ako nema greske (posle normalizacije jednako), inace jedan
    od: transposition, substitution, omission, insertion, wrong_field, other."""
    if entered == reference:
        return None
    if entered != "" and entered in other_refs:
        return "wrong_field"
    if len(entered) == len(reference):
        diffs = [i for i in range(len(entered)) if entered[i] != reference[i]]
        if (len(diffs) == 2 and diffs[1] == diffs[0] + 1
                and entered[diffs[0]] == reference[diffs[1]]
                and entered[diffs[1]] == reference[diffs[0]]):
            return "transposition"
        return "substitution"
    if len(entered) == len(reference) - 1 and _s2_is_single_deletion(entered, reference):
        return "omission"
    if len(entered) == len(reference) + 1 and _s2_is_single_deletion(reference, entered):
        return "insertion"
    return "other"


def s2_load_items(data_dir: Path):
    path = data_dir / "items_S2.json"
    if not path.exists():
        return None
    return ac.load_json(path)


def s2_build_reference_index(items_data):
    """(participant_id, n_fields, item_id) -> {field_name: reference_value}
    za wrong_field poredjenje (sve N vrednosti u toj stavki, ne samo N koja
    se trenutno proverava)."""
    index = {}
    if items_data is None:
        return index

    def add_block(pid, n, items):
        for item in items:
            values = {f["field_name"]: str(f["reference_value"]) for f in item["fields"]}
            index[(pid, str(n), item["item_id"])] = values

    practice = items_data.get("practice")
    if practice:
        add_block("PRACTICE", practice["n_fields"], practice["items"])

    for pid, by_n in items_data.get("participants", {}).items():
        for n, items in by_n.items():
            add_block(pid, n, items)

    return index


def s2_analyze(blocks, ref_index, detail=False):
    all_events = []
    for path, session, events in blocks:
        for e in events:
            e["_path"] = str(path)
            e["_participant"] = session.get("participant_id") if session else None
            e["_n"] = session.get("n_fields") if session else None
        all_events.extend(events)

    cell_focus = [e for e in all_events if e.get("event") == "cell_focus"]
    cell_submitted_all = [e for e in all_events if e.get("event") == "cell_submitted"]
    # Svako napustanje celije se beleze (blur), ali samo TACNO JEDAN dogadjaj
    # po (stavka, polje) nosi is_final:true -- konacna vrednost, poslata pri
    # potvrdi stavke (app/task.js, submitBtn.onclick). Sve mere tacnosti,
    # tipova gresaka i first_keystroke_ms se racunaju ISKLJUCIVO iz ovih.
    cell_submitted = [e for e in cell_submitted_all if e.get("is_final")]
    window_switch = [e for e in all_events if e.get("event") == "window_switch"]
    item_starts = [e for e in all_events if e.get("event") == "item_start"]
    encoding_ends = [e for e in all_events if e.get("event") == "encoding_end"]
    copy_blocked = [e for e in all_events if e.get("event") == "copy_blocked"]
    paste_blocked = [e for e in all_events if e.get("event") == "paste_blocked"]

    n_items = len(item_starts)
    print("=" * 72)
    print(f"Blokova: {len(blocks)}  Stavki: {n_items}  Polja (cell_submitted, is_final=true): {len(cell_submitted)}"
          f"  (ukupno cell_submitted dogadjaja, sve posete: {len(cell_submitted_all)})")
    print("=" * 72)

    # --- provera: broj is_final polja mora biti tacno stavke * N, po bloku ---
    expected_fields = 0
    actual_by_block = Counter()
    for path, session, events in blocks:
        if session is None:
            continue
        n_fields = session.get("n_fields")
        block_items = {e["item"] for e in events if e.get("event") == "item_start"}
        expected_fields += len(block_items) * (n_fields or 0)
    for s in cell_submitted:
        actual_by_block[s.get("_path")] += 1
    actual_fields = sum(actual_by_block.values())
    check_status = "OK" if actual_fields == expected_fields else "NESLAGANJE"
    print(f"Provera broja polja: is_final dogadjaja={actual_fields}, ocekivano (stavke x N)={expected_fields}  [{check_status}]")
    if check_status != "OK":
        print("  UPOZORENJE: broj is_final:true dogadjaja ne odgovara stavke x N -- proveriti da li "
              "je log snimljen ovom verzijom app/task.js (is_final polje uvedeno naknadno).")

    # --- resolucija svake cell_submitted na (reference_value, weight_class, entered_norm, ref_norm) ---
    weight_by_key = {}
    position_by_key = {}
    for f in cell_focus:
        key = (f.get("_participant"), str(f.get("_n")), f.get("item_id"), f.get("field_name"))
        weight_by_key[key] = f.get("weight_class")
        position_by_key[key] = f.get("field")  # 1-zasnovana pozicija u tabeli (redosled kolona)

    # medju is_final dogadjajima bi trebalo da postoji tacno jedan po
    # (path, item, field_name); "poslednji pobedjuje" ovde je samo odbrana
    # od eventualnog duplikata, ne oslanjanje na redosled kao ranije.
    last_submit = {}
    for s in cell_submitted:
        key = (s.get("_path"), s.get("item"), s.get("field_name"))
        last_submit[key] = s

    resolved = []
    unresolved_refs = 0
    for s in last_submit.values():
        pid, n = s.get("_participant"), str(s.get("_n"))
        item_id = s.get("item_id")
        refs = ref_index.get((pid, n, item_id))
        if refs is None or s.get("field_name") not in refs:
            unresolved_refs += 1
            continue
        reference_raw = refs[s["field_name"]]
        entered_raw = s.get("entered_value", "")
        field_name = s["field_name"]
        # svako OSTALO polje se normalizuje sa SVOJIM field_name-om (ne sa
        # onim polja koje trenutno proveravamo) -- npr. ako je trenutno
        # polje "pib", a ispitanik je greskom uneo vrednost polja
        # "contact_phone", to poredjenje mora da koristi telefonska
        # pravila normalizacije da bi se wrong_field uopste prepoznao.
        other_refs_strict = {s2_normalize_strict(v, k) for k, v in refs.items() if k != field_name}
        entered_strict = s2_normalize_strict(entered_raw, field_name)
        reference_strict = s2_normalize_strict(reference_raw, field_name)
        entered_lenient = s2_normalize_lenient(entered_raw)
        reference_lenient = s2_normalize_lenient(reference_raw)
        weight = weight_by_key.get((pid, n, item_id, field_name), "?")
        position = position_by_key.get((pid, n, item_id, field_name), 999)
        error_type = s2_classify_error(entered_strict, reference_strict, other_refs_strict)
        subclass = s2_classify_subclass(entered_raw, reference_raw, field_name)
        # legal_form_only je NAMERNO netacno bez obzira sta strict poredjenje
        # kaze (pravni oblik je semanticki deo naziva firme) -- videti
        # napomenu uz s2_classify_subclass. correct_lenient je ISKLJUCIVO za
        # uporednu meru u izvestaju (tacka 4 dopune uputstva), ne utice na
        # error_type/subclass/correct.
        correct = (error_type is None) and subclass != "legal_form_only"
        correct_lenient = entered_lenient == reference_lenient
        resolved.append({
            "path": s.get("_path"), "n": n, "item": s.get("item"), "item_id": item_id,
            "field_name": field_name, "weight_class": weight, "position": position,
            "reference_raw": reference_raw, "entered_raw": entered_raw,
            "correct": correct, "correct_lenient": correct_lenient,
            "error_type": error_type, "subclass": subclass,
            "first_keystroke_ms": s.get("first_keystroke_ms"),
            "backspace_count": s.get("backspace_count"),
        })

    if unresolved_refs:
        print(f"\nUPOZORENJE: {unresolved_refs} cell_submitted dogadjaja nije moglo da se poveze sa "
              f"items_S2.json (nepoznat participant_id/n/item_id -- proveriti da li su podaci "
              f"generisani istim seedom kao log).")

    # --- tacnost (strict, sluzbena mera correct=true), po klasi tezine ---
    print("\nTacnost STRICT (udeo correct=true, doslovno poredjenje), po klasi tezine:")
    by_weight = defaultdict(list)
    for r in resolved:
        by_weight[r["weight_class"]].append(r["correct"])
    for w in ("high", "medium", "low"):
        vals = by_weight.get(w, [])
        print(f"  {w:8s} {ac.pct(sum(vals), len(vals)) if vals else 'n/a':>8s}  (n={len(vals)})")

    # --- tacnost strict vs lenient, jedna pored druge, po klasi tezine
    # (tacka 4 dopune uputstva) -- koliko je gresaka iskljucivo pravopisne
    # prirode (velika/mala slova, dijakritika). STRICT je sluzbena mera
    # (correct=true gore); LENIENT je STARO pravilo, samo za poredjenje. ---
    print("\nTacnost STRICT vs LENIENT, po klasi tezine (razlika = udeo gresaka koje su "
          "iskljucivo pravopisne prirode):")
    by_weight_lenient = defaultdict(list)
    for r in resolved:
        by_weight_lenient[r["weight_class"]].append(r["correct_lenient"])
    for w in ("high", "medium", "low"):
        strict_vals = by_weight.get(w, [])
        lenient_vals = by_weight_lenient.get(w, [])
        if strict_vals:
            strict_pct = ac.pct(sum(strict_vals), len(strict_vals))
            lenient_pct = ac.pct(sum(lenient_vals), len(lenient_vals))
            diff_pp = 100 * (sum(lenient_vals) / len(lenient_vals) - sum(strict_vals) / len(strict_vals))
            print(f"  {w:8s} strict {strict_pct:>7s}   lenient {lenient_pct:>7s}   "
                  f"razlika {diff_pp:+5.1f}pp  (n={len(strict_vals)})")
        else:
            print(f"  {w:8s} n/a")

    # --- tacnost po polju (strict) ---
    print("\nTacnost po polju (strict):")
    by_field = defaultdict(list)
    for r in resolved:
        by_field[r["field_name"]].append(r["correct"])
    for field, vals in sorted(by_field.items()):
        print(f"  {field:22s} {ac.pct(sum(vals), len(vals)):>8s}  (n={len(vals)})")

    # --- broj povrataka u prozor A po stavci, po N ---
    print("\nBroj povrataka u Prozor A (window_switch to=document, reason=user) po stavci, po N:")
    returns_by_item = defaultdict(int)
    for w in window_switch:
        if w.get("to") == "document" and w.get("reason") == "user":
            returns_by_item[(w.get("_path"), w.get("item"))] += 1
    by_n_returns = defaultdict(list)
    item_n = {(e.get("_path"), e.get("item")): e.get("_n") for e in item_starts}
    for key in item_n:
        by_n_returns[item_n[key]].append(returns_by_item.get(key, 0))
    for n, vals in sorted(by_n_returns.items(), key=lambda x: str(x[0])):
        print(f"  N={n}: prosek {stats.mean(vals):.2f} povrataka po stavci  (stavki={len(vals)})")

    # --- ukupno vreme u Prozoru A po stavci, po N (dopuna uputstva) ---
    # document_stay_ms se belezi na window_switch(to=spreadsheet) -- trajanje
    # boravka koji se upravo zavrsava. Suma po stavci je ukupno vreme
    # provedeno u Prozoru A tokom te stavke (posle faze kodiranja).
    print("\nUkupno vreme u Prozoru A po stavci (document_stay_ms, zbir), po N:")
    stay_ms_by_item = defaultdict(float)
    for w in window_switch:
        if w.get("to") == "spreadsheet" and w.get("document_stay_ms") is not None:
            stay_ms_by_item[(w.get("_path"), w.get("item"))] += w["document_stay_ms"]
    by_n_stay = defaultdict(list)
    for key in item_n:
        by_n_stay[item_n[key]].append(stay_ms_by_item.get(key, 0.0))
    for n, vals in sorted(by_n_stay.items(), key=lambda x: str(x[0])):
        print(f"  N={n}: prosek {stats.mean(vals):.0f} ms, medijana {stats.median(vals):.0f} ms po stavci  "
              f"(stavki={len(vals)})")

    # --- odnos broj_povrataka / N po stavci, prosek i medijana po N ---
    print("\nOdnos broj_povrataka / N po stavci, po N:")
    ratio_by_n = defaultdict(list)
    for key, n in item_n.items():
        if not n:
            continue
        ratio_by_n[n].append(returns_by_item.get(key, 0) / n)
    for n, vals in sorted(ratio_by_n.items(), key=lambda x: str(x[0])):
        print(f"  N={n}: prosek {stats.mean(vals):.2f}, medijana {stats.median(vals):.2f}  (stavki={len(vals)})")

    # --- udeo stavki u kojima je MAX_SWITCHES_PER_ITEM iskorisceno do kraja ---
    max_switches_by_path = {str(path): session.get("max_switches_per_item")
                             for path, session, _ in blocks if session is not None}
    print("\nUdeo stavki u kojima je ogranicenje povrataka iskorisceno do kraja, po N:")
    exhausted_by_n = defaultdict(list)
    for key, n in item_n.items():
        path = key[0]
        limit = max_switches_by_path.get(path)
        if limit is None:
            continue  # blok bez ogranicenja (MAX_SWITCHES_PER_ITEM=null) -- nema smisla za ovu meru
        exhausted_by_n[n].append(returns_by_item.get(key, 0) >= limit)
    if exhausted_by_n:
        for n, vals in sorted(exhausted_by_n.items(), key=lambda x: str(x[0])):
            print(f"  N={n}: {ac.pct(sum(vals), len(vals))}  (stavki={len(vals)})")
    else:
        print("  n/a (nijedan ucitani blok nema postavljen MAX_SWITCHES_PER_ITEM)")

    # --- broj pokusaja switch_denied (povratak posle iskoriscenog
    # ogranicenja), po N -- mera pritiska na kapacitet radne memorije,
    # treba da raste sa N. ---
    print("\nBroj pokusaja switch_denied (povratak posle iskoriscenog ogranicenja), po N:")
    switch_denied = [e for e in all_events if e.get("event") == "switch_denied"]
    denied_by_n = defaultdict(int)
    for e in switch_denied:
        n = item_n.get((e.get("_path"), e.get("item")))
        denied_by_n[n] += 1
    if switch_denied:
        for n, count in sorted(denied_by_n.items(), key=lambda x: str(x[0])):
            n_items_at_n = sum(1 for k, v in item_n.items() if v == n)
            print(f"  N={n}: {count} pokusaja  ({count / n_items_at_n:.2f} po stavci, stavki={n_items_at_n})")
    else:
        print("  0 (nema switch_denied dogadjaja u ucitanim logovima)")

    # --- broj povrataka u Prozor A PRE nego sto je svako pojedinacno polje
    # uneto: window_switch(to=document, reason=user) nosi from_field --
    # polje koje je bilo aktivno u tabeli u trenutku odlaska. Svaki takav
    # povratak se pripisuje tom polju. ---
    print("\nBroj povrataka u Prozor A pre unosa polja (po from_field), po klasi tezine:")
    returns_before_field = defaultdict(int)
    for w in window_switch:
        if w.get("to") == "document" and w.get("reason") == "user" and w.get("from_field"):
            key = (w.get("_path"), w.get("item"), w.get("from_field"))
            returns_before_field[key] += 1
    # svako polje koje je uopste bilo fokusirano (cell_focus) racuna se, i
    # kad je vrednost 0 (nikad se nije vracao pre unosa tog polja).
    returns_before_field_by_weight = defaultdict(list)
    seen_fields = set()
    for f in cell_focus:
        key = (f.get("_path"), f.get("item"), f.get("field_name"))
        if key in seen_fields:
            continue
        seen_fields.add(key)
        returns_before_field_by_weight[f.get("weight_class", "?")].append(returns_before_field.get(key, 0))
    for w in ("high", "medium", "low"):
        vals = returns_before_field_by_weight.get(w, [])
        if vals:
            print(f"  {w:8s} prosek {stats.mean(vals):.2f}, medijana {stats.median(vals):.1f}  (n={len(vals)})")
        else:
            print(f"  {w:8s} n/a")

    # --- broj ponovnih ulazaka u ISTU celiju, po klasi tezine ---
    # cell_focus se belezi na svakom fokusiranju (i prvom i svakom povratku),
    # pa je broj ponovnih ulazaka = (broj cell_focus za to polje u toj
    # stavci) - 1. Ovo je odvojena mera od "broj povrataka u Prozor A" gore:
    # ta broji odlaske u dokument, ova broji koliko se puta ISTO POLJE
    # iznova fokusira (moze da naraste i bez odlaska u Prozor A, npr. Tab pa
    # Shift+Tab unutar tabele, iako je to redak slucaj u ovom UI-ju).
    focus_counts = Counter()
    focus_weight = {}
    for f in cell_focus:
        key = (f.get("_path"), f.get("item"), f.get("field_name"))
        focus_counts[key] += 1
        focus_weight[key] = f.get("weight_class")
    reentries_by_weight = defaultdict(list)
    for key, count in focus_counts.items():
        reentries_by_weight[focus_weight.get(key, "?")].append(count - 1)
    print("\nBroj ponovnih ulazaka u istu celiju (cell_focus - 1), po klasi tezine:")
    for w in ("high", "medium", "low"):
        vals = reentries_by_weight.get(w, [])
        if vals:
            print(f"  {w:8s} prosek {stats.mean(vals):.2f}, medijana {stats.median(vals):.1f}  (n={len(vals)})")
        else:
            print(f"  {w:8s} n/a")

    # --- raspodela tipova gresaka ---
    print("\nRaspodela tipova gresaka (samo netacna polja):")
    error_counts = Counter(r["error_type"] for r in resolved if not r["correct"])
    total_errors = sum(error_counts.values())
    for t in ("transposition", "substitution", "omission", "insertion", "wrong_field", "other"):
        print(f"  {t:14s} {ac.pct(error_counts.get(t, 0), total_errors) if total_errors else 'n/a':>8s}  (n={error_counts.get(t, 0)})")

    # --- podklase gresaka (na sirovim vrednostima, dopuna uputstva) ---
    # ODVOJENO od gornje raspodele -- ne ulazi u sest tipova. Racuna se nad
    # SVIM poljima (ne samo netacnim), jer case_only/diacritic_only/
    # spacing_only mogu da se jave i na polju koje je posle normalizacije
    # ipak correct=true (namerno, vidi napomenu uz s2_classify_subclass).
    print("\nRaspodela podklasa gresaka (na sirovim vrednostima, odvojeno od tipova gore), "
          "sa oznakom da li se ocenjuju kao tacne (strict):")
    subclass_counts = Counter(r["subclass"] for r in resolved if r["subclass"])
    total_with_subclass = sum(subclass_counts.values())
    for sc in ("case_only", "legal_form_only", "diacritic_only", "spacing_only", "word_order"):
        # Verdikt se racuna IZ PODATAKA (ne iz fiksne tabele) -- svaka
        # podklasa ima deterministicki ishod pod strict pravilom, ali ovo
        # sluzi i kao samo-provera: ako bi ikad bio mesovit, odmah se vidi.
        vals = [r["correct"] for r in resolved if r["subclass"] == sc]
        if not vals:
            verdict = "n/a"
        elif all(vals):
            verdict = "TACNO"
        elif not any(vals):
            verdict = "NETACNO"
        else:
            verdict = f"MESOVITO ({sum(vals)}/{len(vals)} tacno -- neocekivano, proveriti)"
        print(f"  {sc:16s} n={subclass_counts.get(sc, 0):3d}  [{verdict}]")
    if total_with_subclass:
        still_correct = sum(1 for r in resolved if r["subclass"] and r["correct"])
        print(f"  (od toga, correct=true uprkos podklasi -- ovo je sad iskljucivo spacing_only: "
              f"{still_correct}/{total_with_subclass})")

    # --- first_keystroke_ms: medijana/p90 po klasi tezine ---
    print("\nVreme do prvog pritiska (first_keystroke_ms), medijana / p90, po klasi tezine:")
    for w in ("high", "medium", "low"):
        vals = sorted(r["first_keystroke_ms"] for r in resolved
                      if r["weight_class"] == w and r["first_keystroke_ms"] is not None)
        if vals:
            print(f"  {w:8s} medijana {stats.median(vals):7.0f} ms   p90 {ac.percentile(vals, 90):7.0f} ms  (n={len(vals)})")
        else:
            print(f"  {w:8s} n/a")

    # --- kopiranje/lepljenje ---
    print(f"\nPoništeni pokušaji kopiranja (copy_blocked): {len(copy_blocked)}")
    if copy_blocked:
        reasons = Counter(e.get("reason") for e in copy_blocked)
        print("  " + ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())))
    print(f"Poništeni pokušaji lepljenja (paste_blocked): {len(paste_blocked)}")

    # --- backspace_count raspodela ---
    print("\nRaspodela backspace_count, po N:")
    bks_by_n = defaultdict(list)
    for r in resolved:
        if r["backspace_count"] is not None:
            bks_by_n[r["n"]].append(r["backspace_count"])
    for n, vals in sorted(bks_by_n.items(), key=lambda x: str(x[0])):
        print(f"  N={n}: prosek {stats.mean(vals):.2f}, medijana {stats.median(vals):.1f}  (n={len(vals)})")

    # --- encoding_actual_ms, po N, medijana/p90, odvojeno user/auto (dopuna
    # uputstva) -- koliko dugo ispitanik stvarno ostaje u fazi kodiranja
    # kad sam odluci da je gotov (mode="user") naspram automatskog isteka
    # (mode="auto", ocekivano ~puno trajanje encodingDuration). ---
    print("\nTrajanje faze kodiranja (encoding_actual_ms), medijana / p90, po N i po nacinu prelaska:")
    encoding_by_n_mode = defaultdict(list)
    for e in encoding_ends:
        n = item_n.get((e.get("_path"), e.get("item")))
        mode = e.get("mode", "?")
        if e.get("encoding_actual_ms") is not None:
            encoding_by_n_mode[(n, mode)].append(e["encoding_actual_ms"])
    ns = sorted({n for n, _ in encoding_by_n_mode}, key=str)
    if ns:
        for n in ns:
            for mode in ("user", "auto"):
                vals = sorted(encoding_by_n_mode.get((n, mode), []))
                if vals:
                    print(f"  N={n} {mode:4s}: medijana {stats.median(vals):6.0f} ms   "
                          f"p90 {ac.percentile(vals, 90):6.0f} ms  (n={len(vals)})")
                else:
                    print(f"  N={n} {mode:4s}: n/a")
    else:
        print("  n/a (nema encoding_end dogadjaja sa encoding_actual_ms)")

    # --- odstupanje SWITCH_DELAY_MS ---
    delays = [w["delay_actual_ms"] for w in window_switch if "delay_actual_ms" in w]
    if delays:
        target_candidates = {s.get("switch_delay_ms") for _, s, _ in blocks if s is not None}
        target_candidates.discard(None)
        target = sorted(target_candidates)[0] if len(target_candidates) == 1 else None
        if target is not None:
            deviations = [abs(d - target) for d in delays]
            max_dev = max(deviations)
            print(f"\nOdstupanje SWITCH_DELAY_MS: cilj {target} ms, "
                  f"srednje odstupanje {stats.mean(deviations):.1f} ms, "
                  f"max odstupanje {max_dev:.1f} ms  (n={len(delays)})")
            if max_dev > S2_SWITCH_MAX_DEVIATION_WARN_MS:
                print(f"  UPOZORENJE: max odstupanje > {S2_SWITCH_MAX_DEVIATION_WARN_MS} ms -- "
                      f"tajming nije pouzdan za analizu po prozorima od 1 s (sekcija 10).")
        else:
            print(f"\nOdstupanje SWITCH_DELAY_MS: PRAGOVI SE RAZLIKUJU MEDJU BLOKOVIMA "
                  f"({sorted(target_candidates)} ms) -- preskačem proveru.")

    # --- znaci odustajanja: trend tacnosti/vremena prva vs poslednja trecina stavki, po bloku ---
    print("\nZnaci odustajanja (prva/poslednja trecina stavki po bloku):")
    correct_by_item_path = defaultdict(list)
    for r in resolved:
        correct_by_item_path[(r["path"], r["item"])].append(r["correct"])

    item_end_t = {}
    item_start_t = {}
    for e in all_events:
        if e.get("event") == "item_start":
            item_start_t[(e.get("_path"), e.get("item"))] = e.get("t")
        if e.get("event") == "item_end":
            item_end_t[(e.get("_path"), e.get("item"))] = e.get("t")

    for path, session, events in blocks:
        item_indices = sorted({e["item"] for e in events if e.get("event") == "item_start"})
        if len(item_indices) < 6:
            print(f"  {path}: nema dovoljno stavki za ovu proveru (ima {len(item_indices)}, "
                  f"potrebno bar 6 da bi se delile na trecine)")
            continue
        third = max(1, len(item_indices) // 3)
        first_items = item_indices[:third]
        last_items = item_indices[-third:]

        def acc_for(idx_list):
            vals = []
            for idx in idx_list:
                cells = correct_by_item_path.get((str(path), idx), [])
                vals.extend(cells)
            return sum(vals) / len(vals) if vals else float("nan")

        def time_for(idx_list):
            durs = []
            for idx in idx_list:
                key = (str(path), idx)
                if key in item_start_t and key in item_end_t:
                    durs.append(item_end_t[key] - item_start_t[key])
            return stats.mean(durs) if durs else float("nan")

        acc_first, acc_last = acc_for(first_items), acc_for(last_items)
        time_first, time_last = time_for(first_items), time_for(last_items)
        flag = ""
        if not math.isnan(acc_first) and not math.isnan(acc_last) and not math.isnan(time_first) and not math.isnan(time_last):
            if acc_last < acc_first - 0.1 and time_last > time_first * 1.1:
                flag = "  <- pad tacnosti + rast vremena: mozda odustajanje"
        print(f"  {path}: tacnost prva/poslednja trecina {acc_first*100:.0f}%/{acc_last*100:.0f}%, "
              f"vreme po stavci {time_first:.0f}/{time_last:.0f} ms{flag}")

    print()

    if detail:
        s2_print_detail_table(resolved, returns_before_field)


S2_DETAIL_COLUMNS = [
    "Stavka", "Polje", "Tezina", "Tacna vrednost", "Uneto (sirovo)",
    "Tacno", "Tip greske", "Podklasa", "1.pritisak(ms)", "Backspace", "Povrataka pre",
]


def s2_print_detail_table(resolved, returns_before_field):
    """--detail: tabela po polju (sekcija dopune uputstva). Dopunjava
    zbirni izvestaj, ne zamenjuje ga -- poziva se posle njega."""
    print("=" * 72)
    print("DETALJI PO POLJU (--detail)")
    print("=" * 72)

    rows = []
    for r in sorted(resolved, key=lambda x: (x["path"], x["item"], x["position"])):
        key = (r["path"], r["item"], r["field_name"])
        rows.append([
            str(r["item"]),
            r["field_name"],
            r["weight_class"],
            r["reference_raw"],
            r["entered_raw"],
            "DA" if r["correct"] else "NE",
            r["error_type"] or "-",
            r["subclass"] or "-",
            f"{r['first_keystroke_ms']:.0f}" if r["first_keystroke_ms"] is not None else "-",
            str(r["backspace_count"]) if r["backspace_count"] is not None else "-",
            str(returns_before_field.get(key, 0)),
        ])

    print(ac.format_table(S2_DETAIL_COLUMNS, rows))
    print()


# ==========================================================================
# Scenario S3 -- premesteno bez izmene ponasanja iz s3-demo/analyze_log.py.
# ==========================================================================

S3_TARGET_OUTCOME_QUOTAS = {
    "true_positive": 0.10,
    "true_negative": 0.65,
    "missed_error": 0.15,
    "false_alarm": 0.10,
}
S3_TARGET_MISMATCH_RATE = 0.25
S3_SUGGESTION_LATENCY_TARGET_MS = 1500
S3_LATENCY_MAX_DEVIATION_WARN_MS = 50


def s3_verify_hashes_or_die(blocks, data_dir: Path):
    """Pre bilo kakve analize: za svaki blok sa session zaglavljem, uporedi
    items_hash/companies_hash iz loga sa hesom fajlova koje bi ovaj log
    trebalo da odgovara (data/items_S3a.json ili items_S3b.json prema
    session['variant'], i data/companies.json). Prekida odmah na prvo
    neslaganje ili nedostajuce polje -- isti mehanizam kao za S2, radi
    uporedivosti."""
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

        expected_items_hash = ac.sha256_of_file(items_path)
        if logged_items_hash != expected_items_hash:
            sys.exit(
                f"PREKID: {path} -- items_hash iz loga ({logged_items_hash}) ne odgovara "
                f"trenutnom {items_path} ({expected_items_hash}). Log je verovatno snimljen sa "
                f"drugom generacijom stimulusa (drugi seed/broj ucesnika) -- rezultati poredjenja "
                f"bi bili besmisleni. Regenerisati stimuluse istim seedom kao pri snimanju, ili "
                f"ne mesati logove iz razlicitih generacija."
            )

        expected_companies_hash = ac.sha256_of_file(companies_path)
        if logged_companies_hash != expected_companies_hash:
            sys.exit(
                f"PREKID: {path} -- companies_hash iz loga ({logged_companies_hash}) ne "
                f"odgovara trenutnom {companies_path} ({expected_companies_hash})."
            )


def s3_analyze(blocks):
    all_events = []
    for path, session, events in blocks:
        for e in events:
            e["_path"] = str(path)
        all_events.extend(events)

    value_submitted = [e for e in all_events if e.get("event") == "value_submitted"]
    suggestion_shown = [e for e in all_events if e.get("event") == "suggestion_shown"]
    decisions = [e for e in all_events if e.get("event") == "decision"]
    field_active = [e for e in all_events if e.get("event") == "field_active"]
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
        for cls, target in S3_TARGET_OUTCOME_QUOTAS.items():
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
        for cls in S3_TARGET_OUTCOME_QUOTAS:
            vals = by_class.get(cls, [])
            rate = sum(vals) / len(vals) if vals else None
            print(f"  {cls:16s} {ac.pct(sum(vals), len(vals)) if vals else 'n/a':>8s}  (n={len(vals)})")

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
              f"{ac.pct(caught, len(missed))}  ({caught}/{len(missed)})")

        # --- odstupanje latencije sugestije od 1500ms ---
        latencies = [s["latency_actual_ms"] for s in suggestion_shown if "latency_actual_ms" in s]
        if latencies:
            deviations = [abs(l - S3_SUGGESTION_LATENCY_TARGET_MS) for l in latencies]
            max_dev = max(deviations)
            sd = stats.pstdev(latencies) if len(latencies) > 1 else 0.0
            print(f"\nLatencija sugestije: cilj {S3_SUGGESTION_LATENCY_TARGET_MS} ms, "
                  f"srednje odstupanje {stats.mean(deviations):.1f} ms, "
                  f"max odstupanje {max_dev:.1f} ms, sd {sd:.1f} ms")
            if max_dev > S3_LATENCY_MAX_DEVIATION_WARN_MS:
                print(f"  UPOZORENJE: max odstupanje > {S3_LATENCY_MAX_DEVIATION_WARN_MS} ms -- "
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
              f"p75 {ac.percentile(decision_vals, 75):.0f} ms, "
              f"p90 {ac.percentile(decision_vals, 90):.0f} ms  (n={len(decision_vals)})")
        over_deadline_n = sum(1 for v in value_submitted if v.get("over_deadline"))
        thresholds = {s.get("decision_ms_per_field") for _, s, _ in blocks if s is not None}
        thresholds.discard(None)
        threshold_note = f"prag={sorted(thresholds)[0]} ms" if len(thresholds) == 1 else \
            (f"PRAGOVI SE RAZLIKUJU MEDJU BLOKOVIMA: {sorted(thresholds)} ms" if thresholds else "prag nepoznat (staro zaglavlje)")
        print(f"Udeo polja preko praga (over_deadline=true, {threshold_note}): "
              f"{ac.pct(over_deadline_n, len(value_submitted))}  (n={over_deadline_n})")

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
        parts = ", ".join(f"{k}={ac.pct(v,total)}" for k, v in counter.items())
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
        print(f"  {weight:8s} {ac.pct(sum(vals), len(vals)) if vals else 'n/a':>8s}  (n={len(vals)})")

    # --- match/mismatch udeo, provera prema ciljanih 25% ---
    statuses = [f.get("true_status") for f in field_active]
    mismatch_rate = statuses.count("mismatch") / len(statuses) if statuses else 0
    print(f"\nUdeo mismatch polja: {mismatch_rate*100:.1f}% (cilj {S3_TARGET_MISMATCH_RATE*100:.0f}%)")

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
        parts = ", ".join(f"{k}={ac.pct(v,total)}" for k, v in counter.items())
        print(f"  N={n}: {parts}")

    # --- znaci odustajanja ---
    print("\nZnaci odustajanja:")
    timed_out = [v for v in value_submitted if v.get("timed_out")]
    print(f"  Udeo polja resenih na isteku vremenskog limita (timed_out; smisleno samo kad je "
          f"enforce_decision_deadline=true u zaglavlju): {ac.pct(len(timed_out), len(value_submitted))}")

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


# ==========================================================================
# Scenario S1 -- SPEC_S1_demo.md, korak 5. Bez stavka-firma veze -- referenca
# dolazi iz data/items_S1.json preko (participant_id, n, item_id,
# sentence_index), ne preko company_id.
#
# Tacka F uputstva za spajanje jezgra (odlozena iz koraka D, "poreklo kao
# konfund"): ova grana takodje racuna tacnost po polju "source"
# (enron/constructed) i statisticki proverava razliku (dvoproporcioni
# z-test) -- videti s1_source_confound_check() i njen poziv u s1_analyze().
# ==========================================================================

S1_BURST_MAX_MS = 500    # "razmaci kraci od 500 ms" -- brzina kucanja u naletu (sekcija 6)
S1_PAUSE_MIN_MS = 1000   # "pauze duze od 1000 ms" -- struktura pauza (sekcija 6)
S1_CONFOUND_ALPHA = 0.05  # prag znacajnosti za "bitno razlikuju" (tacka F)

# Funkcijske reci za prepoznavanje "paraphrase" podklase (sekcija 5.3):
# "dovoljno je prepoznati slucajeve sa dodatim ili izostavljenim
# funkcijskim recima uz ocuvane sadrzinske". Namerno NIJE iscrpna --
# uputstvo eksplicitno kaze "pravilo se u pilotu podesava". Prosiriti ovde,
# ne na vise mesta, kad pilot pokaze propuste.
S1_FUNCTION_WORDS = {
    "da", "je", "su", "i", "u", "na", "za", "sa", "se", "ne", "li", "ali",
    "ili", "pa", "kao", "koji", "koja", "koje", "taj", "ta", "to", "ovaj",
    "ova", "ovo", "ce", "bi", "bih", "bismo", "biste", "sam", "si", "smo",
    "ste", "ga", "joj", "mu", "im", "ih", "ju", "me", "te", "nam", "vam",
    "od", "do", "iz", "po", "o", "pri", "kroz", "bez", "sto", "kad",
    "kada", "gde", "kako", "vec", "jos", "samo", "cak", "tek",
}


def s1_verify_hashes_or_die(blocks, data_dir: Path):
    """Isti mehanizam kao S2/S3 (samo items_hash -- S1 nema companies_hash,
    nema stavka-firma vezu)."""
    items_path = data_dir / "items_S1.json"
    if not items_path.exists():
        return  # s1_load_items() dole vec ispisuje upozorenje i preskace tacnost
    expected_items_hash = ac.sha256_of_file(items_path)

    for path, session, events in blocks:
        if session is None:
            continue
        logged_items_hash = session.get("items_hash")
        if logged_items_hash is None:
            sys.exit(
                f"PREKID: {path} nema items_hash u zaglavlju sesije -- log je verovatno "
                f"snimljen pre uvodjenja provere integriteta, ili je zaglavlje osteceno."
            )
        if logged_items_hash != expected_items_hash:
            sys.exit(
                f"PREKID: {path} -- items_hash iz loga ({logged_items_hash}) ne odgovara "
                f"trenutnom {items_path} ({expected_items_hash}). Log je verovatno snimljen sa "
                f"drugom generacijom stimulusa -- poredjenje tacnosti bi bilo besmisleno. "
                f"Regenerisati stimuluse istim seedom kao pri snimanju, ili ne mesati logove "
                f"iz razlicitih generacija."
            )


def s1_load_items(data_dir: Path):
    path = data_dir / "items_S1.json"
    if not path.exists():
        return None
    return ac.load_json(path)


def s1_build_reference_index(items_data):
    """(participant_id, n, item_id) -> {sentence_index: {text, length_class,
    source, is_question}}. Ukljucuje i vezbu (participant_id "PRACTICE")."""
    index = {}
    if items_data is None:
        return index

    def add_block(pid, n, items):
        for item in items:
            by_idx = {s["sentence_index"]: s for s in item["sentences"]}
            index[(pid, str(n), item["item_id"])] = by_idx

    practice = items_data.get("practice")
    if practice:
        add_block("PRACTICE", practice["n_fields"], practice["items"])

    for pid, by_n in items_data.get("participants", {}).items():
        for n, items in by_n.items():
            add_block(pid, n, items)

    return index


# --------------------------------------------------------------------------
# Normalizacija. STRICT: doslovno poredjenje, zavrsna tacka se zanemaruje
# (SPEC_S1_demo.md sekcija 5). LENIENT: velika/mala slova + dijakritika se
# opraštaju (uporedna mera, kao u S2) -- dijakritika u referenci NE POSTOJI
# (sentences.json je vec bez dijakritike, build_sentences.py korak 7), pa
# ovde LENIENT jedino ima efekta ako je ISPITANIK uneo dijakritiku koje u
# referenci nema (obrnut smer od S2/S3).
# --------------------------------------------------------------------------

def s1_normalize_strict(raw: str) -> str:
    s = str(raw).strip()
    if s.endswith("."):
        s = s[:-1].rstrip()
    return s


def s1_normalize_lenient(raw: str) -> str:
    s = s1_normalize_strict(raw).lower()
    s = s.translate(_S2_DIACRITICS)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s


def s1_classify_subclass(entered_raw: str, reference_raw: str) -> str | None:
    """Podklase (sekcija 5.3), na SIROVIM vrednostima, odvojeno od tipova
    gresaka. case_only/diacritic_only netacno, punctuation_only tacno
    (zavrsna tacka se zanemaruje), paraphrase izdvojeno (nije ni tacno ni
    deo standardne raspodele tipova)."""
    entered_stripped = s1_normalize_strict(entered_raw)
    reference_stripped = s1_normalize_strict(reference_raw)

    if entered_stripped == reference_stripped:
        if entered_raw.strip() != reference_raw.strip():
            return "punctuation_only"
        return None

    if entered_stripped.lower() == reference_stripped.lower():
        return "case_only"

    diac_e = entered_stripped.translate(_S2_DIACRITICS_CASE_PRESERVING)
    diac_r = reference_stripped.translate(_S2_DIACRITICS_CASE_PRESERVING)
    if diac_e == diac_r:
        return "diacritic_only"

    entered_words = entered_stripped.lower().split()
    ref_words = reference_stripped.lower().split()
    content_entered = [w for w in entered_words if w not in S1_FUNCTION_WORDS]
    content_ref = [w for w in ref_words if w not in S1_FUNCTION_WORDS]
    if content_entered == content_ref and entered_words != ref_words:
        return "paraphrase"

    return None


def _s1_word_align(ref_words: list[str], entered_words: list[str]):
    """Poravnanje reci Levenstajnovom distancom (trosak 1 za zamenu/umetanje/
    izostavljanje, 0 za tacno poklapanje). Vraca listu operacija u redosledu
    poravnanja: ("match"|"sub", ref_word, entered_word), ("del", ref_word,
    None) -- rec izostavljena, ili ("ins", None, entered_word) -- dodata rec."""
    n, m = len(ref_words), len(entered_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost_sub = 0 if ref_words[i - 1] == entered_words[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost_sub,
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
            )

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost_sub = 0 if ref_words[i - 1] == entered_words[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost_sub:
                ops.append(("match" if cost_sub == 0 else "sub", ref_words[i - 1], entered_words[j - 1]))
                i -= 1
                j -= 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", ref_words[i - 1], None))
            i -= 1
            continue
        if j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            ops.append(("ins", None, entered_words[j - 1]))
            j -= 1
            continue
        break  # ne bi trebalo da se desi
    ops.reverse()
    return ops


def s1_classify_field(entered_raw: str, reference_raw: str, other_refs_raw: list[str]) -> dict:
    """Vraca tacnost (strict/lenient, doslovno) i, ako nije tacno, tacno
    JEDNU klasifikaciju za raspodelu tipova gresaka (sekcija 5.2):
    sentence_label (sentence_order/word_order, na nivou cele recenice) ILI
    word_labels (jedan po ne-poklopljenoj reci iz Levenstajn poravnanja --
    word_substitution/word_omission/word_insertion/intrusion/cross_intrusion).
    Ova dva su medjusobno iskljuciva (hijerarhija: sentence_order pre
    word_order pre poravnanja po recima) -- ali su ODVOJENI od tacnosti po
    reci (n_match/n_ref_words), koja se RACUNA IZ PORAVNANJA UVEK, bez
    obzira na hijerarhiju, jer "tacnost po reci" (5.1) i "tipovi gresaka"
    (5.2) su dve razlicite, komplementarne mere, ne jedna izvedena iz druge."""
    entered_strict = s1_normalize_strict(entered_raw)
    reference_strict = s1_normalize_strict(reference_raw)
    correct = entered_strict == reference_strict
    correct_lenient = s1_normalize_lenient(entered_raw) == s1_normalize_lenient(reference_raw)

    ref_words = reference_strict.split()
    entered_words = entered_strict.split()
    n_ref_words = len(ref_words)

    ops = _s1_word_align(ref_words, entered_words)
    n_match = sum(1 for op in ops if op[0] == "match")

    sentence_label = None
    word_labels = []
    if not correct:
        other_norm = [s1_normalize_strict(o) for o in other_refs_raw]
        if entered_strict in other_norm:
            sentence_label = "sentence_order"
        elif entered_words and sorted(entered_words) == sorted(ref_words):
            sentence_label = "word_order"
        else:
            other_words_pool = set()
            for o in other_norm:
                other_words_pool.update(o.split())
            ref_words_set = set(ref_words)
            for op, rw, ew in ops:
                if op == "match":
                    continue
                if op == "del":
                    word_labels.append("word_omission")
                else:
                    if ew in other_words_pool and ew not in ref_words_set:
                        word_labels.append("cross_intrusion")
                    elif ew not in ref_words_set:
                        word_labels.append("intrusion")
                    else:
                        word_labels.append("word_insertion" if op == "ins" else "word_substitution")

    return {
        "correct": correct, "correct_lenient": correct_lenient,
        "n_match": n_match, "n_ref_words": n_ref_words,
        "sentence_label": sentence_label, "word_labels": word_labels,
    }


def _s1_norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def s1_two_proportion_ztest(x1: int, n1: int, x2: int, n2: int):
    """Dvoproporcioni z-test (samo standardna biblioteka, math.erf za
    p-vrednost). Vraca (z, p) ili (None, None) ako neka grupa nema
    zapazanja."""
    if n1 == 0 or n2 == 0:
        return None, None
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    if p_pool <= 0 or p_pool >= 1:
        return 0.0, 1.0
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    p_value = 2 * (1 - _s1_norm_cdf(abs(z)))
    return z, p_value


def s1_typing_measures(intervals_by_class: dict) -> dict:
    """Sekcija 6: brzina kucanja u naletu (znakova/s, samo iz razmaka <
    S1_BURST_MAX_MS) i struktura pauza (broj/trajanje razmaka >=
    S1_PAUSE_MIN_MS), po klasi duzine."""
    out = {}
    for cls, intervals in intervals_by_class.items():
        bursts = [x for x in intervals if x < S1_BURST_MAX_MS]
        pauses = [x for x in intervals if x >= S1_PAUSE_MIN_MS]
        burst_rate = (len(bursts) / (sum(bursts) / 1000)) if bursts and sum(bursts) > 0 else None
        out[cls] = {
            "burst_rate_cps": burst_rate,
            "n_bursts": len(bursts),
            "n_pauses": len(pauses),
            "avg_pause_ms": stats.mean(pauses) if pauses else None,
            "total_pause_ms": sum(pauses),
        }
    return out


def s1_item_meta(item_starts):
    """(path, item) -> (participant_id, n, item_id) -- veza ka referenci u
    items_S1.json, potrebna svakom dogadjaju koji sam po sebi ne nosi n/pid
    (peek_start, field_submitted)."""
    meta = {}
    for e in item_starts:
        meta[(e.get("_path"), e.get("item"))] = (e.get("_participant"), str(e.get("_n")), e.get("item_id"))
    return meta


def s1_collect_field_revisions(all_events):
    """(path, item, sentence_index) -> SVE field_submitted verzije (ne samo
    is_final), sortirane po "revision". Tacka 1 uputstva ("Prosiri
    belezenje"): medjuverzije unosa su mera, ne sum -- ranije verzije se ne
    odbacuju, is_final ostaje rezervisano za primarnu tacnost."""
    by_key = defaultdict(list)
    for e in all_events:
        if e.get("event") == "field_submitted":
            key = (e.get("_path"), e.get("item"), e.get("sentence_index"))
            by_key[key].append(e)
    for key in by_key:
        by_key[key].sort(key=lambda e: e.get("revision", 0))
    return by_key


def s1_collect_peeks(all_events):
    """(path, item) -> lista {t_start, t_end, snapshot} sortirana po t_start.
    snapshot je {sentence_index: uneti_tekst} iz fields_snapshot na
    peek_start (tacka 2 uputstva: stanje svih N polja u trenutku uvida,
    ukljucujuci jos nepotvrdjenu vrednost u fokusiranom polju)."""
    starts, ends = defaultdict(list), defaultdict(list)
    for e in all_events:
        key = (e.get("_path"), e.get("item"))
        if e.get("event") == "peek_start":
            starts[key].append(e)
        elif e.get("event") == "peek_end":
            ends[key].append(e)
    peeks_by_item = defaultdict(list)
    for key, start_list in starts.items():
        s_sorted = sorted(start_list, key=lambda e: e.get("t", 0))
        e_sorted = sorted(ends.get(key, []), key=lambda e: e.get("t", 0))
        for s, en in zip(s_sorted, e_sorted):
            snapshot = {fs["sentence_index"]: fs["text"] for fs in (s.get("fields_snapshot") or [])}
            peeks_by_item[key].append({"t_start": s.get("t"), "t_end": en.get("t"), "snapshot": snapshot})
    return peeks_by_item


def s1_corrections_after_peek(peeks_by_item, revisions_by_field, item_meta, ref_index):
    """Tacka 3 uputstva: za svako polje, uporedjuje vrednost NEPOSREDNO PRE
    uvida (snimak sa peek_start) sa vrednoscu POSLE uvida (poslednja
    revizija sa t > peek_end, do sledeceg uvida ili kraja stavke -- ako
    nema nove revizije u tom prozoru, vrednost se smatra nepromenjenom, pa
    se NE racuna kao izmena). Vraca listu izmenjenih polja, svaka
    klasifikovana po TRANZICIJI tacnosti (strict): corrected/regressed/
    revised_still_incorrect/revised_still_correct -- vrsta izmene trazena
    uputstvom, izvedena iz vec postojece definicije tacnosti umesto nove
    posebne taksonomije."""
    results = []
    for (path, item), peeks in peeks_by_item.items():
        meta = item_meta.get((path, item))
        if meta is None:
            continue
        pid, n, item_id = meta
        by_idx = ref_index.get((pid, n, item_id))
        if by_idx is None:
            continue
        for i, peek in enumerate(peeks):
            next_t_start = peeks[i + 1]["t_start"] if i + 1 < len(peeks) else float("inf")
            if peek["t_end"] is None or next_t_start is None:
                continue
            for sentence_index, before_text in peek["snapshot"].items():
                ref_entry = by_idx.get(sentence_index)
                if ref_entry is None:
                    continue
                revs = revisions_by_field.get((path, item, sentence_index), [])
                after_candidates = [
                    r for r in revs
                    if r.get("t") is not None and peek["t_end"] < r["t"] <= next_t_start
                ]
                after_text = after_candidates[-1]["entered_text"] if after_candidates else before_text
                before_norm, after_norm = s1_normalize_strict(before_text), s1_normalize_strict(after_text)
                if before_norm == after_norm:
                    continue
                ref_norm = s1_normalize_strict(ref_entry["text"])
                before_correct, after_correct = before_norm == ref_norm, after_norm == ref_norm
                if not before_correct and after_correct:
                    kind = "corrected"
                elif before_correct and not after_correct:
                    kind = "regressed"
                elif not before_correct and not after_correct:
                    kind = "revised_still_incorrect"
                else:
                    kind = "revised_still_correct"
                results.append({"path": path, "item": item, "n": n, "sentence_index": sentence_index, "kind": kind})
    return results


def s1_permutation_measure(revisions_by_field, item_meta, ref_index):
    """Tacka 4 uputstva: da li je recenica PRVO uneta u pogresno numerisano
    polje pa PREMESTENA. Prva NEPRAZNA revizija polja X se poredi sa
    referencama SVIH OSTALIH polja iste stavke; poklapanje sa poljem Y != X
    je kandidat za permutaciju. "Ispravljena" ako finalna (najveca
    revizija) vrednost polja X pogadja SOPSTVENU referencu -- inace je
    "neispravljena" (isti slucaj koji sentence_order tip greske u
    s1_classify_field vec hvata na finalnoj vrednosti, ovde eksplicitno
    prijavljen kao par sa pocetnim stanjem)."""
    by_item = defaultdict(dict)
    for (path, item, sentence_index), revs in revisions_by_field.items():
        by_item[(path, item)][sentence_index] = revs

    results = []
    for (path, item), fields_map in by_item.items():
        meta = item_meta.get((path, item))
        if meta is None:
            continue
        pid, n, item_id = meta
        by_idx = ref_index.get((pid, n, item_id))
        if by_idx is None:
            continue
        for sentence_index, revs in fields_map.items():
            ref_entry = by_idx.get(sentence_index)
            if ref_entry is None or not revs:
                continue
            first_nonempty = next((r for r in revs if (r.get("entered_text") or "").strip()), None)
            if first_nonempty is None:
                continue
            first_norm = s1_normalize_strict(first_nonempty["entered_text"])
            own_ref_norm = s1_normalize_strict(ref_entry["text"])
            if first_norm == own_ref_norm:
                continue
            from_field = next(
                (other_idx for other_idx, other_ref in by_idx.items()
                 if other_idx != sentence_index and first_norm == s1_normalize_strict(other_ref["text"])),
                None,
            )
            if from_field is None:
                continue
            final_norm = s1_normalize_strict(revs[-1].get("entered_text", ""))
            results.append({
                "path": path, "item": item, "n": n, "field": sentence_index,
                "from_field": from_field, "corrected": final_norm == own_ref_norm,
            })
    return results


def s1_analyze(blocks, ref_index, detail=False):
    all_events = []
    for path, session, events in blocks:
        for e in events:
            e["_path"] = str(path)
            e["_participant"] = session.get("participant_id") if session else None
            # items_S1.json ima N kao string kljuc ("3"/"5"/"7") -- string i ovde,
            # da se izbegne neuskladjenost tipova sa ref_index/resolved nizvodno.
            e["_n"] = str(session.get("n_fields")) if session else None
        all_events.extend(events)

    item_starts = [e for e in all_events if e.get("event") == "item_start"]
    field_submitted_all = [e for e in all_events if e.get("event") == "field_submitted"]
    field_submitted = [e for e in field_submitted_all if e.get("is_final")]
    encoding_ends = [e for e in all_events if e.get("event") == "encoding_end"]
    peek_events = [e for e in all_events if e.get("event") in ("peek_start", "peek_end")]

    n_items = len(item_starts)
    print("=" * 72)
    print(f"Blokova: {len(blocks)}  Stavki: {n_items}  Recenica (field_submitted, is_final=true): "
          f"{len(field_submitted)}  (ukupno field_submitted dogadjaja, sve posete: {len(field_submitted_all)})")
    print("=" * 72)

    # --- provera: broj is_final polja mora biti tacno stavke * N, po bloku ---
    expected_fields = 0
    actual_by_block = Counter()
    for path, session, events in blocks:
        if session is None:
            continue
        n_fields = session.get("n_fields")
        block_items = {e["item"] for e in events if e.get("event") == "item_start"}
        expected_fields += len(block_items) * (n_fields or 0)
    for s in field_submitted:
        actual_by_block[s.get("_path")] += 1
    actual_fields = sum(actual_by_block.values())
    check_status = "OK" if actual_fields == expected_fields else "NESLAGANJE"
    print(f"Provera broja polja: is_final dogadjaja={actual_fields}, ocekivano (stavke x N)={expected_fields}  [{check_status}]")

    # --- resolucija svakog field_submitted na referencu ---
    item_n = {(e.get("_path"), e.get("item")): e.get("_n") for e in item_starts}
    last_submit = {}
    for s in field_submitted:
        key = (s.get("_path"), s.get("item"), s.get("sentence_index"))
        last_submit[key] = s

    resolved = []
    unresolved_refs = 0
    for s in last_submit.values():
        pid, n = s.get("_participant"), str(s.get("_n"))
        item_id = s.get("item_id")
        by_idx = ref_index.get((pid, n, item_id))
        sentence_index = s.get("sentence_index")
        if by_idx is None or sentence_index not in by_idx:
            unresolved_refs += 1
            continue
        ref_entry = by_idx[sentence_index]
        other_refs = [v["text"] for k, v in by_idx.items() if k != sentence_index]
        cls = s1_classify_field(s.get("entered_text", ""), ref_entry["text"], other_refs)
        subclass = s1_classify_subclass(s.get("entered_text", ""), ref_entry["text"])
        resolved.append({
            "path": s.get("_path"), "n": n, "item": s.get("item"), "item_id": item_id,
            "sentence_index": sentence_index, "length_class": ref_entry["length_class"],
            "source": ref_entry["source"], "is_question": ref_entry["is_question"],
            "reference_raw": ref_entry["text"], "entered_raw": s.get("entered_text", ""),
            **cls, "subclass": subclass,
            "first_keystroke_ms": s.get("first_keystroke_ms"),
            "backspace_count": s.get("backspace_count"),
            "total_input_ms": s.get("total_input_ms"),
            "inter_key_intervals": s.get("inter_key_intervals") or [],
        })

    if unresolved_refs:
        print(f"\nUPOZORENJE: {unresolved_refs} field_submitted dogadjaja nije moglo da se poveze sa "
              f"items_S1.json (nepoznat participant_id/n/item_id/sentence_index -- proveriti da li su "
              f"podaci generisani istim seedom kao log).")

    if not resolved:
        print("\n(Nema recenica koje su se mogle povezati sa referencom -- ostatak izvestaja se preskace.)")
        print()
        return

    ns = sorted({r["n"] for r in resolved}, key=str)

    # --- tacnost po reci (PRIMARNA) i po recenici (SEKUNDARNA), strict/lenient, po N ---
    print("\nTacnost po reci (primarna) i po recenici (sekundarna), strict vs lenient, po N:")
    for n in ns:
        rows = [r for r in resolved if r["n"] == n]
        word_matches = sum(r["n_match"] for r in rows)
        word_total = sum(r["n_ref_words"] for r in rows)
        word_acc_strict = word_matches / word_total if word_total else 0
        sent_acc_strict = sum(r["correct"] for r in rows) / len(rows) if rows else 0
        sent_acc_lenient = sum(r["correct_lenient"] for r in rows) / len(rows) if rows else 0
        # lenient tacnost po reci: nezavisno poravnanje na lenient-normalizovanim tokenima
        lenient_word_matches = 0
        lenient_word_total = 0
        for r in rows:
            le = s1_normalize_lenient(r["entered_raw"]).split()
            lr = s1_normalize_lenient(r["reference_raw"]).split()
            lenient_word_total += len(lr)
            lenient_word_matches += sum(1 for op in _s1_word_align(lr, le) if op[0] == "match")
        word_acc_lenient = lenient_word_matches / lenient_word_total if lenient_word_total else 0
        print(f"  N={n}:")
        print(f"    po reci:     strict {word_acc_strict*100:5.1f}%   lenient {word_acc_lenient*100:5.1f}%   "
              f"razlika {100*(word_acc_lenient-word_acc_strict):+5.1f}pp  (reci={word_total})")
        print(f"    po recenici: strict {sent_acc_strict*100:5.1f}%   lenient {sent_acc_lenient*100:5.1f}%   "
              f"razlika {100*(sent_acc_lenient-sent_acc_strict):+5.1f}pp  (recenica={len(rows)})")

    # --- tacnost po klasi duzine recenice ---
    print("\nTacnost po reci, po klasi duzine recenice:")
    by_length_class = defaultdict(list)
    for r in resolved:
        by_length_class[r["length_class"]].append(r)
    for cls in ("low", "medium", "high"):
        rows = by_length_class.get(cls, [])
        wm = sum(r["n_match"] for r in rows)
        wt = sum(r["n_ref_words"] for r in rows)
        print(f"  {cls:8s} {ac.pct(wm, wt) if wt else 'n/a':>8s}  (reci={wt}, recenica={len(rows)})")

    # --- raspodela tipova gresaka (5.2), na netacnim recenicama ---
    print("\nRaspodela tipova gresaka (samo netacne recenice, strict):")
    error_counts = Counter()
    for r in resolved:
        if r["correct"]:
            continue
        if r["sentence_label"]:
            error_counts[r["sentence_label"]] += 1
        else:
            for lbl in r["word_labels"]:
                error_counts[lbl] += 1
    total_errors = sum(error_counts.values())
    for t in ("word_substitution", "word_omission", "word_insertion", "word_order",
              "sentence_order", "intrusion", "cross_intrusion"):
        print(f"  {t:18s} {ac.pct(error_counts.get(t, 0), total_errors) if total_errors else 'n/a':>8s}  "
              f"(n={error_counts.get(t, 0)})")

    # --- podklase (5.3), sa izdvojenim udelom paraphrase ---
    print("\nRaspodela podklasa (na sirovim vrednostima, odvojeno od tipova gore):")
    subclass_counts = Counter(r["subclass"] for r in resolved if r["subclass"])
    for sc in ("case_only", "diacritic_only", "punctuation_only", "paraphrase"):
        n_sc = subclass_counts.get(sc, 0)
        note = ""
        if sc == "punctuation_only":
            note = "  [TACNO -- zavrsna tacka se zanemaruje]"
        elif sc == "paraphrase":
            note = "  [NETACNO, ali izdvojeno -- najvrednija mera ovog scenarija]"
        elif n_sc:
            note = "  [NETACNO]"
        print(f"  {sc:18s} n={n_sc:4d}{note}")

    # --- ponovni uvid: broj po stavci, odnos prema N, ukupno vreme ---
    print("\nBroj ponovnih uvida po stavci i ukupno vreme u uvidu, po N:")
    peek_start_by_item = defaultdict(int)
    peek_ms_by_item = defaultdict(float)
    for e in all_events:
        if e.get("event") == "peek_start":
            peek_start_by_item[(e.get("_path"), e.get("item"))] += 1
        if e.get("event") == "peek_end" and e.get("peek_duration_ms") is not None:
            peek_ms_by_item[(e.get("_path"), e.get("item"))] += e["peek_duration_ms"]
    by_n_peeks = defaultdict(list)
    by_n_peek_ms = defaultdict(list)
    for key, n in item_n.items():
        by_n_peeks[n].append(peek_start_by_item.get(key, 0))
        by_n_peek_ms[n].append(peek_ms_by_item.get(key, 0.0))
    for n in ns:
        vals = by_n_peeks.get(n, [])
        ms_vals = by_n_peek_ms.get(n, [])
        if vals:
            print(f"  N={n}: prosek {stats.mean(vals):.2f} uvida po stavci, "
                  f"ukupno vreme u uvidu prosek {stats.mean(ms_vals):.0f} ms  (stavki={len(vals)})")

    # --- tacka 3: izmene POSLE uvida (poredjenje snimka sa peek_start
    # naspram sledece revizije polja) ---
    item_meta = s1_item_meta(item_starts)
    revisions_by_field = s1_collect_field_revisions(all_events)
    peeks_by_item = s1_collect_peeks(all_events)
    corrections = s1_corrections_after_peek(peeks_by_item, revisions_by_field, item_meta, ref_index)
    total_peeks = sum(len(v) for v in peeks_by_item.values())
    print(f"\nIzmene polja POSLE uvida (poredjenje sa stanjem na pocetku uvida):")
    if total_peeks:
        print(f"  {len(corrections)} izmenjenih polja od {total_peeks} uvida "
              f"({len(corrections) / total_peeks:.2f} po uvidu)")
        kind_counts = Counter(c["kind"] for c in corrections)
        for k in ("corrected", "regressed", "revised_still_incorrect", "revised_still_correct"):
            print(f"    {k:24s} n={kind_counts.get(k, 0)}")
    else:
        print("  (nema uvida u ucitanim logovima)")

    # --- tacka 4: permutacija -- recenica prvo u pogresnom polju, pa premestena ---
    permutations = s1_permutation_measure(revisions_by_field, item_meta, ref_index)
    print(f"\nPermutacija recenica (prva verzija polja odgovarala tudjoj referenci iste stavke): "
          f"{len(permutations)} slucajeva")
    if permutations:
        corrected_n = sum(1 for p in permutations if p["corrected"])
        print(f"    ispravljena (finalni odgovor tacan)        n={corrected_n}")
        print(f"    neispravljena (finalni odgovor i dalje pogresan) n={len(permutations) - corrected_n}")

    # --- trajanje faze kodiranja, odvojeno user/auto ---
    print("\nTrajanje faze kodiranja (encoding_actual_ms), medijana / p90, po N i po nacinu prelaska:")
    encoding_by_n_mode = defaultdict(list)
    for e in encoding_ends:
        n = item_n.get((e.get("_path"), e.get("item")))
        mode = e.get("mode", "?")
        if e.get("encoding_actual_ms") is not None:
            encoding_by_n_mode[(n, mode)].append(e["encoding_actual_ms"])
    for n in ns:
        for mode in ("user", "auto"):
            vals = sorted(encoding_by_n_mode.get((n, mode), []))
            if vals:
                print(f"  N={n} {mode:4s}: medijana {stats.median(vals):6.0f} ms   "
                      f"p90 {ac.percentile(vals, 90):6.0f} ms  (n={len(vals)})")
            else:
                print(f"  N={n} {mode:4s}: n/a")

    # --- mere kucanja: brzina u naletu i struktura pauza, po klasi duzine ---
    print("\nBrzina kucanja u naletu (znakova/s, razmaci < 500 ms) i struktura pauza "
          "(razmaci >= 1000 ms), po klasi duzine:")
    intervals_by_class = defaultdict(list)
    for r in resolved:
        intervals_by_class[r["length_class"]].extend(r["inter_key_intervals"])
    typing = s1_typing_measures(intervals_by_class)
    for cls in ("low", "medium", "high"):
        m = typing.get(cls)
        if not m or m["burst_rate_cps"] is None:
            print(f"  {cls:8s} n/a")
            continue
        avg_pause = f"{m['avg_pause_ms']:.0f} ms" if m["avg_pause_ms"] is not None else "n/a"
        print(f"  {cls:8s} brzina u naletu {m['burst_rate_cps']:.2f} znak/s (n={m['n_bursts']})   "
              f"pauze: {m['n_pauses']} (prosek {avg_pause}, ukupno {m['total_pause_ms']:.0f} ms)")

    # --- efekat pozicije: tacnost po rednom broju recenice unutar stavke, po N ---
    print("\nEfekat pozicije: tacnost po reci, po rednom broju recenice unutar stavke, po N:")
    for n in ns:
        rows = [r for r in resolved if r["n"] == n]
        by_pos = defaultdict(lambda: [0, 0])
        for r in rows:
            acc = by_pos[r["sentence_index"]]
            acc[0] += r["n_match"]
            acc[1] += r["n_ref_words"]
        parts = []
        for pos in sorted(by_pos):
            wm, wt = by_pos[pos]
            parts.append(f"{pos}:{ac.pct(wm, wt) if wt else 'n/a'}")
        print(f"  N={n}: " + "  ".join(parts))

    # --- znaci odustajanja: trend tacnosti kroz blok ---
    print("\nZnaci odustajanja (prva/poslednja trecina stavki po bloku):")
    acc_by_item_path = defaultdict(list)
    for r in resolved:
        acc_by_item_path[(r["path"], r["item"])].append(r["correct"])
    for path, session, events in blocks:
        item_indices = sorted({e["item"] for e in events if e.get("event") == "item_start"})
        if len(item_indices) < 6:
            print(f"  {path}: nema dovoljno stavki za ovu proveru (ima {len(item_indices)}, potrebno bar 6)")
            continue
        third = max(1, len(item_indices) // 3)
        first_items, last_items = item_indices[:third], item_indices[-third:]

        def acc_for(idx_list):
            vals = []
            for idx in idx_list:
                vals.extend(acc_by_item_path.get((str(path), idx), []))
            return sum(vals) / len(vals) if vals else float("nan")

        acc_first, acc_last = acc_for(first_items), acc_for(last_items)
        flag = "  <- pad tacnosti: mozda odustajanje" if (
            not math.isnan(acc_first) and not math.isnan(acc_last) and acc_last < acc_first - 0.1
        ) else ""
        print(f"  {path}: tacnost prva/poslednja trecina {acc_first*100:.0f}%/{acc_last*100:.0f}%{flag}")

    print()

    s1_source_confound_check(resolved)

    if detail:
        peeks_before = s1_peeks_before_field(resolved, all_events)
        s1_print_detail_table(resolved, peeks_before)


def s1_peeks_before_field(resolved, all_events):
    """Broj F2-uvida (peek_start) u istoj stavci koji su se desili PRE nego
    sto je dato polje stvarno zavrseno.

    Trenutak zavrsetka polja NIJE "t" njegovog is_final:true dogadjaja --
    scenarios/s1.js emituje is_final:true za SVIH N polja zajedno, u istom
    prolazu, na kraju cele stavke (finishEntry), pa taj "t" ne razlikuje
    kad je koje polje stvarno popunjeno. Umesto toga koristi se poslednji
    "prirodan" (is_final:false) field_submitted za to polje -- blur pri
    prelasku tastaturom na sledece polje, koji se desava u stvarnom
    trenutku zavrsetka. Jedini izuzetak je poslednje polje stavke, koje
    nikad prirodno ne izgubi fokus (Enter/Tab na njemu direktno zove
    finishEntry) -- za njega je is_final:true i jedini raspoloziv i tacan
    signal, jer se emituje odmah pri tom pritisku."""
    peek_starts_by_item = defaultdict(list)
    natural_t = {}
    final_t = {}
    for e in all_events:
        if e.get("t") is None:
            continue
        if e.get("event") == "peek_start":
            peek_starts_by_item[(e.get("_path"), e.get("item"))].append(e["t"])
        elif e.get("event") == "field_submitted":
            key = (e.get("_path"), e.get("item"), e.get("sentence_index"))
            if e.get("is_final"):
                final_t[key] = e["t"]
            elif key not in natural_t or e["t"] > natural_t[key]:
                natural_t[key] = e["t"]

    counts = {}
    for r in resolved:
        key = (r["path"], r["item"], r["sentence_index"])
        completion_t = natural_t.get(key, final_t.get(key))
        if completion_t is None:
            counts[key] = 0
            continue
        ts = peek_starts_by_item.get((r["path"], r["item"]), [])
        counts[key] = sum(1 for t in ts if t < completion_t)
    return counts


S1_DETAIL_COLUMNS = [
    "Stavka", "Redni broj", "Klasa duzine", "Izvorna recenica", "Uneti tekst",
    "Tacnost po reci", "Tip greske", "Podklasa", "first_keystroke_ms",
    "Broj brisanja", "Broj uvida pre unosa",
]


def s1_print_detail_table(resolved, peeks_before):
    """--detail (SPEC_S1_demo.md sekcija 9, korak 6): tabela po recenici.
    Dopunjava zbirni izvestaj, ne zamenjuje ga -- poziva se posle njega,
    isti obrazac kao s2_print_detail_table."""
    print("=" * 72)
    print("DETALJI PO RECENICI (--detail)")
    print("=" * 72)

    rows = []
    for r in sorted(resolved, key=lambda x: (x["path"], x["n"], x["item"], x["sentence_index"])):
        key = (r["path"], r["item"], r["sentence_index"])
        if r["sentence_label"]:
            error_type = r["sentence_label"]
        elif r["word_labels"]:
            error_type = "+".join(sorted(set(r["word_labels"])))
        else:
            error_type = "-"
        rows.append([
            str(r["item"]),
            str(r["sentence_index"]),
            r["length_class"],
            r["reference_raw"],
            r["entered_raw"],
            f"{r['n_match']}/{r['n_ref_words']}",
            error_type,
            r["subclass"] or "-",
            f"{r['first_keystroke_ms']:.0f}" if r["first_keystroke_ms"] is not None else "-",
            str(r["backspace_count"]) if r["backspace_count"] is not None else "-",
            str(peeks_before.get(key, 0)),
        ])

    print(ac.format_table(S1_DETAIL_COLUMNS, rows))
    print()


def s1_source_confound_check(resolved):
    """Tacka F uputstva za spajanje jezgra (odlozena iz koraka D): tacnost
    po polju source (enron naspram constructed), sa dvoproporcionim
    z-testom. Ako se dve grupe ZNACAJNO razlikuju (p < S1_CONFOUND_ALPHA),
    poreklo recenice je konfund i MORA se izvestiti -- ne samo ispisati
    brojeve, nego eksplicitno upozoriti."""
    print("Tacnost po polju 'source' (enron naspram constructed) -- tacka F:")
    by_source = defaultdict(lambda: [0, 0, 0, 0])  # [word_match, word_total, sent_correct, sent_total]
    for r in resolved:
        acc = by_source[r["source"]]
        acc[0] += r["n_match"]
        acc[1] += r["n_ref_words"]
        acc[2] += int(r["correct"])
        acc[3] += 1

    for src in ("enron", "constructed"):
        wm, wt, sc, st = by_source.get(src, [0, 0, 0, 0])
        print(f"  {src:12s} po reci: {ac.pct(wm, wt) if wt else 'n/a':>8s}  (reci={wt})   "
              f"po recenici: {ac.pct(sc, st) if st else 'n/a':>8s}  (recenica={st})")

    wm_e, wt_e, sc_e, st_e = by_source.get("enron", [0, 0, 0, 0])
    wm_c, wt_c, sc_c, st_c = by_source.get("constructed", [0, 0, 0, 0])

    z_word, p_word = s1_two_proportion_ztest(wm_e, wt_e, wm_c, wt_c)
    if p_word is not None:
        print(f"\n  Dvoproporcioni z-test, tacnost po reci: z={z_word:+.2f}  p={p_word:.4f}")
        if p_word < S1_CONFOUND_ALPHA:
            diff_pp = 100 * (wm_e / wt_e - wm_c / wt_c) if wt_e and wt_c else 0
            print(f"  UPOZORENJE: poreklo recenice (source) je ZNACAJAN KONFUND "
                  f"(p={p_word:.4f} < {S1_CONFOUND_ALPHA}), razlika {diff_pp:+.1f}pp po reci "
                  f"(enron - constructed). Rezultati po klasi duzine/N treba tumaciti uz ovo u vidu, "
                  f"ili balans porekla po stavci (tacka E) preispitati pre glavne studije.")
        else:
            print(f"  Nema znacajne razlike (p >= {S1_CONFOUND_ALPHA}) -- poreklo recenice nije konfund "
                  f"po ovoj meri.")
    else:
        print("\n  Nedovoljno podataka za z-test (jedna od grupa nema zapazanja).")


# ==========================================================================
# main -- grupise blokove po session["scenario"] i grana se.
# ==========================================================================

def session_normalize_scenario(scen):
    """S3a/S3b su varijante istog zadatka -- za potrebe provere prisustva u
    sesiji (jedan zadatak S3 po sesiji, ne dva) racunaju se kao "S3"."""
    if scen in ("S3a", "S3b"):
        return "S3"
    return scen


def find_session_logfiles():
    paths = []
    for d in SESSION_LOG_DIRS:
        if d.is_dir():
            paths.extend(sorted(d.glob("*.jsonl")))
    return paths


def print_session_summary(session_id, blocks):
    """Tacka 4/5 odobrenja integracije sesije: zbirni prikaz sva tri zadatka
    jedan pored drugog, sa jasnom prijavom nedostajuceg zadatka -- to NIJE
    greska, nego ocekivano stanje kad ispitanik prekine sesiju."""
    by_task = {}
    for path, session, events in blocks:
        if session is None:
            continue
        scen = session_normalize_scenario(session.get("scenario"))
        by_task[scen] = (path, session, events)

    ref_session = next(iter(by_task.values()))[1]
    code = ref_session.get("participant_id")
    task_order = ref_session.get("task_order") or []
    visit_number = ref_session.get("visit_number")
    order = task_order or ["S1", "S2", "S3"]

    print("=" * 72)
    print(f"PREGLED SESIJE  (--session {session_id})")
    print("=" * 72)
    print(f"sifra ispitanika:  {code}")
    print(f"redosled zadataka: {' -> '.join(order)}" if task_order else
          "redosled zadataka: (nepoznat -- header ne sadrzi task_order)")
    print(f"redni broj posete: {visit_number if visit_number is not None else '(nepoznat)'}")
    print("-" * 72)

    missing = []
    for i, task in enumerate(order, start=1):
        entry = by_task.get(task)
        if entry is None:
            missing.append(task)
            print(f"  {i}. {task}: NEDOSTAJE u ovoj sesiji.")
            continue
        path, session, events = entry
        ts = [e["t"] for e in events if e.get("t") is not None]
        dur = f"{(max(ts) - min(ts)) / 1000:.1f}s" if len(ts) >= 2 else "n/a"
        print(f"  {i}. {task}: prisutan -- {path.name}  "
              f"({len(events)} dogadjaja, trajanje ~{dur}, "
              f"task_position={session.get('task_position')})")

    print("-" * 72)
    if missing:
        print(f"NAPOMENA: nedostaje {len(missing)} od {len(order)} zadatka u sesiji "
              f"({', '.join(missing)}). Ovo nije greska logovanja -- ocekivano je kad "
              f"ispitanik prekine sesiju pre kraja. Analiza ispod obuhvata samo prisutne "
              f"zadatke.")
    else:
        print("Sva tri zadatka sesije su prisutna.")
    print("=" * 72)
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logfiles", nargs="*", type=Path)
    ap.add_argument("--session", type=str,
                     help="Ucitaj celu sesiju po session_id umesto pojedinacnih logfiles -- "
                          "skenira logs/, s2-demo/logs/, s3-demo/logs/ (integracija sesije, "
                          "tacka 4/5), ispisuje zbirni pregled sva tri zadatka jedan pored "
                          "drugog i jasno prijavljuje nedostajuci zadatak, pa nastavlja sa "
                          "punom analizom za svaki prisutan zadatak.")
    ap.add_argument("--data", type=Path,
                     help="Podrazumevano: s2-demo/data odn. s3-demo/data u odnosu na ovaj fajl, "
                          "zavisno od scenarija otkrivenog u svakoj grupi blokova.")
    ap.add_argument("--detail", action="store_true",
                     help="za S2 i S1: dopuni zbirni izvestaj tabelom po polju/recenici "
                          "(stavka, polje/redni broj, tezina/klasa duzine, tacna/uneta vrednost, "
                          "tacnost, tip greske, podklasa, first_keystroke_ms, backspace_count, "
                          "broj povrataka/uvida pre unosa)")
    args = ap.parse_args()

    if args.session:
        if args.logfiles:
            print("UPOZORENJE: logfiles se ignorisu kad je naveden --session.", file=sys.stderr)
        candidate_paths = find_session_logfiles()
        all_blocks = ac.load_events(candidate_paths)
        blocks = [b for b in all_blocks if b[1] and b[1].get("session_id") == args.session]
        if not blocks:
            searched = ", ".join(str(d) for d in SESSION_LOG_DIRS)
            print(f"GRESKA: nijedan log sa session_id={args.session!r} nije pronadjen "
                  f"(pretrazeno: {searched}).", file=sys.stderr)
            sys.exit(1)
        print_session_summary(args.session, blocks)
    elif not args.logfiles:
        ap.error("navedi logfiles ili --session")
    else:
        blocks = ac.load_events(args.logfiles)

    by_scenario = defaultdict(list)
    for b in blocks:
        _, session, _ = b
        scen = session.get("scenario") if session else None
        by_scenario[scen].append(b)

    for scen, group in by_scenario.items():
        if scen == "S2":
            data_dir = args.data or (EEG_TASKS_ROOT / "s2-demo" / "data")
            s2_verify_hashes_or_die(group, data_dir)
            items_data = s2_load_items(data_dir)
            if items_data is None:
                print(f"UPOZORENJE: {data_dir / 'items_S2.json'} ne postoji -- tacnost i tipologija "
                      f"gresaka ce biti preskoceni (pokreni prvo generate_stimuli.py --scenario S2).",
                      file=sys.stderr)
            ref_index = s2_build_reference_index(items_data) if items_data else {}
            s2_analyze(group, ref_index, detail=args.detail)
        elif scen in ("S3a", "S3b"):
            data_dir = args.data or (EEG_TASKS_ROOT / "s3-demo" / "data")
            s3_verify_hashes_or_die(group, data_dir)
            s3_analyze(group)
        elif scen == "S1":
            data_dir = args.data or (EEG_TASKS_ROOT / "data")
            s1_verify_hashes_or_die(group, data_dir)
            items_data = s1_load_items(data_dir)
            if items_data is None:
                print(f"UPOZORENJE: {data_dir / 'items_S1.json'} ne postoji -- tacnost i tipologija "
                      f"gresaka ce biti preskoceni (pokreni prvo generate_stimuli.py --scenario S1).",
                      file=sys.stderr)
            ref_index = s1_build_reference_index(items_data) if items_data else {}
            s1_analyze(group, ref_index, detail=args.detail)
        else:
            paths = ", ".join(str(p) for p, _, _ in group)
            print(f"UPOZORENJE: {len(group)} blok(ova) bez prepoznatog 'scenario' polja "
                  f"(vrednost: {scen!r}) -- preskačem: {paths}", file=sys.stderr)


if __name__ == "__main__":
    main()
