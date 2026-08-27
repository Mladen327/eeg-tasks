"""Provera ispravnosti log datoteka za Scenario 2 (sekcija 10 uputstva).

Cita jednu ili vise .jsonl datoteka (jedan blok po datoteci) i ispisuje
sumarne statistike. Za razliku od Scenarija 3, tacnost se NE nalazi u logu
(sekcija 6.2) -- ovaj skript je poredi sa data/items_S2.json.

Upotreba:
    python analyze_log_s2.py logs/*.jsonl
    python analyze_log_s2.py logs/<SIFRA>_S2_5_20260826T101403Z.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics as stats
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent

SWITCH_MAX_DEVIATION_WARN_MS = 50


def sha256_of_file(path: Path) -> str:
    """Isti format kao app/task.js (bufToHashHex): 'sha256:' + hex, nad
    sirovim bajtovima fajla."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hashes_or_die(blocks, data_dir: Path):
    """Pre bilo kakve analize: za svaki blok sa session zaglavljem, uporedi
    items_hash/companies_hash iz loga sa hesom fajlova koje ovaj skript
    STVARNO cita (data/items_S2.json, data/companies.json). Prekida odmah
    na prvo neslaganje ili nedostajuce polje (sekcija 10 dopune uputstva) --
    log snimljen sa drugim seedom/brojem ucesnika bi inace davao besmislene
    (tiho pogresne) rezultate poredjenja tacnosti."""
    items_path = data_dir / "items_S2.json"
    companies_path = data_dir / "companies.json"
    if not items_path.exists() or not companies_path.exists():
        return  # load_items() dole vec ispisuje upozorenje i preskace tacnost
    expected_items_hash = sha256_of_file(items_path)
    expected_companies_hash = sha256_of_file(companies_path)

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

_DIACRITICS = str.maketrans({
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
_DIACRITICS_CASE_PRESERVING = str.maketrans({
    "č": "c", "ć": "c", "Č": "C", "Ć": "C",
    "ž": "z", "Ž": "Z", "š": "s", "Š": "S",
    "đ": "dj", "Đ": "Dj",
})


def normalize_strict(raw, field_name: str) -> str:
    s = str(raw).strip()
    if field_name in SPACING_FIELDS:
        s = re.sub(r"[\s./\-]", "", s)
    else:
        s = re.sub(r"\s", "", s)
    return s


def normalize_lenient(raw) -> str:
    s = str(raw).strip().lower()
    s = s.translate(_DIACRITICS)
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
# crtu/crticu za SPACING_FIELDS), legal_form_only ostaje NETACNO (u analyze()
# eksplicitno forsirano, iako bi u praksi vec ispalo netacno i bez toga,
# jer normalize_strict ne uklanja tacke van SPACING_FIELDS).
# --------------------------------------------------------------------------

LEGAL_FORMS = ["d.o.o.", "a.d.", "o.d."]
# Polja gde je razmak/tacka/kosa crta deo PRIKAZA (segmentacija, sekcija
# 3.3), ne sadrzaja -- spacing_only ima smisla samo za njih.
SPACING_FIELDS = {"pib", "registration_number", "contact_phone"}


def _strip_legal_form(s: str) -> tuple[str, str] | tuple[None, None]:
    for form in LEGAL_FORMS:
        if s.endswith(form):
            return s[: -len(form)].rstrip(), form
    return None, None


def classify_subclass(entered_raw: str, reference_raw: str, field_name: str) -> str | None:
    if not entered_raw or entered_raw == reference_raw:
        return None

    if entered_raw.lower() == reference_raw.lower():
        return "case_only"

    base_e, form_e = _strip_legal_form(entered_raw)
    base_r, form_r = _strip_legal_form(reference_raw)
    if base_e is not None and base_r is not None and base_e == base_r and form_e != form_r:
        return "legal_form_only"

    # case-preserving mapa (NE ista kao normalize_lenient, videti napomenu
    # uz _DIACRITICS_CASE_PRESERVING) -- ovde nas zanima ISKLJUCIVO
    # dijakritika, ne i case/spacing (ti imaju svoje, prioritetnije provere
    # iznad).
    diac_e = entered_raw.translate(_DIACRITICS_CASE_PRESERVING)
    diac_r = reference_raw.translate(_DIACRITICS_CASE_PRESERVING)
    if diac_e == diac_r:
        return "diacritic_only"

    if field_name in SPACING_FIELDS:
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

def _is_single_deletion(shorter: str, longer: str) -> bool:
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


def classify_error(entered: str, reference: str, other_refs: set[str]) -> str | None:
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
    if len(entered) == len(reference) - 1 and _is_single_deletion(entered, reference):
        return "omission"
    if len(entered) == len(reference) + 1 and _is_single_deletion(reference, entered):
        return "insertion"
    return "other"


# --------------------------------------------------------------------------
# Ucitavanje.
# --------------------------------------------------------------------------

def load_events(paths):
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


def load_items(data_dir: Path):
    path = data_dir / "items_S2.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_reference_index(items_data):
    """(participant_id, n_fields, item_id) -> {field_name: reference_value}
    i (participant_id, n_fields, item_id) -> {field_name: reference_value, ...ostala polja te stavke}
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


def pct(n, d):
    return f"{(100 * n / d):.1f}%" if d else "n/a"


def percentile(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


# --------------------------------------------------------------------------
# Analiza.
# --------------------------------------------------------------------------

def analyze(blocks, ref_index, detail=False):
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
        other_refs_strict = {normalize_strict(v, k) for k, v in refs.items() if k != field_name}
        entered_strict = normalize_strict(entered_raw, field_name)
        reference_strict = normalize_strict(reference_raw, field_name)
        entered_lenient = normalize_lenient(entered_raw)
        reference_lenient = normalize_lenient(reference_raw)
        weight = weight_by_key.get((pid, n, item_id, field_name), "?")
        position = position_by_key.get((pid, n, item_id, field_name), 999)
        error_type = classify_error(entered_strict, reference_strict, other_refs_strict)
        subclass = classify_subclass(entered_raw, reference_raw, field_name)
        # legal_form_only je NAMERNO netacno bez obzira sta strict poredjenje
        # kaze (pravni oblik je semanticki deo naziva firme) -- videti
        # napomenu uz classify_subclass. correct_lenient je ISKLJUCIVO za
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
        print(f"  {w:8s} {pct(sum(vals), len(vals)) if vals else 'n/a':>8s}  (n={len(vals)})")

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
            strict_pct = pct(sum(strict_vals), len(strict_vals))
            lenient_pct = pct(sum(lenient_vals), len(lenient_vals))
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
        print(f"  {field:22s} {pct(sum(vals), len(vals)):>8s}  (n={len(vals)})")

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
            print(f"  N={n}: {pct(sum(vals), len(vals))}  (stavki={len(vals)})")
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
        print(f"  {t:14s} {pct(error_counts.get(t, 0), total_errors) if total_errors else 'n/a':>8s}  (n={error_counts.get(t, 0)})")

    # --- podklase gresaka (na sirovim vrednostima, dopuna uputstva) ---
    # ODVOJENO od gornje raspodele -- ne ulazi u sest tipova. Racuna se nad
    # SVIM poljima (ne samo netacnim), jer case_only/diacritic_only/
    # spacing_only mogu da se jave i na polju koje je posle normalizacije
    # ipak correct=true (namerno, vidi napomenu uz classify_subclass).
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
            print(f"  {w:8s} medijana {stats.median(vals):7.0f} ms   p90 {percentile(vals, 90):7.0f} ms  (n={len(vals)})")
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
                          f"p90 {percentile(vals, 90):6.0f} ms  (n={len(vals)})")
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
            if max_dev > SWITCH_MAX_DEVIATION_WARN_MS:
                print(f"  UPOZORENJE: max odstupanje > {SWITCH_MAX_DEVIATION_WARN_MS} ms -- "
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
        print_detail_table(resolved, returns_before_field)


DETAIL_COLUMNS = [
    "Stavka", "Polje", "Tezina", "Tacna vrednost", "Uneto (sirovo)",
    "Tacno", "Tip greske", "Podklasa", "1.pritisak(ms)", "Backspace", "Povrataka pre",
]


def print_detail_table(resolved, returns_before_field):
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

    widths = [len(c) for c in DETAIL_COLUMNS]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(fmt_row(DETAIL_COLUMNS))
    print(fmt_row(["-" * w for w in widths]))
    for row in rows:
        print(fmt_row(row))
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logfiles", nargs="+", type=Path)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--detail", action="store_true",
                     help="dopuni zbirni izvestaj tabelom po polju (stavka, polje, tezina, "
                          "tacna/uneta vrednost, tacno DA/NE, tip greske, podklasa, "
                          "first_keystroke_ms, backspace_count, povrataka pre unosa)")
    args = ap.parse_args()

    blocks = load_events(args.logfiles)
    verify_hashes_or_die(blocks, args.data)

    items_data = load_items(args.data)
    if items_data is None:
        print(f"UPOZORENJE: {args.data / 'items_S2.json'} ne postoji -- tacnost i tipologija "
              f"gresaka ce biti preskoceni (pokreni prvo generate_stimuli_s2.py).", file=sys.stderr)
    ref_index = build_reference_index(items_data) if items_data else {}

    analyze(blocks, ref_index, detail=args.detail)


if __name__ == "__main__":
    main()
