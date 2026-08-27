"use strict";

/* ==========================================================================
   core/guard.js -- blokiranje kopiranja, secenja, lepljenja, kontekstnog
   menija i prevlacenja, uz belezenje pokusaja i BEZ poruke ispitaniku.

   Premesteno bez izmene ponasanja iz s2-demo/app/task.js -- prvobitno je
   postojalo samo u S2 (S3 ga nije kacio, nije ga dobijao ovim refaktorom,
   uputstvo sekcija 8: bez funkcionalne izmene). To pravilo je vazilo za
   sam refaktor, ne trajno; posle zavrsetka i provere refaktora (korak
   "Uskladi S1 sa S2/S3", tacka 5) installCopyProtection je aktiviran i za
   S1 (nad celim #stage) i za S3 (ogranicen na read-only prikaze --
   #contract-mount/#reference-mount/#peek-mount/#suggestion-text, NE i
   #options-panel/#suggestion-buttons, da ne bi ometao klik na ponudjene
   vrednosti -- videti s3-demo/app/task.js runBlock()).

   Generalizovano u odnosu na original SAMO onoliko koliko je neophodno da
   funkcije rade nad proizvoljnim elementom, ne hardkodovano nad
   els["window-document"]:
   - installCopyProtection(targetEl, isActive, getItemIndex): isActive()
     zamenjuje staru proveru `currentWindowName !== "document"`. NIJE
     zamenjeno sa "targetEl je trenutno vidljiv" (npr. provera .hidden
     klase) jer to NIJE tacan ekvivalent -- switchWindow() sakriva OBA
     prozora odmah na pocetku prelaska, a currentWindowName se menja tek
     POSLE SWITCH_DELAY_MS kasnjenja, pa bi provera vidljivosti dala
     drugaciji odgovor od originalne tokom tog kratkog prozora. isActive()
     zato ostaje scenario-ova sopstvena provera, prosledjena kao
     zatvaranje, da bi se ponasanje ocuvalo tacno.
   - installPasteProtection(cellEl, fieldName, getItemIndex): vec je bio
     opsti (prima element i ime polja); getItemIndex je zamenio hardkodovan
     currentItemRef.current.

   currentItemRef/currentWindowName OSTAJU u scenariju (task.js) -- nisu
   guard-specificni, koristi ih i switchWindow()/F2 logika, pa bi njihovo
   premestanje ovde uvelo nepotrebnu spregu.
   ========================================================================== */

function installCopyProtection(targetEl, isActive, getItemIndex) {
  const blockEvent = (ev, reason) => {
    ev.preventDefault();
    Logger.log({ event: "copy_blocked", item: getItemIndex(), reason });
  };
  targetEl.addEventListener("copy", (e) => blockEvent(e, "copy_event"));
  targetEl.addEventListener("cut", (e) => blockEvent(e, "cut_event"));
  targetEl.addEventListener("contextmenu", (e) => blockEvent(e, "contextmenu"));
  targetEl.addEventListener("dragstart", (e) => blockEvent(e, "dragstart"));

  window.addEventListener("keydown", (e) => {
    if (!isActive()) return;
    const k = e.key.toLowerCase();
    const ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && k === "c") { blockEvent(e, "ctrl_c"); return; }
    if (ctrl && k === "x") { blockEvent(e, "ctrl_x"); return; }
    if (ctrl && k === "a") { blockEvent(e, "ctrl_a"); return; }
    if (ctrl && e.key === "Insert") { blockEvent(e, "ctrl_insert"); return; }
  });
}

function installPasteProtection(cellEl, fieldName, getItemIndex) {
  cellEl.addEventListener("paste", (e) => {
    e.preventDefault();
    Logger.log({ event: "paste_blocked", item: getItemIndex(), field_name: fieldName });
  });
}
