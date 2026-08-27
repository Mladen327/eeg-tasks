"use strict";

/* ==========================================================================
   core/block.js -- trajanje bloka, redosled stavki, prelaz izmedju stavki,
   dovrsavanje stavke koja je u toku kada vreme istekne, ekran kraja bloka.

   Premesteno bez izmene ponasanja: petlja, provera BLOCK_DURATION_MS,
   ITEM_GAP_MS prelaz, block_start/block_end logovanje i preuzimanje fajla
   na kraju su bili bajt-identicni izmedju S2 i S3. Dve stvari NISU bile
   identicne pa su ostale van ovog fajla (poziva ih scenario, ne jezgro):

   1. Poziv runItem() -- S2 ga zove sa (item, index, n), S3 sa
      (item, index, n, variant, suggestionsByItem, isPractice). Zato
      runBlockCore prima `itemRunner(item, itemIndex, n)` kao parametar --
      scenario ga daje kao zatvaranje (closure) koje samo prosledi svoje
      dodatne argumente svom sopstvenom runItem-u. Petlja u jezgru uvek
      poziva itemRunner sa TACNO ta tri argumenta, bez obzira sta scenario
      radi s njima.

   2. Postavljanje pre/posle bloka koje NIJE bilo identicno: S2 dodaje
      blockRefreshKeys/installCopyProtection (F5/F11/Ctrl+R zastita,
      kopiranje), S3 dodaje "priming" renderovanje ugovora pre merenja
      ROI-ja. Oba ostaju u scenario wrapperu OKO poziva runBlockCore, ne
      unutra -- originalno da S3 ne bi slucajno dobio F5/kopi-zastitu koju
      tada nije imao (uputstvo, sekcija 8: bez funkcionalne izmene, vazilo
      je za sam refaktor). To pravilo vise ne vazi kao razlog da razlika
      ostane: posle zavrsetka refaktora S3 (i S1) su dobili obe zastite
      (korak "Uskladi S1 sa S2/S3", tacka 5) -- ali svaki scenario i dalje
      sam poziva blockRefreshKeys/installCopyProtection u svom wrapperu, ne
      jezgro, jer S3-ova kopi-zastita je ogranicena na read-only elemente
      (razlicit skup ciljnih elemenata od S1/S2), pa poziv ostaje
      scenario-specifican bez obzira sto ga sad sva tri koriste.
      computeRoiAndSendHeader(ctx) je iz istog razloga ostao u scenario
      wrapperu (potpuno scenario-specifican sadrzaj sesijskog zaglavlja),
      poziva se PRE runBlockCore.

   sessionAborted i showScreen() su ovde jer su bili bajt-identicni i
   direktno sluze petlji/prelazima. updateProgress() NIJE ovde -- razlikuje
   se za jedan DOM id (S2: #counter-cell, S3: #counter-field), pa ostaje
   scenario-specifican (referenciran ovde kao slobodna promenljiva,
   razresava se u trenutku poziva). Isto i za onResizeAbort, koji ostaje u
   scenariju do koraka 5 (core/screen.js) -- ovde se samo kaci/skida kao
   resize listener, referenciran po imenu.
   ========================================================================== */

let sessionAborted = false;

// Upravljanje trajanjem faze kodiranja: donja granica minMs (dugme
// Spreman/F2 ne rade pre nje), gornja granica encodingDuration (automatski
// prelazak na isteku ako ispitanik ne pritisne nista). Vraca
// {mode: "user"|"auto", actualMs}.
//
// PREMESTENO IZ s2-demo/app/task.js (bilo je jedino tamo, S3 ovu
// mogucnost nikad nije dobio -- dormantno/nekaceno, isti obrazac kao
// MAX_SWITCHES_PER_ITEM u core/screen.js). SPEC_S1_demo.md (uputstvo za
// Scenario 1) pretpostavlja da je ovo VEC deo jezgra ("Upravljanje
// trajanjem preuzima se iz jezgra") -- to u trenutku pisanja tog uputstva
// NIJE bilo tacno (raniji refaktor, korak 4, nije ovo zapravo izvukao iz
// S2 iako ga je sekcija 4 uputstva za refaktor jezgra vec najavljivala).
// Popravljeno ovde, pri izradi S1 (korak 4 njegovog uputstva), umesto da
// se S1 napravi sa sopstvenom trecom kopijom.
//
// Generalizacija u odnosu na original je SAMO parametrizacija DOM
// elemenata (readyBtn, countdownEl) i praga (minMs) umesto hardkodovanih
// els["btn-encoding-ready"]/els["encoding-countdown"]/ENCODING_MIN_MS --
// S2-ov poziv (core/block.js poziva se sa els["btn-encoding-ready"],
// els["encoding-countdown"], ENCODING_MIN_MS) ostaje bihevioralno
// identican originalu.
async function runEncodingWait(encodingDuration, minMs, readyBtn, countdownEl) {
  const start = performance.now();
  let minElapsed = false;

  const minTimer = setTimeout(() => {
    minElapsed = true;
    readyBtn.disabled = false;
  }, minMs);

  let cleanupReady = () => {};
  const readyPromise = new Promise((resolve) => {
    const tryResolve = () => { if (minElapsed) resolve(); };
    const onClick = () => tryResolve();
    const onKey = (e) => { if (e.key === "F2") { e.preventDefault(); tryResolve(); } };
    readyBtn.addEventListener("click", onClick);
    window.addEventListener("keydown", onKey);
    cleanupReady = () => {
      readyBtn.removeEventListener("click", onClick);
      window.removeEventListener("keydown", onKey);
    };
  });

  const timeoutPromise = waitFor(encodingDuration, (remaining) => {
    countdownEl.textContent = `Preostalo: ${Math.ceil(remaining / 1000)} s`;
  });

  const mode = await Promise.race([
    readyPromise.then(() => "user"),
    timeoutPromise.then(() => "auto"),
  ]);

  clearTimeout(minTimer);
  cleanupReady();

  return { mode, actualMs: round1(performance.now() - start) };
}

function showScreen(name) {
  // "global-intro"/"session-overview"/"instructions" su dodati uz uvodne
  // ekrane zajednicke za sva tri scenarija (core/intro.js); "intro" je
  // uklonjen -- taj ekran je preimenovan u "instructions" (isti markap,
  // sad citljiviji sadrzaj iz data/instructions.json). "end" ostaje isti
  // div za kraj zadatka I kraj sesije -- samo mu se tekst menja
  // (core/intro.js: applyEndScreenText), nema posebnog "task-end" ekrana.
  ["loading", "global-intro", "session-overview", "instructions", "task", "gap", "end"].forEach((n) => {
    els[`screen-${n}`].classList.toggle("hidden", n !== name);
  });
}

async function runBlockCore(ctx, itemRunner) {
  const { participantId, variant, n, items, isDemo } = ctx;

  window.addEventListener("resize", onResizeAbort);

  Logger.log({ event: "block_start", n_fields: n, variant, planned_items: items.length });

  const blockStart = performance.now();
  let completed = 0;

  for (let i = 0; i < items.length; i++) {
    if (sessionAborted) break;
    if (!isDemo && performance.now() - blockStart >= BLOCK_DURATION_MS) break;

    updateProgress((performance.now() - blockStart) / BLOCK_DURATION_MS, i + 1, items.length);
    await itemRunner(items[i], i + 1, n);
    completed++;

    if (sessionAborted) break;
    showScreen("gap");
    await waitFor(ITEM_GAP_MS);
    if (!sessionAborted) showScreen("task");
  }

  window.removeEventListener("resize", onResizeAbort);

  Logger.log({ event: "block_end", items_completed: completed, elapsed_ms: round1(performance.now() - blockStart) });

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const filename = `${participantId}_${variant}_${n}_${timestamp}.jsonl`;
  const downloaded = Logger.downloadIfNeeded(filename);
  els["download-note"].classList.toggle("hidden", !downloaded);

  showScreen("end");
}
