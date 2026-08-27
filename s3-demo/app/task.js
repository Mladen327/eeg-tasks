"use strict";

/* ==========================================================================
   Konstante tajminga (sekcija 6). Ne menjati u toku sesije.
   Trajanje faze kodiranja = ENCODING_BASE_MS + n_fields * ENCODING_MS_PER_FIELD.
   DECISION_MS_PER_FIELD (limit po polju u fazi verifikacije, sekcija 6.1)
   je odvojena konstanta -- ranije je bila izjednacena sa
   ENCODING_MS_PER_FIELD, ali su to sad namerno dva razlicita broja otkako
   se ENCODING_MS_PER_FIELD menja nezavisno.
   ========================================================================== */
const ENCODING_BASE_MS      = 4000;
const ENCODING_MS_PER_FIELD = 5000;
const SUGGESTION_LATENCY_MS = 1500;
const ITEM_GAP_MS           = 1500;
const PEEK_DURATION_MS      = 3000;
const BLOCK_DURATION_MS     = 180000;

// DECISION_MS_PER_FIELD je prag za MERENJE (over_deadline u value_submitted),
// ne vremenski limit koji pomera polje. Polje uvek napreduje samo posle
// klika ispitanika na ponudu (runField).
//
// ENFORCE_DECISION_DEADLINE=true vraca staro ponasanje: posle isteka
// DECISION_MS_PER_FIELD polje samo napreduje bez izbora (timed_out:true).
// Namerno ostavljeno u kodu kao grana za period posle pilota, kad se prag
// eventualno ponovo aktivira -- ne brisati.
const DECISION_MS_PER_FIELD = 3000;
const ENFORCE_DECISION_DEADLINE = false;

const DEMO_ITEM_CAP = 4;
const WS_PORT = 8765;

// Podrazumevane vrednosti za samostalnu verziju (build_standalone.py) kad
// URL parametri nedostaju ili su neispravni. Vazi samo van ?practice=1 i
// samo kad su podaci ugradjeni (window.__S3_EMBEDDED__) -- server verzija
// i dalje zahteva pune, ispravne URL parametre (sekcija 9).
const EMBEDDED_DEFAULTS = { participant: "DEMO", variant: "S3b", n: 5, demo: true };

const FIELD_LABELS = {
  contract_number: "Broj ugovora",
  company_name: "Naziv firme",
  pib: "PIB",
  registration_number: "Matični broj",
  city: "Grad",
  street: "Ulica",
  street_number: "Broj",
  monthly_fee_per_package: "Mesečna naknada po paketu",
  contact_person: "Kontakt osoba",
  employee_count: "Broj zaposlenih",
  package_count: "Broj paketa",
  contract_months: "Trajanje (meseci)",
  total_monthly_fee: "Ukupna mesečna naknada",
  start_date: "Datum početka",
  contact_phone: "Telefon",
};

// Pun spisak polja referentnog zapisa (kontekstna + polja za proveru).
// Koristi se kao podrazumevana lista za renderReferenceInto() kad se ne
// prosledi uza lista -- trenutno samo za "uvid" (peek) u fazi verifikacije.
// U fazi kodiranja se namerno prikazuje samo N polja koja se u toj stavci
// proveravaju (checkFieldNamesFor()), ne ovaj pun spisak.
const REFERENCE_DISPLAY_FIELDS = [
  "contract_number", "company_name", "pib", "registration_number", "city",
  "street", "street_number", "monthly_fee_per_package", "contact_person",
  "employee_count", "package_count", "contract_months", "total_monthly_fee",
  "start_date", "contact_phone",
];

/* ==========================================================================
   Formatiranje prikaza (sekcija 3.5). Iskljucivo vizuelno -- sirove
   vrednosti u items_*.json i u logu ostaju bez razmaka/segmentacije.
   ========================================================================== */

function groupDigits(digits, sizes) {
  const parts = [];
  let i = 0;
  for (const size of sizes) {
    parts.push(digits.slice(i, i + size));
    i += size;
  }
  return parts.join(" ");
}

function formatDisplay(fieldName, rawValue) {
  const v = String(rawValue);
  switch (fieldName) {
    case "pib":
      return groupDigits(v, [3, 3, 3]);
    case "registration_number":
      return groupDigits(v, [2, 3, 3]);
    case "contract_number": {
      // TK-2026-NNNNN (5 cifara) -> prikaz TK-2026-NNNN (poslednje 4), namerno
      const [prefix, year, tail] = v.split("-");
      return `${prefix}-${year}-${tail.slice(-4)}`;
    }
    case "monthly_fee_per_package":
      return `${Number(v).toLocaleString("sr-RS")} RSD`;
    case "total_monthly_fee":
      return `${Number(v).toLocaleString("sr-RS")} RSD`;
    case "contact_phone":
      return `${v.slice(0, 3)}/${v.slice(3, 6)}-${v.slice(6, 10)}`;
    case "start_date": {
      const [y, m, d] = v.split("-");
      return `${d}.${m}.${y}.`;
    }
    default:
      return v;
  }
}

/* ==========================================================================
   Logger, bufToHashHex, fetchAndHash sada dolaze iz core/logger.js (ucitan
   u app/index.html pre ovog fajla) -- premesteno bez izmene ponasanja,
   videti core/logger.js za napomene.
   ========================================================================== */

/* ==========================================================================
   Pomocne funkcije za tajming: waitFor/raceWithTimeout/round1 sada dolaze
   iz core/clock.js (ucitan u app/index.html pre ovog fajla) -- premesteno
   bez izmene ponasanja, videti core/clock.js za napomene.
   ========================================================================== */

/* ==========================================================================
   Ucitavanje podataka.
   ========================================================================== */

async function loadText(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`ne mogu da ucitam ${path}: ${res.status}`);
  return res.text();
}

/* ==========================================================================
   Izvor podataka: fetch (server/http.server) ILI window.__S3_EMBEDDED__
   (samostalna verzija, build_standalone.py, sve u jednom index.html, radi
   preko file:// bez servera -- fetch() lokalnih fajlova je tamo blokiran
   CORS politikom pregledaca). Isti task.js radi u oba slucaja.
   ========================================================================== */

function isEmbedded() {
  return isEmbeddedCore("__S3_EMBEDDED__");
}

async function fetchTemplate() {
  if (isEmbedded()) return window.__S3_EMBEDDED__.template;
  return loadText(`../data/contract_template.html`);
}

// Vraca i podatke i sha256 heš datoteke koja ih je isporucila (upisuje se u
// session red loga -- videti computeRoiAndSendHeader). U ugradjenom rezimu
// je items vec parsiran JS objekat (nema sirovih bajtova originalne
// datoteke da bi se heš racunao ovde), pa build_standalone.py unapred
// izracuna heš iz istog items_${variant}.json fajla i ugradi ga kao gotovu
// nisku, po varijanti.
async function fetchItemsWithHash(variant) {
  if (isEmbedded()) {
    const data = window.__S3_EMBEDDED__.items[variant];
    const hash = window.__S3_EMBEDDED__.items_hash[variant];
    if (!data) throw new Error(`nema ugradjenih podataka za varijantu ${variant}`);
    return { data, hash };
  }
  const { text, hash } = await fetchAndHash(`../data/items_${variant}.json`);
  return { data: JSON.parse(text), hash };
}

async function fetchSuggestions() {
  if (isEmbedded()) return window.__S3_EMBEDDED__.suggestions;
  const { text } = await fetchAndHash(`../data/suggestions.json`);
  return JSON.parse(text);
}

async function fetchCompaniesHash() {
  if (isEmbedded()) return window.__S3_EMBEDDED__.companies_hash;
  const { hash } = await fetchAndHash(`../data/companies.json`);
  return hash;
}

/* ==========================================================================
   Renderovanje ugovora iz sablona (data/contract_template.html).
   Sablon ima {{field}} markere unutar <span data-field="field">.
   ========================================================================== */

function renderContract(mountEl, templateHtml, printedRecord) {
  let html = templateHtml;
  for (const [field, rawValue] of Object.entries(printedRecord)) {
    if (field === "company_id") continue;
    const formatted = formatDisplay(field, rawValue);
    html = html.split(`{{${field}}}`).join(escapeHtml(formatted));
  }
  mountEl.innerHTML = html;
}

// escapeHtml sada dolazi iz core/screen.js.

// fieldNames: koja polja i kojim redosledom prikazati. Podrazumevano (bez
// treceg argumenta, npr. za peek u fazi verifikacije) prikazuje se pun
// zapis, REFERENCE_DISPLAY_FIELDS. U fazi kodiranja se sada namerno salje
// suzena lista -- samo N polja koja se u toj stavci proveravaju.
function renderReferenceInto(mountEl, referenceRecord, fieldNames) {
  const fields = fieldNames || REFERENCE_DISPLAY_FIELDS;
  const dl = document.createElement("dl");
  for (const field of fields) {
    const dt = document.createElement("dt");
    dt.textContent = FIELD_LABELS[field] || field;
    const dd = document.createElement("dd");
    dd.textContent = formatDisplay(field, referenceRecord[field]);
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  mountEl.innerHTML = "";
  mountEl.appendChild(dl);
}

function clearMount(mountEl) {
  mountEl.innerHTML = "";
}

// Polja za proveru jedne stavke, poredjana po field.order (isti redosled
// koji se koristi i u fazi verifikacije).
function checkFieldNamesFor(item) {
  return item.fields.slice().sort((a, b) => a.order - b.order).map((f) => f.field_name);
}

function highlightContractFields(fieldNames, on) {
  for (const name of fieldNames) {
    const el = document.querySelector(`#contract-mount [data-field="${name}"]`);
    if (el) el.classList.toggle("active", on);
  }
}

/* ==========================================================================
   Opcije za odgovor (sekcija 6.1).
   ========================================================================== */

function shuffled(arr, rng) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Jednostavan deterministicki PRNG (mulberry32) da bi redosled opcija bio
// stabilan po (item_id, field_name) ako se ekran ponovo iscrta, bez novog
// izvora entropije u toku izvodjenja (sekcija 11: bez nasumicnosti u toku
// izvodjenja van generisanja u pripremi). Seed se izvodi iz item_id+field.
function seededRng(seedStr) {
  let h = 1779033703 ^ seedStr.length;
  for (let i = 0; i < seedStr.length; i++) {
    h = Math.imul(h ^ seedStr.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return function () {
    h = Math.imul(h ^ (h >>> 16), 2246822519);
    h = Math.imul(h ^ (h >>> 13), 3266489917);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}

function buildOptions(item, field) {
  const rng = seededRng(`${item.item_id}|${field.field_name}`);
  let raw;
  if (field.true_status === "match") {
    // A i B su ista vrednost: prikazuju se DVE opcije, da izbor drugog
    // ne bi odao da je polje match (sekcija 6.1).
    raw = [
      { value: field.reference_value, role: "reference" },
      { value: field.distractor_value, role: "distractor" },
    ];
  } else {
    raw = [
      { value: field.displayed_value, role: "contract" },
      { value: field.reference_value, role: "reference" },
      { value: field.distractor_value, role: "distractor" },
    ];
  }
  return shuffled(raw, rng);
}

/* ==========================================================================
   Glavni tok.
   ========================================================================== */

const els = {};
function cacheEls() {
  [
    "screen-loading", "screen-global-intro", "screen-session-overview", "screen-instructions",
    "screen-task", "screen-gap", "screen-end", "screen-end-title", "screen-end-message",
    "global-intro-title", "global-intro-input", "global-intro-display", "btn-global-intro-next",
    "session-overview-summary", "session-overview-list", "btn-session-overview-next",
    "instructions-position", "instructions-title", "instructions-lines", "instructions-selectors",
    "btn-start", "intro-suggestion-note", "select-variant", "select-n",
    "progress-bar", "counter-item", "counter-field",
    "contract-mount", "encoding-block", "reference-mount", "encoding-countdown",
    "verification-block", "btn-peek", "peek-mount",
    "suggestion-panel", "suggestion-loading", "suggestion-text",
    "suggestion-buttons", "btn-accept", "btn-reject",
    "options-panel", "options-list", "download-note",
  ].forEach((id) => { els[id] = document.getElementById(id); });
}

// showScreen sada dolazi iz core/block.js.

// parseParams sada dolazi iz core/params.js (parseParamsCore); "variant" je
// jedino polje po kome se S3 razlikuje od S2, prosledjeno kao extraKeys.
function parseParams() {
  return parseParamsCore(["variant"]);
}

const TASK_ID = "S3";

// Renderuje prvu stavku (za ROI merenje) i salje sesijsko zaglavlje --
// izdvojeno iz runBlock() da bi main() moglo da ga pozove RANO (server/
// vezba) ili KASNO (ugradjeni rezim, gde se varijanta/N tek biraju na
// ekranu uputstva). Videti napomenu uz poziv u main().
function primeAndSendHeader(ctx) {
  if (ctx.items.length > 0) {
    renderContract(els["contract-mount"], GLOBAL_TEMPLATE, ctx.items[0].printed);
    renderReferenceInto(els["reference-mount"], ctx.items[0].reference, checkFieldNamesFor(ctx.items[0]));
  }
  measureWhileVisible("task", () => computeRoiAndSendHeader(ctx));
}

async function main() {
  cacheEls();
  const params = parseParams();
  const embedded = isEmbedded();

  // Ekran 1 (core/intro.js) treba da zna sifru ispitanika PRE
  // resolveParamsCore -- videti napomenu u scenarios/s1.js main() (isti
  // obrazac u sva tri scenarija). Vezba je izuzeta.
  if (!params.practice) {
    const known = params.participant || (embedded ? EMBEDDED_DEFAULTS.participant : null);
    params.participant = await runGlobalIntroScreen(known);
  }

  const resolved = resolveParamsCore(params, embedded, EMBEDDED_DEFAULTS, {
    validate: (p) => ["S3a", "S3b"].includes(p.variant),
    fatalMessage: "Nedostaju ili su neispravni URL parametri. Ocekivano: ?participant=P07&variant=S3b&n=5",
    practiceExtra: (r) => { r.effectiveVariant = "S3a"; },
    // Samostalna verzija: bez tvrde provere. Nedostajuci ili neispravni
    // parametri dobijaju podrazumevane vrednosti; svaki URL parametar koji
    // JESTE naveden i validan ima prednost nad svojom podrazumevanom
    // vrednoscu (nezavisno po parametru).
    embeddedExtra: (r, p, defaults) => {
      r.effectiveVariant = ["S3a", "S3b"].includes(p.variant) ? p.variant : defaults.variant;
    },
    serverExtra: (r, p) => { r.effectiveVariant = p.variant; },
  });
  if (resolved.fatal) {
    showFatal(resolved.fatal);
    return;
  }
  const isPractice = resolved.isPractice, participantId = resolved.participantId, isDemo = resolved.isDemo;
  let n = resolved.n, effectiveVariant = resolved.effectiveVariant;

  // U samostalnoj verziji se ucitavaju OBE varijante unapred (vec su
  // ugradjene, nema mrezne cene), tako da izbornik na ekranu uputstva moze
  // da prebaci S3a<->S3b bez ponovnog ucitavanja stranice.
  const itemsByVariant = {};
  const itemsHashByVariant = {};
  let suggestionsData = null;
  let companiesHash, instructionsData;
  try {
    if (isPractice) {
      ({ data: itemsByVariant.S3a, hash: itemsHashByVariant.S3a } = await fetchItemsWithHash("S3a"));
    } else if (embedded) {
      ({ data: itemsByVariant.S3a, hash: itemsHashByVariant.S3a } = await fetchItemsWithHash("S3a"));
      ({ data: itemsByVariant.S3b, hash: itemsHashByVariant.S3b } = await fetchItemsWithHash("S3b"));
      suggestionsData = await fetchSuggestions();
    } else {
      ({ data: itemsByVariant[effectiveVariant], hash: itemsHashByVariant[effectiveVariant] } = await fetchItemsWithHash(effectiveVariant));
      if (effectiveVariant === "S3b") suggestionsData = await fetchSuggestions();
    }
    companiesHash = await fetchCompaniesHash();
    instructionsData = await fetchInstructions(`../../data/instructions.json`);
  } catch (err) {
    showFatal(`Greska pri ucitavanju podataka: ${err.message}`);
    return;
  }

  const wsOk = await Logger.connect();

  function updateSuggestionNote() {
    const v = embedded && !isPractice ? els["select-variant"].value : effectiveVariant;
    els["intro-suggestion-note"].classList.toggle("hidden", v !== "S3b" || isPractice);
  }

  // Vezba i server rezim: varijanta/N su vec poznati, pa se sesijsko
  // zaglavlje salje SADA, pre uvodnih ekrana -- da instructions_shown/
  // dismissed zavrse u ispravnom fajlu (core/intro.js, napomena na vrhu
  // tog fajla). Ugradjeni (demo) rezim ceka do posle ekrana uputstva, gde
  // se varijanta/N tek biraju (izbornici).
  let itemsData, items;
  const earlySend = isPractice || !embedded;
  if (earlySend) {
    itemsData = itemsByVariant[effectiveVariant];
    if (isPractice) {
      n = itemsData.practice.n_fields;
      items = itemsData.practice.items;
    } else {
      items = itemsData.participants[participantId][String(n)];
      if (isDemo) items = items.slice(0, DEMO_ITEM_CAP);
    }
    primeAndSendHeader({
      participantId, variant: isPractice ? "practice" : effectiveVariant, n, items,
      itemsHash: itemsHashByVariant[isPractice ? "S3a" : effectiveVariant], companiesHash, seed: itemsData.seed,
    });
  }

  if (embedded && !isPractice) {
    els["select-variant"].value = effectiveVariant;
    els["select-n"].value = String(n);
    els["select-variant"].addEventListener("change", updateSuggestionNote);
  }
  updateSuggestionNote();

  if (!isPractice) {
    await runSessionOverviewScreen(instructionsData);
  }
  await runInstructionsScreen(instructionsData, TASK_ID, {
    showSelectors: embedded && !isPractice,
    isPractice,
  });

  if (embedded && !isPractice) {
    effectiveVariant = els["select-variant"].value;
    n = parseInt(els["select-n"].value, 10);
    itemsData = itemsByVariant[effectiveVariant];
    items = itemsData.participants[participantId][String(n)];
    if (isDemo) items = items.slice(0, DEMO_ITEM_CAP);
    primeAndSendHeader({
      participantId, variant: effectiveVariant, n, items,
      itemsHash: itemsHashByVariant[effectiveVariant], companiesHash, seed: itemsData.seed,
    });
  }

  let suggestionsByItem = {};
  if (suggestionsData && effectiveVariant === "S3b" && !isPractice) {
    const blockSuggestions = suggestionsData.participants[participantId][String(n)];
    for (const entry of blockSuggestions) {
      const byField = {};
      for (const f of entry.fields) byField[f.field_name] = f;
      suggestionsByItem[entry.item_id] = byField;
    }
  }

  applyEndScreenText(instructionsData, TASK_ID, isPractice);

  showScreen("task");
  await runBlock({
    participantId,
    variant: isPractice ? "practice" : effectiveVariant,
    n,
    items,
    suggestionsByItem,
    isPractice,
    isDemo,
    itemsHash: itemsHashByVariant[isPractice ? "S3a" : effectiveVariant],
    companiesHash,
    seed: itemsData.seed,
  });
}

// showFatal sada dolazi iz core/screen.js.

/* ==========================================================================
   Jedan blok. Petlja/prelazi/kraj bloka su u core/block.js (runBlockCore)
   -- ovde ostaje samo ono sto NIJE bilo identicno sa S2: "priming"
   renderovanje ugovora pre merenja ROI-ja (S2 nema ekvivalent, jer
   #stage ima fiksnu CSS velicinu nezavisnu od sadrzaja), sesijsko
   zaglavlje (potpuno scenario-specifican sadrzaj), i adapter ka runItem()
   (jezgro uvek zove itemRunner(item, index, n) sa tacno tri argumenta; S3
   svom runItem-u prosledjuje jos i variant/suggestionsByItem/isPractice
   preko zatvaranja).

   F5/F11/Ctrl+R/Ctrl+W zastita i kopi-zastita (korak "Uskladi S1 sa S2/S3",
   tacka 5): ranije su postojale samo u S2 -- razlog za izostanak u S3 bio
   je "refaktor bez funkcionalne izmene" (core/screen.js, core/guard.js),
   sto vise ne vazi kao razlog da razlika ostane posto je refaktor zavrsen
   i proveren. Kopi-zastita je namerno OGRANICENA na read-only prikaze
   (ugovor, referentni zapis, uvid, tekst sugestije) -- NE i na
   #options-panel/#suggestion-buttons, da ne bi ometala klik na ponudjene
   vrednosti (dugo drzanje/prevlacenje preko teksta dugmeta), potvrdjeno
   Playwright testom posle ove izmene.
   ========================================================================== */

let copyProtectionInstalled = false;

// Deljena, mutabilna referenca na "trenutnu stavku" -- isti obrazac kao S2
// (currentItemRef), potrebna ovde tek sada da bi installCopyProtection imao
// sta da prosledi kao getItemIndex() zatvaranje.
const currentItemRef = { current: 0 };

async function runBlock(ctx) {
  const { variant, items, suggestionsByItem, isPractice } = ctx;

  // Priming-renderovanje + computeRoiAndSendHeader(ctx) se vise NE zovu
  // ovde -- pozivalac (main()) ih sada zove eksplicitno preko
  // primeAndSendHeader(), RANO (server/vezba) ili KASNO (ugradjeni rezim),
  // pre uvodnih ekrana iz core/intro.js. Videti napomenu u main().

  window.addEventListener("keydown", blockRefreshKeys);
  if (!copyProtectionInstalled) {
    installCopyProtection(els["contract-mount"], () => true, () => currentItemRef.current);
    installCopyProtection(els["reference-mount"], () => true, () => currentItemRef.current);
    installCopyProtection(els["peek-mount"], () => true, () => currentItemRef.current);
    installCopyProtection(els["suggestion-text"], () => true, () => currentItemRef.current);
    copyProtectionInstalled = true;
  }

  await runBlockCore(ctx, (item, itemIndex, n) => runItem(item, itemIndex, n, variant, suggestionsByItem, isPractice));

  window.removeEventListener("keydown", blockRefreshKeys);
}

// onResizeAbort sada dolazi iz core/screen.js.

function computeRoiAndSendHeader(ctx) {
  const contractRect = els["contract-mount"].getBoundingClientRect();
  const rightColRect = els["verification-block"].parentElement.getBoundingClientRect();

  Logger.sessionHeader({
    participant_id: ctx.participantId,
    // Jedino sankcionisano dodavanje polja u log format ovim refaktorom
    // (uputstvo, sekcija 8). scenario je uvek "S3a" ili "S3b" -- za vezbu
    // (ctx.variant === "practice") to je uvek "S3a", jer vezba uvek koristi
    // S3a stavke (main(), isPractice grana). Razlikuje se od "variant"
    // koji dole i dalje razlikuje "S3a"/"S3b"/"practice".
    scenario: ctx.variant === "practice" ? "S3a" : ctx.variant,
    variant: ctx.variant,
    n_fields: ctx.n,
    seed: ctx.seed,
    items_hash: ctx.itemsHash,
    companies_hash: ctx.companiesHash,
    screen: { w: window.screen.width, h: window.screen.height },
    roi: { contract: roiRectArray(contractRect), suggestion: roiRectArray(rightColRect) },
    encoding_base_ms: ENCODING_BASE_MS,
    encoding_ms_per_field: ENCODING_MS_PER_FIELD,
    decision_ms_per_field: DECISION_MS_PER_FIELD,
    enforce_decision_deadline: ENFORCE_DECISION_DEADLINE,
    t0_wall: new Date().toISOString(),
    t0_perf: round1(performance.now()),
  });
}

function updateProgress(fraction, itemIndex, itemTotal) {
  const pct = Math.max(0, Math.min(1, fraction)) * 100;
  els["progress-bar"].style.width = `${pct}%`;
  els["counter-item"].textContent = `Stavka ${itemIndex}`;
  els["counter-field"].textContent = "";
}

/* ==========================================================================
   Jedna stavka: kodiranje pa verifikacija.
   ========================================================================== */

async function runItem(item, itemIndex, n, variant, suggestionsByItem, isPractice) {
  currentItemRef.current = itemIndex;
  Logger.log({ event: "item_start", item: itemIndex, item_id: item.item_id, company_id: item.company_id });

  // --- Faza 1: kodiranje ---
  els["encoding-block"].classList.remove("hidden");
  els["verification-block"].classList.add("hidden");
  els["btn-peek"].classList.add("hidden");
  clearMount(els["peek-mount"]);

  const checkFieldNames = checkFieldNamesFor(item);

  renderContract(els["contract-mount"], GLOBAL_TEMPLATE, item.printed);
  // Referentni zapis u fazi kodiranja prikazuje SAMO ta N polja (istim
  // redosledom), ne ceo zapis -- kontekstna polja ostaju na ugovoru radi
  // realizma, ali se ovde ne prikazuju niti isticu. Ista polja se
  // istovremeno isticu i na ugovoru, da ispitanik odmah zna sta poredi.
  renderReferenceInto(els["reference-mount"], item.reference, checkFieldNames);
  highlightContractFields(checkFieldNames, true);
  els["encoding-countdown"].classList.remove("hidden");

  const encodingDuration = ENCODING_BASE_MS + n * ENCODING_MS_PER_FIELD;
  Logger.log({ event: "encoding_start", item: itemIndex, duration_ms: encodingDuration });
  await waitFor(encodingDuration, (remaining) => {
    els["encoding-countdown"].textContent = `Preostalo: ${Math.ceil(remaining / 1000)} s`;
  });
  Logger.log({ event: "encoding_end", item: itemIndex });

  // --- Faza 2: verifikacija ---
  els["encoding-block"].classList.add("hidden");
  clearMount(els["reference-mount"]); // uklanjanje iz DOM stabla, ne sakrivanje
  highlightContractFields(checkFieldNames, false); // ciscenje pre pojedinacnog isticanja po polju u verifikaciji
  els["verification-block"].classList.remove("hidden");

  let peekUsed = false;
  els["btn-peek"].classList.remove("hidden");
  els["btn-peek"].disabled = false;
  els["btn-peek"].onclick = async () => {
    if (peekUsed) return;
    peekUsed = true;
    els["btn-peek"].disabled = true;
    Logger.log({ event: "peek_start", item: itemIndex });
    renderReferenceInto(els["peek-mount"], item.reference);
    await waitFor(PEEK_DURATION_MS);
    clearMount(els["peek-mount"]);
    Logger.log({ event: "peek_end", item: itemIndex });
  };

  const fieldsInOrder = item.fields.slice().sort((a, b) => a.order - b.order);
  for (let fi = 0; fi < fieldsInOrder.length; fi++) {
    if (sessionAborted) return;
    await runField(item, itemIndex, fieldsInOrder[fi], fi + 1, fieldsInOrder.length, variant, suggestionsByItem, isPractice);
  }

  els["btn-peek"].classList.add("hidden");
  Logger.log({ event: "item_end", item: itemIndex });
}

let GLOBAL_TEMPLATE = "";

/* ==========================================================================
   Jedno polje u fazi verifikacije.
   ========================================================================== */

async function runField(item, itemIndex, field, fieldIndex, fieldTotal, variant, suggestionsByItem, isPractice) {
  els["counter-field"].textContent = `Polje ${fieldIndex}/${fieldTotal}`;

  const target = document.querySelector(`#contract-mount [data-field="${field.field_name}"]`);
  if (target) target.classList.add("active");

  Logger.log({
    event: "field_active",
    item: itemIndex,
    field: fieldIndex,
    field_name: field.field_name,
    weight_class: field.weight_class,
    true_status: field.true_status,
  });

  // --- S3b: predlog modela ---
  if (variant === "S3b" && !isPractice) {
    const suggestion = suggestionsByItem[item.item_id][field.field_name];

    els["suggestion-panel"].classList.remove("hidden");
    els["suggestion-loading"].classList.remove("hidden");
    els["suggestion-text"].classList.add("hidden");
    els["suggestion-buttons"].classList.add("hidden");

    const elapsed = await waitFor(SUGGESTION_LATENCY_MS);
    Logger.log({
      event: "suggestion_shown",
      item: itemIndex,
      field: fieldIndex,
      field_name: field.field_name,
      true_status: field.true_status,
      suggestion_type: suggestion.suggestion_type,
      outcome_class: suggestion.outcome_class,
      latency_actual_ms: round1(elapsed),
    });

    els["suggestion-loading"].classList.add("hidden");
    els["suggestion-text"].textContent = suggestion.text;
    els["suggestion-text"].classList.remove("hidden");
    els["suggestion-buttons"].classList.remove("hidden");

    const decisionStart = performance.now();
    const accepted = await new Promise((resolve) => {
      const onClick = (e) => {
        els["btn-accept"].removeEventListener("click", onAccept);
        els["btn-reject"].removeEventListener("click", onReject);
      };
      const onAccept = () => { onClick(); resolve(true); };
      const onReject = () => { onClick(); resolve(false); };
      els["btn-accept"].addEventListener("click", onAccept);
      els["btn-reject"].addEventListener("click", onReject);
    });
    Logger.log({
      event: "decision",
      item: itemIndex,
      field: fieldIndex,
      field_name: field.field_name,
      accepted,
      decision_time_ms: round1(performance.now() - decisionStart),
    });

    els["suggestion-panel"].classList.add("hidden");
  }

  // --- izbor konacne vrednosti (sekcija 6.1) ---
  const options = buildOptions(item, field);
  els["options-panel"].classList.remove("hidden");
  const list = els["options-list"];
  list.innerHTML = "";

  const optionStart = performance.now();
  const clickPromise = new Promise((resolve) => {
    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.className = "option-btn";
      btn.textContent = formatDisplay(field.field_name, opt.value);
      btn.addEventListener("click", () => resolve(opt), { once: true });
      list.appendChild(btn);
    });
  });

  let chosenOpt, timedOut, elapsedMs;
  if (ENFORCE_DECISION_DEADLINE) {
    // Stara grana: posle isteka DECISION_MS_PER_FIELD polje samo napreduje
    // bez izbora. Vidi napomenu uz ENFORCE_DECISION_DEADLINE gore.
    const result = await raceWithTimeout(clickPromise, DECISION_MS_PER_FIELD);
    chosenOpt = result.value;
    timedOut = result.timedOut;
    elapsedMs = result.elapsed;
  } else {
    // Podrazumevano: bez roka. Polje napreduje iskljucivo posle klika.
    chosenOpt = await clickPromise;
    timedOut = false;
    elapsedMs = performance.now() - optionStart;
  }
  list.querySelectorAll("button").forEach((b) => { b.disabled = true; });

  const correct = !timedOut && chosenOpt.role === "reference";

  Logger.log({
    event: "value_submitted",
    item: itemIndex,
    field: fieldIndex,
    field_name: field.field_name,
    options: options.map((o) => ({ value: o.value, role: o.role })),
    chosen: timedOut ? null : chosenOpt.value,
    chosen_role: timedOut ? null : chosenOpt.role,
    correct,
    timed_out: timedOut,
    over_deadline: elapsedMs > DECISION_MS_PER_FIELD,
    decision_ms: round1(elapsedMs),
  });

  if (isPractice) {
    const fb = document.createElement("p");
    fb.textContent = correct ? "Tacno." : "Netacno.";
    list.appendChild(fb);
    await waitFor(1200);
  }

  els["options-panel"].classList.add("hidden");
  if (target) target.classList.remove("active");
}

/* ==========================================================================
   Init.
   ========================================================================== */

window.addEventListener("DOMContentLoaded", async () => {
  cacheEls();
  try {
    GLOBAL_TEMPLATE = await fetchTemplate();
  } catch (e) {
    showFatal(`Greska pri ucitavanju sablona ugovora: ${e.message}`);
    return;
  }
  main();
});
