# -*- coding: utf-8 -*-
"""Pravi data/sentences.json za Scenario 1 iz
All_sentences_for_Scenario_1_Transcription.xlsx, kolona "Serbian"
(2239 recenica, prevod Enron mobile skupa -- videti README ako se doda),
PLUS 100 rucno napisanih recenica (CONSTRUCTED_SENTENCES nize) za oblasti
administrativnog rada slabo zastupljene u enron korpusu. Svaki zapis u
sentences.json ima polje "source": "enron" ili "constructed" -- videti
interleave_by_source() za nacin na koji su te dve grupe rasporedjene.

Pokretanje:
    python build_sentences.py --input "putanja/do/All_sentences_for_Scenario_1_Transcription.xlsx"
    python build_sentences.py --input ... --out data/sentences.json

Redosled obrade (odstupanje od bukvalnog redosleda 1-8 iz uputstva,
namerno i objasnjeno ovde):

    1. Duzina (5-7 reci, sirovi tekst).
    2. Razresenje rodno obelezene naizmenicne forme (rekao/la -> rekao) --
       ovo je LOGICKI korak 6 iz uputstva, ali se MORA izvesti PRE provere
       zabranjenih znakova (korak 2), jer bi ga korak 2 inace izbacio zbog
       kose crte pre nego sto stigne do koraka 6 gde bi trebalo da bude
       SACUVAN i razresen (a ne izbacen). Skoro 20% recenica u ovom skupu
       koristi bas ovu konstrukciju (prevodilac je rodno neutralan engleski
       glagol preveo naizmenicnim oblikom), pa bi bukvalan redosled 1-8
       izbacio ogromnu vecinu upotrebljivog materijala. Kosa crta OSTAJE
       razlog za izbacivanje za SVAKU DRUGU upotrebu (datumi, razlomci,
       "i/ili" alternative, spojena vlastita imena) -- opsti filter kose
       crte i dalje radi POSLE ove zamene, nad svim preostalim slucajevima.
    3. Zabranjeni znakovi (cifre, zagrade, navodnici, %, zarez, kosa crta,
       & @ $) -- korak 2.
    4. Zavrsna interpunkcija mora postojati (. ? ili !, "!" se dalje
       normalizuje u "." u koraku 8) -- ovo NIJE eksplicitan kriterijum iz
       uputstva, nego preduslov za korak 8 ("zadrzi samo zavrsni znak") --
       ako ga uopste nema, ne moze se "zadrzati", pa se recenica izbacuje.
       Brojano odvojeno od cetiri zvanicna kriterijuma u izvestaju.
    5. Privatne/neposlovne recenice -- korak 3.
    6. Enron/americki energetski sektor -- korak 4.
    7. Zamena vlastitih imena (licna imena, firme iz data/companies.json,
       gradovi) -- korak 5, i istovremeno zamena preostalih ne-rodnih kosih
       crta koje su vec izbacene gore (znaci da se korak 5 ovde svodi na
       zamenu na FINALNOM skupu recenica, posle svih filtera, sto je
       jedini nacin da se izbegne rucno mapiranje imena u recenicama koje
       bi svakako bile izbacene).
    8. Uklanjanje dijakritike -- korak 7.
    9. Zavrsna interpunkcija: zadrzi samo tacku ili upitnik -- korak 8.

Kriterijum 3 (poslovna vs. licna prepiska) i kriterijum 4 (Enron/energetski
sektor) su implementirani kao liste kljucnih reci/izraza, PODRAZUMEVANO
ZADRZI (jer je vecina ovog korpusa vec poslovna prepiska -- Enron interni
mejlovi), izbaci samo na jasan signal. Ovo NIJE savrsena semanticka
klasifikacija (nije moguca bez pravog NLP modela za srpski, koji ovde nije
dostupan) -- kalibrisano rucnim pregledom celog skupa 5-7 reci kandidata
(374 posle filtera znakova, uputstvo trazi najmanje 100 po klasi). Zato
skript na kraju ispisuje 30 nasumicnih primera -- za rucnu proveru i dalje
podesavanje ovih lista ako pregled pokaze sistematsku gresku.

Zamena vlastitih imena (korak 5) je uradjena RUCNO, na nivou tacnog
posmatranog oblika reci (ne leme), jer srpski padezni sistem menja
zavrsetak imena (npr. "Stevea", "Steve-u", "Stanovu") -- generalizovan
pristup (zameni "Steve" pa nadji svaki oblik) ne radi pouzdano bez
NLP-a za srpski. Umesto toga: svaki OPAZEN oblik u finalnom skupu recenica
je posebna stavka u NAME_MAP, sa vrednoscu u ISTOM padezu/rodu (uz paznju
na slaganje glagola/prideva sa rodom zamenjenog imena, npr. "Dynegy
uputio" -> muski rod firme). Firme dolaze iz KORENA imena u
data/companies.json (COMPANY_ROOTS), gradovi iz iste liste gradova koju
vec koristi shared/generate_common.py -- radi doslednosti sa S2/S3.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

# Windows-ova podrazumevana konzolna kodna strana (cp1252) ne ume da ispise
# sve srpske dijakritike u izvestaju (izvestaj se ispisuje PRE uklanjanja
# dijakritike, korak 7 vazi samo za sentences.json). Prisilno UTF-8 na
# stdout/stderr, bezbedno na svim platformama.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

EEG_TASKS_ROOT = Path(__file__).parent

N_LEVELS = (5, 6, 7)
LENGTH_CLASS = {5: "low", 6: "medium", 7: "high"}

# --------------------------------------------------------------------------
# Korak 1 (delimicno) + korak 2: zabranjeni znakovi. Cifre, zagrade,
# navodnici (samo " i ' se stvarno javljaju u ovom korpusu, ostali
# unicode navodnici dodati odbrambeno), procenat, zarez, kosa crta, & @ $.
# --------------------------------------------------------------------------

BAD_CHARS_RE = re.compile(r'[0-9()\[\]{}"“”„‘’\'%,/&@$]')

# --------------------------------------------------------------------------
# Rodno obelezena naizmenicna forma (rekao/la, zatrpan/a, dostupan/na) --
# razresava se izborom PRVOG (muskog) oblika, videti napomenu u zaglavlju
# modula o redosledu. \b(\w+)/(a|na|la)\b pokriva ogromnu vecinu; nekoliko
# punih naizmenicnih reci (voleo/volela) je hardkodovano posebno.
# --------------------------------------------------------------------------

GENDER_SLASH_RE = re.compile(r'\b(\w+)/(a|na|la)\b')
GENDER_SLASH_FULLWORD = {
    "voleo/volela": "voleo",
}


def resolve_gender_slash(text: str) -> str:
    for full, resolved in GENDER_SLASH_FULLWORD.items():
        text = text.replace(full, resolved)
    return GENDER_SLASH_RE.sub(r"\1", text)


# --------------------------------------------------------------------------
# Korak 3: privatne/neposlovne recenice (pozdravi, licna osecanja,
# porodica, razonoda). Podrazumevano ZADRZI, izbaci na jasan signal --
# videti napomenu u zaglavlju modula.
# --------------------------------------------------------------------------

PERSONAL_EXCLUDE = [
    r'\bzdravo\b', r'\bćao\b', r'\bcao\b', r'\bpozdrav[a-z]*\b',
    r'\bnedostaj[ei]š\b', r'\bnedostajete\b', r'\bvoli[mš]\b', r'\bljubav', r'\bdraga?n?\b',
    r'\bčestita', r'\brođendan', r'\bsrećn[a-z]* (novu|božić|praznik)',
    r'\bžao mi je\b', r'\bdrago mi je\b', r'\bnadam se\b',
    r'\btužan\b', r'\btužno\b', r'\bbrinem\b', r'\bzabrinut',
    r'\bžen[ae]\b', r'\bmuž\b', r'\bsuprug', r'\bdeč[ck]', r'\bdete\b', r'\bdec[au]\b',
    r'\bsin[ua]?\b', r'\bćerk', r'\bkćerk', r'\bmajk[ae]\b', r'\botac\b',
    r'\bmam[ae]\b', r'\btat[ae]\b', r'\bbrat[a-zu]*\b', r'\bsestr',
    r'\bporodic', r'\bbab[au]\b', r'\bded[ai]\b',
    r'\bodmor[a-z]*\b', r'\bletovanj', r'\bplaž', r'\bizlet',
    r'\bgodišnj[a-z]* odmor', r'\bputovanj[ae]\b.*\b(odmor|razonod)',
    r'\bbeb[a-z]*\b', r'\bšal[ia]m se\b', r'\bpoljub[a-z]*\b',
    r'\bosećaš? se bolje\b', r'\bosećate se bolje\b',
    r'\bčekaonic[a-z]*\b', r'\bspecijalist[a-z]* +(orl|orl-a)\b',
    r'\bbožić', r'\blep[a-z]* praznik', r'\bpopi[a-z]* vino\b',
    r'\bvrati[a-z]* kući\b', r'\bterapij[a-z]* govora\b',
    r'\bprazni[čc]n[a-z]* nastup\b', r'\bpeca(ti|mo|š|nje)\b',
    r'\butakmic[a-z]*\b', r'\bgolman[a-z]*\b', r'\bmeteora\b',
    r'\budes[a-z]* automobil', r'\bmoli[šm] se\b', r'\blekar[a-z]*\b',
    r'\bdijet[a-z]*\b', r'\brazveseli[a-z]*\b', r'\btrač[a-z]*\b',
    r'\bslatk[a-z]*\b', r'\bvin[ao]\b', r'\bmi je bilo teško\b',
    r'\bmoju škol[a-z]*\b',
]
PERSONAL_RE = re.compile('|'.join(PERSONAL_EXCLUDE), re.IGNORECASE)

# "Godisnji odmor" (godisnji odmora/odmoru/itd.) je HR termin (zakonsko
# pravo na odsustvo), ne razonoda -- nadjeno pri dodavanju kadrovskih
# recenica (korak D uputstva), gde bi bez ovog izuzetka bare "odmor"
# pravilo iznad pogresno izbacilo legitimne poslovne recenice ("Zahtev za
# godisnji odmor je odobren."). Maskira se PRE provere, ne dodaje kao
# jos jedno pravilo -- da ne bi later matchovala neka DRUGA fraza koja
# slucajno sadrzi i "godisnji" i "odmor" razdvojeno.
_PROTECTED_BUSINESS_RE = re.compile(r'\bgodišnj[a-z]* odmor[a-z]*\b', re.IGNORECASE)


def is_personal_content(text: str) -> bool:
    masked = _PROTECTED_BUSINESS_RE.sub('___', text)
    return bool(PERSONAL_RE.search(masked))


# --------------------------------------------------------------------------
# Korak 4: specificno za Enron i americki energetski sektor. "SAD" se
# proverava ODVOJENO, case-sensitive (malim slovima "sad" je obican i cest
# prilog "now", pa case-insensitive provera ne sme da ga pogodi).
# --------------------------------------------------------------------------

ENERGY_EXCLUDE = [
    r'\benron\b', r'\bpwr\b', r'\bferc\b', r'\biso\b',
    r'\bstruj[a-z]*\b', r'\belektričn', r'\belektran',
    r'\bprirodni gas\b', r'\bgasovod', r'\bnaft[ae]\b', r'\bbarel',
    r'\bmegavat', r'\bkilovat', r'\bcevovod',
    r'\bkalifornij', r'\bteksas', r'\bhjuston',
    r'\bsnabdevanj[a-z]* strujom\b',
]
ENERGY_RE = re.compile('|'.join(ENERGY_EXCLUDE), re.IGNORECASE)
SAD_RE = re.compile(r'\bSAD\b')

# --------------------------------------------------------------------------
# Korak 5: zamena vlastitih imena. Kljucevi su TACNI opazeni oblici (sa
# padeznim nastavkom) u finalnom skupu recenica (posle svih filtera gore),
# ne leme -- videti napomenu u zaglavlju modula. Primenjuje se PO DUZINI
# kljuca opadajuce (visestruke reci pre pojedinacnih), preko \b granica
# reci, na tekst POSLE gender-slash razresenja a PRE uklanjanja
# dijakritike.
#
# Licna imena: srpska imena/prezimena (Stevan, Ljiljana, Simic - primeri iz
# uputstva), padez odgovara originalu.
# Firme: SAMO koren "Delta" ili "Sirmium" (shared/generate_common.py,
# S1_ONLY_ROOTS) -- ta dva korena su REZERVISANA iskljucivo za S1 tekst,
# disjunktna od preostalih osam korena koje S2/S3 stvarno dodeljuju
# ispitanicima (uputstvo za spajanje jezgra, korak D). Rod korena odabran
# da odgovara slaganju glagola/prideva u originalnoj recenici (npr.
# "Dynegy uputio" -> muski rod, "Sirmium", ne zenski "Delta").
# Gradovi: ista lista kao COMPANY CITIES (Beograd, Novi Sad, Nis,
# Kragujevac, Subotica, Zrenjanin, Pancevo, Cacak, Kraljevo, Novi Pazar,
# Smederevo, Leskovac, Valjevo, Krusevac, Vranje, Sabac, Sombor,
# Pozarevac, Pirot, Zajecar) -- radi doslednosti sa S2/S3.
# --------------------------------------------------------------------------

NAME_MAP = {
    # --- visereci fraze (moraju pre pojedinacnih reci) ---
    "Chip Schneider": "Zoran Đurić",
    "John Millar": "Ivan Petrović",
    "John Keffer": "Boban Nikolić",
    "Mark Ellenberg": "Marko Vuković",
    "Pam Butler": "Danica Todorović",
    "Roger Willard": "Radovan Obradović",
    # "sa Lara Robinson" je instrumental (posle "sa") -- "Zorica" je bilo
    # pogresno u nominativu, ispravljeno u "Zoricom" (rucni pregled padeza,
    # uputstvo tacka 9). "Robinson" -> "Kostic" ostaje neizmenjeno kao
    # zensko prezime (invarijantno na padez, isto kao original).
    "Lara Robinson": "Zoricom Kostić",
    "Stiv Gilbert": "Miodrag Ristić",
    "Steve Dowd-u": "Petru Nikoliću",
    "Kevin Howard-u": "Vukašinu Stankoviću",
    "Shanna Funkhouser": "Saru Ilić",
    "Brent-om Price-om": "Markom Jovanovićem",
    "Gary Smith-u": "Marku Simiću",
    "Garyju Smithu": "Marku Simiću",
    "UBS Warburg Energy": "Sirmium Tehnologije",
    "Toys R Us": "Sirmium Distribucija",
    "VP PRC": "upravnog odbora",
    "Global Finance Legal": "Sektor za finansije",
    "Zainy Brainy": "prodavnicu igračaka",
    "El Paso-om": "Sirmiumom",   # instrumental, bez slaganja (bio Moravom)
    # "San Francisko" (nominativ, bez "San Francisku") NIJE ovde -- ta
    # recenica ("San Francisko je bio sastanak Interconnect-a.") je u
    # celosti zamenjena u SENTENCE_OVERRIDES, ovaj kljuc bi ostao
    # neiskoriscen. "San Francisku" (lokativ, DRUGA recenica) ostaje.
    "San Francisku": "Novom Sadu",

    # --- pojedinacna licna imena (tacan opazen padezni oblik) ---
    "Scotty": "Stevan",
    "Lindom": "Ljiljanom",
    "Stevea": "Petra",
    "Steve-a": "Petra",
    "Steve-u": "Petru",
    "Steve": "Petar",
    "George": "Vladimir",
    "Georgie": "Danicu",
    "Tracy": "Tamaru",
    "Jima": "Nemanju",
    "Jimom": "Nemanjom",
    # bare "Jimu" (lokativ) NIJE ovde -- jedina recenica gde se javljao je
    # sada pokrivena visom frazom "Tracy i Jimu" iznad.
    "Fallonom": "Jovanovićem",
    "Michael": "Dragan",
    "Mike": "Aleksandar",
    "Avom": "Anom",
    "Becky": "Milicom",
    "Bill": "Dušan",
    "Bowena": "Miloša",
    "Cam-a": "Filipa",
    "Carol": "Jelena",
    "Cassandra": "Vesna",
    "Derrick": "Goran",
    "Džejmsa": "Stefana",
    "Keti": "Katarinu",
    "Pashe": "Jovane",
    "Everett": "Uroš",
    "Nick": "Nikola",
    "Ginger": "Nataše",
    "Glisana": "Kostića",
    "Gregom": "Bobanom",
    "Janet-in": "Sarin",
    "Joel": "Slobodan",
    "Kathy": "Biljana",
    "Laurinu": "Radmilinu",
    "Lynn": "Gordana",
    "Mary Joyce": "Marijom Kostić",
    "Mary": "Snežanom",
    "Oxleya": "Vasića",
    "Savitom": "Milanom",
    "Somerholderom": "Antićem",
    "Stanom": "Vladanom",
    "Stanovu": "Vladanovu",
    "Wasaffa": "Kostića",
    # "Tracy" je bare kljuc nize mapiran u AKUZATIV ("Tamaru", "pozove
    # Tracy"). U OVOJ recenici "Tracy" je posle predloga "o" -- LOKATIV
    # ("o kome/cemu"), koji za Tamaru glasi "Tamari", ne "Tamaru". Original
    # ne razlikuje ova dva padeza povrsinski (isto "Tracy" u oba slucaja),
    # pa opsti kljuc "Tracy" ne moze da pogodi oba tacno -- ova fraza (duza,
    # obradjuje se pre bare "Tracy") ispravlja bas taj slucaj. Nadjeno rucnim
    # pregledom padeza (uputstvo, tacka 9).
    "Tracy i Jimu": "Tamari i Nemanji",

    # --- firme / organizacije (koren, rod prilagodjen slaganju) ---
    #
    # SVE firme ovde MORAJU biti korena "Delta" ili "Sirmium"
    # (shared/generate_common.py, S1_ONLY_ROOTS) -- to su jedina dva korena
    # rezervisana iskljucivo za S1 pominjanje u tekstu, disjunktna od
    # preostalih osam korena koje S2/S3 stvarno dodeljuju ispitanicima
    # (uputstvo za spajanje jezgra, korak D). Originalno su ovde bila SVA
    # deset korena (prebrojano: 10 od 10 mogucih); niz ispod je prepravljen
    # tako da svaki unos i dalje odgovara padezu/rodu iz originalne
    # recenice (proveri kod svakog kljuca u kontekstu iz name_map.json).
    "ANNGTC": "Deltu",           # akuzativ, "razgovor za Deltu" (bio Timok)
    "APS-a": "Delte",            # genitiv, "signali od Delte" (bio Avale)
    "AA": "Delti",               # lokativ, "osoba u Delti" (bio Zenitu)
    "Dyn": "Deltom",             # instrumental, "pred Deltom" (bio Karpatom)
    "Dynegy": "Sirmium",         # nominativ, muski glagol "uputio" -- Sirmium
                                  # se tretira kao muski rod (bio Karpat)
    "Gallup": "Delta",           # bez padeza, "Delta ugovore" (bio Kolubara)
    "NetCo-u": "Delti",          # dativ -- vec Delta, bez izmene
    "GISB": "Sirmium",           # nominativ modifikator, "Sirmium grupa" (bio Panonija)
    "NB": "Delti",               # lokativ -- vec Delta, bez izmene
    "SoCal-om": "Sirmiumom",     # instrumental (bio Kolubarom)
    "TW": "Deltu",               # akuzativ, "ulazi u Deltu" (bio Zenit)
    "FGT": "Sirmium",            # nominativ, muski particip "kupovan" (bio Karpat)
    "ENE": "Deltom",             # instrumental (bio Vegom)
    "EESI": "Sirmium",           # nominativ, deo "su Sirmium i Delta pomesani" (bio Vega)
    "EPMI": "Delta",             # nominativ, isti par kao EESI (bio Panonija)
    "Wessexa": "Delte",          # genitiv, "Prodaja Delte" (bio Kolubare)
    # "Interconnect-a" NIJE ovde -- jedina recenica gde se javljao je u
    # celosti zamenjena u SENTENCE_OVERRIDES (ista recenica kao "San
    # Francisko" iznad).
    "Virgo": "Delta",            # vec Delta, bez izmene
    "Pemexom": "Sirmiumom",      # instrumental (bio Karpatom)
    "Hanover-om": "Sirmiumom",   # vec Sirmium, bez izmene
    "Hartsoe-u": "Delti",         # dativ (bio Avali)
    "Calgerovo": "Miloševo",

    # --- gradovi ---
    "Vašingtonu": "Beogradu",
    "Njujork": "Kragujevac",
    "Njujorku": "Kragujevcu",
    "Dalasu": "Nišu",
    "Redmonda": "Kruševca",
    "Portlandu": "Zrenjaninu",
    "Heaven": "Šabac",
    "FL": "Vranje",
    "FW": "Pirotu",
    "Quil": "Sombor",
    "Palacios": "Valjevo",

    # --- sitno, van osnovnih kategorija ali potrebno za citljivost ---
    # "Targeta" NIJE ovde -- ta recenica je u celosti zamenjena u
    # SENTENCE_OVERRIDES (korisnicka ispravka), ovaj kljuc bi ionako ostao
    # neiskoriscen.
    "Chronicle": "Politiku",
}

# Primenjuje se POSLE NAME_MAP -- zato regex cilja tekst KAKAV JE POSLE
# zamene imena (npr. "Sirmium Distribucija", ne originalno "Toys R Us"),
# jer bi inace nikad ne pogodio (NAME_MAP je vec zamenio original do tog
# trenutka). Rod firme (Distribucija, zenski) mora da se slaze sa
# particip/pridev koji je u originalu slagan sa "Toys R Us" (muski/srednji
# podrazumevani rod stranog naziva).
POST_NAME_FIXUPS = [
    (re.compile(r"\bSirmium Distribucija je upravo preuzet\b"), "Sirmium Distribucija je upravo preuzeta"),
]

# --------------------------------------------------------------------------
# Rucne ispravke posle prvog pregleda (korisnicki zahtev). Primenjuju se na
# `resolved` tekst, PRE NAME_MAP -- redom:
#   1. MANUAL_EXCLUDE_SENTENCES -- neprevodivi ostaci originalnog korpusa
#      (interni kodni naziv projekta, besmislena konstrukcija nastala od
#      prezimena koje se ne uklapa ni u jednu kategoriju iz koraka 5).
#      Izbacuju se u CELOSTI, ne popravljaju se.
#   2. SENTENCE_OVERRIDES -- cela recenica zamenjena prirodnijom formulacijom
#      (kad tacka-po-tacku ispravka naziva ne bi bila dovoljna/citljiva).
#   3. TEXT_FIXES -- manje, lokalizovane zamene terminologije (ne vlastita
#      imena) primenjene isto kao NAME_MAP, preko granica reci.
# Sve troje MENJAJU BROJ RECI -- konacan broj reci/klasa duzine se racuna
# POSLE ovih izmena, ne pre (videti process_and_fix() nize); recenica koja
# posle izmene izadje iz opsega 5-7 reci se izbacuje.
# --------------------------------------------------------------------------

MANUAL_EXCLUDE_SENTENCES = {
    # interni kodni naziv projekta ("slapshot") -- bez znacenja van izvornog
    # konteksta, ne moze se prevesti niti zameniti a da recenica i dalje
    # nosi isti sadrzaj.
    "Ostatak je nusproizvod projekta slapshot.",
    # "niz Wetheimer" je vec u originalu nejasna konstrukcija (prezime
    # tretirano kao da je pravac/ruta) -- zamena prezimena ne resava
    # osnovni problem da recenica nema jasno poslovno znacenje.
    "Da li će doći niz Wetheimer?",
}

SENTENCE_OVERRIDES = {
    "Treba li ti nešto iz Targeta?":
        "Koliki je target za ovaj mesec?",
    "San Francisko je bio sastanak Interconnect-a.":
        "Novi Sad je mesto sastanka sa Dušanom.",
    "Čujem da Tim ima ogromne probleme.":
        "Čujem da tim lider ima ogromne probleme.",
    "Nisam čuo od Ginger ove nedelje.":
        "Nisam čuo komentar od Ginger ove nedelje.",
}

TEXT_FIXES = {
    "senatorima": "narodnim poslanicima",
    "preko pejdžera": "za vikend",
}
_TEXT_FIXES_ITEMS_BY_LEN_DESC = sorted(TEXT_FIXES.items(), key=lambda kv: -len(kv[0]))


def apply_text_fixes(text: str) -> str:
    for src, dst in _TEXT_FIXES_ITEMS_BY_LEN_DESC:
        text = re.sub(r'\b' + re.escape(src) + r'\b', dst, text)
    return text


_NAME_MAP_ITEMS_BY_LEN_DESC = sorted(NAME_MAP.items(), key=lambda kv: -len(kv[0]))


def apply_name_map(text: str, usage: Counter) -> str:
    for src, dst in _NAME_MAP_ITEMS_BY_LEN_DESC:
        pattern = r'\b' + re.escape(src) + r'\b'
        new_text, n = re.subn(pattern, dst, text)
        if n:
            usage[src] += n
        text = new_text
    for pattern, replacement in POST_NAME_FIXUPS:
        text = pattern.sub(replacement, text)
    return text


# --------------------------------------------------------------------------
# Korak 7: uklanjanje dijakritike. c/c->c, s->s, z->z, dj->dj (NE d),
# Dj->Dj (veliko samo prvo slovo digrafa).
# --------------------------------------------------------------------------

_DIACRITICS_MAP = {
    "č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj",
    "Č": "C", "Ć": "C", "Š": "S", "Ž": "Z", "Đ": "Dj",
}
_DIACRITICS_RE = re.compile("|".join(_DIACRITICS_MAP.keys()))


def strip_diacritics(text: str) -> str:
    return _DIACRITICS_RE.sub(lambda m: _DIACRITICS_MAP[m.group(0)], text)


# --------------------------------------------------------------------------
# Korak 8: zavrsna interpunkcija. Zadrzi samo tacku ili upitnik; "!" se
# normalizuje u "." (izjava), sve OSTALE interpunkcijske znake unutar
# recenice ukloni (npr. "P.S:" -> "PS", "David - da li..." vec izbaceno
# jer nema zavrsnu interpunkciju -- ovo pravilo cisti preostale znake KOD
# recenica koje inace prolaze).
# --------------------------------------------------------------------------

_INTERNAL_PUNCT_RE = re.compile(r"[.:;\-]")


def finalize_punctuation(text: str) -> str:
    final = "?" if text.rstrip()[-1] == "?" else "."
    body = text.rstrip()[:-1]
    body = _INTERNAL_PUNCT_RE.sub("", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body + final


# --------------------------------------------------------------------------
# Ucitavanje i filtriranje.
# --------------------------------------------------------------------------

def load_serbian_sentences(xlsx_path: Path) -> list[str]:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Sentences"]
    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        sr = row[2] if len(row) > 2 else None
        if sr:
            out.append(str(sr).strip())
    return out


# --------------------------------------------------------------------------
# Korak D uputstva: 100 rucno napisanih recenica, 20 po oblasti
# administrativnog rada koja je bila slabo zastupljena u enron korpusu
# (originalni korpus su interni mejlovi jedne energetske kompanije, pa
# rutinske administrativne teme -- putni nalozi, kadrovska dokumentacija,
# fakturisanje -- gotovo uopste ne postoje u njemu). Iste norme kao za
# enron recenice: 5-7 reci, bez zabranjenih znakova, prirodan poslovni
# srpski. Imena/firme gde se javljaju su STVARNI unosi iz
# s2-demo/data/companies.json (ista zajednicka baza kao S2/S3), ne
# izmisljeni nazivi -- ali SAMO firme korena "Delta" ili "Sirmium"
# (S1_ONLY_ROOTS), nikad ostalih osam korena koje S2/S3 stvarno dodeljuju
# ispitanicima (korak D, disjunktnost bez logike po ispitaniku).
# Prolaze kroz ISTI filter kao enron recenice (process(),
# vidi napomenu tamo) -- ovo NIJE bezuslovno ubacivanje teksta.
# --------------------------------------------------------------------------

CONSTRUCTED_SENTENCES = [
    # --- rezervacije smeštaja i službena putovanja (20) ---
    "Rezervacija hotela za direktora je potvrđena.",
    "Let za Beograd je već zvanično zakazan.",
    "Službeni put počinje u ponedeljak ujutru.",
    "Hotel u Novom Sadu je rezervisan.",
    "Molim vas potvrdite rezervaciju za konferenciju.",
    "Avionska karta je kupljena za Vladimira Savica.",
    "Putni nalog je potpisan i overen.",
    "Smeštaj za tim je obezbeđen unapred.",
    "Službeno putovanje je konačno odobreno od rukovodstva.",
    "Rezervisali smo salu za poslovni sastanak.",
    "Hotelski vaučer je poslat imejlom.",
    "Povratna karta se kupuje sledeće nedelje.",
    "Putni troškovi se prijavljuju računovodstvu.",
    "Prevoz do aerodroma je blagovremeno organizovan.",
    "Rezervacija je otkazana zbog iznenadne promene plana.",
    "Službeni automobil je na raspolaganju timu.",
    "Konferencijski hotel nudi popust grupama.",
    "Putovanje je produženo zbog dodatnih poslovnih sastanaka.",
    "Delegacija stiže u Kragujevac u utorak.",
    "Smeštaj je plaćen službenom platnom karticom.",

    # --- finansijski izveštaji i analize (20) ---
    "Kvartalni izveštaj šaljem vam do petka.",
    "Finansijski izveštaj Delta Prometa je odobren.",
    "Analiza troškova pokazuje značajnu uštedu.",
    "Bilans stanja je pripremljen za reviziju.",
    "Prihodi su porasli u ovom kvartalu.",
    "Izveštaj o rashodima je u izradi.",
    "Finansijski tim analizira mesečne rezultate poslovanja.",
    "Revizor je zatražio dodatnu dokumentaciju.",
    "Godišnji finansijski izveštaj je zvanično objavljen danas.",
    "Budžet za sledeću godinu je usvojen.",
    "Analiza pokazuje pad prihoda ovog meseca.",
    "Troškovi poslovanja su strogo kontrolisani.",
    "Finansijski direktor Sirmium Grupe predstavlja izveštaj.",
    "Profitabilnost odeljenja je značajno poboljšana.",
    "Bilans uspeha se priprema svakog kvartala.",
    "Analitičar je uporedio rezultate sa planom.",
    "Izveštaj o likvidnosti je hitno potreban timu.",
    "Investicije su usklađene sa finansijskim planom.",
    "Prognoza prihoda je revidirana na više.",
    "Kontrola troškova ostaje prioritet ovog kvartala.",

    # --- kadrovski poslovi: odsustva, obuke, zapošljavanje (20) ---
    "Zahtev za godišnji odmor je odobren.",
    "Novi zaposleni Aleksandar Mitrović počinje u ponedeljak.",
    "Obuka za nove zaposlene počinje sutra.",
    "Kadrovska služba priprema ugovor o radu.",
    "Zahtev za bolovanje je predat kadrovskoj službi.",
    "Prijava za obuku je popunjena ispravno.",
    "Zaposleni je uspešno završio probni rad.",
    "Konkurs za novo radno mesto je otvoren.",
    "Razgovor za posao je zakazan sutra.",
    "Kadrovska evidencija se redovno ažurira.",
    "Zaposlenima je nedavno odobreno dodatno stručno usavršavanje.",
    "Godišnji odmor se planira unapred.",
    "Novi tim se obučava ovog meseca.",
    "Zahtev za premeštaj je razmotren pažljivo.",
    "Ocena učinka se obavlja jednom godišnje.",
    "Ugovor o radu je potpisan danas.",
    "Odsustvo sa posla je najavljeno blagovremeno.",
    "Kadrovska služba organizuje internu obuku svih zaposlenih.",
    "Zaposleni traži produženje godišnjeg odmora.",
    "Prijem novih radnika počinje sledeće nedelje.",

    # --- nabavka, fakturisanje i arhiviranje (20) ---
    "Faktura je prosleđena računovodstvu na overu.",
    "Nabavka kancelarijskog materijala je odobrena danas.",
    "Dobavljač Sirmium Komerc je poslao ponudu.",
    "Faktura je plaćena u predviđenom roku.",
    "Ugovor sa Delta Agrarom je obnovljen danas.",
    "Arhiva dokumenata se redovno ažurira.",
    "Nabavna služba traži dodatnu ponudu.",
    "Račun je evidentiran u sistemu.",
    "Dokumentacija se čuva u arhivi preduzeća.",
    "Faktura čeka odobrenje finansijskog direktora.",
    "Porudžbina je poslata dobavljaču jutros.",
    "Nabavka opreme je planirana za sledeći kvartal.",
    "Skladište je primilo novu pošiljku robe.",
    "Fakturisanje se obavlja krajem svakog meseca.",
    "Arhiviranje ugovora je obavezno po pravilniku.",
    "Nabavni proces zahteva dodatno odobrenje uprave.",
    "Račun je vraćen zbog netačnih podataka.",
    "Dobavljač kasni sa isporukom robe.",
    "Fakture se skeniraju i arhiviraju digitalno.",
    "Nova nabavka je usaglašena sa budžetom.",

    # --- sastanci, rokovi i dokumentacija (20) ---
    "Molim vas potvrdite termin sastanka.",
    "Rok za izveštaj je produžen.",
    "Sastanak tima je pomeren za sredu.",
    "Dokumentacija za projekat je skoro gotova.",
    "Zapisnik sa sastanka je poslat svima.",
    "Rok za dostavu dokumenata ističe sutra.",
    "Sastanak upravnog odbora počinje tačno u podne.",
    "Dnevni red sastanka je usaglašen unapred.",
    "Potpisana dokumentacija je poslata pravnoj službi.",
    "Rok za internu reviziju je pomeren.",
    "Sastanak je otkazan zbog nedostatka kvoruma.",
    "Dokumenta se moraju dostaviti sutra.",
    "Zapisnici se arhiviraju posle svakog sastanka.",
    "Predlog dnevnog reda je poslat unapred.",
    "Sastanak sa Sirmium Konsaltingom je uspešno održan.",
    "Dokumentacija projekta zahteva dodatnu proveru glavnog pravnika.",
    "Rok za odgovor je već istekao.",
    "Sastanak je produžen zbog dodatnih pitanja.",
    "Svi potrebni materijali za sastanak su pripremljeni.",
    "Dokumentacija je overena i prosleđena arhivi.",
]


def interleave_by_source(fixed: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """Korak E, drugi zahtev: rasporedi "constructed" recenice RAVNOMERNO
    kroz "enron" recenice ISTE klase duzine, umesto da ostanu nagomilane na
    jednom mestu (npr. sve na kraju fajla, ako bi neko kasnije uzimao
    UZASTOPNI odsecak recenica za stavku, ne bi zavrsio sa odseckom
    iskljucivo jednog porekla)."""
    by_class = defaultdict(lambda: {"enron": [], "constructed": []})
    for item in fixed:
        _, n, origin = item
        by_class[n][origin].append(item)

    def spread(base: list, insert: list) -> list:
        if not insert:
            return base
        if not base:
            return insert
        result = []
        base_idx = 0
        ratio = len(base) / len(insert)
        for i, ins_item in enumerate(insert):
            take_upto = round((i + 1) * ratio)
            result.extend(base[base_idx:take_upto])
            base_idx = take_upto
            result.append(ins_item)
        result.extend(base[base_idx:])
        return result

    out = []
    for n in sorted(by_class):
        out.extend(spread(by_class[n]["enron"], by_class[n]["constructed"]))
    return out


def process(sentences: list[str], lo: int, hi: int, origin: str):
    """Vraca (kept, exclusion_counts). kept je lista (resolved_text, n_words,
    origin). origin je "enron" (iz xlsx) ili "constructed" (rucno dodate
    recenice, korak D uputstva) -- vidi tacku E: cuva se do kraja u
    sentences.json kao polje "source".

    n_words ovde je SAMO privremena/pocetna vrednost (na osnovu sirovog
    teksta) -- korsti se isključivo za PRVI (grubi) filter po duzini, pre
    bilo kakve izmene sadrzaja. Konacna duzina/klasa se racuna kasnije, u
    apply_fixes(), na tekstu POSLE svih rucnih ispravki i zamene imena --
    videti napomenu tamo za razlog (neke zamene menjaju broj reci).

    Rucno dodate (constructed) recenice prolaze KROZ ISTI filter kao i
    enron recenice (namerno, kao sigurnosna provera), ne dodaju se
    bezuslovno -- da slucajna greska pri pisanju (zabranjen znak, van
    opsega duzine) ne prodje neprimeceno."""
    counts = Counter()
    kept = []
    for raw in sentences:
        n = len(raw.split())
        if not (lo <= n <= hi):
            counts["duzina"] += 1
            continue
        resolved = resolve_gender_slash(raw)
        if BAD_CHARS_RE.search(resolved):
            counts["zabranjeni_znakovi"] += 1
            continue
        if resolved.rstrip()[-1:] not in ".?!":
            counts["bez_zavrsne_interpunkcije"] += 1
            continue
        if ENERGY_RE.search(resolved) or SAD_RE.search(resolved):
            counts["enron_energetski_sektor"] += 1
            continue
        if is_personal_content(resolved):
            counts["privatno_neposlovno"] += 1
            continue
        kept.append((resolved, n, origin))
    return kept, counts


def apply_fixes(kept: list[tuple[str, int]], lo: int, hi: int):
    """Primenjuje MANUAL_EXCLUDE_SENTENCES / SENTENCE_OVERRIDES / TEXT_FIXES
    / NAME_MAP (tim redom) i PONOVO RACUNA broj reci i klasu duzine iz
    KONACNOG teksta (posle svih izmena), umesto da zadrzi broj reci izmeren
    na originalu.

    Ovo NIJE kozmeticka razlika: nekoliko NAME_MAP zamena menja broj reci
    (npr. "UBS Warburg Energy" [3 reci] -> "Sirmium Tehnologije" [2 reci],
    "Toys R Us" -> "Sirmium Distribucija", "El Paso-om" -> "Sirmiumom") -- te
    tri recenice su u prethodnoj verziji ovog skripta NOSILE POGRESNU klasu
    duzine (izracunatu na originalu, ne na stvarno isporucenom tekstu),
    otkriveno tek ovim pooštrenim postupkom. Recenica koja posle izmene
    izadje iz opsega [lo, hi] se izbacuje (ne "ispravlja" nasilno)."""
    counts = Counter()
    fixed = []
    usage = Counter()
    for resolved, _old_n, origin in kept:
        if resolved in MANUAL_EXCLUDE_SENTENCES:
            counts["rucno_izbaceno"] += 1
            continue
        text = SENTENCE_OVERRIDES.get(resolved, resolved)
        text = apply_text_fixes(text)
        text = apply_name_map(text, usage)
        n = len(text.split())
        if not (lo <= n <= hi):
            counts["van_opsega_posle_izmene"] += 1
            continue
        fixed.append((text, n, origin))
    return fixed, counts, usage


def build_records(fixed: list[tuple[str, int, str]]) -> list[dict]:
    records = []
    for i, (text, n, origin) in enumerate(fixed, 1):
        text = strip_diacritics(text)
        text = finalize_punctuation(text)
        records.append({
            "id": f"S1_{i:04d}",
            "text": text,
            "n_words": n,
            "length_class": LENGTH_CLASS.get(n, str(n)),
            "source": origin,
            "is_question": text.endswith("?"),
        })
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, required=True,
                     help="putanja do All_sentences_for_Scenario_1_Transcription.xlsx")
    ap.add_argument("--out", type=Path, default=EEG_TASKS_ROOT / "data" / "sentences.json")
    ap.add_argument("--name-map-out", type=Path, default=EEG_TASKS_ROOT / "data" / "name_map.json")
    ap.add_argument("--seed", type=int, default=1, help="seed za 30 nasumicnih primera u izvestaju")
    args = ap.parse_args()

    sentences = load_serbian_sentences(args.input)
    print(f"Ucitano recenica (enron): {len(sentences)}")
    print(f"Rucno dodatih recenica (constructed, korak D): {len(CONSTRUCTED_SENTENCES)}")

    def run(lo, hi):
        kept_enron, c1 = process(sentences, lo, hi, "enron")
        kept_constructed, c2 = process(CONSTRUCTED_SENTENCES, lo, hi, "constructed")
        c1.update(c2)
        fixed, fix_counts, usage = apply_fixes(kept_enron + kept_constructed, lo, hi)
        c1.update(fix_counts)
        return fixed, c1, usage

    lo, hi = 5, 7
    fixed, counts, usage = run(lo, hi)
    by_class = Counter(n for _, n, _ in fixed)

    widened = False
    if any(by_class.get(n, 0) < 100 for n in N_LEVELS):
        print(f"\nUPOZORENJE: opseg {lo}-{hi} reci ne dostize 100 recenica po klasi "
              f"({dict(by_class)}) -- sirim na 4-8 reci po uputstvu (korak 7).")
        lo, hi = 4, 8
        fixed, counts, usage = run(lo, hi)
        by_class = Counter(n for _, n, _ in fixed)
        widened = True

    fixed = interleave_by_source(fixed)
    records = build_records(fixed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    # data/name_map.json -- tabela zamena, korak 5, "radi provere". Tekst u
    # njoj NAMERNO zadrzava dijakritiku (citljivije za rucnu proveru) --
    # zamena se ionako desava PRE koraka 7 (uklanjanje dijakritike) nad
    # stvarnim tekstom u sentences.json.
    name_map_out = [
        {"from": src, "to": dst, "count": usage.get(src, 0)}
        for src, dst in NAME_MAP.items()
    ]
    args.name_map_out.parent.mkdir(parents=True, exist_ok=True)
    args.name_map_out.write_text(
        json.dumps(name_map_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    unused = [e["from"] for e in name_map_out if e["count"] == 0]

    print("\n" + "=" * 72)
    print(f"Opseg duzine korišćen: {lo}-{hi} reci" + (" (prosireno, videti upozorenje gore)" if widened else ""))
    print(f"Upisano u: {args.out}  ({len(records)} recenica)")
    print(f"Tabela zamena upisana u: {args.name_map_out}  ({len(name_map_out)} stavki"
          + (f", {len(unused)} neiskorisceno" if unused else "") + ")")
    if unused:
        print(f"  Neiskoriscene stavke (mozda se odnose na recenicu izbacenu "
              f"drugim kriterijumom, proveriti): {', '.join(unused)}")
    print("=" * 72)

    print("\nBroj recenica po klasi duzine:")
    for n in range(lo, hi + 1):
        label = LENGTH_CLASS.get(n, str(n))
        print(f"  {n} reci ({label}): {by_class.get(n, 0)}")

    print("\nSastav po poreklu (source), tacka E:")
    by_class_source = Counter((r["length_class"], r["source"]) for r in records)
    for n in range(lo, hi + 1):
        label = LENGTH_CLASS.get(n, str(n))
        e = by_class_source.get((label, "enron"), 0)
        c = by_class_source.get((label, "constructed"), 0)
        print(f"  {label:6s}: enron={e:4d}  constructed={c:3d}")
    total_constructed = sum(1 for r in records if r["source"] == "constructed")
    print(f"  ukupno constructed: {total_constructed} / {len(records)}")

    print("\nBroj izbacenih po kriterijumu:")
    print(f"  1) duzina (van {lo}-{hi} reci): {counts['duzina']}")
    print(f"  2) zabranjeni znakovi: {counts['zabranjeni_znakovi']}")
    print(f"  3) privatno/neposlovno: {counts['privatno_neposlovno']}")
    print(f"  4) Enron/americki energetski sektor: {counts['enron_energetski_sektor']}")
    print(f"  (dodatno, van cetiri zvanicna kriterijuma) bez zavrsne interpunkcije: "
          f"{counts['bez_zavrsne_interpunkcije']}")
    print(f"  (dodatno) rucno izbaceno (neprevodivi ostaci, tacka A6): {counts['rucno_izbaceno']}")
    print(f"  (dodatno) izaslo iz opsega {lo}-{hi} POSLE ispravke/zamene imena: "
          f"{counts['van_opsega_posle_izmene']}")

    n_questions = sum(1 for r in records if r["is_question"])
    print(f"\nOd toga pitanja: {n_questions} ({100 * n_questions / len(records):.1f}%)")

    print("\n30 nasumicnih primera za rucni pregled:")
    rng = random.Random(args.seed)
    sample = rng.sample(records, min(30, len(records)))
    for r in sorted(sample, key=lambda r: r["id"]):
        print(f"  [{r['id']}] ({r['length_class']}, {r['source']}, "
              f"{'pitanje' if r['is_question'] else 'izjava'}) {r['text']}")


if __name__ == "__main__":
    main()
