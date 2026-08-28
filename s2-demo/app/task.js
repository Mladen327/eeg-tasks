"use strict";

/* ==========================================================================
   Konstante tajminga (sekcija 7). Ne menjati u toku sesije.
   Trajanje faze kodiranja = ENCODING_BASE_MS + n_fields * ENCODING_MS_PER_FIELD.
   ========================================================================== */
const ENCODING_BASE_MS      = 4000;
const ENCODING_MS_PER_FIELD = 5000;
// Donja granica faze kodiranja (dopuna uputstva): dugme "Spreman" i F2 ne
// rade pre nego sto protekne ENCODING_MIN_MS, da se stavka ne bi preskocila
// slucajnim pritiskom pre nego sto je ispitanik uopste stigao da pogleda
// podatke. Gornja granica (ENCODING_BASE_MS + n*ENCODING_MS_PER_FIELD)
// ostaje kao pre -- automatski prelazak na isteku, nepromenjeno.
const ENCODING_MIN_MS       = 3000;
// Prelazak izmedju prozora je trenutan -- trosak se sada iskljucivo
// izrazava kroz MAX_SWITCHES_PER_ITEM (ogranicenje broja povrataka), ne
// kroz kasnjenje. Konstanta i dalje postoji i upisuje se u session red
// loga (switch_delay_ms=0), jer waitFor(0)/window_switch mehanizam ostaje
// isti (jedan animacioni frejm praznog ekrana, ~0-16ms), samo mu je
// trajanje sad nula.
const SWITCH_DELAY_MS       = 0;
const ITEM_GAP_MS           = 1500;
const BLOCK_DURATION_MS     = 180000;

// Nema roka po celiji i nema automatskog napredovanja (sekcija 7). Celija
// ceka unos neograniceno. ENFORCE_CELL_DEADLINE ostaje u kodu, spreman za
// kad se posle pilota izvede eventualni rok iz raspodele first_keystroke_ms
// -- nema numericke vrednosti jos, jer uputstvo namerno ne propisuje jednu.
const ENFORCE_CELL_DEADLINE = false;

// Gornja granica broja povrataka u Prozor A PO STAVCI, posle faze
// kodiranja (automatski prelazak na kraju kodiranja se NE broji -- to nije
// "povratak"). null = bez ogranicenja (podrazumevano, za sada) -- povratak
// je neogranicen, F2 i dugme su uvek omoguceni. Logika u goToDocument()
// ostaje potpuno implementirana i neaktivna: kad se ovde ponovo upise broj,
// dalji pokusaji posle granice se opet odbijaju i beleze kao switch_denied.
// Brojac preostalih uvida u Prozoru B je UKLONJEN iz UI-ja (bio je vezan
// za prethodnu aktivaciju ove granice) -- ako se granica ponovo aktivira,
// vizuelna povratna informacija se projektuje iznova tada.
const MAX_SWITCHES_PER_ITEM = null;

const DEMO_ITEM_CAP = 3;
const WS_PORT = 8766; // razlicit od s3-demo (8765) da oba demoa mogu da rade istovremeno

// Podrazumevane vrednosti za samostalnu verziju (standalone/index.html) kad
// URL parametri nedostaju ili su neispravni. Vazi samo van ?practice=1 i
// samo kad su podaci ugradjeni (window.__S2_EMBEDDED__) -- server verzija
// i dalje zahteva pune, ispravne URL parametre (sekcija 9 uputstva S3,
// preuzeto bez izmena za S2).
const EMBEDDED_DEFAULTS = { participant: "DEMO", n: 5, demo: true };

const FIELD_LABELS = {
  company_name: "Naziv firme",
  pib: "PIB",
  registration_number: "Matični broj",
  city: "Grad",
  street: "Ulica",
  street_number: "Broj",
  contact_person: "Kontakt osoba",
  contact_phone: "Telefon",
};

// Redosled prikaza na dokumentu (mora odgovarati data/document_template.html).
const DOCUMENT_FIELD_ORDER = [
  "company_name", "pib", "registration_number", "city",
  "street", "street_number", "contact_person", "contact_phone",
];

/* ==========================================================================
   Formatiranje prikaza (sekcija 3.3). Iskljucivo vizuelno -- sirove
   vrednosti u items_S2.json i u logu ostaju bez razmaka/kose crte.
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
    case "contact_phone":
      return `${v.slice(0, 3)}/${v.slice(3, 6)}-${v.slice(6, 10)}`;
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
   Pomocne funkcije za tajming: waitFor/round1 sada dolaze iz
   core/clock.js (ucitan u app/index.html pre ovog fajla) -- premesteno
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

function isEmbedded() {
  return isEmbeddedCore("__S2_EMBEDDED__");
}

async function fetchTemplate() {
  if (isEmbedded()) return window.__S2_EMBEDDED__.template;
  return loadText(`../data/document_template.html`);
}

// Ucitava items_S2.json i companies.json i vraca i njihove sha256 hesove
// (sekcija 7 dopune uputstva: hes se upisuje u session red loga, radi
// integriteta -- analyze_log_s2.py ga posle poredi sa hesom fajla koji
// stvarno cita, sekcija 10). U ugradjenom (samostalnom) rezimu se hesovi
// NE racunaju ovde -- build_standalone_s2.py ih izracuna unapred iz istih
// fajlova i ugradi kao gotove niske, jer se u tom rezimu ionako ucitava
// vec parsiran JS objekat (window.__S2_EMBEDDED__.items), bez sirovih
// bajtova originalne datoteke nad kojima bi ovde ponovo mogli da racunamo
// heš.
async function fetchItemsAndHashes() {
  if (isEmbedded()) {
    const emb = window.__S2_EMBEDDED__;
    return { itemsData: emb.items, itemsHash: emb.items_hash, companiesHash: emb.companies_hash };
  }
  const itemsFetch = await fetchAndHash(`../data/items_S2.json`);
  const companiesFetch = await fetchAndHash(`../data/companies.json`);
  return {
    itemsData: JSON.parse(itemsFetch.text),
    itemsHash: itemsFetch.hash,
    companiesHash: companiesFetch.hash,
  };
}

/* ==========================================================================
   Renderovanje dokumenta (Prozor A) iz sablona (data/document_template.html).
   Sablon ima {{field}} markere unutar <span data-field="field">.
   ========================================================================== */

function renderDocument(mountEl, templateHtml, documentRecord) {
  let html = templateHtml;
  for (const field of DOCUMENT_FIELD_ORDER) {
    const formatted = formatDisplay(field, documentRecord[field]);
    html = html.split(`{{${field}}}`).join(escapeHtml(formatted));
  }
  mountEl.innerHTML = html;
}

// escapeHtml sada dolazi iz core/screen.js.

function highlightDocumentFields(fieldNames, on) {
  for (const name of fieldNames) {
    const el = document.querySelector(`#document-mount [data-field="${name}"]`);
    if (el) el.classList.toggle("active", on);
  }
}

function checkFieldNamesFor(item) {
  return item.fields.slice().sort((a, b) => a.order - b.order).map((f) => f.field_name);
}

/* ==========================================================================
   Ulazne celije po polju (sekcija 6.1): tip, maska, ogranicenja.
   ========================================================================== */

function digitsOnly(s) { return s.replace(/\D/g, ""); }

function formatPhoneProgressive(digits) {
  // digits: samo cifre, do 10. Progresivno gradi 06X/XXX-XXXX dok se kuca.
  const d = digits.slice(0, 10);
  let out = d.slice(0, 3);
  if (d.length > 3) out += "/" + d.slice(3, 6);
  if (d.length > 6) out += "-" + d.slice(6, 10);
  return out;
}

function cellConfigFor(fieldName) {
  switch (fieldName) {
    case "pib":
      return { kind: "digits", maxDigits: 9 };
    case "registration_number":
      return { kind: "digits", maxDigits: 8 };
    case "contact_phone":
      return { kind: "phone" };
    default:
      return { kind: "text" };
  }
}

/* ==========================================================================
   Glavni tok.
   ========================================================================== */

const els = {};
function cacheEls() {
  [
    "screen-loading", "screen-global-intro", "screen-session-overview", "screen-instructions",
    "screen-task", "screen-gap", "screen-end", "screen-end-title", "screen-end-message", "btn-end-next",
    "global-intro-title", "global-intro-code-field", "global-intro-input", "global-intro-error", "global-intro-display",
    "global-intro-demo-note", "global-intro-device-note", "btn-global-intro-next", "btn-global-intro-demo",
    "session-overview-summary", "session-overview-list", "btn-session-overview-next",
    "session-overview-n-selector", "select-session-n",
    "instructions-position", "instructions-title", "instructions-lines", "instructions-selectors",
    "btn-start", "select-n",
    "progress-bar", "counter-item", "counter-cell", "window-indicator",
    "stage", "window-document", "document-mount", "encoding-countdown",
    "btn-encoding-ready", "btn-switch-to-sheet",
    "window-spreadsheet", "sheet-header-row", "sheet-input-row",
    "btn-switch-to-doc", "btn-submit-item",
    "download-note",
  ].forEach((id) => { els[id] = document.getElementById(id); });
}

// showScreen sada dolazi iz core/block.js.

// parseParams sada dolazi iz core/params.js (parseParamsCore).
function parseParams() {
  return parseParamsCore();
}

const TASK_ID = "S2";

async function main() {
  cacheEls();
  const params = parseParams();
  const embedded = isEmbedded();
  const isPracticeParam = !!params.practice;

  let instructionsData;
  try {
    instructionsData = await fetchInstructions(`../../data/instructions.json`);
  } catch (err) {
    showFatal(`Greska pri ucitavanju uputstva: ${err.message}`);
    return;
  }

  // Integracija sesije (core/intro.js): SAMO server rezim, van vezbe, i
  // SAMO kad URL NE daje eksplicitan participant -- pilot/debag preko
  // eksplicitnog URL parametra ostaje pojedinacan zadatak, nepromenjeno
  // (uputstvo: "Zadrzi mogucnost pokretanja pojedinacnog zadatka...").
  const orchestrated = !embedded && !isPracticeParam && !params.participant;
  let session = null;
  let order = DEFAULT_TASK_ORDER;

  if (orchestrated) {
    let codesData;
    try {
      codesData = await fetchParticipantCodes(`../../data/participant_codes.json`);
    } catch (err) {
      showFatal(`Greska pri ucitavanju liste sifri: ${err.message}`);
      return;
    }
    const orch = await runSessionOrchestration(TASK_ID, codesData, instructionsData);
    if (orch.redirected) return;
    session = orch.session;
    order = session.order;
    params.participant = session.code;
    params.n = session.n;
    params.demo = session.isDemo;
  } else if (!isPracticeParam) {
    // Pojedinacan zadatak (pilot/debag preko eksplicitnog URL parametra,
    // ili ugradjeni/demo rezim) -- isti tok kao pre integracije sesije.
    let codeValidator = null;
    let demoOnly = false;
    if (!embedded) {
      let codesData;
      try {
        codesData = await fetchParticipantCodes(`../../data/participant_codes.json`);
      } catch (err) {
        showFatal(`Greska pri ucitavanju liste sifri: ${err.message}`);
        return;
      }
      codeValidator = createCodeValidator(codesData);
      demoOnly = !!codesData.demo_only;
    }
    const known = params.participant || (embedded ? EMBEDDED_DEFAULTS.participant : null);
    const codeResult = await runGlobalIntroScreen(known, codeValidator, { demoOnly });
    params.participant = codeResult.code;
    await runSessionOverviewScreen(instructionsData);
  }

  const resolved = resolveParamsCore(params, embedded, EMBEDDED_DEFAULTS, {});
  const isPractice = resolved.isPractice, participantId = resolved.participantId, isDemo = resolved.isDemo;
  let n = resolved.n;

  let itemsData, itemsHash, companiesHash;
  try {
    ({ itemsData, itemsHash, companiesHash } = await fetchItemsAndHashes());
  } catch (err) {
    showFatal(`Greska pri ucitavanju podataka: ${err.message}`);
    return;
  }

  const wsOk = await Logger.connect();

  let items;
  if (isPractice) {
    n = itemsData.practice.n_fields;
    items = itemsData.practice.items;
  }

  // Vezba i server rezim: N je vec poznat, pa se sesijsko zaglavlje salje
  // SADA, pre uvodnih ekrana -- da instructions_shown/dismissed zavrse u
  // ispravnom fajlu (core/intro.js, napomena na vrhu tog fajla). Ugradjeni
  // (demo) rezim ceka do posle ekrana uputstva, gde se N tek bira (izbornik).
  const earlySend = isPractice || !embedded;
  if (earlySend) {
    measureWhileVisible("task", () => computeRoiAndSendHeader({
      participantId, variant: isPractice ? "practice" : "S2", n, itemsHash, companiesHash, seed: itemsData.seed,
      ...sessionLogFields(session, order, TASK_ID),
    }));
  }

  await runInstructionsScreen(order, instructionsData, TASK_ID, {
    showSelectors: embedded && !isPractice,
    isPractice,
  });

  if (embedded && !isPractice) {
    n = parseInt(els["select-n"].value, 10);
    computeRoiAndSendHeader({
      participantId, variant: "S2", n, itemsHash, companiesHash, seed: itemsData.seed,
      ...sessionLogFields(session, order, TASK_ID),
    });
  }

  if (!isPractice) {
    items = itemsData.participants[participantId][String(n)];
    if (isDemo) items = items.slice(0, DEMO_ITEM_CAP);
  }

  applyEndScreenText(order, instructionsData, TASK_ID, isPractice, session);

  showScreen("task");
  await runBlock({
    participantId,
    variant: isPractice ? "practice" : "S2",
    n,
    items,
    isPractice,
    isDemo,
    itemsHash,
    companiesHash,
    seed: itemsData.seed,
  });
  clearSessionStateIfFinished(session, order, TASK_ID);
}

// showFatal sada dolazi iz core/screen.js.

/* ==========================================================================
   Zastita od kopiranja/lepljenja (sekcija 5). Prozor A: user-select:none
   (CSS) + presretanje copy/cut/contextmenu/dragstart + Ctrl+C/X/A/Insert.
   Prozor B: paste u celije se poništava. Bez poruke ispitaniku (samo log).
   installCopyProtection/installPasteProtection sada dolaze iz
   core/guard.js; blockRefreshKeys iz core/screen.js. currentWindowName i
   currentItemRef ostaju ovde -- nisu samo guard-specificni (koristi ih i
   switchWindow()/F2 logika), pa bi njihovo premestanje u jezgro uvelo
   nepotrebnu spregu.
   ========================================================================== */

let currentWindowName = "document"; // koristi se da Ctrl+C/X/A ogranicimo na Prozor A

// Deljena, mutabilna referenca na "trenutnu stavku" (azurira se na pocetku
// svakog runItem()). Copy/paste zastita se instalira JEDNOM po bloku (ne po
// stavci), pa mora da cita indeks stavke iz zajednickog mesta koje se menja
// tokom bloka, ne iz snapshot-a uzetog u trenutku instaliranja.
const currentItemRef = { current: 0 };

let copyProtectionInstalled = false;

/* ==========================================================================
   Jedan blok. Petlja/prelazi/kraj bloka su u core/block.js
   (runBlockCore) -- ovde ostaje samo ono sto NIJE bilo identicno sa S3:
   F5/F11/Ctrl+R i kopi-zastita (S2 ih ima, S3 trenutno nema -- ne prenosi
   se u jezgro da S3 ne bi tiho dobio zastitu koju danas nema, uputstvo
   sekcija 8), sesijsko zaglavlje (potpuno scenario-specifican sadrzaj), i
   adapter ka runItem() (jezgro uvek zove itemRunner(item, index, n) sa
   tacno tri argumenta; S2-ov runItem() ionako prima samo ta tri).
   ========================================================================== */

async function runBlock(ctx) {
  // computeRoiAndSendHeader(ctx) se vise NE zove ovde -- pozivalac (main())
  // ga sada zove eksplicitno, RANO (server/vezba) ili KASNO (ugradjeni
  // rezim), pre uvodnih ekrana iz core/intro.js. Videti napomenu u main().
  window.addEventListener("keydown", blockRefreshKeys);
  if (!copyProtectionInstalled) {
    installCopyProtection(els["window-document"], () => currentWindowName === "document", () => currentItemRef.current);
    copyProtectionInstalled = true;
  }

  await runBlockCore(ctx, (item, itemIndex, n) => runItem(item, itemIndex, n));

  window.removeEventListener("keydown", blockRefreshKeys);
}

// onResizeAbort sada dolazi iz core/screen.js.

function computeRoiAndSendHeader(ctx) {
  // #stage ima fiksnu CSS velicinu (sekcija 9) -- oba prozora je popunjavaju
  // u ISTOM fizickom regionu ekrana (samo jedan je vidljiv u datom trenutku),
  // pa im je ROI namerno identican pravougaonik. Nema potrebe za "priming"
  // renderovanjem pre merenja (za razliku od s3-demo), jer velicina ne
  // zavisi od sadrzaja.
  const stageRect = els["stage"].getBoundingClientRect();

  Logger.sessionHeader({
    participant_id: ctx.participantId,
    // Jedino sankcionisano dodavanje polja u log format ovim refaktorom
    // (uputstvo, sekcija 8): scenario je uvek "S2" za ovaj projekat, cak i
    // za vezbu (koja i dalje testira S2 mehaniku) -- razlikuje se od
    // "variant" koji dole i dalje razlikuje "S2"/"practice".
    scenario: "S2",
    variant: ctx.variant,
    n_fields: ctx.n,
    seed: ctx.seed,
    items_hash: ctx.itemsHash,
    companies_hash: ctx.companiesHash,
    // Integracija sesije, tacka 5 odobrenja: session_id + redosled/pozicija
    // zadatka + redni broj posete -- videti core/intro.js sessionLogFields().
    session_id: ctx.session_id,
    task_order: ctx.task_order,
    task_position: ctx.task_position,
    visit_number: ctx.visit_number,
    screen: { w: window.screen.width, h: window.screen.height },
    roi: { document: roiRectArray(stageRect), spreadsheet: roiRectArray(stageRect) },
    encoding_base_ms: ENCODING_BASE_MS,
    encoding_ms_per_field: ENCODING_MS_PER_FIELD,
    encoding_min_ms: ENCODING_MIN_MS,
    switch_delay_ms: SWITCH_DELAY_MS,
    max_switches_per_item: MAX_SWITCHES_PER_ITEM,
    item_gap_ms: ITEM_GAP_MS,
    block_duration_ms: BLOCK_DURATION_MS,
    enforce_cell_deadline: ENFORCE_CELL_DEADLINE,
    t0_wall: new Date().toISOString(),
    t0_perf: round1(performance.now()),
  });
}

function updateProgress(fraction, itemIndex, itemTotal) {
  const pct = Math.max(0, Math.min(1, fraction)) * 100;
  els["progress-bar"].style.width = `${pct}%`;
  els["counter-item"].textContent = `Stavka ${itemIndex}`;
  els["counter-cell"].textContent = "";
}

function updateWindowIndicator(name) {
  els["window-indicator"].innerHTML = name === "document"
    ? `Prozor: <strong>DOKUMENT</strong> &middot; <span class="switch-hint">F2 za tabelu</span>`
    : `Prozor: <strong>TABELA</strong> &middot; <span class="switch-hint">F2 za dokument</span>`;
}

/* ==========================================================================
   Prebacivanje izmedju prozora (sekcija 4.1, 4.3). Svako prebacivanje --
   automatsko (kraj kodiranja) ili na zahtev ispitanika (F2 / dugme) --
   prolazi kroz isti prazan ekran od SWITCH_DELAY_MS, tokom kog je unos
   onemogucen (oba .window-pane dobijaju .hidden).
   ========================================================================== */

let switching = false;

// Vreme dolaska u Prozor A (performance.now()), postavlja se kad
// switchWindow zavrsi prelazak SA to="document", i cita/nulira kad se
// sledeci put prelazi SA to="spreadsheet" -- razlika je koliko je stavka
// provela u Prozoru A tom posetom (document_stay_ms nize). null van
// Prozora A (nema aktivnog boravka za merenje).
let documentArrivedAt = null;

// fromField: samo za logovanje (sekcija 8 dopune) -- field_name celije koja
// je imala fokus neposredno pre odlaska u Prozor A (null kad se ne moze
// odrediti, npr. automatski prelazak posle kodiranja). Omogucava da se u
// analizi izracuna "broj povrataka pre nego sto je svako pojedinacno polje
// uneto": svaki povratak se pripisuje polju koje je u tom trenutku bilo
// aktivno u tabeli.
async function switchWindow(to, reason, fromField) {
  if (switching) return;
  switching = true;

  els["window-document"].classList.add("hidden");
  els["window-spreadsheet"].classList.add("hidden");

  const start = performance.now();
  await waitFor(SWITCH_DELAY_MS);
  const delayActual = performance.now() - start;

  currentWindowName = to;
  els[to === "document" ? "window-document" : "window-spreadsheet"].classList.remove("hidden");
  updateWindowIndicator(to);

  // Trajanje boravka u Prozoru A koji se upravo zavrsava (samo kad se
  // ODLAZI iz Prozora A, tj. to="spreadsheet"). null ako nije bilo aktivnog
  // boravka za merenje (npr. prvi, automatski prelazak na tabelu posle
  // kodiranja -- tada se dokument uopste nije posecivao u ovoj stavci).
  let documentStayMs = null;
  if (to === "document") {
    documentArrivedAt = performance.now();
  } else if (documentArrivedAt !== null) {
    documentStayMs = round1(performance.now() - documentArrivedAt);
    documentArrivedAt = null;
  }

  Logger.log({
    event: "window_switch",
    item: currentItemRef.current,
    to,
    reason,
    from_field: fromField ?? null,
    delay_actual_ms: round1(delayActual),
    document_stay_ms: documentStayMs,
  });

  switching = false;
}

/* ==========================================================================
   Jedna stavka: kodiranje pa unos.
   ========================================================================== */

// runEncodingWait sada dolazi iz core/block.js.

async function runItem(item, itemIndex, n) {
  currentItemRef.current = itemIndex;
  Logger.log({ event: "item_start", item: itemIndex, item_id: item.item_id, company_id: item.company_id });

  const fieldNames = checkFieldNamesFor(item);

  // --- Faza kodiranja: Prozor A prinudno vidljiv, bez troska prebacivanja
  // (nije "prebacivanje" iz drugog prozora -- prethodni ekran je bio prazan
  // razmak izmedju stavki). ---
  els["window-spreadsheet"].classList.add("hidden");
  renderDocument(els["document-mount"], GLOBAL_TEMPLATE, item.document);
  highlightDocumentFields(fieldNames, true);
  els["btn-switch-to-sheet"].classList.add("hidden"); // nema smisla vraćati se u praznu tabelu tokom kodiranja
  els["encoding-countdown"].classList.remove("hidden");
  els["btn-encoding-ready"].classList.remove("hidden");
  els["btn-encoding-ready"].disabled = true; // do ENCODING_MIN_MS
  els["window-document"].classList.remove("hidden");
  currentWindowName = "document";
  updateWindowIndicator("document");

  const encodingDuration = ENCODING_BASE_MS + n * ENCODING_MS_PER_FIELD;
  Logger.log({ event: "encoding_start", item: itemIndex, item_id: item.item_id, duration_ms: encodingDuration });

  const { mode: encodingMode, actualMs: encodingActualMs } = await runEncodingWait(
    encodingDuration, ENCODING_MIN_MS, els["btn-encoding-ready"], els["encoding-countdown"],
  );

  Logger.log({
    event: "encoding_end",
    item: itemIndex,
    item_id: item.item_id,
    encoding_actual_ms: encodingActualMs,
    mode: encodingMode,
  });
  if (sessionAborted) return;

  els["encoding-countdown"].classList.add("hidden");
  els["btn-encoding-ready"].classList.add("hidden");
  highlightDocumentFields(fieldNames, false);

  // --- Faza unosa: automatski prelazak na Prozor B (sa troskom, sekcija 4.3). ---
  await switchWindow("spreadsheet", "auto");
  if (sessionAborted) return;

  await runEntryPhase(item, itemIndex, fieldNames);

  Logger.log({ event: "item_end", item: itemIndex, item_id: item.item_id });
}

let GLOBAL_TEMPLATE = "";

/* ==========================================================================
   Faza unosa jedne stavke: tabela (Prozor B), F2 prebacivanje nazad na
   dokument (Prozor A, sa SVIM obelezenim poljima), potvrda kad su sve
   celije popunjene.
   ========================================================================== */

async function runEntryPhase(item, itemIndex, fieldNames) {
  const fieldsInOrder = item.fields.slice().sort((a, b) => a.order - b.order);

  els["sheet-header-row"].innerHTML = "";
  els["sheet-input-row"].innerHTML = "";

  const cells = []; // { input, fieldName, focusTime, first, last, count, backspaces }
  let lastFocusedIndex = 0;

  for (const field of fieldsInOrder) {
    const th = document.createElement("th");
    th.textContent = FIELD_LABELS[field.field_name] || field.field_name;
    els["sheet-header-row"].appendChild(th);

    const td = document.createElement("td");
    const input = document.createElement("input");
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    const cfg = cellConfigFor(field.field_name);
    if (cfg.kind === "digits") input.maxLength = cfg.maxDigits;
    if (cfg.kind === "phone") input.maxLength = 12; // 06X/XXX-XXXX

    const cellState = { input, fieldName: field.field_name, focusTime: null, first: null, last: null, count: 0, backspaces: 0 };
    cells.push(cellState);
    const cellIndex = cells.length - 1;

    input.addEventListener("focus", () => {
      lastFocusedIndex = cellIndex;
      // Reset po SVAKOM fokusiranju, ne samo prvom -- celija se moze
      // ponovo posetiti (nema ogranicenja na povratak), a first/last se
      // mere u odnosu na OVO fokusiranje (sekcija 8). Bez reseta bi
      // first_keystroke_ms na drugoj poseti mogao da ispadne negativan
      // (stari first iz prve posete, nova focusTime posle njega).
      cellState.focusTime = performance.now();
      cellState.first = null;
      cellState.last = null;
      cellState.count = 0;
      cellState.backspaces = 0;
      els["counter-cell"].textContent = `Polje ${cellIndex + 1}/${fieldsInOrder.length}`;
      Logger.log({
        event: "cell_focus",
        item: itemIndex,
        item_id: item.item_id,
        field: cellIndex + 1,
        field_name: field.field_name,
        weight_class: field.weight_class,
      });
    });

    input.addEventListener("keydown", (e) => {
      const key = e.key;
      const isContentKey = key.length === 1 || key === "Backspace" || key === "Delete";
      if (isContentKey) {
        const now = performance.now();
        if (cellState.first === null) cellState.first = now;
        cellState.last = now;
        cellState.count += 1;
        if (key === "Backspace" || key === "Delete") cellState.backspaces += 1;
      }
      if (key === "Enter") {
        e.preventDefault();
        const next = cellIndex + 1 < cells.length ? cells[cellIndex + 1].input : els["btn-submit-item"];
        next.focus();
      }
    });

    input.addEventListener("input", () => {
      if (cfg.kind === "digits") {
        input.value = digitsOnly(input.value).slice(0, cfg.maxDigits);
      } else if (cfg.kind === "phone") {
        input.value = formatPhoneProgressive(digitsOnly(input.value));
      }
      updateSubmitEnabled(cells);
    });

    input.addEventListener("blur", () => emitCellSubmitted(item, itemIndex, cellState, cellIndex, false));

    installPasteProtection(input, field.field_name, () => currentItemRef.current);

    td.appendChild(input);
    els["sheet-input-row"].appendChild(td);
  }

  updateWindowIndicator("spreadsheet");
  cells[0].input.focus();

  const submitBtn = els["btn-submit-item"];
  submitBtn.disabled = true;

  // Broj povrataka u Prozor A U OVOJ STAVCI (reason="user"). Koristi se za
  // MAX_SWITCHES_PER_ITEM (nije aktivno dok je konstanta null -- povratak
  // je tada neogranicen, F2 i dugme su uvek omoguceni) i ulazi u
  // window_switch/switch_denied dogadjaje.
  let switchesThisItem = 0;

  const f2Handler = (e) => {
    if (e.key !== "F2") return;
    e.preventDefault();
    if (switching) return;
    if (currentWindowName === "spreadsheet") {
      lastFocusedIndex = cells.findIndex((c) => c.input === document.activeElement);
      if (lastFocusedIndex < 0) lastFocusedIndex = 0;
      goToDocument();
    } else {
      goToSheet();
    }
  };
  window.addEventListener("keydown", f2Handler);

  async function goToDocument() {
    // Kad je granica dostignuta (samo ako je MAX_SWITCHES_PER_ITEM broj, ne
    // null): dalji pokusaji se odbijaju i beleze kao switch_denied (mera
    // pritiska na radnu memoriju, treba da raste sa N). Nema vise vizuelne
    // signalizacije ovde (brojac/flash uklonjeni iz UI-ja) -- ako se
    // granica ponovo aktivira, to se projektuje iznova.
    if (MAX_SWITCHES_PER_ITEM !== null && switchesThisItem >= MAX_SWITCHES_PER_ITEM) {
      Logger.log({
        event: "switch_denied",
        item: currentItemRef.current,
        from_field: fieldsInOrder[lastFocusedIndex]?.field_name ?? null,
        switches_so_far: switchesThisItem,
        max_switches_per_item: MAX_SWITCHES_PER_ITEM,
      });
      return;
    }
    switchesThisItem += 1;
    highlightDocumentFields(fieldNames, true); // SVA obelezena polja, ne samo trenutno (sekcija 4.2)
    els["btn-switch-to-sheet"].classList.remove("hidden");
    await switchWindow("document", "user", fieldsInOrder[lastFocusedIndex]?.field_name ?? null);
  }

  async function goToSheet() {
    await switchWindow("spreadsheet", "user");
    if (!sessionAborted) cells[lastFocusedIndex].input.focus();
  }

  els["btn-switch-to-sheet"].onclick = () => { if (!switching) goToSheet(); };
  els["btn-switch-to-doc"].onclick = () => {
    if (switching) return;
    lastFocusedIndex = cells.findIndex((c) => c.input === document.activeElement);
    if (lastFocusedIndex < 0) lastFocusedIndex = 0;
    goToDocument();
  };

  await new Promise((resolve) => {
    submitBtn.onclick = () => {
      if (submitBtn.disabled) return;
      // Tacno JEDAN cell_submitted po polju dobija is_final:true, ovde, za
      // SVE celije (ne samo onu koja je jos fokusirana) -- bez obzira da
      // li je poslednji blur vec poslao isti sadrzaj. Time je broj
      // is_final:true dogadjaja po stavci uvek tacno N, nezavisno od toga
      // koliko je puta svaka celija posecena (sekcija 8: "is_final: true,
      // gde je true samo poslednji unos u tu celiju u toj stavci").
      cells.forEach((c, idx) => emitCellSubmitted(item, itemIndex, c, idx, true));
      resolve();
    };
  });

  window.removeEventListener("keydown", f2Handler);
  els["btn-switch-to-sheet"].classList.add("hidden");
}

function updateSubmitEnabled(cells) {
  const allFilled = cells.every((c) => c.input.value.trim().length > 0);
  els["btn-submit-item"].disabled = !allFilled;
}

// Beleze se SVA napustanja celije (svaki blur), is_final:false za sve osim
// tacno jednog po polju -- onog poslatog iz submitBtn.onclick pri potvrdi
// stavke, koji nosi is_final:true i predstavlja konacnu vrednost. Bez
// izostavljanja/dedupe: cak i ako se poslednji blur i finalni dogadjaj
// poklapaju po sadrzaju, oba se salju (razlikuju se po is_final), jer u
// trenutku blur-a jos nije poznato da li ce celija ponovo biti posecena.
function emitCellSubmitted(item, itemIndex, cellState, cellIndex, isFinal) {
  const value = cellState.input.value;
  Logger.log({
    event: "cell_submitted",
    item: itemIndex,
    item_id: item.item_id,
    field: cellIndex + 1,
    field_name: cellState.fieldName,
    entered_value: value,
    is_final: isFinal,
    first_keystroke_ms: cellState.focusTime !== null && cellState.first !== null ? round1(cellState.first - cellState.focusTime) : null,
    last_keystroke_ms: cellState.focusTime !== null && cellState.last !== null ? round1(cellState.last - cellState.focusTime) : null,
    keystroke_count: cellState.count,
    backspace_count: cellState.backspaces,
  });
}

/* ==========================================================================
   Init.
   ========================================================================== */

window.addEventListener("DOMContentLoaded", async () => {
  cacheEls();
  try {
    GLOBAL_TEMPLATE = await fetchTemplate();
  } catch (e) {
    showFatal(`Greska pri ucitavanju sablona dokumenta: ${e.message}`);
    return;
  }
  main();
});
