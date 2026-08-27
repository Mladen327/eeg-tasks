# Uputstvo za izradu: demonstrator Scenarija 2

Zadatak unosa podataka iz dokumenta u tabelu, sa sintetičkim podacima o firmama u Srbiji, na tri nivoa opterećenja.

Ovaj dokument je dopuna uz `SPEC_S3_demo.md`. Sve što nije ovde izričito promenjeno preuzima se odatle: format logovanja, merenje vremena preko `performance.now()`, pravila o zonama interesovanja, LSL markeri, režimi pokretanja i pravila o nasumičnosti. Kod, nazivi datoteka i identifikatori na engleskom, tekst za ispitanika na srpskom.

**Redosled isporuke: prvo serverska verzija, pa tek onda samostalni HTML.** Samostalna verzija je izvedena iz serverske, sa podacima ugrađenim u datoteku, i pravi se tek kada serverska radi.

---

## 1. Šta Scenario 2 meri i po čemu se razlikuje od Scenarija 3

Misaona operacija je zapamtiti podatak i preneti ga između prozora. Nema asistencije modela, nema odlučivanja o tuđem predlogu, nema poređenja. Ispitanik čita podatke u jednom prozoru, prelazi u drugi i unosi ih po sećanju.

Tri razlike koje moraju ostati:

| | Scenario 3 | Scenario 2 |
|---|---|---|
| Odgovor | izbor iz tri ponuđene vrednosti | **kucanje po sećanju** |
| Asistencija | postoji u varijanti S3b | nema je nikada |
| Ponovni uvid | dugme, jednom po stavci | povratak u prozor sa dokumentom, neograničeno ali sa troškom |

Kucanje se u Scenariju 2 zadržava iako je u Scenariju 3 uklonjeno. Razlog: prenošenje podatka jeste sama operacija koja se meri. Ako bi se zamenilo izborom, Scenario 2 bi postao isti zadatak kao Scenario 3 i matrica prenosa bi izgubila jedno polje.

---

## 2. Struktura projekta

```
s2-demo/
  generate_stimuli_s2.py
  server.py
  analyze_log_s2.py
  dump_item_s2.py
  data/
    companies.json
    items_S2.json
  app/
    index.html
    task.js
    style.css
  standalone/
    index.html
  logs/
  README.md
```

---

## 3. Podaci

Koristi se **isti generator baze firmi** kao u Scenariju 3, sa istim pravilima: naziv od korena i pravnog oblika, PIB od 9 cifara sa ispravnom kontrolnom cifrom po ISO 7064 MOD 11,10, matični broj od 8 cifara, gradovi i ulice iz fiksne liste, kontakt osoba i telefon.

**Firme dodeljene istom ispitaniku u Scenariju 2 i u Scenariju 3 moraju biti disjunktni skupovi.** Ako se ista firma pojavi u oba zadatka, drugi susret je lakši zbog poznavanja materijala, a to bi se u matrici prenosa videlo kao lažni efekat. Generator prima parametar `--exclude data/items_S3b.json` i izbacuje već iskorišćene firme.

### 3.1 Polja za unos i klase težine

| Polje | Format | Klasa |
|---|---|---|
| `pib` | 9 cifara | visoka |
| `registration_number` | 8 cifara | visoka |
| `company_name` | 2 do 3 reči | srednja |
| `street` plus `street_number` | tekst plus broj | srednja |
| `contact_phone` | 06X/XXX-XXXX | srednja |
| `city` | jedna reč | niska |
| `contact_person` | ime i prezime | niska |

### 3.2 Sastav stavke po nivoima

Isto pravilo kao u Scenariju 3, i iz istog razloga: više od jednog niza cifara bez značenja istovremeno gura sve ispitanike u zonu otkaza.

| N | Visoka | Srednja | Niska |
|---|---|---|---|
| 3 | 1 | 1 | 1 |
| 5 | 1 | 2 | 2 |
| 7 | 1 | 3 | 3 |

### 3.3 Prikaz vrednosti

Segmentacija kao u Scenariju 3: PIB `108 452 291`, matični broj `20 447 719`, telefon `063/241-8870`. Segmentacija je isključivo vizuelna; u `items_S2.json` i u logu vrednosti se čuvaju bez razmaka i bez kose crte.

---

## 4. Tok zadatka

### 4.1 Dva prozora, jedan vidljiv

Prozor A je dokument sa podacima o firmi, vizuelno oblikovan kao izvod iz PDF čitača. Prozor B je tabela za unos, vizuelno oblikovana kao Excel.

**Uvek je vidljiv tačno jedan prozor.** Ovo je jedini eksperimentalni zahtev; Alt+Tab je samo njegov oblik u stvarnom radu. Oba prozora istovremeno vidljiva ukinula bi zadržavanje u memoriji, koje je predmet merenja.

**Alt+Tab se ne može presresti iz pregledača**, jer ga Windows obrađuje na nivou sistema. Prebacivanje se vezuje za taster `F2` i za dugme na ekranu. U uputstvu za ispitanika se piše „prebacivanje tasterom F2", ne Alt+Tab.

Blokirati `F5`, `Ctrl+R`, `F11` i `Ctrl+W` dok blok traje, jer slučajno osvežavanje uništava blok.

### 4.2 Tok jedne stavke

1. **Faza kodiranja.** Vidljiv je prozor A. Prikazani su podaci o jednoj firmi, sa istaknutih N polja koja treba preneti. Traje `ENCODING_BASE_MS + N * ENCODING_MS_PER_FIELD`, sa vidljivim odbrojavanjem. Po isteku se automatski prelazi na prozor B.
2. **Faza unosa.** Vidljiv je prozor B. Ispitanik unosi vrednosti u ćelije, redom. Napredovanje kroz ćelije tasterom Enter ili Tab.
3. **Povratak u prozor A** je dozvoljen tasterom F2, neograničen broj puta, ali sa troškom (vidi 4.3).
4. Stavka se završava kada su sve ćelije popunjene i ispitanik potvrdi. Prazan ekran `ITEM_GAP_MS`, pa sledeća stavka.

Bez povratne informacije o tačnosti, ni u jednom trenutku.

### 4.3 Trošak prebacivanja

Prelazak između prozora traje `SWITCH_DELAY_MS` (800), tokom kojih je ekran prazan i unos onemogućen.

Bez troška bi ispitanik prebacivao posle svakog polja i zadržavanja u memoriji ne bi ni bilo. Sa troškom, prebacivanje ostaje moguće ali se isplati pamćenje, što je i realno ponašanje u stvarnom radu.

**Broj povrataka u prozor A po stavci je glavna dodatna mera opterećenja i treba da raste sa N.** To je u Scenariju 2 ekvivalent dugmeta za ponovni uvid iz Scenarija 3, s tom razlikom što je ovde ugrađen u samu prirodu zadatka.

Pri povratku u prozor A prikazuju se **sva** istaknuta polja, ne samo ono koje se trenutno unosi.

---

## 5. Onemogućavanje kopiranja

Prozor A se iscrtava kao HTML tekst, ne kao ugrađen PDF u `iframe`. Ugrađen PDF se ne može pouzdano zaštititi od kopiranja.

Mere, sve zajedno:

- `user-select: none` na celom prozoru A
- presretanje i poništavanje `copy`, `cut`, `contextmenu` i `dragstart` događaja
- blokiranje `Ctrl+C`, `Ctrl+X`, `Ctrl+A`, `Ctrl+Insert`
- `paste` u ćelije prozora B se poništava, uz beleženje događaja `paste_blocked` u log

Pokušaj kopiranja se ne prijavljuje ispitaniku porukom, samo se beleži. Poruka bi prekinula tok i unela iznenađenje koje se vidi u fiziologiji.

---

## 6. Unos i provera tačnosti

### 6.1 Ćelije sa fiksnom dužinom

Ćelije za PIB i matični broj imaju vidljivu strukturu od 9 odnosno 8 mesta i primaju samo cifre. Fiksna dužina je zahtev iz protokola i ima merni razlog: bez nje ispitanik troši radnu memoriju i na to koliko je cifara već uneo.

Ćelija za telefon ima masku `06X/XXX-XXXX`. Ćelije za tekst nemaju masku.

Bez automatskog dopunjavanja i bez predloga iz istorije pregledača. Postaviti `autocomplete="off"` i `spellcheck="false"`.

### 6.2 Tačnost se ne računa u aplikaciji

Isto pravilo kao u Scenariju 3. Aplikacija beleži uneti niz, a `analyze_log_s2.py` ga u analizi poredi sa `items_S2.json`.

Normalizacija pre poređenja: uklanjanje razmaka i kose crte, svođenje na mala slova, uklanjanje dijakritike. Pravilo normalizacije mora biti na jednom mestu u skriptu, jer se posle pilota podešava.

### 6.3 Tipologija grešaka

`analyze_log_s2.py` za svako netačno polje određuje tip greške, jer razlike među njima govore o različitim uzrocima:

| Tip | Opis | Tumačenje |
|---|---|---|
| `transposition` | dve susedne cifre zamenile mesta | greška u zadržavanju redosleda |
| `substitution` | jedna cifra ili slovo pogrešno | greška u zadržavanju sadržaja |
| `omission` | nedostaje znak | prekid unosa |
| `insertion` | višak znaka | motorička greška |
| `wrong_field` | uneta vrednost pripada drugom polju iste firme | greška u vezivanju vrednosti za polje |
| `other` | ostalo | |

`wrong_field` je posebno informativan, jer razdvaja pamćenje vrednosti od pamćenja toga kojoj vrednosti pripada.

---

## 7. Tajming

```
ENCODING_BASE_MS      = 4000
ENCODING_MS_PER_FIELD = 5000
SWITCH_DELAY_MS       = 800
ITEM_GAP_MS           = 1500
BLOCK_DURATION_MS     = 180000
```

Sve konstante se upisuju u `session` red loga.

**Nema roka po ćeliji i nema automatskog napredovanja.** Ćelija čeka unos neograničeno. Vreme po ćeliji se meri i beleži, i posle pilota se iz njegove raspodele izvodi eventualni rok. Konstanta `ENFORCE_CELL_DEADLINE = false` ostaje u kodu za kasnije.

---

## 8. Logovanje

Format i pravila iz `SPEC_S3_demo.md`, sekcija 7. Razlike u tipovima događaja:

Obavezni: `block_start`, `item_start`, `encoding_start`, `encoding_end`, `window_switch` (sa `to: "document" | "spreadsheet"` i `reason: "auto" | "user"`), `cell_focus`, `cell_submitted`, `paste_blocked`, `copy_blocked`, `item_end`, `block_end`.

`cell_submitted` sadrži `field_name`, `entered_value` (bez normalizacije, tačno kako je otkucano), `first_keystroke_ms`, `last_keystroke_ms`, `keystroke_count` i `backspace_count`.

`first_keystroke_ms` je vreme od fokusiranja ćelije do prvog pritiska. To je mera prizivanja iz memorije, odvojena od vremena kucanja, i vrednija je od ukupnog vremena po ćeliji.

`backspace_count` je mera nesigurnosti i treba da raste sa N.

Beleže se vremena pritisaka tastera **samo unutar ćelija zadatka**, ne globalno.

---

## 9. Izgled ekrana

Prozor A oblikovati kao dokument: bela stranica, zaglavlje sa nazivom dokumenta, podaci u dve kolone naziv i vrednost. Istaknuta polja obeležiti promenom pozadine, ne promenom veličine.

Prozor B oblikovati kao tabelu: zaglavlja kolona, ćelije sa ivicama, aktivna ćelija obeležena okvirom.

Zajednička pravila iz Scenarija 3 ostaju: fiksne dimenzije, bez animacija, bez pomeranja sadržaja, ista svetlina pozadine u oba prozora i u svim fazama. Poslednje je ovde posebno važno, jer se prozori smenjuju desetinama puta po bloku, a zenica reaguje na promenu svetline.

Zone interesovanja se u `session` red loga upisuju za oba prozora, jer se prebacivanjem menja koji je aktivan.

---

## 10. Provera ispravnosti

`analyze_log_s2.py` ispisuje, po nivou N:

- tačnost po polju i po klasi težine
- **broj povrataka u prozor A po stavci**; očekuje se rast sa N
- raspodelu tipova grešaka
- medijanu i 90. percentil vremena do prvog pritiska, po klasi težine
- broj poništenih pokušaja kopiranja i lepljenja
- raspodelu `backspace_count`
- znake odustajanja: trend tačnosti od prve do poslednje stavke u bloku, uz vreme po stavci
- odstupanje `SWITCH_DELAY_MS` od zadate vrednosti, sa maksimumom

Poslednja stavka je tehnička provera. Ako maksimalno odstupanje pređe 50 ms, tajming nije upotrebljiv za analizu po prozorima od 1 s.

---

## 11. Šta ne raditi

- Ne prikazivati oba prozora istovremeno, ni u jednom režimu osim vežbe.
- Ne pokušavati presretanje Alt+Tab.
- Ne ugrađivati stvarni PDF u `iframe`.
- Ne računati tačnost u aplikaciji.
- Ne dozvoliti lepljenje u ćelije.
- Ne stavljati više od jednog polja visoke težine u istu stavku.
- Ne uvoditi rok po ćeliji sa automatskim napredovanjem.
- Ne uvoditi nasumičnost u toku izvođenja; sve iz `generate_stimuli_s2.py` i iz zadatog seeda.
- Ne dodeljivati istom ispitaniku firme koje je već video u Scenariju 3.

---

## 12. Redosled izrade

1. `generate_stimuli_s2.py`, sa proverom kontrolnih cifara, sa klasama težine i sa isključivanjem firmi iz Scenarija 3. Pregledati 20 nasumičnih stavki.
2. `dump_item_s2.py`, tabelarni ispis stavki za kontrolni list.
3. **Serverska verzija:** `app/` sa prozorom A, prozorom B, prebacivanjem i tajmingom. Proveriti odstupanje `SWITCH_DELAY_MS` preko `analyze_log_s2.py`.
4. Onemogućavanje kopiranja i lepljenja, sa beleženjem pokušaja.
5. `analyze_log_s2.py` u punom obimu, sa tipologijom grešaka.
6. `server.py`, prijem loga preko WebSocket veze i upis u `logs/`, uz LSL markere ako je `pylsl` dostupan.
7. **Samostalna verzija** u `standalone/index.html`, sa podacima ugrađenim u datoteku, bez tvrde provere URL parametara, sa izbornikom za N na početnom ekranu. Podrazumevano `participant=DEMO`, `n=5`, `demo=1`.
8. `README.md` sa uputstvom za pokretanje i sa spiskom parametara koje treba podesiti posle pilota.

Posle svakog koraka pokrenuti jedan demo blok od kraja do kraja i pregledati log. Ne prelaziti na sledeći korak bez potvrde.
