# s2-demo — demonstrator Scenarija 2

Radna demonstracija zadatka prenošenja podataka o firmi između dva prozora
(sintetički materijal, dokument → tabela, po sećanju, N ∈ {3,5,7}). Vidi
izvorno uputstvo (dopuna uz `SPEC_S3_demo.md`) za punu specifikaciju; ovaj
README pokriva samo pokretanje i odstupanja/pretpostavke koje je trebalo
razrešiti da bi uputstvo bilo izvodljivo.

**Ovaj projekat NEMA runtime zavisnost od `../s3-demo`.** Baza firmi
(`data/companies.json`) se generiše lokalno, iz istog seed-a. Jedina veza sa
s3-demo-om je jednokratan, eksplicitan korak koji pravi lokalni snimak
iskljucenih firmi (`data/excluded_companies.json`) -- posle njega,
`generate_stimuli.py --scenario S2` više nikad ne dodiruje `../s3-demo`.
Videti "Zajednička baza firmi sa Scenarijem 3" niže.

## Pokretanje

```
python generate_stimuli.py --scenario S2 --snapshot-exclusions s3-demo/data/items_S3b.json   # JEDNOM, iz korena repozitorijuma
python generate_stimuli.py --scenario S2 --seed 20260825 --participants 40                     # isti --seed kao s3-demo!
cd s2-demo
python server.py                                                                                # http :8000, ws :8766
```

Prvi poziv (`--snapshot-exclusions`) se ponavlja samo ako se `s3-demo`
ponovo generiše (nov seed ili nova lista učesnika) -- videti niže. Drugi
poziv (`--seed`/`--participants`) je normalno, ponovljivo generisanje i
NE dodiruje `../s3-demo` uopšte; ako `data/excluded_companies.json` ne
postoji, prekida se sa jasnom porukom umesto da tiho generiše bez
iskljucivanja.

`server.py`-jev staticki koren je `eeg-tasks/` (roditelj s2-demo/), ne
s2-demo/ sam -- `app/index.html` ucitava deljeni `core/` i `data/` preko
`"../../"`, pa URL uvek nosi `/s2-demo/` prefiks (ranije je nedostajao,
davao je 404 na core/*.js -- ispravljeno).

Otvoriti u pregledaču, na primer (`<SIFRA>` je jedna od stvarnih šifri iz
`data/participant_codes.json`, generisanih preko `generate_participant_codes.py`
-- ne postoji fiksan format tipa "P07"):

```
http://localhost:8000/s2-demo/app/index.html?participant=<SIFRA>&n=5
http://localhost:8000/s2-demo/app/index.html?participant=DEMO&n=5&demo=1
http://localhost:8000/s2-demo/app/index.html?practice=1
```

`server.py` zahteva paket `websockets` (`pip install websockets`). Bez njega
HTTP deo i dalje radi normalno; WebSocket prijem se gasi uz upozorenje u
konzoli, a `app/task.js` tada sam preuzima `.jsonl` log kao fajl iz
pregledača na kraju bloka (vidi "Logovanje bez servera" niže). `pylsl` je
potpuno opciono i samo za EEG markere (sekcija 8). Port WebSocket-a (8766)
je namerno različit od s3-demo-a (8765) da oba demoa mogu da rade
istovremeno na istoj mašini.

Kontrolni ispis stavki (sekcija 12, korak 1-2):

```
python dump_item_s2.py --participant DEMO --n 5 --random 20 --seed 1
```

Analiza:

```
python analyze_log_s2.py logs/*.jsonl
```

Na Windows konzoli, ako se srpska dijakritika (č/ć/š/ž/đ) u ispisu prikazuje
kao `?` ili nepravilni znaci, pokrenuti sa `PYTHONIOENCODING=utf-8` ispred
komande -- ovo je ograničenje podrazumevanog kodnog rasporeda konzole, ne
greška u skriptu (podaci u `.jsonl` su ispravan UTF-8).

## Samostalna verzija (bez servera, dvoklik)

Analogno s3-demo-u: `build_standalone_s2.py` pravi jedan
`standalone/index.html` fajl sa svim podacima (svih ~40 učesnika, sve tri
vrednosti N) i celim `task.js`/`style.css` ugrađenim direktno u fajl.
Otvara se dvoklikom (`file://`), radi bez mreže.

```
python ../generate_stimuli.py --scenario S2 --seed 20260825 --participants 40   # ako vec nije pokrenuto
python build_standalone_s2.py
```

Rezultat je `standalone/index.html` (~2-3 MB -- znatno manje od s3-demo-a
jer S2 nema `suggestions.json` niti distraktore po polju). Podržava iste
URL parametre kao server verzija (`?participant=...&n=...`, `&demo=1`,
`?practice=1`).

**Bez tvrde provere URL parametara**, isti obrazac kao s3-demo: nedostajući
ili neispravan parametar dobija podrazumevanu vrednost
(`participant=DEMO&n=5&demo=1`) umesto da odbije da krene. Na početnom
ekranu postoji mali izbornik (N: 3/5/7); ako se ne dira, koristi se
vrednost iz URL-a/podrazumevana. Isti `app/task.js` radi u oba režima
(server i samostalni) -- prepoznaje `window.__S2_EMBEDDED__` i preskače
mrežne pozive kad postoji. `standalone/index.html` je **generisan** fajl --
izmene se rade u `app/`, pa se `build_standalone_s2.py` pokrene ponovo.

**Živi javni URL (GitHub Pages).** Ista `standalone/index.html` sadržina je
objavljena na `https://mladen327.github.io/s2-demo-standalone/` --
GitHub Pages servira iz `docs/` foldera (jedina putanja koju Pages UI nudi
osim korena grane), pa je `docs/index.html` **doslovna kopija**
`standalone/index.html`. Posle svakog `build_standalone_s2.py`, ako se
želi da javni URL prati izmenu:
```
cp standalone/index.html docs/index.html
git add docs/index.html && git commit -m "..." && git push
```
Isti URL parametri rade i tu (npr.
`?participant=DEMO&n=5&demo=1`), isto bez tvrde provere. Log se, kao i u
svakoj `file://`/bez-servera situaciji, preuzima kao `.jsonl` fajl preko
pregledača na kraju bloka -- GitHub Pages nema WebSocket server.

## Zajednička baza firmi sa Scenarijem 3

Sekcija 3 uputstva zahteva da firme dodeljene istom ispitaniku u S2 i S3
budu **disjunktni skupovi** (inače bi ponovni susret sa istom firmom bio
lakši zbog poznavanja materijala -- lažni efekat u matrici prenosa).

Da bi iskljucivanje po `company_id` uopšte imalo smisla, `"C047"` mora da
označava **istu firmu** u oba projekta. To više nije pitanje dve odvojene,
ručno usklađene kopije koda -- `gen_companies()` živi jednom, u
`shared/generate_common.py`, i konsolidovani `generate_stimuli.py` je zove
identično za `--scenario S2` i `--scenario S3` (iste fiksne liste, isti
redosled `rng.*` poziva -- uključujući polja koja S2 uopšte ne koristi, npr.
`contract_number`, `employee_count`; ona su zadržana u `companies.json`
isključivo da bi redosled povlačenja iz generatora ostao identičan S3-u).
Za **isti `--seed`**, `s2-demo/data/companies.json` i `s3-demo/data/companies.json`
su bajt-identični za deljena polja -- provereno automatski (videti niže).

**Iskljucivanje je dvokoračno, sa jasnom granicom oko toga ko sme da dodirne
`../s3-demo`:**

1. **Jednokratan snimak** (jedino mesto koje čita iz s3-demo-a), iz korena
   repozitorijuma:
   ```
   python generate_stimuli.py --scenario S2 --snapshot-exclusions s3-demo/data/items_S3b.json
   ```
   Ovo učitava `items_S3b.json`, gradi
   `{participant_id: [company_id koje je taj ucesnik video u S3b]}` (unija
   preko N=3/5/7, jer se S3b sempluje po N nezavisno pa se firma može
   ponoviti i unutar samog S3b), i upisuje `data/excluded_companies.json`
   -- **unutar `s2-demo/data/`**, zajedno sa sha256 hešom izvornog
   `items_S3b.json` (radi sledljivosti: iz kog tačno stanja s3-demo-a je
   snimak napravljen).

2. **Normalno generisanje** (`--seed`/`--participants`, bez ijedne mrežne ili
   cross-folder operacije) čita **isključivo** `data/excluded_companies.json`
   i primenjuje ga po učesniku. **Ako fajl ne postoji, skript prekida sa
   jasnom porukom** (ne generiše tiho bez isključivanja -- razlika u odnosu
   na raniju verziju, koja je u tom slučaju samo upozoravala i nastavljala).

Snimak treba osvežiti (ponovo pokrenuti korak 1) samo ako se `s3-demo`
ponovo generiše sa drugim `--seed` ili drugim brojem učesnika.

Provereno posle generisanja (seed=20260825, 40 učesnika + DEMO): baza firmi
je bajt-identična s3-demo-u (0 razlika u 200×8 deljenih polja), sve PIB/
matični broj kontrolne cifre validne, i **0 preklapanja** između S2 i S3b
skupova firmi kod svih 41 ucesnika -- ponovo provereno i posle ovog
refaktorisanja.

## Integritet stimulusa (heš u logu)

Svaki `session` red loga sadrži `items_hash` i `companies_hash` -- sha256
sirovih bajtova `data/items_S2.json` i `data/companies.json` u trenutku
snimanja te sesije (`"sha256:<hex>"`, ista šema u oba fajla i u obe
verzije aplikacije). U server režimu ih `app/task.js` računa uživo, preko
`fetch()` + `crypto.subtle.digest`, nad tačno onim bajtovima koji su
stigli preko mreže (ne nad ponovo serijalizovanim JSON-om). U samostalnoj
verziji, gde nema mreže, iste heševe unapred izračuna `build_standalone_s2.py`
(iz istih fajlova, `hashlib.sha256`) i ugrađuje ih kao gotove niske.

`analyze_log_s2.py` na početku svakog pokretanja (pre bilo kakve analize)
ponovo izračuna heš trenutnog `data/items_S2.json`/`data/companies.json` i
uporedi ga sa `items_hash`/`companies_hash` iz zaglavlja **svakog** učitanog
bloka. Ako se ne poklapaju (ili polje nedostaje), skript **prekida odmah**,
sa porukom koja imenuje fajl i oba heša -- log snimljen sa drugom
generacijom stimulusa (drugi seed, drugi broj učesnika, ručno izmenjen
fajl) bi inače dao tiho pogrešno poređenje tačnosti. Provereno: prolazi na
validnom logu, i ispravno prekida (exit 1) kad se `items_S2.json` posle
snimanja izmeni.

## Odstupanja od uputstva i zašto

**1. Klase težine polja za proveru (sekcija 3.1/3.2) -- isti problem i isto
rešenje kao u s3-demo.** Tabela u 3.1 tretira "ulica + broj" kao jedno polje
srednje težine, čime klasa niske težine ima samo dva polja (`city`,
`contact_person`) -- nedovoljno za N=7 iz tabele 3.2, koja traži tri polja
niske težine. Kao i u s3-demo (videti `s3-demo/README.md`), `street_number`
je ovde izdvojen kao svoje polje niske težine (kratak broj bez značenja,
lako se pamti pogrešno), dok `street` ostaje srednje. Rezultat: 2 visoka /
3 srednja / 3 niska polja, tačno pokriva N=3/5/7. Videti komentar u
`generate_stimuli.py` uz `S2_FIELD_WEIGHT`. Posledica ove podele: u
Prozoru B, "ulica" i "broj" se pojavljuju kao dve odvojene kolone kad su
oba deo iste stavke (nikad oba istovremeno, pošto su u različitim klasama
težine i mogu ali ne moraju biti izabrani zajedno).

**2. Tačnost je DOSLOVNA (strict), ne pravopisno tolerantna (revidirano
posle pilota).** Prvobitna verzija je koristila jednu normalizaciju
(lowercase + bez dijakritike + bez razmaka/tačke/kose crte/crtice) za
`correct=true`. To je promenjeno: `normalize_strict()` u
`analyze_log_s2.py` sad poredi **doslovno** -- ne svodi na mala slova, ne
uklanja dijakritiku. Jedini izuzetak ostaje razmak (svuda) i, samo za polja
čiju masku unosi interfejs a ne ispitanik (`SPACING_FIELDS`: PIB, matični
broj, telefon), tačka/kosa crta/crtica -- isti skup znakova koji
`classify_subclass()` koristi za podklasu `spacing_only`, namerno
usaglašeno. Razlog dodavanja tačke: prikaz telefona (sekcija 3.3) ubacuje i
kosu crtu i crticu (`063/241-8870`), dok je sirova `reference_value` čist
niz cifara -- bez ovoga bi ispravno otkucan telefon bio lažno označen kao
netačan.

Stara (pravopisno tolerantna) normalizacija nije obrisana -- živi kao
`normalize_lenient()` i koristi se isključivo za uporednu "lenient" meru
tačnosti u izveštaju (odeljak "Podklase grešaka" niže), da se u pilotu vidi
koliko je grešaka isključivo pravopisne prirode. Pravilo normalizacije je i
dalje na jednom mestu po varijanti (sekcija 6.2: "Pravilo normalizacije
mora biti na jednom mestu") -- sad na dva imenovana mesta umesto jednog,
jer sad postoje dve NAMERNO različite definicije tačnosti, ne jedna.

**3. Zona interesovanja (ROI) -- jedan pravougaonik za oba prozora.**
Sekcija 9 traži da se ROI upiše za oba prozora u `session` redu loga.
Pošto je u ovom scenariju **uvek vidljiv tačno jedan prozor** i oba
zamenjuju jedno drugo unutar istog fiksnog `#stage` elementa (CSS, fiksna
širina/visina, nezavisno od sadržaja -- sekcija 9: "fiksne dimenzije, bez
pomeranja sadržaja"), Prozor A i Prozor B fizički zauzimaju **isti
pravougaonik na ekranu**. `roi.document` i `roi.spreadsheet` u sesijskom
zaglavlju su zato namerno identične vrednosti -- ne greška, nego posledica
dizajna koji sprečava bilo kakav pomeraj/skok pri prebacivanju (bitno jer
se ono dešava desetinama puta po bloku). Za razliku od s3-demo-a, ovde nije
bilo potrebno "priming" renderovanje pre merenja ROI-ja jer `#stage` ima
fiksnu CSS veličinu nezavisnu od sadržaja.

**4. Vežba (`?practice=1`) bez povratne informacije o tačnosti.** Za
razliku od s3-demo-a (čija vežba prikazuje "Tačno"/"Netačno" po stavci),
S2 vežba **ne** prikazuje ništa o tačnosti unosa. Razlog: sekcija 4.2
uputstva kaže "Bez povratne informacije o tačnosti, ni u jednom trenutku" --
formulacija je apsolutna i nije ograničena na glavni blok, pa je primenjena
i na vežbu. Vežba ostaje korisna za upoznavanje sa F2 prebacivanjem i
tipom ćelija, samo bez ocene ispravnosti.

## Mere u logu i izveštaju

Ovo poglavlje popisuje sve što je dodato posle prve verzije demonstratora,
kroz nekoliko rundi revizije zasnovane na probnim blokovima.

**Tačan broj polja (`is_final`).** Svako napuštanje ćelije (blur) se i
dalje beleži kao `cell_submitted`, uključujući ponovne posete posle
povratka u Prozor A -- ali samo TAČNO JEDAN takav događaj po (stavka,
polje) nosi `is_final: true` (poslat pri potvrdi stavke, za sve ćelije
odjednom). Sve mere tačnosti, tipova grešaka i `first_keystroke_ms` u
`analyze_log_s2.py` se računaju isključivo iz `is_final: true` događaja.
Izveštaj eksplicitno proverava da je broj takvih događaja tačno
`stavke × N` po bloku ("Provera broja polja: ... [OK]").

**Trošak prebacivanja je premešten sa kašnjenja na ograničenje broja
povrataka.** `SWITCH_DELAY_MS = 0` -- prelazak između prozora je trenutan
(jedan animacioni frejm, ~0-16ms). `MAX_SWITCHES_PER_ITEM` (broj povrataka
u Prozor A dozvoljen po stavci, posle faze kodiranja) postoji kao potpuno
implementirana, ali **neaktivna** (`null`) mehanika: kad se postavi na
broj, dalji pokušaji povratka posle granice se odbijaju i beleže kao
`switch_denied` (`from_field`, `switches_so_far`). I dalje se beleži svaki
uspešan povratak (`window_switch`) i njegovo trajanje (`document_stay_ms`,
niže). Izveštaj sadrži: broj povrataka po stavci i odnos prema N (prosek i
medijana), udeo stavki gde je granica iskorišćena do kraja (kad je
postavljena; "n/a" kad nije), i broj `switch_denied` pokušaja po N.

**Trajanje boravka u Prozoru A (`document_stay_ms`).** Svaki `window_switch`
ka tabeli nosi trajanje boravka koji se upravo završava (`null` za
automatski prelazak posle kodiranja, jer se tada ništa nije ni posećivalo).
Izveštaj sabira ovo po stavci: "Ukupno vreme u Prozoru A po stavci".

**Ispitanik sam može da završi kodiranje.** Dugme "Spreman (F2)" u Prozoru
A i taster F2 prelaze u Prozor B pre isteka planiranog trajanja kodiranja.
Donja granica `ENCODING_MIN_MS = 3000` sprečava slučajan preskok -- dugme
je `disabled` i F2 se ignoriše do tada, bez ikakvog loga za ignorisane rane
pokušaje. Gornja granica (`ENCODING_BASE_MS + N*ENCODING_MS_PER_FIELD`)
ostaje nepromenjena kao automatski prelazak. `encoding_end` nosi
`encoding_actual_ms` i `mode: "user"|"auto"`. Izveštaj: medijana/p90
trajanja kodiranja, po N i odvojeno po `user`/`auto`.

**Podklase grešaka, na sirovim (nenormalizovanim) vrednostima, računaju se
PRE tipologije od šest tipova i izveštavaju se odvojeno:**

| Podklasa | Opis | Ocena (strict) |
|---|---|---|
| `case_only` | razlika samo u velikim/malim slovima | NETAČNO |
| `legal_form_only` | razlika samo u pravnom obliku (a.d./d.o.o./o.d.) | NETAČNO (forsirano) |
| `diacritic_only` | razlika samo u dijakritici | NETAČNO |
| `spacing_only` | razlika samo u razmaku/tački/kosoj crti/crtici (PIB, matični broj, telefon) | TAČNO |
| `word_order` | iste reči, drugi redosled | NETAČNO |

Verdikt u izveštaju se računa iz podataka (ne iz fiksne tabele) kao
samo-provera. Pošto `spacing_only` ostaje tačno a preostale četiri postaju
netačne, izveštaj dodatno prikazuje tačnost na dva načina, jedno pored
drugog, po klasi težine: **strict** (doslovno, sad zvanična mera) i
**lenient** (staro pravopisno tolerantno pravilo), sa razlikom u procentnim
poenima -- da se u pilotu vidi koliko je grešaka isključivo pravopisne
prirode.

**Opcija `--detail`** dodaje tabelu po polju (stavka, polje, klasa težine,
tačna/uneta vrednost, tačno DA/NE, tip greške, podklasa,
`first_keystroke_ms`, `backspace_count`, broj povrataka pre unosa tog
polja) posle zbirnog izveštaja, ne umesto njega:
```
python analyze_log_s2.py --detail logs/*.jsonl
```

## Šta NIJE potpuno pokriveno / poznata ograničenja

- **F5 / Ctrl+R / F11 / Ctrl+W blokiranje (sekcija 4.1)** je best-effort.
  Skriptovano sprečavanje ovih kombinacija je u većini modernih pregledača
  dozvoljeno za F5/Ctrl+R (test u Chromium potvrđuje `preventDefault()`
  radi), ali neki pregledači namerno ne dozvoljavaju stranicama da blokiraju
  F11 (fullscreen) ili Ctrl+W (zatvaranje kartice) iz bezbednosnih razloga,
  bez obzira na `preventDefault()`. Kod pokušava u sva četiri slučaja
  (`blockRefreshKeys` u `app/task.js`); ako se u praksi pokaže da neki
  pregledač ipak dozvoli slučajno zatvaranje/osvežavanje, jedina pouzdana
  odbrana je uputstvo ispitivaču da ne koristi te tastere, ne kod.
- **Logovanje bez servera.** Isti mehanizam kao s3-demo: ako `server.py`
  (ili paket `websockets`) nije dostupan, `app/task.js` baferuje događaje u
  memoriji i na kraju bloka ih preuzima kao `.jsonl` fajl preko pregledača.
  Ako se veza sa serverom prekine usred sesije, rani događaji su već
  isporučeni; samo događaji posle prekida se preuzimaju kao fajl -- log te
  sesije je tada podeljen na dva mesta.
- **Vežba** koristi zajedničke stavke (nije po `participant` parametru,
  isto kao s3-demo). `server.py` je usmerava u `logs/practice/` na osnovu
  `variant` polja u zaglavlju sesije.
- **UI JESTE testiran u pravom pregledaču** u ovoj sesiji (Playwright +
  Chromium, headless), za razliku od s3-demo-a čiji README beleži da to
  nije urađeno. Testirano: ceo tok kodiranje → automatsko prebacivanje →
  unos → F2 napred/nazad (sa svim obeleženim poljima pri povratku,
  vrednost ćelije sačuvana kroz prebacivanje) → potvrda → sledeća stavka,
  za ceo demo blok (server režim i samostalna `file://` verzija), plus
  blokiranje kopiranja/lepljenja, gejting dugmeta za potvrdu, vežba, i
  greška pri nedostajućim URL parametrima. `analyze_log_s2.py` je pokrenut
  nad stvarno snimljenim logovima iz oba režima; tipologija grešaka je
  dodatno proverena sa 10 ručno pripremljenih parova (uneto, referenca) po
  svih 5 tipova + tačan pogodak. I dalje vredi ponoviti vizuelnu proveru na
  stvarnom ekranu/rezoluciji ispitivača pre snimanja pravih podataka
  (pogotovo pre EEG merenja) -- headless test ne hvata sve što bi oko
  uhvatilo (npr. font rendering, DPI skaliranje).
- **Maska telefona i pozicija kursora.** `formatPhoneProgressive()` u
  `app/task.js` progresivno umeće `/` i `-` dok se kuca, ali ne upravlja
  eksplicitno pozicijom kursora nakon umetanja -- kod brisanja/izmene usred
  broja kursor može da "skoči" na kraj polja. Ne utiče na sadržaj koji se
  na kraju beleži (`entered_value` je uvek tačan tekst iz polja), samo na
  udobnost kucanja; prihvatljivo za demonstrator, vredi doraditi ako se
  telefon pokaže kao polje sa neuobičajeno visokom stopom grešaka tipa
  `insertion`/`omission` koje bi mogle biti artefakt kursora umesto
  stvarnog zaboravljanja.

## Parametri za reviziju posle pilota

- `ENCODING_BASE_MS`, `ENCODING_MS_PER_FIELD`, `ENCODING_MIN_MS`,
  `SWITCH_DELAY_MS`, `MAX_SWITCHES_PER_ITEM`, `ITEM_GAP_MS`,
  `BLOCK_DURATION_MS`, `ENFORCE_CELL_DEADLINE` -- vrh `app/task.js`. Svi se
  upisuju i u `session` red loga (`encoding_base_ms`,
  `encoding_ms_per_field`, `encoding_min_ms`, `switch_delay_ms`,
  `max_switches_per_item`, `item_gap_ms`, `block_duration_ms`,
  `enforce_cell_deadline`), pa se za svaki snimljeni blok tačno zna pod
  kojim je tajmingom sniman. Trenutne vrednosti: `SWITCH_DELAY_MS = 0`
  (prelazak trenutan) i `MAX_SWITCHES_PER_ITEM = null` (povratak
  neograničen) -- oba su svesni izbor posle nekoliko rundi probe (videti
  "Mere u logu i izveštaju" gore), ne podrazumevane vrednosti koje čekaju
  podešavanje. `MAX_SWITCHES_PER_ITEM` ima potpuno implementiranu logiku
  spremnu za reaktivaciju (samo upisati broj); UI povratna informacija
  (brojač/vizuelni signal) je uklonjena i trebalo bi je ponovo osmisliti
  ako se granica ikad ponovo aktivira. `ENFORCE_CELL_DEADLINE` nema još
  numeričku vrednost (sekcija 7: rok se izvodi iz raspodele
  `first_keystroke_ms` tek posle pilota) -- kad se odredi, dodati konstantu
  `CELL_DEADLINE_MS` i granu u `runEntryPhase()`.
- `DEMO_ITEM_CAP` (broj stavki u `&demo=1` režimu, podrazumevano 3) --
  imati na umu da je po stavci znatno duže nego u s3-demo-u (npr. N=7 samo
  faza kodiranja traje do 39s ako se ne završi ranije dugmetom "Spreman"),
  pa ceo demo blok na N=7 može trajati više minuta.
- `S2_ITEMS_PER_BLOCK`, `S2_PRACTICE_ITEMS`, `S2_PRACTICE_N` -- vrh S2 dela
  u `generate_stimuli.py`. `S2_ITEMS_PER_BLOCK=30` je namerno velikodušno --
  koliko se stavki stvarno završi u `BLOCK_DURATION_MS=180000` zavisi
  mnogo od N (mnogo manje nego u s3-demo-u, gde je po stavci brže), ali
  višak samo znači da nikad neće "ponestati" stavki pre isteka bloka.
- `SWITCH_MAX_DEVIATION_WARN_MS` (prag upozorenja u `analyze_log_s2.py`,
  sekcija 10 traži 50 ms; u testiranju u Chromium izmereno maksimalno
  odstupanje ~16 ms).
- `--seed` za `generate_stimuli.py --scenario S2` **mora** ostati usklađen
  sa onim korišćenim za `--scenario S3` da bi baza firmi ostala ista
  (videti "Zajednička baza firmi sa Scenarijem 3" gore) -- ako se seed za
  S3 ikad promeni, ponovo generisati i S2 sa istim novim seedom.
