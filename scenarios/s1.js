"use strict";

/* ==========================================================================
   Scenario 1 -- prekucavanje poslovne korespondencije (SPEC_S1_demo.md).

   Gradi se NA core/, bez dupliranog koda -- svi mehanizmi zajednicki sa
   S2/S3 (merenje vremena, log, tok bloka, ROI/F5-zastita/prekid sesije,
   kopi-zastita, URL parametri, upravljanje trajanjem faze kodiranja)
   dolaze odatle nepromenjeni, isti obrazac kao s2-demo/app/task.js i
   s3-demo/app/task.js. Ovaj fajl sadrzi ISKLJUCIVO ono sto je S1-u
   sopstveno: prikaz N rečenica u fazi kodiranja, N polja za kucanje u fazi
   unosa, i ponovni uvid bez ogranicenja.

   NEMA stavka-firma vezu (SPEC_S1_demo.md 3.3, uputstvo za spajanje
   jezgra korak D): items_S1.json ne sadrzi company_id nigde, pa ovaj fajl
   ne racuna hes za companies.json niti ga ucitava.
   ========================================================================== */

/* --------------------------------------------------------------------------
   Konstante tajminga (SPEC_S1_demo.md sekcija 4/6). Ne menjati u toku sesije.
   Trajanje faze kodiranja = ENCODING_BASE_MS + n * ENCODING_MS_PER_ITEM.
   -------------------------------------------------------------------------- */
const ENCODING_BASE_MS      = 3000;
const ENCODING_MS_PER_ITEM  = 4000;
const ENCODING_MIN_MS       = 3000;

// ITEM_GAP_MS/BLOCK_DURATION_MS NISU propisani u SPEC_S1_demo.md (koje
// vrednosti da koristi runBlockCore) -- preuzete su iste vrednosti kao
// S2/S3, radi doslednosti opsteg toka bloka medju sva tri scenarija; to je
// ODLUKA, ne prepis eksplicitnog zahteva iz uputstva.
const ITEM_GAP_MS           = 1500;
const BLOCK_DURATION_MS     = 180000;

const DEMO_ITEM_CAP = 4;
const WS_PORT = 8767; // razlicit od s2-demo (8766) i s3-demo (8765), sva tri mogu da rade istovremeno

const EMBEDDED_DEFAULTS = { participant: "DEMO", n: 5, demo: true };

/* ==========================================================================
   Ucitavanje podataka. Samo items_S1.json -- nema sablona, nema
   companies.json (nema stavka-firma vezu).
   ========================================================================== */

function isEmbedded() {
  return isEmbeddedCore("__S1_EMBEDDED__");
}

async function fetchItemsAndHash() {
  if (isEmbedded()) {
    const emb = window.__S1_EMBEDDED__;
    return { itemsData: emb.items, itemsHash: emb.items_hash };
  }
  const itemsFetch = await fetchAndHash(`../data/items_S1.json`);
  return { itemsData: JSON.parse(itemsFetch.text), itemsHash: itemsFetch.hash };
}

/* ==========================================================================
   Glavni tok.
   ========================================================================== */

const els = {};
function cacheEls() {
  [
    "screen-loading", "screen-global-intro", "screen-session-overview", "screen-instructions",
    "screen-task", "screen-gap", "screen-end", "screen-end-title", "screen-end-message", "btn-end-next",
    "global-intro-title", "global-intro-input", "global-intro-error", "global-intro-display", "btn-global-intro-next",
    "session-overview-summary", "session-overview-list", "btn-session-overview-next",
    "instructions-position", "instructions-title", "instructions-lines", "instructions-selectors",
    "btn-start", "select-n",
    "progress-bar", "counter-item", "counter-phase",
    "stage", "encoding-view", "encoding-list", "encoding-countdown", "btn-encoding-ready",
    "entry-view", "entry-list", "btn-peek-open", "btn-submit-item",
    "peek-overlay", "peek-list", "btn-peek-close",
    "download-note",
  ].forEach((id) => { els[id] = document.getElementById(id); });
}

// showScreen sada dolazi iz core/block.js.

// parseParams sada dolazi iz core/params.js (parseParamsCore).
function parseParams() {
  return parseParamsCore();
}

const TASK_ID = "S1";

async function main() {
  cacheEls();
  const params = parseParams();
  const embedded = isEmbedded();
  const isPracticeParam = !!params.practice;

  let instructionsData;
  try {
    instructionsData = await fetchInstructions(`../data/instructions.json`);
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
      codesData = await fetchParticipantCodes(`../data/participant_codes.json`);
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
  } else if (!isPracticeParam) {
    // Pojedinacan zadatak (pilot/debag preko eksplicitnog URL parametra,
    // ili ugradjeni/demo rezim) -- isti tok kao pre integracije sesije.
    let codeValidator = null;
    if (!embedded) {
      let codesData;
      try {
        codesData = await fetchParticipantCodes(`../data/participant_codes.json`);
      } catch (err) {
        showFatal(`Greska pri ucitavanju liste sifri: ${err.message}`);
        return;
      }
      codeValidator = createCodeValidator(codesData);
    }
    const known = params.participant || (embedded ? EMBEDDED_DEFAULTS.participant : null);
    const codeResult = await runGlobalIntroScreen(known, codeValidator);
    params.participant = codeResult.code;
    await runSessionOverviewScreen(instructionsData);
  }

  const resolved = resolveParamsCore(params, embedded, EMBEDDED_DEFAULTS, {
    fatalMessage: "Nedostaju ili su neispravni URL parametri. Ocekivano: ?participant=P07&n=5",
  });
  if (resolved.fatal) {
    showFatal(resolved.fatal);
    return;
  }
  const isPractice = resolved.isPractice, participantId = resolved.participantId, isDemo = resolved.isDemo;
  let n = resolved.n;

  let itemsData, itemsHash;
  try {
    ({ itemsData, itemsHash } = await fetchItemsAndHash());
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

  // Vezba i server rezim: N je vec poznat (itemsData.practice.n_fields
  // odn. URL/sesijsko stanje), pa se sesijsko zaglavlje salje SADA, pre
  // uvodnih ekrana -- da instructions_shown/dismissed zavrse u ispravnom
  // fajlu (core/intro.js, napomena na vrhu tog fajla). Ugradjeni (demo)
  // rezim ceka do posle ekrana uputstva, gde se N tek bira (izbornik).
  const earlySend = isPractice || !embedded;
  if (earlySend) {
    measureWhileVisible("task", () => computeRoiAndSendHeader({
      participantId, variant: isPractice ? "practice" : "S1", n, itemsHash, seed: itemsData.seed,
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
      participantId, variant: "S1", n, itemsHash, seed: itemsData.seed,
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
    variant: isPractice ? "practice" : "S1",
    n,
    items,
    isPractice,
    isDemo,
    itemsHash,
    seed: itemsData.seed,
  });
}

// showFatal sada dolazi iz core/screen.js.

/* ==========================================================================
   Zastita od kopiranja/lepljenja (SPEC_S1_demo.md sekcija 10: "core/guard.js
   to vec resava"). Za razliku od S2 (dva prozora, aktivnost zavisi od
   koje je vidljivo), S1 ima JEDAN prozor -- kopi-zastita je aktivna tokom
   CELOG bloka (rečenice se vide i u fazi kodiranja i pri ponovnom uvidu,
   nema trenutka kad bi bila bezopasno iskljuciti je). Paste-zastita se
   kaci na SVAKO polje za unos.
   ========================================================================== */

const currentItemRef = { current: 0 };
let copyProtectionInstalled = false;

/* ==========================================================================
   Jedan blok. Petlja/prelazi/kraj bloka su u core/block.js (runBlockCore).
   ========================================================================== */

async function runBlock(ctx) {
  // computeRoiAndSendHeader(ctx) se vise NE zove ovde -- pozivalac (main())
  // ga sada zove eksplicitno, RANO (server/vezba) ili KASNO (ugradjeni
  // rezim), pre uvodnih ekrana iz core/intro.js. Videti napomenu u main().
  window.addEventListener("keydown", blockRefreshKeys);
  if (!copyProtectionInstalled) {
    installCopyProtection(els["stage"], () => true, () => currentItemRef.current);
    copyProtectionInstalled = true;
  }

  await runBlockCore(ctx, (item, itemIndex, n) => runItem(item, itemIndex, n));

  window.removeEventListener("keydown", blockRefreshKeys);
}

// onResizeAbort sada dolazi iz core/screen.js.

function computeRoiAndSendHeader(ctx) {
  // #stage ima fiksnu CSS velicinu; faza kodiranja, faza unosa i ponovni
  // uvid je sve popunjavaju u ISTOM fizickom regionu ekrana (samo jedan
  // prikaz vidljiv u datom trenutku), pa je ROI jedan te isti pravougaonik
  // za sve -- isti obrazac kao S2 (core/screen.js, computeRoiAndSendHeader).
  const stageRect = els["stage"].getBoundingClientRect();

  Logger.sessionHeader({
    participant_id: ctx.participantId,
    scenario: "S1",
    variant: ctx.variant,
    n_fields: ctx.n,
    seed: ctx.seed,
    items_hash: ctx.itemsHash,
    // Integracija sesije, tacka 5 odobrenja: session_id + redosled/pozicija
    // zadatka + redni broj posete -- videti core/intro.js sessionLogFields().
    session_id: ctx.session_id,
    task_order: ctx.task_order,
    task_position: ctx.task_position,
    visit_number: ctx.visit_number,
    screen: { w: window.screen.width, h: window.screen.height },
    roi: { stage: roiRectArray(stageRect) },
    encoding_base_ms: ENCODING_BASE_MS,
    encoding_ms_per_item: ENCODING_MS_PER_ITEM,
    encoding_min_ms: ENCODING_MIN_MS,
    item_gap_ms: ITEM_GAP_MS,
    block_duration_ms: BLOCK_DURATION_MS,
    t0_wall: new Date().toISOString(),
    t0_perf: round1(performance.now()),
  });
}

function updateProgress(fraction, itemIndex, itemTotal) {
  const pct = Math.max(0, Math.min(1, fraction)) * 100;
  els["progress-bar"].style.width = `${pct}%`;
  els["counter-item"].textContent = `Stavka ${itemIndex}`;
  els["counter-phase"].textContent = "";
}

/* ==========================================================================
   Jedna stavka: kodiranje pa unos.
   ========================================================================== */

function renderSentenceListInto(listEl, sentences) {
  listEl.innerHTML = "";
  for (const s of sentences) {
    const li = document.createElement("li");
    li.textContent = s.text;
    listEl.appendChild(li);
  }
}

function clearMount(el) {
  el.innerHTML = "";
}

async function runItem(item, itemIndex, n) {
  currentItemRef.current = itemIndex;
  Logger.log({ event: "item_start", item: itemIndex, item_id: item.item_id });

  // --- Faza kodiranja ---
  els["entry-view"].classList.add("hidden");
  els["peek-overlay"].classList.add("hidden");
  els["btn-peek-open"].classList.add("hidden");
  renderSentenceListInto(els["encoding-list"], item.sentences);
  els["encoding-countdown"].classList.remove("hidden");
  els["btn-encoding-ready"].classList.remove("hidden");
  els["btn-encoding-ready"].disabled = true; // do ENCODING_MIN_MS
  els["encoding-view"].classList.remove("hidden");
  els["counter-phase"].textContent = "Kodiranje";

  const encodingDuration = ENCODING_BASE_MS + n * ENCODING_MS_PER_ITEM;
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
  els["encoding-view"].classList.add("hidden");

  // --- Faza unosa ---
  await runEntryPhase(item, itemIndex, n);

  Logger.log({ event: "item_end", item: itemIndex, item_id: item.item_id });
}

/* ==========================================================================
   Faza unosa jedne stavke: N numerisanih polja. Navigacija/zavrsetak (korak
   "Uskladi S1 sa S2/S3"):
   - Tab UVEK kruzi kroz polja stavke, (fieldIndex+1) % N -- posle
     poslednjeg polja vraca na prvo. Nikad ne izlazi iz grupe polja.
   - Enter napreduje na sledece polje, kao ranije; na POSLEDNJEM polju vise
     NE zavrsava stavku -- pomera fokus na dugme "Potvrdi unos" (identican
     mehanizam kao S2, koje isto tako Enterom na poslednjoj celiji samo
     pomera fokus na submitBtn, bez sopstvenog rukovaoca tastature na
     dugmetu: Enter/Space na fokusiranom dugmetu su native ponasanje
     pregledaca, vec okidaju "click").
   - Stavka se zavrsava ISKLJUCIVO klikom (ili native Enter/Space
     aktivacijom) na "Potvrdi unos", omoguceno tek kad su sva polja
     popunjena (updateSubmitEnabled), isti obrazac kao S2 (btn-submit-item).
   Ponovni uvid (F2, sekcija 4 "Ponovni uvid"): NEOGRANICEN broj puta, bez
   zastoja, prikazuje SVIH N rečenica (ne samo onu koja se trenutno kuca),
   za razliku od S3-ovog PEEK_DURATION_MS tajmovanog uvida. Sada ima i
   dugme na ekranu (btn-peek-open/btn-peek-close), pored F2 -- ista
   dvodugmetna sema kao S2-ovo btn-switch-to-sheet/btn-switch-to-doc.
   ========================================================================== */

async function runEntryPhase(item, itemIndex, n) {
  els["entry-list"].innerHTML = "";
  els["counter-phase"].textContent = "Unos";

  const fields = []; // { input, sentenceIndex, focusTime, first, last, count, backspaces, intervals, lastKeyTime }

  function updateSubmitEnabled() {
    const allFilled = fields.every((f) => f.input.value.trim().length > 0);
    els["btn-submit-item"].disabled = !allFilled;
  }

  for (const s of item.sentences) {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.className = "entry-index";
    label.textContent = `${s.sentence_index}.`;
    const input = document.createElement("input");
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    li.appendChild(label);
    li.appendChild(input);
    els["entry-list"].appendChild(li);

    const fieldState = {
      input, sentenceIndex: s.sentence_index,
      focusTime: null, first: null, last: null, count: 0, backspaces: 0,
      intervals: [], lastKeyTime: null,
      // Redni broj OVOG polja-submit-a u OVOJ stavci (ne globalno) --
      // medjuverzije unosa su mera, ne sum (uputstvo: "Prosiri belezenje"),
      // pa se svaki field_submitted (i is_final:false i is_final:true) sad
      // nosi eksplicitan redosled umesto da se izvodi iz polozaja u logu.
      revisionCount: 0,
    };
    fields.push(fieldState);
    const fieldIndex = fields.length - 1;

    input.addEventListener("focus", () => {
      // Reset po SVAKOM fokusiranju (moze se ponovo posetiti posle
      // ponovnog uvida) -- isti obrazac kao S2 cell_focus.
      fieldState.focusTime = performance.now();
      fieldState.first = null;
      fieldState.last = null;
      fieldState.count = 0;
      fieldState.backspaces = 0;
      fieldState.intervals = [];
      fieldState.lastKeyTime = null;
      Logger.log({
        event: "field_focus",
        item: itemIndex,
        item_id: item.item_id,
        sentence_index: fieldState.sentenceIndex,
      });
    });

    input.addEventListener("keydown", (e) => {
      const key = e.key;
      const isContentKey = key.length === 1 || key === "Backspace" || key === "Delete";
      if (isContentKey) {
        const now = performance.now();
        if (fieldState.first === null) fieldState.first = now;
        if (fieldState.lastKeyTime !== null) fieldState.intervals.push(round1(now - fieldState.lastKeyTime));
        fieldState.lastKeyTime = now;
        fieldState.last = now;
        fieldState.count += 1;
        if (key === "Backspace" || key === "Delete") fieldState.backspaces += 1;
      }
      if (key === "Tab") {
        // Kruzi UNUTAR polja stavke -- nikad ne izlazi ka dugmetu, cak ni
        // sa poslednjeg polja (namerno drugacije od Enter-a, videti komentar
        // iznad runEntryPhase).
        e.preventDefault();
        fields[(fieldIndex + 1) % fields.length].input.focus();
      } else if (key === "Enter") {
        e.preventDefault();
        if (fieldIndex + 1 < fields.length) {
          fields[fieldIndex + 1].input.focus();
        } else {
          els["btn-submit-item"].focus();
        }
      }
    });

    input.addEventListener("input", updateSubmitEnabled);

    // Referenca cuvana na fieldState da bi finishEntry() mogao da je skine
    // PRE prisilnog is_final:true prolaza (videti finishEntry) -- inace bi
    // sakrivanje #entry-view odmah posle izazvalo jos jedan, zakasneli
    // "prirodan" blur i jos jedan is_final:false red POSLE item_end --
    // nadjeno rucnim testom (Playwright), ne u uputstvu.
    fieldState.blurHandler = () => emitFieldSubmitted(item, itemIndex, fieldState, false);
    input.addEventListener("blur", fieldState.blurHandler);

    installPasteProtection(input, `sentence_${s.sentence_index}`, () => currentItemRef.current);
  }

  els["entry-view"].classList.remove("hidden");
  els["btn-peek-open"].classList.remove("hidden");
  updateSubmitEnabled();
  fields[0].input.focus();

  /* ---- ponovni uvid (F2 ili dugme), neogranicen ---- */
  let peekOpen = false;
  let peekStart = null;
  let fieldBeforePeek = 0;

  function openPeek() {
    if (peekOpen) return;
    fieldBeforePeek = fields.findIndex((f) => f.input === document.activeElement);
    if (fieldBeforePeek < 0) fieldBeforePeek = 0;
    peekOpen = true;
    peekStart = performance.now();
    // Stanje SVIH N polja U TOM TRENUTKU, ukljucujuci polje koje je jos
    // fokusirano (jos NIJE emitovalo field_submitted za ovu verziju, jer
    // otvaranje uvida ne izaziva blur) -- bez ovoga bi upravo otkucana, jos
    // nepotvrdjena vrednost bila nevidljiva u logu (uputstvo, tacka 2).
    const fieldsSnapshot = fields.map((f) => ({ sentence_index: f.sentenceIndex, text: f.input.value }));
    Logger.log({ event: "peek_start", item: itemIndex, item_id: item.item_id, fields_snapshot: fieldsSnapshot });
    renderSentenceListInto(els["peek-list"], item.sentences);
    els["btn-peek-open"].classList.add("hidden");
    els["peek-overlay"].classList.remove("hidden");
  }

  function closePeek() {
    if (!peekOpen) return;
    peekOpen = false;
    const durationMs = round1(performance.now() - peekStart);
    clearMount(els["peek-list"]);
    els["peek-overlay"].classList.add("hidden");
    els["btn-peek-open"].classList.remove("hidden");
    Logger.log({ event: "peek_end", item: itemIndex, item_id: item.item_id, peek_duration_ms: durationMs });
    if (!sessionAborted) fields[fieldBeforePeek].input.focus();
  }

  const f2Handler = (e) => {
    if (e.key !== "F2") return;
    e.preventDefault();
    if (peekOpen) closePeek(); else openPeek();
  };
  window.addEventListener("keydown", f2Handler);
  els["btn-peek-open"].onclick = openPeek;
  els["btn-peek-close"].onclick = closePeek;

  /* ---- zavrsetak stavke: iskljucivo dugme "Potvrdi unos" (ili native
     Enter/Space dok je ono u fokusu -- videti keydownFlagHandler ispod). ---- */
  const submitBtn = els["btn-submit-item"];

  // Beleze se dva NEZAVISNA signala o tome kako je klik nastao, radi tacke
  // 5/6 uputstva ("mera nacina zavrsetka ne sme da unosi tihu netacnost"):
  // (a) MouseEvent/click.detail === 0 za tastaturom/programski okinut klik
  //     (native ponasanje pregledaca za fokusirano dugme + Enter/Space),
  //     detail >= 1 za stvaran klik misem;
  //     (b) sopstvena zastavica, postavljena SAMO u keydown na OVOM dugmetu
  //     za Enter/Space, koja ne preduzima nista sama (ne zove submit, ne
  //     preventDefault) -- samo belezi da je poslednji dogadjaj pre klika
  //     bio taster. Ako se (a) i (b) ne slazu, upisuje se mode:"unknown"
  //     umesto da se proizvoljno bira jedno -- ovo je sporedna mera i ne
  //     sme tiho da pogresi.
  let keyActivationFlag = false;
  submitBtn.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") keyActivationFlag = true;
  });

  let resolveEntry;
  const entryDone = new Promise((resolve) => { resolveEntry = resolve; });

  submitBtn.onclick = (e) => {
    if (submitBtn.disabled) return;
    const detailSaysKey = e.detail === 0;
    const flagSaysKey = keyActivationFlag;
    keyActivationFlag = false;
    let mode;
    if (detailSaysKey && flagSaysKey) mode = "key";
    else if (!detailSaysKey && !flagSaysKey) mode = "button";
    else mode = "unknown";
    finishEntry(mode);
  };

  function finishEntry(mode) {
    Logger.log({ event: "item_submitted", item: itemIndex, item_id: item.item_id, mode });
    // Skini "blur" osluskivace PRE prisilnog is_final:true prolaza --
    // poslednje polje moze jos uvek biti "poslednje fokusirano" u ovom
    // trenutku (ako je stavka zavrsena Enter/Space na dugmetu neposredno
    // posle napustanja poslednjeg polja) -- inace bi sakrivanje #entry-view
    // odmah posle ovog poziva izazvalo jos jedan, zakasneli "prirodan" blur
    // i jos jedan is_final:false red za to polje POSLE item_end.
    fields.forEach((f) => f.input.removeEventListener("blur", f.blurHandler));
    // Tacno JEDAN field_submitted po polju dobija is_final:true, ovde, za
    // SVA polja (ne samo ono jos fokusirano) -- isti obrazac kao S2
    // (submitBtn.onclick), tako da je broj is_final:true dogadjaja po
    // stavci uvek tacno N.
    fields.forEach((f) => emitFieldSubmitted(item, itemIndex, f, true));
    resolveEntry();
  }

  await entryDone;

  window.removeEventListener("keydown", f2Handler);
  if (peekOpen) {
    // Odbrambena grana za svaki slucaj (danas nedostizna: dok je uvid
    // otvoren fokus je na overlay-u/dugmetu unutra, ne na submitBtn-u, pa
    // stavka ne moze da se zavrsi dok je uvid otvoren) -- bez logovanja
    // (nema stvarnog peek_end para bez merenog trajanja koje bi imalo smisla).
    els["peek-overlay"].classList.add("hidden");
    clearMount(els["peek-list"]);
  }
  els["entry-view"].classList.add("hidden");
  els["btn-peek-open"].classList.add("hidden");
}

// Beleze se SVA napustanja polja (svaki blur), is_final:false za sve osim
// tacno jednog po polju -- onog poslatog pri zavrsetku stavke (finishEntry),
// koji nosi is_final:true i predstavlja konacnu vrednost za PRIMARNU
// tacnost (SPEC_S1_demo.md sekcija 8, pravilo preuzeto iz Scenarija 2 bez
// izmene) -- ranije verzije se NE odbacuju, "revision" ih redom obelezava
// (uputstvo: "medjuverzije unosa nisu sum nego mera").
function emitFieldSubmitted(item, itemIndex, fieldState, isFinal) {
  const text = fieldState.input.value;
  const revision = fieldState.revisionCount;
  fieldState.revisionCount += 1;
  Logger.log({
    event: "field_submitted",
    item: itemIndex,
    item_id: item.item_id,
    sentence_index: fieldState.sentenceIndex,
    entered_text: text,
    is_final: isFinal,
    revision,
    first_keystroke_ms: fieldState.focusTime !== null && fieldState.first !== null
      ? round1(fieldState.first - fieldState.focusTime) : null,
    keystroke_count: fieldState.count,
    backspace_count: fieldState.backspaces,
    total_input_ms: fieldState.first !== null && fieldState.last !== null
      ? round1(fieldState.last - fieldState.first) : null,
    inter_key_intervals: fieldState.intervals,
  });
}

/* ==========================================================================
   Init.
   ========================================================================== */

window.addEventListener("DOMContentLoaded", () => {
  main();
});
