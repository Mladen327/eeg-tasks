# Uputstvo za izradu: Scenario 1, prekucavanje poslovne korespondencije

Treći i poslednji scenario. Gradi se **na postojećem jezgru** iz `core/`, unutar projekta `eeg-tasks`.

**Ne praviti novu infrastrukturu.** Merenje vremena, zapisivanje loga, upravljanje blokom, zaštita ekrana, blokiranje kopiranja, čitanje URL parametara i upravljanje fazom kodiranja već postoje u `core/` i koriste se nepromenjeni. Ovaj scenario doprinosi samo `scenarios/s1.js` i granom za `S1` u zajedničkim Python skriptovima.

Ovo je najjednostavniji od tri zadatka: jedan prozor, bez asistencije, bez odlučivanja o tuđem predlogu, bez poređenja sa referencom.

---

## 1. Šta Scenario 1 meri

Misaona operacija je zapamtiti i doslovno reprodukovati. Ispitanik vidi grupu od N rečenica iz poslovne korespondencije, rečenice nestaju, i on ih kuca po sećanju, redom.

Razlika prema ostala dva scenarija:

| | S1 | S2 | S3 |
|---|---|---|---|
| Operacija | doslovna reprodukcija | prenošenje između prozora | poređenje i odluka |
| Jedinica | rečenica | polje | polje |
| Odgovor | kucanje | kucanje | izbor iz ponuđenog |
| Prozori | jedan | dva | jedan |

---

## 2. Odluka o načinu unosa

**Rečenice se unose jedna po jedna, u N odvojenih polja, fiksnim redosledom.**

Alternativa je bila jedno veliko polje za ceo tekst. Odbačena je jer sedam rečenica u neprekidnom kucanju daje preko dvesta znakova po stavci, pa se opterećenje zadržavanjem meša sa izdržljivošću u kucanju. To je isti problem koji je u Scenariju 3 doveo do prelaska sa kucanja na izbor.

Odvojena polja daju i strukturu paralelnu sa Scenarijem 2, gde se N vrednosti unosi u N ćelija, što matricu prenosa čini tumačivom.

Opterećenje ostaje stvarno: dok kuca prvu rečenicu, ispitanik mora da zadrži preostalih N minus jedan.

---

## 3. Materijal

`data/sentences.json` sadrži oko 400 rečenica iz poslovne korespondencije, na srpskom, **bez dijakritike**, radi doslednosti sa bazom firmi iz Scenarija 2 i 3. Doslovno poređenje inače ne bi značilo isto u različitim scenarijima.

Rečenice su izmišljene, poslovno uverljive, bez ličnih podataka i bez preuzimanja iz stvarne prepiske. Mogu pominjati firme iz zajedničke baze, čime materijal deluje povezano sa ostalim zadacima.

Primeri oblika: potvrde prijema, obaveštenja o rokovima, zahtevi za dopunu dokumentacije, najave sastanaka, obaveštenja o fakturisanju.

### 3.1 Klase dužine

Rečenica koja ima sedam reči nije isto opterećenje kao ona sa pet. Bez fiksnog sastava dve stavke istog nivoa ne bi bile uporedive.

| Klasa | Broj reči |
|---|---|
| visoka | 7 |
| srednja | 6 |
| niska | 5 |

Bez skraćenica, bez brojeva, bez interpunkcije unutar rečenice. Svaka rečenica se završava tačkom, koja se pri poređenju ne uzima u obzir.

### 3.2 Sastav stavke po nivoima

Isto pravilo i ista tabela kao u Scenarijima 2 i 3:

| N | Visoka | Srednja | Niska |
|---|---|---|---|
| 3 | 1 | 1 | 1 |
| 5 | 1 | 2 | 2 |
| 7 | 1 | 3 | 3 |

Ukupan broj reči po stavci: 18 na N = 3, 29 na N = 5, 40 na N = 7.

### 3.3 Disjunktnost

Ni jedna rečenica se ne sme ponoviti istom ispitaniku unutar sesije. Generator vodi evidenciju po ispitaniku, kao što već radi za firme.

**Firme.** Rečenice smeju pominjati firme iz zajedničke baze (companies.json), ali ne bilo koju. Za razliku od rečenica, ovde se disjunktnost ne rešava evidencijom po ispitaniku — S1 nema `company_id` po stavci, samo slobodan tekst, pa nema šta da se evidentira. Umesto toga, koreni firmi (`company_name.split()[0]`) su trajno podeljeni na dva disjunktna skupa, u `shared/generate_common.py`:

- `S2_S3_ROOTS` — osam korena, jedini koje `generate_stimuli.py` sme da dodeli ispitaniku u Scenariju 2 ili 3.
- `S1_ONLY_ROOTS` — `["Delta", "Sirmium"]`, jedina dva korena koja S1 sme da pominje u tekstu rečenice.

Granica je izabrana brojanjem: u `name_map.json` (zamene ličnih imena/firmi iz enron korpusa) su se zatekla sva deset korena, pa je trebalo da S2/S3 zadrži bar 150 od 200 firmi. Dva najmanja korena u generisanoj bazi za seed 20260825 — Delta (16) i Sirmium (17) — daju 33 firme za S1 i 167 za S2/S3, iznad minimuma uz najmanji gubitak raznovrsnosti. Granica je zapisana eksplicitno u `companies.json`, kao polja `"s1_only_roots"` i `"s2_s3_roots"`, ne kao pretpostavka u kodu.

Pošto se koreni nikad ne poklapaju, nijedna konkretna firma ne može istovremeno biti i pominjana u S1 i dodeljena u S2/S3 — disjunktnost je zagarantovana samom podelom, bez ikakve logike po ispitaniku.

---

## 4. Tok zadatka

### Faza kodiranja

Prikazuje se N numerisanih rečenica, jedna ispod druge. Upravljanje trajanjem preuzima se iz jezgra: donja granica `ENCODING_MIN_MS`, gornja `ENCODING_BASE_MS + N * ENCODING_MS_PER_ITEM`, dugme Spreman i taster F2, uz beleženje `encoding_actual_ms` i `mode`.

Predložene polazne vrednosti za ovaj scenario, jer je čitanje duže nego u Scenariju 2:

```
ENCODING_BASE_MS      = 3000
ENCODING_MS_PER_ITEM  = 4000
ENCODING_MIN_MS       = 3000
```

Gornja granica na N = 7 iznosi 31 s, ali se u praksi retko dostiže zbog dugmeta Spreman.

### Faza unosa

Rečenice nestaju. Prikazuje se N numerisanih polja, jedno ispod drugog. Ispitanik kuca redom, prelazak Enter ili Tab.

Polja su neograničene dužine, bez maske, bez automatskog dopunjavanja, bez provere pravopisa. Postaviti `autocomplete="off"` i `spellcheck="false"`.

Nema roka po polju i nema automatskog napredovanja.

### Ponovni uvid

Dugme i taster F2 vraćaju prikaz svih N rečenica. **Neograničeno, bez zastoja**, kao što je rešeno u Scenariju 2 posle ispitivanja.

Beleži se broj uvida i trajanje svakog, uz meru ukupnog vremena u uvidu po stavci. Prikazuju se uvek sve rečenice, ne samo ona koja se trenutno kuca.

Bez povratne informacije o tačnosti, osim u režimu vežbe.

---

## 5. Ocena tačnosti

Ocena se ne računa u aplikaciji nego u analizi, kao u ostala dva scenarija. Poređenje je doslovno, po pravilu usvojenom u Scenariju 2: velika i mala slova i dijakritika se ne opraštaju. Završna tačka se zanemaruje.

### 5.1 Dve mere tačnosti

**Tačnost po reči** je primarna: udeo reči tačno reprodukovanih na tačnoj poziciji, u odnosu na ukupan broj reči u stavci. Poravnanje po rečima preko Levenštajnove distance na nivou reči.

**Tačnost po rečenici** je sekundarna: udeo rečenica reprodukovanih u celini doslovno.

Primarna mera mora biti po reči. Ocena po celoj rečenici na N = 7 daje vrednosti blizu nule kod gotovo svih ispitanika, jer jedna omaška u kucanju poništava celu rečenicu, pa nestaje varijansa koja se meri.

### 5.2 Tipovi grešaka

Izvedeni iz poravnanja po rečima:

| Tip | Opis |
|---|---|
| `word_substitution` | reč zamenjena drugom |
| `word_omission` | reč izostavljena |
| `word_insertion` | dodata reč koje nema u izvoru |
| `word_order` | iste reči, drugi redosled unutar rečenice |
| `sentence_order` | rečenica uneta u pogrešno numerisano polje |
| `intrusion` | reč koja ne postoji ni u jednoj od N rečenica te stavke |
| `cross_intrusion` | reč iz druge rečenice iste stavke, uneta u pogrešnu |

### 5.3 Podklase

Kao u Scenariju 2, računaju se na sirovim vrednostima i izveštavaju zasebno:

| Podklasa | Ocena |
|---|---|
| `case_only` | netačno |
| `diacritic_only` | netačno |
| `punctuation_only` | tačno, jer se završna tačka zanemaruje |
| **`paraphrase`** | **netačno, ali izdvojeno** |

`paraphrase` je najvrednija mera u ovom scenariju. Označava rečenicu koja je smisleno tačna ali nije doslovna, na primer „Molimo da potvrdite prijem" umesto „Molimo potvrdite prijem". Razdvaja pamćenje smisla od pamćenja tačnog oblika, što je jedini nalaz koji Scenario 1 daje a ostala dva ne mogu.

Prepoznavanje: rečenica u kojoj su sve reči iz izvorne rečenice ili njihovi oblici, uz izmenjen redosled ili dodate funkcijske reči, a nijedna sadržinska reč nije zamenjena. Pravilo se u pilotu podešava; do tada je dovoljno prepoznati slučajeve sa dodatim ili izostavljenim funkcijskim rečima uz očuvane sadržinske.

Uz to se izveštava i tačnost računata na dva načina, `strict` i `lenient`, kao u Scenariju 2.

---

## 6. Mere kucanja

U ovom zadatku je kucanje sama operacija, pa je brzina kucanja najveći konfund. Test kucanja iz Sesije 1 je kovarijata, ali se meri i unutar zadatka.

Po polju se beleži: `first_keystroke_ms`, `keystroke_count`, `backspace_count`, ukupno vreme unosa, i **niz razmaka između pritisaka**.

Iz razmaka se u analizi izvode dve mere:

- **brzina kucanja u naletu**: znakova u sekundi, računato samo iz razmaka kraćih od 500 ms, dakle bez pauza
- **struktura pauza**: broj i trajanje pauza dužih od 1000 ms

Podela je bitna. Brzina u naletu je motorička sposobnost i ne bi trebalo da zavisi od N. Pauze su prizivanje iz memorije i treba da rastu sa N. Ako obe rastu sa N, u pitanju je opšte usporenje, a ne opterećenje radne memorije, i to treba znati.

Beleže se vremena pritisaka **samo unutar polja zadatka**.

---

## 7. Izgled ekrana

Jedan prozor. Rečenice u fazi kodiranja i polja za unos zauzimaju isti prostor na ekranu, tako da se raspored ne pomera pri prelasku između faza.

Rečenice numerisane, jedna ispod druge, ista veličina slova kao u poljima za unos.

Zajednička pravila iz jezgra ostaju: fiksne dimenzije, bez animacija, bez pomeranja sadržaja, ista svetlina pozadine u svim fazama, zone interesovanja upisane u `session` red.

Pri ponovnom uvidu rečenice se ubacuju u stranicu i posle zatvaranja ponovo uklanjaju, ne sakrivaju preko CSS-a.

---

## 8. Logovanje

Format iz `core/logger.js`, `scenario: "S1"`.

Tipovi događaja: `block_start`, `item_start`, `encoding_start`, `encoding_end` (sa `encoding_actual_ms` i `mode`), `peek_start`, `peek_end` (sa `peek_duration_ms`), `field_focus`, `field_submitted`, `item_end`, `block_end`.

`field_submitted` sadrži `sentence_index`, `entered_text` (sirovo, tačno kako je otkucano), `first_keystroke_ms`, `keystroke_count`, `backspace_count`, `total_input_ms`, `inter_key_intervals` i `is_final`.

Pravilo `is_final` iz Scenarija 2 važi i ovde: sve mere tačnosti se računaju isključivo iz poslednjeg unosa u polje.

---

## 9. Provera ispravnosti

`analyze_log.py`, grana za `S1`, ispisuje po nivou N:

- tačnost po reči i po rečenici, `strict` i `lenient`, sa razlikom u procentnim poenima
- tačnost po klasi dužine rečenice
- raspodelu tipova grešaka i podklasa, sa izdvojenim udelom `paraphrase`
- broj uvida po stavci, odnos prema N, ukupno vreme u uvidu
- trajanje faze kodiranja, odvojeno za `user` i `auto` prelazak
- brzinu kucanja u naletu i strukturu pauza, po klasi dužine
- **efekat pozicije**: tačnost po rednom broju rečenice unutar stavke. Očekuje se bolja reprodukcija prve i poslednje, što je provera da zadatak zaista opterećuje zadržavanje
- znake odustajanja i odstupanje tajminga

Provera broja polja: mora biti tačno `stavke * N`.

Opcija `--detail` daje tabelu po rečenici: stavka, redni broj, klasa dužine, izvorna rečenica, uneti tekst, tačnost po reči, tip greške, podklasa, `first_keystroke_ms`, broj brisanja, broj uvida pre unosa.

---

## 10. Šta ne raditi

- Ne praviti novu infrastrukturu; koristiti `core/`.
- Ne uzimati tačnost po celoj rečenici kao primarnu meru.
- Ne uvoditi zastoj ni ograničenje na ponovni uvid.
- Ne uvoditi rok po polju sa automatskim napredovanjem.
- Ne računati tačnost u aplikaciji.
- Ne uključivati proveru pravopisa ni automatsko dopunjavanje.
- Ne dozvoliti kopiranje i lepljenje; `core/guard.js` to već rešava.
- Ne uvoditi dijakritiku u materijal dok se ne odluči za sva tri scenarija odjednom.
- Ne uvoditi nasumičnost u toku izvođenja.

---

## 11. Redosled izrade

1. Generisanje rečenica: `data/sentences.json`, sa klasama dužine i proverom broja reči. Pregledati 30 nasumičnih rečenica pre nastavka.
2. Grana `--scenario S1` u `generate_stimuli.py`, sa sastavom po nivoima i disjunktnošću po ispitaniku.
3. Grana za `S1` u `dump_item.py`.
4. **Serverska verzija:** `scenarios/s1.js`, faza kodiranja i unosa, ponovni uvid. Proveriti da se koristi `core/`, bez dupliranog koda.
5. Grana za `S1` u `analyze_log.py`: poravnanje po rečima, tipovi grešaka, podklase, mere kucanja, efekat pozicije. **Otvorena stavka, odložena sa koraka D uputstva za spajanje jezgra (tačka F): ista grana treba da doda i tačnost po polju `source` (`enron` naspram `constructed`) i da izveštava ako se te dve grupe bitno razlikuju (poreklo kao konfund).** Nije rešeno ranije jer S1 do sada nije imao definisan zadatak/log šemu da bi "tačno" uopšte imalo značenje — sada ih ovaj korak definiše, pa se F rešava ovde, ne odvojeno.
6. Opcija `--detail` za `S1`.
7. **Samostalna verzija** u `standalone/`, sa ugrađenim materijalom za `DEMO` ispitanika, bez tvrde provere URL parametara, sa izbornikom za N.
8. Dopuna `README.md`.

Posle svakog koraka pokrenuti demo blok na N = 3 i N = 7 i pregledati log. Ne prelaziti dalje bez potvrde.

Posle koraka 4 proveriti da izmene nisu promenile ponašanje Scenarija 2 i 3, poređenjem sa referentnim logovima iz refaktora.
