"use strict";

/* ==========================================================================
   core/intro.js -- ekrani ZAJEDNICKI za S1/S2/S3, van bloka: pocetni ekran
   (sifra ispitanika), pregled sesije (spisak zadataka), uputstvo pre
   zadatka (sadrzaj iz data/instructions.json, ista struktura u sva tri),
   i tekst za ekran kraja (kraj zadatka naspram kraj sesije).

   Redosled zadataka u sesiji = redosled niza "tasks" u instructions.json --
   JEDAN izvor istine i za tekst i za "Zadatak X od Y" (nema odvojene liste
   za redosled). Svaki scenario zove ove funkcije iz svog main(), sa
   sopstvenim taskId-jem ("S1"/"S2"/"S3") i sopstvenim els/showScreen.

   STUDY_TITLE je PLACEHOLDER -- prava specifikacija ne daje naziv studije,
   zameniti pre snimanja pravih podataka.

   Vezano za tajming slanja sesijskog zaglavlja (Logger.sessionHeader):
   instructions_shown/instructions_dismissed MORAJU stici POSLE zaglavlja
   da bi server upisao ih u ISPRAVAN fajl (core/logger.js: fajl se otvara
   tek na "session" red, dogadjaji pre toga zavrsavaju u UNKNOWN_*.jsonl).
   Za server rezim i vezbu (n je vec poznato -- iz URL-a odn. iz
   itemsData.practice) svaki scenario salje zaglavlje RANO, pre ovih
   ekrana. Za ugradjeni (demo) rezim N/varijanta se BIRAJU tek na ekranu
   uputstva (izbornik), pa zaglavlje ostaje na STAROM, kasnom mestu (tik
   pred runBlock, kao i pre ove izmene) -- posledica je da u demo/samostalnoj
   verziji ovi dogadjaji mogu prethoditi "session" redu u preuzetom fajlu.
   Prihvaceno kao ogranicenje samo demo rezima, ne stvarnog snimanja.
   ========================================================================== */

const STUDY_TITLE = "Merenje kognitivnog opterećenja u kancelarijskim zadacima";

async function fetchInstructions(path) {
  if (typeof window.__INSTRUCTIONS_EMBEDDED__ !== "undefined") {
    return window.__INSTRUCTIONS_EMBEDDED__;
  }
  const res = await fetch(path);
  if (!res.ok) throw new Error(`ne mogu da ucitam ${path}: ${res.status}`);
  return res.json();
}

function taskPosition(instructionsData, taskId) {
  const idx = instructionsData.tasks.findIndex((t) => t.id === taskId);
  if (idx < 0) throw new Error(`nepoznat task_id u instructions.json: ${taskId}`);
  return { position: idx + 1, total: instructionsData.tasks.length, task: instructionsData.tasks[idx] };
}

function isLastTask(instructionsData, taskId) {
  const { position, total } = taskPosition(instructionsData, taskId);
  return position === total;
}

/* ---- Ekran 1: pocetni ekran ----
   participantKnown: vec poznata sifra (URL parametar, ili podrazumevana
   vrednost za demo) -- prikazuje se READ-ONLY. Ako je null/prazno,
   prikazuje se prazno polje za unos. Vraca Promise<string>. */
function runGlobalIntroScreen(participantKnown) {
  els["global-intro-title"].textContent = STUDY_TITLE;
  const known = !!participantKnown;
  els["global-intro-display"].textContent = participantKnown || "";
  els["global-intro-display"].classList.toggle("hidden", !known);
  els["global-intro-input"].classList.toggle("hidden", known);
  if (!known) els["global-intro-input"].value = "";

  showScreen("global-intro");
  if (!known) els["global-intro-input"].focus();

  return new Promise((resolve) => {
    els["btn-global-intro-next"].onclick = () => {
      const value = known ? participantKnown : els["global-intro-input"].value.trim();
      if (!value) return; // prazno polje -- ne pomeramo se dalje
      resolve(value);
    };
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
   dwell_ms = vreme zadrzavanja na ekranu) pri kliku na "Počni" -- van
   bloka (uputstvo, korak "Dodaj uvodne ekrane"): "vreme čitanja uputstva
   je podatak, ne mrtvo vreme".
   opts.showSelectors: ostavlja #instructions-selectors vidljiv (ugradjeni
   demo rezim, gde N/varijanta jos nisu konacni) -- pozivalac je vec
   popunio taj markup (select-n/select-variant) pre poziva.
   opts.isPractice: naslov pozicije postaje "Vežba" umesto "Zadatak X od Y"
   (vezba nema poziciju u sesiji). */
function runInstructionsScreen(instructionsData, taskId, opts) {
  opts = opts || {};
  const { position, total, task } = taskPosition(instructionsData, taskId);
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

/* ---- Tekst ekrana kraja (isti #screen-end div, sadrzaj se menja) ----
   Postavlja se PRE runBlock() (ne posle) da izbegne i najkraci bljesak
   podrazumevanog teksta -- core/block.js interno zove showScreen("end")
   na kraju bloka, sadrzaj mora vec biti tacan u tom trenutku. */
function applyEndScreenText(instructionsData, taskId, isPractice) {
  if (isPractice) {
    els["screen-end-title"].textContent = "Kraj vežbe";
    els["screen-end-message"].textContent = "Hvala. Vežba je završena.";
    return;
  }
  const { position, total } = taskPosition(instructionsData, taskId);
  if (position === total) {
    els["screen-end-title"].textContent = "Kraj sesije";
    els["screen-end-message"].textContent = "Hvala Vam na učešću. Sesija je završena.";
  } else {
    const next = instructionsData.tasks[position]; // position je 1-bazirano, sledeci je na tom indeksu
    els["screen-end-title"].textContent = "Kraj zadatka";
    els["screen-end-message"].textContent = `Ovaj zadatak je završen. Sledeći zadatak: ${next.name}.`;
  }
}
