# Uputstvo: izvlačenje zajedničkog jezgra iz Scenarija 2 i 3

Cilj je da se pre izrade Scenarija 1 zajednički kod izvuče u jezgro, tako da se treći scenario gradi na njemu, a integracija sva tri na kraju bude spajanje modula umesto spajanja tri aplikacije.

**Ovo je premeštanje koda, ne izmena ponašanja.** Nijedna funkcionalna promena nije dozvoljena. Svaki korak se proverava poređenjem logova pre i posle.

---

## 1. Zašto sada

Scenariji 2 i 3 trenutno sadrže dve kopije istog koda za merenje vremena, zapisivanje loga, upravljanje blokom, komunikaciju sa serverom i zaštitu ekrana. Ako se Scenario 1 napravi kao treća kopija, na integraciji će postojati tri verzije istog mehanizma, međusobno razišle tokom razvoja. Svaka razlika u merenju vremena ili u formatu loga tada postaje izvor greške koji se traži u fiziološkim podacima, gde se ne vidi.

Oba scenarija sada prolaze sve provere, pa je ovo jedini trenutak u kome se posle premeštanja može pouzdano utvrditi da se ponašanje nije promenilo.

---

## 2. Ciljna struktura

```
eeg-tasks/
  core/
    clock.js       merenje vremena, performance.now(), provera odstupanja
    logger.js      JSONL zapis, WebSocket veza, preuzimanje, IndexedDB
    block.js       trajanje bloka, redosled stavki, prelaz izmedju stavki
    screen.js      zone interesovanja, blokiranje F5/F11/Ctrl+R, svetlina
    guard.js       blokiranje kopiranja, lepljenja, kontekstnog menija
    params.js      citanje URL parametara, podrazumevane vrednosti
  scenarios/
    s1.js
    s2.js
    s3.js
  shared/
    generate_common.py   baza firmi, kontrolne cifre, klase tezine, seed
    analyze_common.py    hes provera, tipovi gresaka, podklase, odustajanje
  data/
    companies.json
    items_S1.json
    items_S2.json
    items_S3a.json
    items_S3b.json
    excluded_companies.json
  app/
    index.html
    style.css
  standalone/
  logs/
  server.py
  generate_stimuli.py
  analyze_log.py
  dump_item.py
  README.md
```

Jedan projekat umesto dva odvojena. Time nestaje i zavisnost preko relativne putanje između foldera, koja je već jednom pravila problem.

---

## 3. Šta ide u jezgro

### core/clock.js

Sve merenje vremena. `performance.now()` kao jedini izvor, zidni sat samo za grubu sinhronizaciju. Zakazivanje preko `setTimeout` je dozvoljeno, merenje nije.

Obavezno zadržati: merenje stvarno proteklog vremena za svaki zakazani interval i njegovo upisivanje u log, kako je već rađeno za latenciju sugestije u S3 i za fazu kodiranja u S2.

### core/logger.js

Format `session` reda, format redova događaja, računanje heša datoteka sa stimulusima, WebSocket veza sa serverom, preuzimanje datoteke i čuvanje u IndexedDB.

`session` red mora sadržati polje `scenario` sa vrednostima `S1`, `S2`, `S3a` ili `S3b`, i sve konstante tajminga tog scenarija, ma koliko ih bilo.

### core/block.js

Trajanje bloka, redosled stavki, prelaz između stavki, dovršavanje stavke koja je u toku kada vreme istekne, ekran kraja bloka.

### core/screen.js

Zone interesovanja i njihovo upisivanje u `session` red, blokiranje `F5`, `Ctrl+R`, `F11` i `Ctrl+W` tokom bloka, prekid sesije i događaj `window_resized` pri promeni veličine prozora, jednaka svetlina pozadine u svim ekranima.

### core/guard.js

Blokiranje kopiranja, sečenja, lepljenja, kontekstnog menija i prevlačenja, uz beleženje pokušaja i bez poruke ispitaniku. Trenutno postoji samo u S2, ali pripada jezgru jer isto važi za sva tri scenarija.

### core/params.js

Čitanje URL parametara i podrazumevane vrednosti. Serverska verzija zahteva `participant`; samostalna koristi `DEMO` ako parametar nedostaje. Ova razlika je danas rešena na dva različita načina u dva projekta i mora se ujednačiti.

---

## 4. Šta ostaje u scenariju

Isključivo logika samog zadatka:

| Scenario | Sopstvena logika |
|---|---|
| S2 | dva prozora, prebacivanje tasterom F2, ćelije sa maskom, brojanje povrataka i trajanja boravka |
| S3 | referentni zapis i njegovo uklanjanje, panel sa sugestijom, tri ponuđene vrednosti, dugme za ponovni uvid |
| S1 | biće definisano zasebnom specifikacijom |

Faza kodiranja je zajednička po strukturi, ali se razlikuje po sadržaju, pa u jezgro ide samo upravljanje njenim trajanjem (donja granica, gornja granica, taster Spreman, `encoding_actual_ms`, `mode`), dok prikaz materijala ostaje u scenariju.

---

## 5. Python strana

`shared/generate_common.py`: generisanje baze firmi, kontrolne cifre po ISO 7064 MOD 11,10, klase težine, sastav stavke po nivoima, determinizam iz seed-a, snimak isključenih firmi.

`shared/analyze_common.py`: provera heša pre analize, tipovi grešaka, podklase, znaci odustajanja, odstupanje tajminga, provera `stavke × N`.

Umesto tri para skriptova, jedan `generate_stimuli.py --scenario S1|S2|S3` i jedan `analyze_log.py`, koji scenario prepoznaje iz `session` reda i grana se na mere specifične za njega. Isto i `dump_item.py`.

**Disjunktnost firmi sada važi za sva tri scenarija.** Generator mora obezbediti da isti ispitanik ni u jednom paru scenarija ne dobije istu firmu, ne samo između S2 i S3.

---

## 6. Redosled izvođenja

Posle svakog koraka pokrenuti demo blok oba scenarija, na N = 3 i N = 7, i uporediti log sa referentnim. Ne prelaziti dalje bez potvrde.

1. Napraviti `eeg-tasks/` i preneti oba projekta bez izmena. Generisati referentne logove sa fiksiranim seed-om i sačuvati ih kao osnovu za poređenje.
2. `core/clock.js`. Najosetljiviji deo; izvlači se prvi, dok je pažnja najveća.
3. `core/logger.js`.
4. `core/block.js`.
5. `core/screen.js` i `core/guard.js`.
6. `core/params.js`, uz ujednačavanje razlike između serverske i samostalne verzije.
7. Python strana: `shared/`, pa objedinjeni `generate_stimuli.py`, `analyze_log.py` i `dump_item.py`.
8. Ponovna izgradnja samostalnih verzija.

---

## 7. Kriterijum uspeha

Posle svakog koraka, za oba scenarija i oba nivoa N:

- logovi pre i posle premeštanja moraju biti identični u svim poljima osim vremenskih oznaka
- broj polja i dalje jednak `stavke × N`
- odstupanje tajminga u istim granicama kao pre
- izveštaj iz `analyze_log` daje iste brojeve

Ako se bilo koji od ova četiri uslova ne ispuni, korak se vraća i uzrok se traži pre nastavka.

---

## 8. Šta ne raditi

- Ne menjati ponašanje ni u jednom detalju, ni kada se u kodu naiđe na nešto što izgleda kao propust. Zapisati takve nalaze zasebno i rešiti ih posle refaktora.
- Ne uvoditi okvire, alate za prevođenje niti spoljne zavisnosti.
- Ne menjati format loga, osim dodavanja polja `scenario` ako već ne postoji.
- Ne brisati stare projekte dok kriterijum uspeha nije ispunjen za sve korake.
