"use strict";

/* ==========================================================================
   core/params.js -- citanje URL parametara i podrazumevanih vrednosti.

   Premesteno bez izmene ponasanja iz S2/S3 task.js. Obe scenario-datoteke
   su danas resavale ISTO pitanje (server verzija zahteva `participant` i
   validan `n`, u suprotnom fatalna greska; samostalna/embedded verzija
   nikad ne zahteva nista -- nedostajuci ili neispravni parametri dobijaju
   podrazumevane vrednosti iz EMBEDDED_DEFAULTS; practice uvek ima svoje
   fiksne vrednosti) DUPLIRANIM, skoro bajt-identicnim kodom. To je "dva
   razlicita nacina" iz uputstva -- ne dva razlicita PONASANJA, vec dve
   odvojene kopije istog mehanizma (S3-ova kopija je imala samo jedno
   dodatno polje, `variant`, i objasnjavajuci komentar). Ovde su spojene u
   jednu deljenu implementaciju; jedina stvarna razlika izmedju S2 i S3
   (S3-ovo `variant` polje: S3a/S3b) je izrazena kroz `config` argumente
   (extraKeys/validate/practiceExtra/embeddedExtra/serverExtra), NE
   hardkodovana -- S2-ov poziv ostaje bez tog dela konfiguracije, potpuno
   neizmenjenog ponasanja.

   resolveParamsCore reprodukuje redosled/logiku prethodnog if/else lanca
   (practice -> embedded -> server) polje-po-polje identicno. Provere u
   uslovu za "server" granu (!participant, invalid n, invalid extra) su sve
   ciste (bez sporednih efekata) pa je njihov redosled unutar OR izraza
   bihevioralno irelevantan -- spajanje u `extraValid` na kraju izraza ne
   menja rezultat ni u jednom slucaju.
   ========================================================================== */

function parseParamsCore(extraKeys) {
  const p = new URLSearchParams(location.search);
  const params = {
    participant: p.get("participant"),
    n: p.has("n") ? parseInt(p.get("n"), 10) : null,
    // demo je namerno null kad parametar uopste nije naveden u URL-u
    // (razlikuje se od "demo=0"), tako da se podrazumevana vrednost u
    // samostalnoj verziji primenjuje samo kad ispitivac nije rekao nista.
    demo: p.has("demo") ? p.get("demo") === "1" : null,
    practice: p.get("practice") === "1",
  };
  (extraKeys || []).forEach((key) => { params[key] = p.get(key); });
  return params;
}

function isEmbeddedCore(flagName) {
  return typeof window !== "undefined" && !!window[flagName];
}

function resolveParamsCore(params, embedded, embeddedDefaults, config) {
  const cfg = config || {};
  const result = { isPractice: params.practice };

  if (result.isPractice) {
    result.participantId = "PRACTICE";
    if (cfg.practiceExtra) cfg.practiceExtra(result);
    return result;
  }

  if (embedded) {
    result.participantId = params.participant || embeddedDefaults.participant;
    result.n = [3, 5, 7].includes(params.n) ? params.n : embeddedDefaults.n;
    result.isDemo = params.demo === null ? embeddedDefaults.demo : params.demo;
    if (cfg.embeddedExtra) cfg.embeddedExtra(result, params, embeddedDefaults);
    return result;
  }

  const extraValid = cfg.validate ? cfg.validate(params) : true;
  if (!params.participant || ![3, 5, 7].includes(params.n) || !extraValid) {
    result.fatal = cfg.fatalMessage || "Nedostaju ili su neispravni URL parametri.";
    return result;
  }
  result.participantId = params.participant;
  result.n = params.n;
  result.isDemo = !!params.demo;
  if (cfg.serverExtra) cfg.serverExtra(result, params);
  return result;
}
