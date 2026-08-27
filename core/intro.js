"use strict";

/* ==========================================================================
   core/intro.js -- ekrani ZAJEDNICKI za S1/S2/S3, van bloka (pocetni ekran,
   pregled sesije, uputstvo pre zadatka, ekran kraja), PLUS orkestracija
   koja spaja sve tri aplikacije u JEDNU sesiju ("Integrisi tri aplikacije
   u jednu sesiju"): sifra se unosi i redosled zadataka se odredjuje SAMO
   JEDNOM, na prvom zadatku; ostala dva se dobijaju automatskom navigacijom
   (window.location.href), bez rucnog otvaranja adresa.

   PILOT/DEBAG OSTAJE NEPROMENJEN: ako URL eksplicitno daje ?participant=...
   (ili je ugradjena/samostalna verzija, ili je ?practice=1), orkestracija
   se PRESKACE potpuno -- stranica se ponasa kao pojedinacan zadatak, tacno
   kao pre ove izmene. Orkestracija se aktivira ISKLJUCIVO kad je server
   rezim I nema eksplicitnog participant parametra u URL-u.

   Redosled zadataka van orkestracije (pilot/embedded/vezba) je uvek
   DEFAULT_TASK_ORDER (S1,S2,S3) -- "Zadrzi mogucnost pokretanja
   pojedinacnog zadatka..." i "Za DEMO i vezbu ostaje slobodan izbor".
   Unutar orkestracije, redosled dolazi iz dodele (generate_participant_codes.py
   "assignments"), kontrabalansirane po sifri.

   STUDY_TITLE je PLACEHOLDER -- prava specifikacija ne daje naziv studije.

   Vezano za tajming slanja sesijskog zaglavlja (Logger.sessionHeader):
   instructions_shown/instructions_dismissed MORAJU stici POSLE zaglavlja
   da bi server upisao ih u ISPRAVAN fajl (core/logger.js: fajl se otvara
   tek na "session" red). Za server rezim i vezbu (n je vec poznato) svaki
   scenario salje zaglavlje RANO, pre ovih ekrana. Ugradjeni (demo) rezim
   ostaje na STAROM, kasnom mestu (N/varijanta se biraju tek na ekranu
   uputstva) -- ogranicenje samo demo rezima, ne stvarnog snimanja.

   TACKA 5 (odobreno: tri povezana loga sa istim session_id, ne jedan log
   po sesiji): session_id se generise TACNO JEDNOM, pri stvaranju nove
   sesije (makeSessionId, izveden iz sifre + vreme pocetka), i putuje kroz
   sacuvano stanje -- oporavak posle prekida ga PREUZIMA, ne generise
   nov. Svaki od tri session reda dobija session_id, redosled zadataka
   dodeljen tom ispitaniku, redni broj OVOG zadatka u sesiji (task_position
   -- merni podatak, ne samo evidencija) i redni broj posete (visit_number)
   preko sessionLogFields(), koju svaki scenario poziva u svom
   computeRoiAndSendHeader(ctx).
   ========================================================================== */

const STUDY_TITLE = "Merenje kognitivnog opterećenja u kancelarijskim zadacima";

// Putanje OD KORENA SAJTA -- ispravne bez obzira sa koje od tri stranice se
// navigira, JER sve tri sad moraju biti posluzene sa ISTOG porekla (isti
// host:port) da bi sessionStorage/IndexedDB uopste mogli da prezive
// navigaciju medju njima (server.py root-fix, videti README-ove). "Koren
// sajta" NIJE nuzno koren porekla (window.location.origin): kad je sajt
// hostovan pod pod-putanjom (npr. GitHub Pages projektna stranica,
// https://user.github.io/eeg-tasks/...), sve tri stranice i dalje dele
// zajednicko poreklo (isto sto treba za sessionStorage/IndexedDB), ali
// apsolutna putanja mora da ukljuci i tu pod-putanju -- zato se ovde
// koriste putanje RELATIVNE NA KOREN SAJTA, a siteBasePath() (ispod)
// odredjuje taj koren u trenutku navigacije, iz trenutne URL putanje.
const TASK_URLS = { S1: "/app/index.html", S2: "/s2-demo/app/index.html", S3: "/s3-demo/app/index.html" };
const DEFAULT_TASK_ORDER = ["S1", "S2", "S3"];

// Nalazi koren sajta iz trenutne putanje, trazeci poznati marker (svaka od
// tri stranice zivi pod /app/, /s2-demo/app/ ili /s3-demo/app/ u odnosu na
// taj koren). Bez pod-putanje (lokalni server.py, koren sajta == koren
// porekla) vraca "". Ako marker nije pronadjen (nepoznata putanja), vraca
// "" -- redirectToTask() se tada ponasa kao ranije (apsolutno od porekla).
// VAZAN REDOSLED: /s2-demo/app/ i /s3-demo/app/ MORAJU se proveriti PRE
// generickog /app/, jer obe sadrze "/app/" kao podnisku -- generican marker
// bi se inace pogresno poklopio unutar njih (npr. "/s3-demo/app/..." bi
// "/app/" prepoznao na indeksu 8, odsekavsi "/s3-demo" kao lazni koren).
function siteBasePath() {
  const path = window.location.pathname;
  for (const marker of ["/s2-demo/app/", "/s3-demo/app/", "/app/"]) {
    const idx = path.indexOf(marker);
    if (idx >= 0) return path.slice(0, idx);
  }
  return "";
}

const SESSION_STORAGE_KEY = "eeg_session_state";
const SESSION_DB_NAME = "eeg_sessions";
const SESSION_DB_STORE = "sessions";

async function fetchInstructions(path) {
  if (typeof window.__INSTRUCTIONS_EMBEDDED__ !== "undefined") {
    return window.__INSTRUCTIONS_EMBEDDED__;
  }
  const res = await fetch(path);
  if (!res.ok) throw new Error(`ne mogu da ucitam ${path}: ${res.status}`);
  return res.json();
}

/* order: niz task_id-jeva OVE sesije (dodeljen ili DEFAULT_TASK_ORDER) --
   "Zadatak X od Y" se sada racuna iz NJEGA, ne iz fiksnog redosleda u
   instructions.json (koji ostaje izvor NAZIVA/TEKSTA, ne redosleda). */
function taskPosition(order, instructionsData, taskId) {
  const idx = order.indexOf(taskId);
  if (idx < 0) throw new Error(`task_id ${taskId} nije u redosledu [${order}]`);
  const task = instructionsData.tasks.find((t) => t.id === taskId);
  if (!task) throw new Error(`nepoznat task_id u instructions.json: ${taskId}`);
  return { position: idx + 1, total: order.length, task };
}

/* ---- Sifre ispitanika + dodela redosleda (generate_participant_codes.py) ----
   Lista sifri/dodela se NE ugradjuje u samostalnu (demo) verziju -- namerno:
   objavljivanje spiska pravih sifri (i njihovog redosleda) u javno
   preuzimljivom demo fajlu bi ponistilo svrhu sifri kao (slabe) kontrole
   pristupa. Zato je provera dostupna SAMO u server rezimu.

   "DEMO" je REZERVISANA sifra (generate_participant_codes.py je nikad ne
   generise -- sadrzi "O") i UVEK je prihvacena bez provere liste, bez
   broja sesije i bez dodele redosleda (uvek DEFAULT_TASK_ORDER). */
async function fetchParticipantCodes(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`ne mogu da ucitam ${path}: ${res.status}`);
  return res.json();
}

function createCodeValidator(codesData) {
  const validCodes = new Set(codesData.codes);
  return async function validate(code) {
    if (code === "DEMO") return { valid: true, sessionNumber: null };
    if (!validCodes.has(code)) {
      return { valid: false, error: "Nepoznata šifra. Obratite se istraživaču." };
    }
    let sessionNumber = null;
    try {
      const r = await fetch(`/api/session-count?code=${encodeURIComponent(code)}`);
      if (r.ok) {
        const j = await r.json();
        sessionNumber = j.count + 1;
      }
    } catch (e) {
      // best-effort -- odsustvo broja sesije ne sprecava nastavak
    }
    return { valid: true, sessionNumber };
  };
}

function taskOrderForCode(codesData, code) {
  return (codesData.assignments && codesData.assignments[code]) || DEFAULT_TASK_ORDER;
}

// session_id: stabilan za CELU posetu (izveden iz sifre + vreme pocetka),
// ne po zadatku -- generise se TACNO JEDNOM, pri stvaranju nove sesije
// (runSessionOrchestration), i posle toga samo putuje kroz sacuvano stanje
// (session.sessionId), ukljucujuci oporavak posle prekida (session =
// recovered preuzima ga neizmenjenog, nikad se ne generise ponovo).
function makeSessionId(code, startedAt) {
  const compact = new Date(startedAt).toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  return `${code}_${compact}`;
}

// Polja koja idu u SVAKI od tri (povezana) session reda -- integracija
// sesije, odobrena tacka 5 + tacke 1-3 iz odobrenja: session_id, sifra
// (participant_id vec postoji u zaglavlju -- ne duplira se ovde), redosled
// zadataka DODELJEN TOM ISPITANIKU, redni broj OVOG zadatka u sesiji
// (task_position -- merni podatak, ne samo evidencija: zamor/uvezbavanje
// rastu kroz sesiju), i redni broj posete (visit_number, 1/2/3). Van
// orkestracije (pilot/embedded/vezba, session===null) task_order/
// task_position i dalje idu (DEFAULT_TASK_ORDER, radi doslednosti sa
// "Zadatak X od Y" na ekranu), ali session_id/visit_number ostaju null --
// pojedinacan zadatak nije deo prave, brojane posete.
function sessionLogFields(session, order, taskId) {
  return {
    session_id: session ? session.sessionId : null,
    task_order: order,
    task_position: order.indexOf(taskId) + 1,
    visit_number: session ? session.sessionNumber : null,
  };
}

/* ---- Ekran 1: pocetni ekran ----
   participantKnown: vec poznata sifra (URL parametar, ili podrazumevana
   vrednost za demo) -- PREPOPUNJENA i odmah proverena (jedan klik manje).
   validator: async (code) => {valid, sessionNumber?, error?}, ili null za
   ugradjeni (demo) rezim (bez provere liste, bez broja sesije).
   Vraca Promise<{code, sessionNumber}> -- sifra je VELIKIM SLOVIMA. */
function runGlobalIntroScreen(participantKnown, validator, opts) {
  opts = opts || {};
  els["global-intro-title"].textContent = STUDY_TITLE;

  // Prikazna (GitHub Pages) instanca: provera prave sifre ne moze da radi
  // jer se stvarna data/participant_codes.json namerno nikad ne objavljuje
  // (sadrzi dodele ispitanicima). Umesto polja za unos i poruke "nepoznata
  // sifra", nudi se direktno dugme koje pokrece sesiju sa sifrom DEMO.
  if (opts.demoOnly) {
    els["global-intro-code-field"].classList.add("hidden");
    els["global-intro-error"].classList.add("hidden");
    els["global-intro-display"].classList.add("hidden");
    els["global-intro-demo-note"].classList.remove("hidden");
    els["btn-global-intro-next"].classList.add("hidden");
    els["btn-global-intro-demo"].classList.remove("hidden");
    showScreen("global-intro");
    return new Promise((resolve) => {
      els["btn-global-intro-demo"].onclick = () => resolve({ code: "DEMO", sessionNumber: null });
    });
  }

  return new Promise((resolve) => {
    let confirmed = null; // {code, sessionNumber}

    function showEntry(prefill, errorMsg) {
      confirmed = null;
      els["global-intro-input"].classList.remove("hidden");
      els["global-intro-display"].classList.add("hidden");
      els["btn-global-intro-next"].textContent = "Dalje";
      els["global-intro-input"].value = prefill || "";
      els["global-intro-error"].textContent = errorMsg || "";
      els["global-intro-error"].classList.toggle("hidden", !errorMsg);
      els["global-intro-input"].focus();
    }

    function showConfirm(code, sessionNumber) {
      confirmed = { code, sessionNumber };
      els["global-intro-input"].classList.add("hidden");
      els["global-intro-error"].classList.add("hidden");
      els["global-intro-display"].classList.remove("hidden");
      els["global-intro-display"].textContent = sessionNumber != null
        ? `Šifra: ${code} — sesija ${sessionNumber} od 3`
        : `Šifra: ${code}`;
      els["btn-global-intro-next"].textContent = "Potvrdi";
    }

    async function attempt(rawCode) {
      const code = (rawCode || "").trim().toUpperCase();
      if (!code) return;
      if (!validator) { showConfirm(code, null); return; } // ugradjeni rezim -- bez provere liste
      const result = await validator(code);
      if (!result.valid) { showEntry(code, result.error); return; }
      showConfirm(code, result.sessionNumber);
    }

    els["btn-global-intro-next"].onclick = () => {
      if (confirmed) { resolve(confirmed); return; }
      attempt(els["global-intro-input"].value);
    };

    showScreen("global-intro");
    showEntry(participantKnown, null);
    if (participantKnown) attempt(participantKnown);
  });
}

/* ---- Ekran 2: pregled sesije ---- */
function runSessionOverviewScreen(instructionsData) {
  els["session-overview-summary"].textContent = instructionsData.session_summary;
  els["session-overview-list"].innerHTML = "";
  for (const t of instructionsData.tasks) {
    const li = document.createElement("li");
    li.textContent = t.name;
    els["session-overview-list"].appendChild(li);
  }
  showScreen("session-overview");
  return new Promise((resolve) => {
    els["btn-session-overview-next"].onclick = () => resolve();
  });
}

/* ---- Ekran 3: uputstvo pre zadatka ----
   Loguje instructions_shown pri prikazu i instructions_dismissed (sa
   dwell_ms) pri kliku na "Počni" -- van bloka. */
function runInstructionsScreen(order, instructionsData, taskId, opts) {
  opts = opts || {};
  const { position, total, task } = taskPosition(order, instructionsData, taskId);
  els["instructions-title"].textContent = task.name;
  els["instructions-position"].textContent = opts.isPractice ? "Vežba" : `Zadatak ${position} od ${total}`;
  els["instructions-lines"].innerHTML = "";
  for (const line of task.lines) {
    const li = document.createElement("li");
    li.textContent = line;
    els["instructions-lines"].appendChild(li);
  }
  els["instructions-selectors"].classList.toggle("hidden", !opts.showSelectors);

  showScreen("instructions");
  const shownAt = performance.now();
  Logger.log({ event: "instructions_shown", task_id: taskId });

  return new Promise((resolve) => {
    els["btn-start"].onclick = () => {
      const dwellMs = round1(performance.now() - shownAt);
      Logger.log({ event: "instructions_dismissed", task_id: taskId, dwell_ms: dwellMs });
      resolve();
    };
  });
}

/* ---- Ekran kraja (isti #screen-end div, sadrzaj i dugme se menjaju) ----
   Postavlja se PRE runBlock() da izbegne i najkraci bljesak podrazumevanog
   teksta -- core/block.js interno zove showScreen("end") na kraju bloka.
   session: {code, order, completed} kad je stranica deo orkestrirane
   sesije (core/intro.js: runSessionOrchestration) -- "Dalje" dugme tad
   stvarno navigira i belezi zavrsetak. Van orkestracije (pilot/embedded/
   vezba) session je null -- poruka je samo informativna, bez dugmeta,
   jer nema sesijsko stanje koje bi navigacija azurirala. */
function applyEndScreenText(order, instructionsData, taskId, isPractice, session) {
  els["btn-end-next"].classList.add("hidden");
  els["btn-end-next"].onclick = null;

  if (isPractice) {
    els["screen-end-title"].textContent = "Kraj vežbe";
    els["screen-end-message"].textContent = "Hvala. Vežba je završena.";
    return;
  }
  const { position, total } = taskPosition(order, instructionsData, taskId);
  if (position === total) {
    els["screen-end-title"].textContent = "Kraj sesije";
    els["screen-end-message"].textContent = "Hvala Vam na učešću. Sesija je završena.";
    return;
  }

  const nextId = order[position]; // position je 1-bazirano, sledeci je na tom indeksu
  const next = instructionsData.tasks.find((t) => t.id === nextId);
  els["screen-end-title"].textContent = "Kraj zadatka";

  if (session) {
    els["screen-end-message"].textContent = "Ovaj zadatak je završen.";
    els["btn-end-next"].classList.remove("hidden");
    els["btn-end-next"].textContent = `Dalje: ${next.name}`;
    els["btn-end-next"].onclick = () => {
      session.completed.push(taskId);
      saveSessionState(session);
      redirectToTask(nextId, session.n, session.variant, session.isDemo);
    };
  } else {
    // Pojedinacan (pilot/debag) zadatak van orkestracije -- samo
    // informativno, nema sesijsko stanje da bi dugme imalo sta da azurira.
    els["screen-end-message"].textContent = `Ovaj zadatak je završen. Sledeći zadatak: ${next.name}.`;
  }
}

/* ==========================================================================
   Integracija sesije: sifra + redosled zadataka + navigacija se resavaju
   JEDNOM (na prvom zadatku), a ne rucnim otvaranjem tri adrese.
   ========================================================================== */

// n/variant putuju kroz sesijsko stanje (session.n/session.variant), ne
// kroz DEFAULT_TASK_ORDER -- sva tri zadatka jedne sesije koriste ISTI N
// (nivo opterecenja te posete), pa navigacija mora da ga prenese dalje u
// URL-u (resolveParamsCore u server rezimu i dalje zahteva ?n= u URL-u
// svake stranice). variant je S3-specifican (S3a/S3b), ali se PRENOSI
// kroz S1/S2 takodje -- ako je S3 na redu docnije u redosledu, sifra se
// unosi na PRVOJ stranici sesije (moze biti S1 ili S2), koja tada mora da
// zna variant iako ga sama ne koristi, samo da bi ga prosledila dalje.
function redirectToTask(taskId, n, variant, isDemo) {
  const url = new URL(siteBasePath() + TASK_URLS[taskId], window.location.origin);
  if (n != null) url.searchParams.set("n", n);
  if (variant != null) url.searchParams.set("variant", variant);
  if (isDemo) url.searchParams.set("demo", "1");
  window.location.href = url.toString();
}

function saveSessionState(state) {
  try { sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(state)); } catch (e) {
    // privatni rezim pregledaca i sl. -- sessionStorage moze biti nedostupan
  }
  saveSessionStateToDb(state); // best-effort, ne cekamo (ne blokira tok)
}

function loadSessionStateFromTab() {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function openSessionDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") { reject(new Error("indexedDB nedostupan")); return; }
    const req = indexedDB.open(SESSION_DB_NAME, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(SESSION_DB_STORE, { keyPath: "code" }); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function saveSessionStateToDb(state) {
  try {
    const db = await openSessionDb();
    const tx = db.transaction(SESSION_DB_STORE, "readwrite");
    tx.objectStore(SESSION_DB_STORE).put(state);
  } catch (e) {
    // best-effort -- IndexedDB nedostupan ne prekida tok (sessionStorage je
    // vec upisan iznad, dovoljno za nastavak DOK je kartica otvorena)
  }
}

async function loadSessionStateFromDb(code) {
  try {
    const db = await openSessionDb();
    return await new Promise((resolve) => {
      const tx = db.transaction(SESSION_DB_STORE, "readonly");
      const req = tx.objectStore(SESSION_DB_STORE).get(code);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  } catch (e) {
    return null;
  }
}

/* runSessionOrchestration(taskId, codesData, instructionsData): poziva se
   SAMO kad je server rezim, van vezbe, i URL NE daje eksplicitan
   ?participant= (pilot/debag uslov ostaje van ove funkcije, u main()
   svakog scenarija).

   n/variant se citaju OVDE, direktno iz location.search -- ne preko
   parseParamsCore() pozivaoca, jer S1/S2 uopste ne prijavljuju "variant"
   kao poznat kljuc (samo S3 to radi preko extraKeys), a bas TA stranica
   moze biti prva u redosledu sesije i mora da prosledi variant dalje i za
   S3, iako ga sama ne koristi.

   Ekran 2 (pregled sesije) je NAMERNO deo OVE funkcije, ne pozivaoca --
   mora se prikazati PRE provere "da li je OVAJ zadatak stvarno prvi u
   redosledu", inace bi se, kad prvi zadatak NIJE bas taj sa kog je sesija
   pokrenuta ("app/index.html u korenu" je uvek POLAZNA tacka, tacka 1, ali
   stvarno prvi zadatak po kontrabalansiranom redosledu moze biti bilo koji
   od tri), stranica preusmerila PRE nego sto je pregled ikad prikazan.

   Vraca:
     {redirected: true} -- navigacija je vec pokrenuta (window.location.href),
       pozivalac MORA odmah da prekine main() (return), ne nastavljati dalje.
     {redirected: false, session} -- nastaviti NA OVOJ stranici sa
       session.code/session.order (ekran uputstva je sledeci korak
       pozivaoca; pregled sesije je, ako je bio potreban, vec prikazan
       ovde). */
async function runSessionOrchestration(taskId, codesData, instructionsData) {
  let session = loadSessionStateFromTab();

  if (session) {
    // Ista kartica, sesija vec u toku (stigli smo ovde navigacijom sa
    // prethodnog zadatka) -- ekrani 1/2 su vec odradjeni ranije.
    const nextTaskId = session.order[session.completed.length];
    if (nextTaskId !== taskId) {
      redirectToTask(nextTaskId, session.n, session.variant, session.isDemo);
      return { redirected: true };
    }
    return { redirected: false, session };
  }

  // Nema stanja u ovoj kartici -- prvi zadatak nove sesije, ili je kartica
  // zatvorena i ponovo otvorena usred sesije (oporavak preko IndexedDB,
  // kljuc je sifra koju ispitanik ponovo unese ovde).
  const urlParams = new URLSearchParams(location.search);
  const requestedN = urlParams.has("n") ? parseInt(urlParams.get("n"), 10) : null;
  const requestedVariant = urlParams.get("variant");
  const requestedDemo = urlParams.get("demo") === "1";

  const codeValidator = createCodeValidator(codesData);
  const { code, sessionNumber } = await runGlobalIntroScreen(null, codeValidator, { demoOnly: !!codesData.demo_only });

  const recovered = await loadSessionStateFromDb(code);
  if (recovered && recovered.completed.length < recovered.order.length) {
    session = recovered;
  } else {
    // n/variant dolaze iz URL-a SAMO pri stvaranju nove sesije (prvi
    // zadatak) -- sva tri zadatka te sesije ih posle dele preko
    // session.n/session.variant, preneseno kroz redirectToTask(), ne
    // ponovnim citanjem URL-a svake stranice.
    const startedAt = Date.now();
    session = {
      code, sessionNumber, order: taskOrderForCode(codesData, code),
      n: requestedN, variant: requestedVariant, isDemo: requestedDemo,
      completed: [], startedAt, sessionId: makeSessionId(code, startedAt),
    };
  }
  saveSessionState(session);

  await runSessionOverviewScreen(instructionsData);

  const nextTaskId = session.order[session.completed.length];
  if (nextTaskId !== taskId) {
    redirectToTask(nextTaskId, session.n, session.variant, session.isDemo);
    return { redirected: true };
  }

  return { redirected: false, session };
}
