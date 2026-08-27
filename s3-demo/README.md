# s3-demo — demonstrator Scenarija 3

Radna demonstracija zadatka provere ugovora (sintetički materijal, S3a bez
asistencije / S3b sa sugestijama modela, N ∈ {3,5,7}). Vidi izvorno
uputstvo za punu specifikaciju; ovaj README pokriva samo pokretanje i
odstupanja/pretpostavke koje je trebalo razrešiti da bi uputstvo bilo
izvodljivo.

## Pokretanje

```
cd s3-demo
python generate_stimuli.py --seed 20260825 --participants 40   # jednom, ili posle svake izmene liste ucesnika
python server.py                                                # http :8000, ws :8765
```

`server.py`-jev staticki koren je `eeg-tasks/` (roditelj s3-demo/), ne
s3-demo/ sam -- `app/index.html` ucitava deljeni `core/` i `data/` preko
`"../../"`, pa URL uvek nosi `/s3-demo/` prefiks (ranije je nedostajao,
davao je 404 na core/*.js -- ispravljeno).

Otvoriti u pregledaču, na primer (`<SIFRA>` je jedna od stvarnih šifri iz
`data/participant_codes.json`, generisanih preko `generate_participant_codes.py`
-- ne postoji fiksan format tipa "P07"):

```
http://localhost:8000/s3-demo/app/index.html?participant=<SIFRA>&variant=S3b&n=5
http://localhost:8000/s3-demo/app/index.html?participant=DEMO&variant=S3b&n=5&demo=1
http://localhost:8000/s3-demo/app/index.html?practice=1
```

`server.py` zahteva paket `websockets` (`pip install websockets`). Bez
njega HTTP deo i dalje radi normalno; WebSocket prijem se gasi uz
upozorenje u konzoli, a `app/task.js` tada sam preuzima `.jsonl` log kao
fajl iz pregledača na kraju bloka (vidi "Logovanje bez servera" niže).
`pylsl` je potpuno opciono i samo za EEG markere (sekcija 7).

Analiza:

```
python analyze_log.py logs/*.jsonl
```

## Integritet stimulusa (heš u logu)

Svaki `session` red loga sadrži `items_hash` (sha256 sirovih bajtova
`data/items_S3a.json` ili `data/items_S3b.json`, zavisno koja je varijanta
stvarno korišćena u toj sesiji -- za vežbu uvek `items_S3a.json`) i
`companies_hash` (sha256 `data/companies.json`), oba u obliku
`"sha256:<hex>"`. U server režimu ih `app/task.js` računa uživo preko
`fetch()` + `crypto.subtle.digest`; u samostalnoj verziji ih unapred
izračuna `build_standalone.py` i ugrađuje kao gotove niske (po varijanti za
`items_hash`). Isti mehanizam kao u `s2-demo`, radi uporedivosti.

`analyze_log.py` na početku svakog pokretanja ponovo izračuna heš trenutnih
fajlova i uporedi ga sa zaglavljem **svakog** učitanog bloka (biraju se
`items_S3a.json`/`items_S3b.json` prema `session["variant"]`); na
neslaganje ili nedostajuće polje **prekida odmah**, imenujući fajl i oba
heša.

## Samostalna verzija (bez servera, dvoklik)

Za brz prikaz bez servera i bez `python -m http.server`: `build_standalone.py`
pravi jedan `standalone/index.html` fajl sa svim podacima (sva 40
ucesnika, obe varijante, sve tri vrednosti N) i celim `task.js`/`style.css`
ugradjenim direktno u fajl. Otvara se dvoklikom (`file://`), radi bez
mreze i bez ijedne spoljne zavisnosti.

```
python generate_stimuli.py --seed 20260825 --participants 40   # ako vec nije pokrenuto
python build_standalone.py
```

Rezultat je `standalone/index.html` (~15-16 MB, jer sadrzi ceo
`items_S3a.json` + `items_S3b.json` + `suggestions.json`). Podrzava iste
URL parametre kao server verzija (`?participant=...&variant=...&n=...`,
`&demo=1`, `?practice=1`) — dodaju se na `file://.../standalone/index.html?...`.

**Bez tvrde provere URL parametara.** Za razliku od server verzije (koja
odbija da krene bez ispravnih `participant`/`variant`/`n`), samostalna
verzija otvorena bez ijednog parametra jednostavno kreće sa podrazumevanim
`participant=DEMO&variant=S3b&n=5&demo=1`. Svaki parametar koji JESTE
naveden u URL-u (i validan je) ima prednost nad svojom podrazumevanom
vrednoscu, nezavisno od ostalih. Na početnom ekranu postoji i mali
izbornik (varijanta S3a/S3b, N 3/5/7) — mentor može da proba obe
varijante klikom, bez izmene adrese; ako se selektor ne dira, koristi se
vrednost iz URL-a/podrazumevana vrednost. `demo` sam po sebi nema kontrolu
u izborniku (ostaje ono sto je URL/podrazumevano dao — podrazumevano
`demo=1`, tj. 3 stavke).

Ovo pravilo vazi samo kad su podaci ugradjeni (`window.__S3_EMBEDDED__`)
— isti `app/task.js` na serveru i dalje trazi pune parametre, jer je tamo
tiho podrazumevanje rizicnije (moglo bi da upise podatke pod pogresnim
`participant`/`variant` u pravoj sesiji). Iz istog razloga je generator
dobio dodatnog ucesnika `"DEMO"` (pored `P01..PNN`) u
`generate_stimuli.py`, na koga se podrazumevana vrednost oslanja.

Razlike u odnosu na server verziju:
- `fetch()` poziva nema uopste (blokirani su CORS politikom za `file://`);
  `app/task.js` prepoznaje `window.__S3_EMBEDDED__` i preskace mrezne
  pozive kad postoji (isti fajl radi u oba rezima).
  Napomena: `standalone/index.html` je **generisan** fajl -- izmene se
  rade u `app/task.js`/`app/style.css`/`app/index.html`, pa se
  `build_standalone.py` pokrene ponovo.
- WebSocket ka `server.py` se ni ne pokusava (nema servera na `file://`);
  log bloka se **uvek** preuzima kao `.jsonl` fajl preko pregledaca na
  kraju bloka (Downloads folder), nema LSL/EEG markera u ovom rezimu.
- Ako se `data/*.json` promene (novi seed, novi broj ucesnika), fajl
  treba ponovo generisati (`build_standalone.py`) -- stari
  `standalone/index.html` i dalje sadrzi staru zamrznutu kopiju podataka.

## Odstupanja od uputstva i zašto

**1. Klase težine polja za proveru (sekcija 3.3/3.4).** Originalna tabela
grupiše `street` i `street_number` u jedno polje srednje težine, čime
ostaju samo dva polja niske težine (`city`, `contact_person`) — nedovoljno
za N=7, koje traži tri. Sekcija 4 uputstva ionako već tretira `street` i
`street_number` kao dva odvojena polja sa odvojenim pravilima odstupanja,
pa su ovde razdvojena i u klasifikaciji: `street` ostaje srednje,
`street_number` prelazi u nisku težinu. Rezultat je čist raspored 3
visoka/3 srednja/3 niska koji tačno pokriva N=3/5/7 bez ijednog novog
polja. Vidi komentar u `generate_stimuli.py` uz `FIELD_WEIGHT`.

**2. Vremenski limit po polju u fazi verifikacije (sekcija 6.1) — REVIDIRANO.**
Uputstvo kaže "vremenski limit po polju ostaje na snazi" ali ga nikad ne
imenuje među pet konstanti u sekciji 6. Prva verzija je uvela
`DECISION_MS_PER_FIELD` sa auto-napredovanjem na isteku (polje bi samo
prešlo na sledeće bez klika) — posle probe se pokazalo da to nije
poželjno: **polje sad napreduje isključivo posle klika ispitanika na
ponuđenu vrednost, bez ikakvog roka koji bi ga sam pomerio.**
`DECISION_MS_PER_FIELD` (3000 ms) je ostao kao konstanta, ali sad služi
samo kao prag za MERENJE: kad stvarno vreme do odluke pređe prag,
`value_submitted` dobija `over_deadline: true` i stvarno vreme u
`decision_ms` (bez ikakvog vizuelnog signala ispitaniku, bez uticaja na
tok). `timed_out` polje je ostalo u šemi ali će pod podrazumevanim
podešavanjem uvek biti `false`, jer se do njega više ne može doći.

Staro ponašanje (auto-napredovanje) je namerno ostavljeno u kodu iza
`const ENFORCE_DECISION_DEADLINE = false;` (vrh `app/task.js`) — kad se
prag posle pilota ponovo aktivira, menja se samo ta jedna konstanta u
`true`. Oba parametra (`decision_ms_per_field`, `enforce_decision_deadline`)
se upisuju u `session` red loga, tako da se iz svakog fajla vidi pod kojim
je režimom snimljen — bitno ako se u istoj analizi mešaju blokovi
snimljeni pre i posle ove izmene.

**3. Naknada po paketu bez eksplicitnog "popusta" (sekcija 3.3).**
Uputstvo dozvoljava `monthly_fee_per_package` kao polje za proveru samo
ako postoji mehanizam koji sprečava da se izvede iz vidljivog sadržaja
("pregovarani popust koji se ne štampa"). Umesto posebnog polja za popust,
`total_monthly_fee` (kontekstno polje, odštampano) se za svaku stavku
računa iz **odštampane** (eventualno netačne) vrednosti
`monthly_fee_per_package`, ne iz referentne. Deljenje
`total_monthly_fee / package_count` zato uvek daje tačno ono što već piše
na ugovoru — tautologija, ne otkriva odstupanje. Vidi komentar u
`build_item()`.

## Šta NIJE potpuno pokriveno / poznata ograničenja

- **ROI u sesijskom zaglavlju** je jedan fiksan pravougaonik po koloni
  (`contract`, `suggestion`), izmeren posle iscrtavanja prve stavke. Ako
  se dužina teksta u poljima (npr. dužina naziva firme) bitno razlikuje
  između stavki, stvarna visina `#contract-mount` može odstupati od
  izmerene za par piksela — uputstvo traži fiksan ROI za celu sesiju, pa
  je ovo inherentan kompromis dizajna, ne bag.
- **Logovanje bez servera.** Ako `server.py` (ili paket `websockets`)
  nije dostupan, `app/task.js` baferuje događaje u memoriji i na kraju
  bloka ih preuzima kao `.jsonl` fajl preko pregledača (`<a download>`).
  Ovo NIJE eksplicitno opisano u uputstvu (koje logovanje vezuje samo za
  `server.py`), ali sprečava da demo bez servera ostane bez ikakvog loga.
  Ako se veza sa serverom prekine usred sesije (WS `onclose`), rani
  događaji su već isporučeni serveru; samo događaji posle prekida se
  preuzimaju kao fajl na kraju — log te sesije je tada podeljen na dva
  mesta.
- **Vežba (`?practice=1`)** koristi S3a stavke (bez sugestija modela) na
  N=3, deljene za sve ispitanike (nije po `participant` parametru, jer
  uputstvo ne specifikuje da vežba treba da bude personalizovana).
  `server.py` je usmerava u `logs/practice/` na osnovu `variant` polja u
  zaglavlju sesije.
- **UI nije testiran u pravom pregledaču** u ovoj sesiji (bez pristupa
  browseru/headless alatu u okruženju u kom je kod pisan) — testiran je
  ceo tok server → WebSocket → `.jsonl` → `analyze_log.py` preko
  simuliranog klijenta, i sav HTML/CSS/JS je ručno pregledan, ali vizuelni
  raspored, ROI koordinate uživo i tajming u realnom pregledaču treba
  potvrditi pre snimanja pravih podataka (pogotovo pre EEG merenja).

## Parametri za reviziju posle pilota

- `ENCODING_BASE_MS`, `ENCODING_MS_PER_FIELD`, `DECISION_MS_PER_FIELD`,
  `ENFORCE_DECISION_DEADLINE`, `SUGGESTION_LATENCY_MS`, `ITEM_GAP_MS`,
  `PEEK_DURATION_MS`, `BLOCK_DURATION_MS` — vrh `app/task.js`. Svi osim
  `ENFORCE_DECISION_DEADLINE` se upisuju i u `session` red loga
  (`encoding_base_ms`, `encoding_ms_per_field`, `decision_ms_per_field`,
  `enforce_decision_deadline`), pa se za svaki snimljeni blok tačno zna
  pod kojim je tajmingom/režimom sniman.
- `ITEMS_PER_BLOCK` (koliko stavki se unapred generiše po bloku, sekcija
  generatora) i `SUGGESTION_QUOTAS` / `WARM_UP_FIELDS` — vrh
  `generate_stimuli.py`.
- `LATENCY_MAX_DEVIATION_WARN_MS` (prag upozorenja u `analyze_log.py`,
  sekcija 10 traži 50 ms).
