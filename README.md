# eeg-tasks — Scenario 1: prekucavanje poslovne korespondencije

Radna demonstracija zadatka prekucavanja rečenica iz poslovne korespondencije
iz pamćenja (sintetičan + Enron-izveden materijal, N ∈ {3,5,7}). Vidi
`SPEC_S1_demo.md` za punu specifikaciju; ovaj README pokriva samo pokretanje
i odstupanja/odluke koje je trebalo doneti da bi uputstvo bilo izvodljivo.

Za razliku od Scenarija 2 i 3 (`s2-demo/`, `s3-demo/`, svaki sopstveni
projekat), Scenario 1 **nema sopstveni projekat** — gradi se direktno na
`core/` i zajedničkom `data/`, po `SPEC_refaktor_jezgro.md`. Svi fajlovi
specifični za S1 žive u korenu `eeg-tasks/`: `app/`, `scenarios/s1.js`,
`server.py`, `build_standalone.py`.

## Pokretanje

```
python build_sentences.py --input "putanja/do/All_sentences_for_Scenario_1_Transcription.xlsx"
python generate_stimuli.py --scenario S1 --seed 20260825 --participants 40
python server.py                                                # http :8000, ws :8767
```

Otvoriti u pregledaču, na primer:

```
http://localhost:8000/app/index.html?participant=P07&n=5
http://localhost:8000/app/index.html?participant=DEMO&n=5&demo=1
http://localhost:8000/app/index.html?practice=1
```

`server.py` zahteva paket `websockets` (`pip install websockets`). Bez njega
HTTP deo i dalje radi normalno; WebSocket prijem se gasi uz upozorenje u
konzoli, a `scenarios/s1.js` tada sam preuzima `.jsonl` log kao fajl iz
pregledača na kraju bloka (isti mehanizam kao S2/S3, vidi "Logovanje bez
servera" niže). `pylsl` je potpuno opciono i samo za EEG markere.

Pregled generisanog materijala pre snimanja (sekcija 12 dopune uputstva):

```
python dump_item.py --scenario S1 --participant DEMO --n 7 --items 1 2
python dump_item.py --scenario S1 --participant DEMO --n 5 --random 20 --seed 1
```

Analiza:

```
python analyze_log.py logs/*.jsonl
python analyze_log.py logs/*.jsonl --detail    # + tabela po recenici
```

`--data` je podrazumevano `data/` (zajedničko), nema potrebe navoditi ga
osim ako je materijal generisan na drugu putanju.

## Integritet stimulusa (heš u logu)

Svaki `session` red loga sadrži `items_hash` (sha256 sirovih bajtova
`data/items_S1.json`), u obliku `"sha256:<hex>"`. U server režimu ga
`scenarios/s1.js` računa uživo preko `fetch()` + `crypto.subtle.digest`; u
samostalnoj verziji ga unapred izračuna `build_standalone.py` i ugrađuje kao
gotovu nisku. Isti mehanizam kao u `s2-demo`/`s3-demo`, radi uporedivosti —
**bez** `companies_hash`: S1 nema stavka-firma vezu (`items_S1.json` ne
sadrži `company_id` nigde, `SPEC_S1_demo.md` 3.3), pa nema šta drugo da se
proveri.

`analyze_log.py` na početku svakog pokretanja ponovo izračuna heš trenutnog
`data/items_S1.json` i uporedi ga sa zaglavljem **svakog** učitanog bloka;
na neslaganje ili nedostajuće polje **prekida odmah**, imenujući fajl i oba
heša.

## Samostalna verzija (bez servera, dvoklik)

```
python generate_stimuli.py --scenario S1 --seed 20260825 --participants 40   # ako vec nije pokrenuto
python build_standalone.py
```

Rezultat je `standalone/index.html` (~1 MB, sadrži ceo `items_S1.json` i
`scenarios/s1.js`/`core/*.js`/`app/style.css` ugrađene direktno u fajl).
Otvara se dvoklikom (`file://`), radi bez mreže i bez ijedne spoljne
zavisnosti.

**Bez tvrde provere URL parametara.** Otvorena bez ijednog parametra,
samostalna verzija jednostavno kreće sa podrazumevanim
`participant=DEMO&n=5&demo=1` (isti `resolveParamsCore` iz `core/params.js`
kao S2/S3). Na početnom ekranu postoji izbornik za N (3/5/7) — menja se
klikom, bez izmene adrese; ako se ne dira, koristi se podrazumevana
vrednost. Server verzija i dalje zahteva pune parametre (`participant`+`n`)
— tiho podrazumevanje je rizičnije u pravoj sesiji.

Razlike u odnosu na server verziju: `fetch()` poziva nema uopšte (CORS
politika za `file://`); `scenarios/s1.js` prepoznaje
`window.__S1_EMBEDDED__` i preskače mrežne pozive kad postoji (isti fajl
radi u oba režima). WebSocket ka `server.py` se ni ne pokušava; log bloka se
**uvek** preuzima kao `.jsonl` fajl preko pregledača na kraju bloka
(Downloads folder), nema LSL/EEG markera u ovom režimu.

`standalone/index.html` je **generisan** fajl — izmene se rade u
`app/index.html`/`app/style.css`/`scenarios/s1.js`/`core/*.js`, pa se
`build_standalone.py` pokrene ponovo. Isto ako se `data/items_S1.json`
promeni (novi seed, novi broj učesnika).

## Odstupanja od uputstva i zašto

**1. Podela baze firmi na dva disjunktna dela (companies.json).** S1 pominje
firme u tekstu rečenica ali nema `company_id` po stavci — nema šta da se
evidentira po ispitaniku da bi se sprečilo ukrštanje sa S2/S3. Umesto toga,
koreni imena firmi su trajno podeljeni: `S1_ONLY_ROOTS` (Delta, Sirmium — 33
firme) isključivo za pominjanje u S1, `S2_S3_ROOTS` (preostalih osam korena
— 167 firmi) isključivo za dodelu ispitanicima u S2/S3. Granica je izabrana
brojanjem stvarnih pojavljivanja u `name_map.json`, uz uslov da S2/S3
zadrže bar 150 firmi. Zapisano u `companies.json` kao eksplicitna polja
`s1_only_roots`/`s2_s3_roots`, ne kao pretpostavka u kodu — vidi
`SPEC_S1_demo.md` 3.3 i `shared/generate_common.py`.

**2. `S1_ITEMS_PER_BLOCK = 10`, ne 30 kao S2/S3.** Sastav stavke (sekcija
3.2) traži do `6*n` rečenica niske klase dužine po stavci pri N=7, protiv
disjunktnosti po ispitaniku (nijedna rečenica se ne ponavlja unutar
sesije) nad bazenom od 149 niskih rečenica — 30 stavki po bloku bi zahtevalo
znatno više materijala nego što bazen nudi. Vrednost je podešena tako da
generisanje uspeva pouzdano za sve N u istoj sesiji (`used_ids` deljen
preko N=3/5/7). Vidi komentar uz `S1_ITEMS_PER_BLOCK` u
`generate_stimuli.py`.

**3. `ITEM_GAP_MS`/`BLOCK_DURATION_MS` nisu propisani uputstvom.** Sekcija
4/6 daje tačne vrednosti za tajming kodiranja, ali ne i za pauzu između
stavki ili trajanje bloka. Preuzete su iste vrednosti kao S2/S3 (1500 ms,
180000 ms) radi doslednosti opšteg toka bloka među sva tri scenarija — ovo
je ODLUKA, ne prepis eksplicitnog zahteva. Vidi komentar u
`scenarios/s1.js`.

**4. Nema poseban taster za potvrdu unosa.** Uputstvo ne pominje "potvrdi"
dugme — jedini opisani mehanizam navigacije je "Enter ili Tab" između
polja. Isti mehanizam je zato iskorišćen i za završetak stavke: Enter/Tab
na poslednjem polju završava unos. Nema vizuelnog dugmeta "pošalji".

**5. `runEncodingWait` prebačen u `core/block.js`.** `SPEC_refaktor_jezgro.md`
sekcija 4 pretpostavlja da je upravljanje trajanjem faze kodiranja već u
`core/` iz ranijeg refaktora S2/S3 — u praksi je postojala samo lokalna
kopija u `s2-demo/app/task.js`, S3 je nikad nije ni imao. Izdvojeno u
`core/block.js::runEncodingWait()` (parametrizovano po dugmetu/elementu
odbrojavanja/minimalnom trajanju), pozivnici u S2 ažurirani. Provereno
izolovanim poređenjem loga pre/posle izdvajanja (`IDENTICNI`) da ponašanje
S2 nije promenjeno.

## Šta NIJE potpuno pokriveno / poznata ograničenja

- **`paraphrase` podklasa (sekcija 5.3)** koristi pojednostavljeno pravilo
  koje uputstvo samo eksplicitno dozvoljava za ovu fazu: prepoznaju se samo
  slučajevi sa dodatim/izostavljenim funkcijskim rečima uz očuvane
  sadržinske (`S1_FUNCTION_WORDS` u `analyze_log.py`, namerno neiscrpna
  lista). Uputstvo samo kaže "pravilo se u pilotu podešava" — proširiti listu
  ili pravilo kad pilot pokaže propuste, ne pre toga.
- **`word_substitution` je redak po dizajnu.** Pošto `intrusion`/
  `cross_intrusion` imaju prednost nad njim čim uneta reč postoji bilo gde
  u rečenicama te stavke (tačna definicija iz sekcije 5.2), `word_substitution`
  se u praksi javlja samo kad je zamenjena reč iz **iste** referentne
  rečenice (npr. lokalna permutacija koju `word_order` ne uhvati) — svaka
  potpuno strana/izmišljena reč pada pod `intrusion`. Ovo je namerno,
  proveno ručnim test-slučajevima, ne previd.
- **Logovanje bez servera.** Ako `server.py` (ili paket `websockets`) nije
  dostupan, `scenarios/s1.js` baferuje događaje u memoriji i na kraju bloka
  ih preuzima kao `.jsonl` fajl preko pregledača. Ako se veza sa serverom
  prekine usred sesije, rani događaji su već isporučeni; samo događaji posle
  prekida se preuzimaju kao fajl — log te sesije je tada podeljen na dva
  mesta.
- **UI je testiran preko Playwright-a (headless Chromium)**, ne ručno u
  pravom pregledaču: pun tok (kodiranje → unos → ponovni uvid F2 → kraj
  stavke/bloka) proveren na N=3 i N=7, i u server i u samostalnom režimu,
  uključujući preuzimanje `.jsonl` fajla i ceo `analyze_log.py` izveštaj
  (uključujući `--detail`). Vizuelni raspored uživo (font rendering, tačna
  širina `#stage`) i tajming na stvarnom EEG hardveru ipak treba potvrditi
  pre snimanja pravih podataka.

## Parametri za reviziju posle pilota

- `ENCODING_BASE_MS`, `ENCODING_MS_PER_ITEM`, `ENCODING_MIN_MS` — vrh
  `scenarios/s1.js`. Uputstvo ih samo naziva "predložene polazne
  vrednosti" (sekcija 4), ne konačne. Upisuju se u `session` red loga
  (`encoding_base_ms`, `encoding_ms_per_item`, `encoding_min_ms`).
- `ITEM_GAP_MS`, `BLOCK_DURATION_MS` — vrh `scenarios/s1.js` (odluka, ne iz
  uputstva — videti tačku 3 iznad). Upisuju se u `session` red loga
  (`item_gap_ms`, `block_duration_ms`).
- `S1_ITEMS_PER_BLOCK`, `S1_PRACTICE_N`, `S1_PRACTICE_ITEMS` — vrh
  `generate_stimuli.py` (videti tačku 2 iznad).
- `DEMO_ITEM_CAP` (4 stavke u `demo=1` režimu) — vrh `scenarios/s1.js`.
- `S1_BURST_MAX_MS` (500), `S1_PAUSE_MIN_MS` (1000) — pragovi za mere
  kucanja iz sekcije 6, vrh `analyze_log.py`.
- `S1_CONFOUND_ALPHA` (0.05) — prag značajnosti za proveru konfunda
  porekla rečenice (tačka F), vrh `analyze_log.py`.
- `S1_FUNCTION_WORDS` — lista za prepoznavanje `paraphrase`, vrh
  `analyze_log.py` (videti "Poznata ograničenja" iznad).
