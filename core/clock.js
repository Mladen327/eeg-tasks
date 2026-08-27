"use strict";

/* ==========================================================================
   core/clock.js -- merenje vremena, zajednicko za sve scenarije.

   performance.now() je JEDINI izvor merenja proteklog vremena; zidni sat
   (Date/ISO) se koristi samo za grubu sinhronizaciju (t_wall polja u logu,
   core/logger.js), nikad za merenje trajanja. Zakazivanje preko
   setTimeout/requestAnimationFrame je dozvoljeno, ali funkcije ovde UVEK
   vracaju STVARNO protekli interval (performance.now() razlika), ne
   nominalno trazeno trajanje -- to je vrednost koju scenario upisuje u log
   (npr. encoding_actual_ms u S2, latency_actual_ms sugestije u S3,
   delay_actual_ms pri prebacivanju prozora u S2).

   Premesteno bez izmene ponasanja iz app/task.js oba scenarija (bili su
   bajt-identicni za waitFor/round1; raceWithTimeout je postojao samo u
   S3, ovde ostaje dostupan svima).
   ========================================================================== */

function round1(x) { return Math.round(x * 10) / 10; }

// Ceka durationMs, pozivajuci onTick(preostalo_ms, proteklo_ms) na svakom
// animacionom frejmu (npr. za odbrojavanje na ekranu). Resolve-uje se sa
// stvarno proteklim vremenom.
function waitFor(durationMs, onTick) {
  return new Promise((resolve) => {
    const start = performance.now();
    function frame(now) {
      const elapsed = now - start;
      if (onTick) onTick(Math.max(0, durationMs - elapsed), elapsed);
      if (elapsed >= durationMs) resolve(elapsed);
      else requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });
}

// Trka izmedju date promise-a i vremenskog ograničenja od durationMs.
// Vraca { timedOut, value, elapsed } -- elapsed je uvek stvarno proteklo
// vreme, bez obzira ko je "pobedio" trku.
function raceWithTimeout(promise, durationMs) {
  return new Promise((resolve) => {
    let done = false;
    const start = performance.now();
    promise.then((value) => {
      if (!done) { done = true; resolve({ timedOut: false, value, elapsed: performance.now() - start }); }
    });
    waitFor(durationMs).then(() => {
      if (!done) { done = true; resolve({ timedOut: true, value: null, elapsed: performance.now() - start }); }
    });
  });
}
