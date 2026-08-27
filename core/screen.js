"use strict";

/* ==========================================================================
   core/screen.js -- zone interesovanja (pomocni format za session red),
   blokiranje F5/Ctrl+R/F11/Ctrl+W tokom bloka, prekid sesije i dogadjaj
   window_resized pri promeni velicine prozora.

   Premesteno bez izmene ponasanja: escapeHtml/showFatal/onResizeAbort su
   bili bajt-identicni izmedju S2 i S3. roiRectArray je izvucen iz lokalne
   `const roiRect = (r) => [...]` strelice koja je TAKODJE bila
   bajt-identicna unutar computeRoiAndSendHeader() u oba scenarija (ostatak
   te funkcije -- koji elementi se mere, sta ide u sesijsko zaglavlje --
   ostaje potpuno scenario-specifican, u svakom task.js).

   blockRefreshKeys POSTOJI OVDE (generisano/deljeno). Prvobitno ga je
   kacio samo S2 -- S3 ga nije dobijao ovim refaktorom (uputstvo, sekcija
   8: bez funkcionalne izmene). To pravilo je vazilo za sam refaktor, ne
   trajno; posle zavrsetka i provere refaktora (korak "Uskladi S1 sa
   S2/S3", tacka 5) blockRefreshKeys je aktiviran i za S1 i za S3 -- sad ga
   kace sva tri scenarija.

   "Jednaka svetlina pozadine u svim ekranima" (uputstvo) je CSS pitanje
   (--bg promenljiva u style.css svakog scenarija), nema JS logiku za
   premestanje ovde.
   ========================================================================== */

function roiRectArray(r) {
  return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
}

// Meri/salje ROI+zaglavlje PRE nego sto se #screen-<name> stvarno prikaze
// ispitaniku (uvodni ekrani iz core/intro.js sada prethode zadatku, ali
// getBoundingClientRect() zahteva da je element ULOZEN u tok stranice, ne
// samo da postoji u DOM-u -- .hidden je display:none). Bilo koji drugi
// #screen-* koji je TRENUTNO vidljiv (npr. ekran 1 uvodne sekvence, vec
// prikazan u trenutku poziva) mora se PRIVREMENO sakriti pre otkrivanja
// cilja -- inace bi oba ".screen" diva (obican blok, ne preklapaju se sami)
// istovremeno ucestvovala u toku stranice i pomerila merenje nanize.
// Sve se desava SINHRONO (nema await unutra kod pozivalaca) i vraca u
// prvobitno stanje pre povratka, bez posrednog crtanja (paint), pa
// ispitanik ovo ne vidi.
function measureWhileVisible(screenName, fn) {
  const target = els[`screen-${screenName}`];
  // Filtrirano po klasi "screen", ne po prefiksu imena -- neki cacheEls()
  // id-jevi (npr. "screen-end-title") pocinju sa "screen-" a NISU sami
  // ekrani, vec deca jednog ekrana.
  const previouslyVisible = Object.keys(els)
    .filter((k) => els[k] && els[k].classList && els[k].classList.contains("screen") && !els[k].classList.contains("hidden"));
  previouslyVisible.forEach((k) => els[k].classList.add("hidden"));
  target.classList.remove("hidden");
  const result = fn();
  target.classList.add("hidden");
  previouslyVisible.forEach((k) => els[k].classList.remove("hidden"));
  return result;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showFatal(msg) {
  showScreen("loading");
  els["screen-loading"].innerHTML = `<p>${escapeHtml(msg)}</p>`;
}

function onResizeAbort() {
  if (sessionAborted) return;
  sessionAborted = true;
  Logger.log({ event: "window_resized" });
  showFatal("Sesija je prekinuta jer je promenjena velicina prozora. Pokrenite blok ponovo.");
}

// Best-effort: neki pregledaci ne dozvoljavaju skriptovano blokiranje
// F11/Ctrl+W iz bezbednosnih razloga -- videti README.
function blockRefreshKeys(e) {
  const k = e.key;
  const ctrl = e.ctrlKey || e.metaKey;
  if (k === "F5" || (ctrl && k.toLowerCase() === "r") || k === "F11" || (ctrl && k.toLowerCase() === "w")) {
    e.preventDefault();
  }
}
