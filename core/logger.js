"use strict";

/* ==========================================================================
   core/logger.js -- format session/dogadjaj redova, WebSocket veza sa
   serverom, preuzimanje .jsonl fajla kad veza nije dostupna, i racunanje
   heša datoteka sa stimulusima.

   Premesteno bez izmene ponasanja iz app/task.js oba scenarija (Logger IIFE
   i bufToHashHex/fetchAndHash su bili funkcionalno identicni izmedju S2 i
   S3, sitne razlike su bile samo u komentarima -- zadrzana je opsirnija
   verzija). Logger sada koristi round1() iz core/clock.js (ucitan pre ovog
   fajla) umesto sopstvene privatne kopije koju je do sada imao svaki
   task.js.

   WS_PORT je i dalje SCENARIO-specificna konstanta (8765 za S3, 8766 za
   S2), definisana u task.js -- connect() je referencira kao slobodnu
   promenljivu. Ovo radi ispravno iako je core/logger.js ucitan PRE task.js:
   JS razresava slobodne promenljive u trenutku POZIVA funkcije (connect()
   se zove tek iz main(), posle DOMContentLoaded, kad je WS_PORT vec
   definisan), ne u trenutku definicije. Isto vazi za sessionHeader() koji
   prima ceo header objekat od pozivaoca (scenario odlucuje sta u njega
   ide, ukljucujuci sada obavezno polje "scenario" -- videti scenario
   task.js fajlove).

   NIJE IMPLEMENTIRANO (namerno, zapisano za kasnije, ne ovaj refaktor):
   cuvanje u IndexedDB. Ciljna struktura (uputstvo, sekcija 2/3) navodi
   IndexedDB kao deo core/logger.js odgovornosti, ali TRENUTNO nijedan
   scenario (S2 ni S3) tu mogucnost nema -- dodavanje bi bilo NOVA
   funkcionalnost, ne premestanje postojeceg koda, sto je ovim refaktorom
   izricito zabranjeno (uputstvo, sekcija 8). Kad se IndexedDB uvede (npr.
   za S1, ili kao opsta robusnost), to je zaseban zadatak sa sopstvenom
   proverom ponasanja.
   ========================================================================== */

function bufToHashHex(buf) {
  return "sha256:" + Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Hesuje SIROVE bajtove kako su stigli preko mreze (arrayBuffer, ne .text())
// -- tekst se dekodira IZ istog bafera posle heshovanja, tako da heš tacno
// odgovara bajtovima fajla na disku, bez rizika da neki medjukorak
// (normalizacija newline-ova, BOM) tiho promeni ono sto se hesuje.
async function fetchAndHash(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`ne mogu da ucitam ${path}: ${res.status}`);
  const buf = await res.arrayBuffer();
  const hash = bufToHashHex(await crypto.subtle.digest("SHA-256", buf));
  const text = new TextDecoder("utf-8").decode(buf);
  return { text, hash };
}

const Logger = (() => {
  let ws = null;
  let ready = false;
  const buffer = [];

  function connect() {
    return new Promise((resolve) => {
      // file:// (dvoklik na samostalni index.html, bez servera): nema
      // smisla ni pokusavati WebSocket, samo bi uveo nepotreban zastoj od
      // 800ms pre pocetka. Odmah pada na preuzimanje .jsonl fajla.
      if (location.protocol === "file:") { resolve(false); return; }
      let settled = false;
      const finish = (ok) => { if (!settled) { settled = true; resolve(ok); } };
      try {
        ws = new WebSocket(`ws://${location.hostname}:${WS_PORT}`);
      } catch (e) {
        finish(false);
        return;
      }
      const timer = setTimeout(() => finish(false), 800);
      ws.onopen = () => {
        // Ako je veza uspostavljena i posle isteka 800ms roka (connect()
        // se vec razresio na false), ipak salje sve dogadjaje koji su u
        // medjuvremenu baferovani, da ne bi ostali izgubljeni (ni poslati
        // preko WS-a, ni preuzeti kao fajl, jer bi "ready" izgledalo tacno).
        clearTimeout(timer);
        ready = true;
        while (buffer.length) ws.send(JSON.stringify(buffer.shift()));
        finish(true);
      };
      ws.onerror = () => { clearTimeout(timer); finish(false); };
      ws.onclose = () => { ready = false; };
    });
  }

  function sendRaw(obj) {
    if (ready && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    } else {
      buffer.push(obj);
    }
  }

  function sessionHeader(header) {
    sendRaw(Object.assign({ type: "session" }, header));
  }

  function log(event) {
    const full = Object.assign(
      { t: round1(performance.now()), t_wall: new Date().toISOString() },
      event,
    );
    sendRaw(full);
  }

  function downloadIfNeeded(filename) {
    if (ready) return false;
    const text = buffer.map((e) => JSON.stringify(e)).join("\n") + "\n";
    const blob = new Blob([text], { type: "application/x-ndjson" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return true;
  }

  return { connect, log, sessionHeader, downloadIfNeeded, isConnected: () => ready };
})();
