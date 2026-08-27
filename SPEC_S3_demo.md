# Uputstvo za izradu: demonstrator Scenarija 3

Namena: radna demonstracija zadatka provere ugovora, sa sintetičkim podacima, u dve varijante (bez asistencije i uz asistenciju jezičkog modela) i na tri nivoa opterećenja. Koristi se za prikaz saradnicima i etičkoj komisiji, za pilot merenja i kao osnova za glavnu studiju.

Kod, nazivi datoteka i identifikatori na engleskom. Sav tekst koji ispitanik vidi na srpskom.

---

## 1. Tehnološki izbor

- Frontend: obična HTML, CSS i JavaScript datoteka, bez okvira i bez koraka prevođenja. Razlog: tajming mora biti proverljiv čitanjem koda, a build alati unose nepredvidivo kašnjenje pri prvom prikazu.
- Priprema stimulusa: Python 3.11, standardna biblioteka plus `faker` nije obavezan.
- Server: `python -m http.server` je dovoljan za demo; za rad sa EEG opremom koristiti `server.py` iz sekcije 7.
- Bez spoljnih CDN zavisnosti. Sve lokalno, jer laboratorija može biti bez mreže.

---

## 2. Struktura projekta

```
s3-demo/
  generate_stimuli.py
  server.py
  analyze_log.py
  data/
    companies.json
    contract_template.html
    items_S3a.json
    items_S3b.json
    suggestions.json
  app/
    index.html
    task.js
    style.css
  logs/
  README.md
```

---

## 3. Domen: ugovor o pružanju telekomunikacionih usluga

Materijal je ugovor između fiktivnog operatera i jedne firme iz sintetičke baze. Predmet je zakup paketa mobilne telefonije za zaposlene.

**Operater (isti u svim ugovorima):** Interlink Telekom d.o.o., Beograd, Bulevar Zorana Đinđića 105, PIB 104778213, matični broj 20447719. Naziv mora biti očigledno izmišljen i nesličan postojećim operaterima. Šablon ugovora se piše od nule; ne prepisivati odredbe iz objavljenih ugovora.

`contract_template.html` je HTML šablon sa mestima za popunjavanje u obliku `{{field_name}}`. Struktura: zaglavlje, ugovorne strane, predmet ugovora, komercijalni uslovi, trajanje, kontakt osobe, potpisi.

### 3.1 Sintetička baza firmi

`generate_stimuli.py` generiše 200 firmi. Polja:

| Polje | Opis |
|---|---|
| `company_name` | koren plus pravni oblik, npr. Vega Logistika d.o.o. Koreni: Vega, Panonija, Delta, Morava, Kolubara, Zenit, Sirmium, Timok, Avala, Karpat. Oblici: d.o.o., a.d., o.d. |
| `pib` | 9 cifara, ispravna kontrolna cifra po ISO 7064 MOD 11,10 |
| `registration_number` | 8 cifara, ista provera |
| `city`, `street`, `street_number` | iz fiksne liste 20 gradova i 40 ulica u Srbiji |
| `contact_person`, `contact_phone` | ime i prezime, mobilni broj u formatu 06X/XXX-XXXX |
| `employee_count` | 8 do 240 |
| `contract_number` | format `TK-2026-NNNNN`, pet cifara, jedinstven |

Nevažeći PIB bi iskusnom kancelarijskom radniku bio uočljiv iz pogrešnog razloga, pa bi kvario merenje. Isto važi za matični broj.

### 3.2 Izvedena komercijalna polja

| Polje | Pravilo |
|---|---|
| `package_count` | `employee_count` pomnoženo faktorom iz opsega 0,8 do 1,2, zaokruženo |
| `monthly_fee_per_package` | 800 do 2.400 dinara, zaokruženo na 50 |
| `contract_months` | iz skupa 12, 24, 36 |
| `total_monthly_fee` | `package_count` puta `monthly_fee_per_package` |
| `start_date` | u 2026. godini |

Sve determinističko za dati `--seed`.

### 3.3 Dve klase polja: kritično pravilo

**Polja za proveru** su ona iz kojih se bira N. Moraju biti proizvoljna, dakle neizvodiva iz bilo čega drugog na stranici. Ako se vrednost može izračunati iz drugog vidljivog polja, ispitanik je računa umesto da je pamti, polje prestaje da bude stavka radne memorije, i etiketa opterećenja prestaje da znači isto što u S1 i S2.

| Polje za proveru | Klasa težine |
|---|---|
| `contract_number` | visoka |
| `pib` | visoka |
| `registration_number` | visoka |
| `company_name` | srednja |
| `street` plus `street_number` | srednja |
| `monthly_fee_per_package` | srednja |
| `city` | niska |
| `contact_person` | niska |

`monthly_fee_per_package` sme da bude polje za proveru **samo uz sledeće pravilo**: referentni zapis sadrži pregovarani popust koji se ne štampa na ugovoru, pa se naknada ne može izvesti iz vidljivog sadržaja. Ako se popust ne uvede, izbaciti ovo polje iz liste za proveru.

**Kontekstna polja se nikada ne proveravaju** i nikada ne ulaze u N: `employee_count`, `package_count`, `contract_months`, `total_monthly_fee`, `start_date`, `contact_phone`. Štampaju se na ugovoru zbog realizma.

### 3.4 Sastav stavke po nivoima

Devetocifren PIB nije isto opterećenje kao reč Kragujevac. Bez fiksnog sastava dva pod-bloka istog nivoa ne bi bila uporediva.

**Najviše jedno polje visoke težine po stavci, bez obzira na N.** Ovo je tvrdo ograničenje, utvrđeno na demonstraciji. Tri niza cifara bez značenja istovremeno su iznad kapaciteta gotovo svakog ispitanika, pa se ne meri gradacija opterećenja nego se svi nalaze u zoni otkaza, uz odustajanje. N stepenuje opterećenje kroz broj stavki, a ne kroz njihovu apsolutnu težinu.

| N | Visoka | Srednja | Niska |
|---|---|---|---|
| 3 | 1 | 1 | 1 |
| 5 | 1 | 2 | 2 |
| 7 | 1 | 3 | 3 |

Koja konkretna polja ulaze bira se nasumično unutar klase, iz zadatog seeda, i zapisuje u `items_*.json`.

### 3.5 Prikaz vrednosti

Dugi nizovi cifara se prikazuju segmentirano, i na ugovoru i u referentnom zapisu. Segmentacija je standardna praksa u poslovnim dokumentima i znatno olakšava zadržavanje bez menjanja broja stavki.

| Polje | Prikaz |
|---|---|
| `pib` | `108 452 291`, tri grupe po tri cifre |
| `registration_number` | `20 447 719`, grupe 2-3-3 |
| `contract_number` | `TK-2026-4817`, **četiri** cifre u završnom delu umesto pet |
| `monthly_fee_per_package` | `1.450 RSD` |
| `contact_phone` | `063/241-8870` |

Segmentacija je isključivo vizuelna. U `items_*.json` i u logu vrednosti se čuvaju bez razmaka, da poređenje tačnosti ne zavisi od formatiranja.

Poziv: `python generate_stimuli.py --seed 20260825 --participants 40`

---

## 4. Konstrukcija stavki

Jedna stavka je jedan nacrt ugovora sa N označenih polja koja treba proveriti. N uzima vrednosti 3, 5 i 7.

Za svako polje se bira status:

| Status | Udeo | Šta znači |
|---|---|---|
| `match` | 75% | Vrednost u ugovoru odgovara referentnoj |
| `mismatch` | 25% | Vrednost u ugovoru odstupa od referentne |

**Uverljivost odstupanja je ključna.** Očigledno pogrešna vrednost ne meri ništa, a vrednost koja se može odbaciti zdravorazumski meri rasuđivanje umesto pamćenja.

| Polje | Oblik odstupanja |
|---|---|
| `contract_number` | promena jedne cifre u petocifrenom delu, ili zamena mesta dve susedne cifre |
| `pib`, `registration_number` | zamena mesta dve susedne cifre |
| `company_name` | drugi koren iz iste liste, isti pravni oblik (Vega naspram Zenit) |
| `street_number` | zamena mesta cifara (14 naspram 41) ili razlika od jedan |
| `street` | druga ulica iz iste liste |
| `city` | drugi grad iz iste liste |
| `contact_person` | ime i prezime druge kontakt osobe iz baze |
| `monthly_fee_per_package` | razlika od jednog koraka od 50 dinara, uz obavezno ostajanje u opsegu 800 do 2.400 |

Pravila koja važe za sva odstupanja:

- odstupanje nikada ne sme da izbaci vrednost iz uverljivog opsega
- odstupanje se nikada ne uvodi u kontekstna polja, jer bi bilo otkriveno računanjem
- kontrolna cifra PIB-a i matičnog broja se posle odstupanja **ne popravlja**; ispitanik je ne proverava, a popravljanje bi promenilo više od jedne cifre
- Zabranjeno: prazna polja, besmislen tekst, pogrešan format, vrednosti van opsega

Položaj polja sa odstupanjem je nasumičan po ispitaniku, ali determinističan za dati `--seed` i ID ispitanika, i uvek se zapisuje u `items_*.json`.

---

## 5. Sugestije modela

`suggestions.json` sadrži unapred izračunatu sugestiju za svako polje svake stavke u varijanti S3b. **Model se nikada ne poziva u toku sesije.**

Za svako polje sugestija ima jedan od tri oblika:

| `suggestion_type` | Tekst | Kada se koristi |
|---|---|---|
| `confirm` | „Vrednost odgovara referenci." | Model tvrdi da je polje u redu |
| `flag` | „Vrednost odstupa od reference. Predlog: {vrednost}" | Model tvrdi da polje odstupa i nudi ispravku |
| `uncertain` | „Vrednost izgleda neobično. Proverite." | Model signalizira sumnju bez predloga |

Sugestija se ukršta sa stvarnim statusom polja tako da se dobiju četiri ishoda, sa ciljanom pouzdanošću modela od 75%:

| Stvarni status polja | Sugestija | Naziv u logu | Ciljani udeo od svih polja |
|---|---|---|---|
| `mismatch` | `flag` sa tačnim predlogom | `true_positive` | 10% |
| `match` | `confirm` | `true_negative` | 65% |
| `mismatch` | `confirm` | `missed_error` | 15% |
| `match` | `flag` sa netačnim predlogom | `false_alarm` | 10% |

`missed_error` je najvažniji tip: model potvrđuje netačno polje, a ispitanik ima šansu da grešku uhvati sam. To je merilo kvaliteta nadzora.

Prvih 8 polja u svakoj sesiji su isključivo `true_positive` ili `true_negative`, kao uvodni period visoke pouzdanosti koji izgrađuje poverenje. Bez toga popustljivost se ne stigne razviti.

Udeli se zadaju kao parametri u zaglavlju skripta, jer se u pilotu podešavaju.

**Ako se koristi pravi model za generisanje teksta sugestija:** poziv se izvodi jednom, u pripremi, sa `temperature=0`, sa fiksiranom verzijom modela, a rezultat se snima u `suggestions.json` i ručno pregleda. Naziv modela, verzija i datum generisanja upisuju se u zaglavlje datoteke. Za demonstraciju je dovoljno generisati tekst iz šablona iznad.

---

## 6. Tok zadatka i tajming

Tajming je eksperimentalno kritičan. Vrednosti se zadaju kao konstante na vrhu `task.js` i ne smeju se menjati u toku sesije.

```
ENCODING_MS_PER_FIELD = 3000
SUGGESTION_LATENCY_MS = 1500
ITEM_GAP_MS           = 1500
PEEK_DURATION_MS      = 3000
BLOCK_DURATION_MS     = 180000
```

### Faza 1, kodiranje

Prikazuju se nacrt ugovora i referentni zapis jedan pored drugog. Trajanje je `N * ENCODING_MS_PER_FIELD`. Odbrojavanje je vidljivo.

### Faza 2, verifikacija

Referentni zapis se **uklanja iz DOM stabla**, ne samo sakriva preko `display:none` ili `visibility:hidden`. Skriveni element se može pročitati preko alata za razvoj i ostavlja tekst u pristupačnosnom stablu.

Zatim, za svako polje redom:

1. Polje postaje aktivno i vizuelno se ističe.
2. U varijanti S3b: indikator učitavanja tačno `SUGGESTION_LATENCY_MS`, pa se prikaže sugestija. Latencija se meri preko `performance.now()`, ne preko `setTimeout` samog, i stvarno proteklo vreme se upisuje u log.
3. Ispitanik pritisne Prihvati ili Odbij (u varijanti S3a ovog koraka nema).
4. Ispitanik bira konačnu vrednost polja iz ponuđenih (vidi 6.1).
5. Prelazak na sledeće polje.

Bez povratne informacije o tačnosti, ni u jednom trenutku.

Posle poslednjeg polja: prazan ekran `ITEM_GAP_MS`, pa sledeća stavka.

Blok traje `BLOCK_DURATION_MS`. Stavka koja je u toku kada vreme istekne se završava, pa se blok zatvara.

### 6.1 Unos odgovora: izbor, ne prekucavanje

Ispitanik ne kuca vrednost iz sećanja. Prikazuju se tri ponuđene vrednosti i on bira jednu.

Razlog je merni. Prekucavanje devetocifrenog PIB-a iz sećanja meri prizivanje plus motoričko izvođenje, a greška u kucanju se ne razlikuje od greške u pamćenju. Uz to je motorički trošak glavni izvor frustracije i odustajanja, utvrđen na demonstraciji. Izbor meri prepoznavanje, što je i bliže stvarnom poslu, jer se u proveri ugovora vrednost potvrđuje ili ispravlja, retko prekucava.

Sastav ponuđenih vrednosti, uvek tri, u nasumičnom redosledu:

| Ponuda | Sadržaj |
|---|---|
| A | vrednost koja stoji na ugovoru |
| B | stvarna referentna vrednost |
| C | omet, generisan istim pravilom odstupanja kao u sekciji 4, iz iste klase polja |

Kada je polje `match`, A i B su ista vrednost, pa se prikazuju dve ponude umesto tri. Ovo mora biti tako, jer bi dodavanje veštačke treće ponude odalo da polje nije `match`.

Omet C nikada ne sme biti jednak ni A ni B. Ako pravilo odstupanja proizvede takvu vrednost, generiše se ponovo.

Vremenski limit po polju ostaje na snazi. Bez njega izbor podiže tačnost ka plafonu, jer ispitanik može neograničeno da odmerava ponude.

### 6.2 Ponovni uvid

Jednom po stavci, ne po polju, ispitanik može dugmetom prizvati referentni zapis na `PEEK_DURATION_MS` (3000). Dugme se posle upotrebe onemogućava do sledeće stavke.

Uvid sprečava efekat poda i zadržava ekološku valjanost, jer se u stvarnom radu referenca može ponovo pogledati. Broj i trenutak uvida se beleže i predstavljaju dodatnu bihejvioralnu meru opterećenja: broj uvida treba da raste sa N.

Tokom uvida referentni zapis se ubacuje u DOM i posle isteka ponovo uklanja, ne sakriva.

---

## 7. Logovanje

Jedna JSONL datoteka po bloku, u `logs/`. Naziv: `{participant_id}_{variant}_{N}_{timestamp}.jsonl`.

Prvi red je zaglavlje sesije:

```json
{"type":"session","participant_id":"P07","variant":"S3b","n_fields":5,
 "seed":20260825,"stimuli_hash":"sha256:...","screen":{"w":1920,"h":1080},
 "roi":{"contract":[24,96,380,420],"suggestion":[420,96,640,260]},
 "t0_wall":"2026-08-25T10:14:03.221Z","t0_perf":1043.7}
```

`roi` su pravougaonici zona interesovanja u pikselima, potrebni za obradu praćenja pogleda. Moraju biti fiksni tokom cele sesije. Ako se prozor promeni, sesija se prekida i beleži se događaj `window_resized`.

Svaki naredni red je jedan događaj:

```json
{"t":18432.5,"t_wall":"...","event":"suggestion_shown","item":4,"field":3,
 "field_name":"city","true_status":"match","suggestion_type":"flag",
 "outcome_class":"false_alarm","latency_actual_ms":1501.2}
```

Obavezni tipovi događaja: `block_start`, `item_start`, `encoding_start`, `encoding_end`, `field_active`, `suggestion_shown`, `decision` (sa `accepted: true|false`), `peek_start` i `peek_end`, `value_submitted`, `item_end`, `block_end`.

`value_submitted` sadrži `options` (sve ponuđene vrednosti u redosledu u kom su prikazane), `chosen`, `chosen_role` sa vrednošću `contract`, `reference` ili `distractor`, i `correct: true|false`. Uloga izabrane ponude je informativnija od same tačnosti: izbor ponude `contract` na polju sa odstupanjem znači da referentna vrednost nije zadržana, a izbor ponude `distractor` znači da je zadržavanje otkazalo u celini.

`t` je uvek `performance.now()`, u milisekundama, sa jednom decimalom. Zidni sat služi samo za grubu sinhronizaciju.

### Markeri za EEG

`server.py` prima događaje preko WebSocket veze i prosleđuje ih kao LSL markere preko `pylsl`, u tok naziva `S3_markers`, tip `Markers`. Ako `pylsl` nije dostupan, server samo upisuje u datoteku i ispisuje upozorenje, a zadatak nastavlja da radi. Demonstracija ne sme da zavisi od prisustva EEG opreme.

---

## 8. Izgled ekrana

Dvokolonski raspored. Levo lista polja ugovora, desno panel sa sugestijom i dugmadima. Ispod panela polje za unos konačne vrednosti.

- Aktivno polje se ističe promenom pozadine, ne promenom veličine, jer promena veličine pomera zone interesovanja.
- Panel sa sugestijom ima **fiksnu visinu** bez obzira na dužinu teksta, iz istog razloga.
- Bez animacija, bez prelaza, bez pomeranja sadržaja.
- Svetlina pozadine je ista u svim ekranima i blokovima. Zabranjeno je koristiti belu pozadinu u jednom stanju i sivu u drugom, jer zenica reaguje na svetlo.
- Zaglavlje pokazuje redni broj stavke i redni broj polja, ali ne i preostalo vreme u sekundama, jer bi to uvelo vremenski pritisak koji nije deo manipulacije. Prikazati grubu traku napretka bloka.

Raspored preuzeti iz makete koja je već napravljena u razgovoru; vizuelni stil nije kritičan, položaji i dimenzije jesu.

---

## 9. Režimi pokretanja

```
?participant=P07&variant=S3b&n=5           standardni blok
?participant=DEMO&variant=S3b&n=5&demo=1   demo: 4 stavke pa kraj, za prikaz
?practice=1                                vežba sa povratnom informacijom
```

Vežba je jedini režim u kome se prikazuje tačnost odgovora, i njeni podaci se snimaju odvojeno, u `logs/practice/`.

---

## 10. Provera ispravnosti

`analyze_log.py` čita jednu ili više log datoteka i ispisuje:

- broj obrađenih stavki i polja
- stvarnu raspodelu četiri klase ishoda naspram ciljane
- stopu prihvatanja sugestija, odvojeno za `true_positive`, `true_negative`, `missed_error` i `false_alarm`
- **stopu hvatanja propuštenih grešaka**: udeo `missed_error` polja u kojima je ispitanik uneo tačnu vrednost uprkos potvrdi modela
- srednje vreme do odluke po klasi ishoda
- **raspodelu polja po klasi težine** (visoka, srednja, niska) po nivou N, radi provere da je sastav iz sekcije 3.4 ispoštovan
- **stopu otkrivanja po klasi težine**, jer se očekuje da PIB i broj ugovora budu teži od grada i imena
- **broj ponovnih uvida po stavci, po nivou N**; očekuje se rast sa N, a izostanak rasta znači da uvid nije potreban ili da je zadatak prelak
- **raspodelu `chosen_role`** po nivou N; udeo izbora ponude `distractor` je pokazatelj otkaza zadržavanja
- **znake odustajanja**: udeo polja rešenih na isteku vremenskog limita, i trend tačnosti od prve do poslednje stavke u bloku. Pad tačnosti kroz blok uz porast vremena do odluke znači da ispitanik odustaje, i tada podaci ne mere opterećenje
- odstupanje ostvarene latencije od zadatih 1500 ms, sa maksimumom i standardnom devijacijom

Poslednja stavka je provera tehničke ispravnosti. Ako maksimalno odstupanje pređe 50 ms, tajming nije upotrebljiv za analizu po prozorima od 1 s i mora se rešiti pre pilota.

---

## 11. Šta ne raditi

- Ne pozivati jezički model u toku sesije.
- Ne koristiti `setTimeout` kao meru vremena; koristiti ga samo za zakazivanje, a meriti preko `performance.now()`.
- Ne sakrivati referentni zapis preko CSS-a.
- Ne davati povratnu informaciju o tačnosti izvan režima vežbe.
- Ne uvoditi nasumičnost u toku izvođenja; sve što je nasumično određuje se u `generate_stimuli.py` i snima u datoteku.
- Ne stavljati kontekstna polja među polja za proveru. Vrednost izvodiva iz drugog vidljivog polja meri računanje, ne pamćenje.
- Ne stavljati više od jednog polja visoke težine u istu stavku, ni na jednom nivou N.
- Ne tražiti od ispitanika da vrednost prekucava iz sećanja. Odgovor je uvek izbor iz ponuđenih.
- Ne menjati raspored ili dimenzije elemenata između blokova.

---

## 12. Redosled izrade

1. `contract_template.html`, šablon ugovora sa mestima za popunjavanje. Popuniti ga jednom firmom i pregledati u pregledaču pre nego što se pređe dalje.
2. `generate_stimuli.py` sa proverom kontrolnih cifara i sa podelom na klase polja, pa ručno pregledati 20 nasumičnih stavki.
3. `task.js` u varijanti S3a, bez modela. Proveriti tajming preko `analyze_log.py`.
4. Dodati varijantu S3b i panel sa sugestijama.
5. `server.py` sa WebSocket prijemom i LSL izlazom.
6. `analyze_log.py` u punom obimu.
7. `README.md` sa uputstvom za pokretanje i sa spiskom parametara koje treba podesiti posle pilota.

Posle svakog koraka pokrenuti jedan demo blok od kraja do kraja i pregledati log.
