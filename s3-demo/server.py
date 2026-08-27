"""Server za demonstrator Scenarija 3.

Radi dve stvari istovremeno:

1. Sluzi staticke fajlove (app/, data/) kao obican HTTP server, tako da se
   ceo demo moze pokrenuti sa samo ovim jednim procesom.
2. Prima WebSocket vezu od app/task.js (ws://<host>:8765) i za svaku
   primljenu poruku (jedan JSON dogadjaj po poruci):
     - upisuje red u odgovarajucu .jsonl datoteku u logs/ (ili
       logs/practice/ za variant=="practice"), sekcija 7 uputstva
     - ako je pylsl dostupan, prosledjuje dogadjaj kao LSL marker u tok
       "S3_markers" (tip "Markers"), radi sinhronizacije sa EEG snimanjem

Ako pylsl nije instaliran, server nastavlja da radi normalno (samo upisuje
u fajl i jednom ispise upozorenje) -- demonstracija ne sme da zavisi od
prisustva EEG opreme.

Pokretanje:
    python server.py                    # http :8000, ws :8765
    python server.py --http-port 8080 --ws-port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
import socketserver
import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    import websockets
except ImportError:
    websockets = None

try:
    from pylsl import StreamInfo, StreamOutlet
    HAVE_LSL = True
except ImportError:
    HAVE_LSL = False

ROOT = Path(__file__).parent
# app/index.html ucitava deljeni core/ i data/instructions.json/
# participant_codes.json preko "../../" (SPEC_refaktor_jezgro.md) -- pravi
# koren za staticku poslugu je zato roditelj s3-demo/ (eeg-tasks/), ne
# s3-demo/ sam. Bez ovoga core/*.js daje 404 kad se server pokrene po
# dokumentovanom "python server.py" iz s3-demo/ (nadjeno rucnim testom).
STATIC_ROOT = ROOT.parent
LOGS_DIR = ROOT / "logs"
LOGS_PRACTICE_DIR = LOGS_DIR / "practice"
# "DEMO" (core/intro.js: rezervisana, van dozvoljenog skupa
# generate_participant_codes.py) -- probne datoteke se cuvaju odvojeno od
# pravih ucesnika (uputstvo, tacka 6), isti obrazac kao logs/practice/.
LOGS_DEMO_DIR = LOGS_DIR / "demo"


class SessionLogWriter:
    """Jedan JSONL fajl po bloku (sekcija 7). Fajl se otvara na prvi
    "session" red te veze i zatvara kad se veza zatvori."""

    def __init__(self):
        self.file = None
        self.path = None

    def handle(self, event: dict):
        if event.get("type") == "session":
            self._open_for_session(event)
        if self.file is None:
            # dogadjaj je stigao pre session zaglavlja -- ne bi trebalo da
            # se desi, ali ne gubimo podatke: otvori fallback fajl.
            self._open_fallback()
        self.file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.file.flush()

    def _open_for_session(self, header: dict):
        participant = header.get("participant_id", "UNKNOWN")
        variant = header.get("variant", "unknown")
        n = header.get("n_fields", "x")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if variant == "practice":
            folder = LOGS_PRACTICE_DIR
        elif participant == "DEMO":
            folder = LOGS_DEMO_DIR
        else:
            folder = LOGS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{participant}_{variant}_{n}_{timestamp}.jsonl"
        self.file = self.path.open("a", encoding="utf-8")
        print(f"[log] nova sesija -> {self.path}")

    def _open_fallback(self):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = LOGS_DIR / f"UNKNOWN_{timestamp}.jsonl"
        self.file = self.path.open("a", encoding="utf-8")
        print(f"[log] UPOZORENJE: dogadjaj bez session zaglavlja -> {self.path}")

    def close(self):
        if self.file:
            self.file.close()
            print(f"[log] zatvoreno {self.path}")


class LslForwarder:
    def __init__(self):
        self.outlet = None
        self._warned = False
        if HAVE_LSL:
            info = StreamInfo("S3_markers", "Markers", 1, 0, "string", "s3-demo-markers")
            self.outlet = StreamOutlet(info)
            print("[lsl] LSL tok 'S3_markers' pokrenut")
        else:
            print("[lsl] UPOZORENJE: pylsl nije dostupan -- markeri se ne salju, "
                  "log u fajl radi normalno.")

    def push(self, event: dict):
        if self.outlet is None:
            return
        label = event.get("event") or event.get("type") or "event"
        payload = f"{label}|{json.dumps(event, ensure_ascii=False)}"
        try:
            self.outlet.push_sample([payload])
        except Exception as exc:  # ne sme da obori sesiju zbog EEG opreme
            if not self._warned:
                print(f"[lsl] UPOZORENJE: slanje markera nije uspelo ({exc}); nastavljam bez LSL-a")
                self._warned = True


async def ws_handler(lsl: LslForwarder, websocket):
    writer = SessionLogWriter()
    peer = websocket.remote_address
    print(f"[ws] veza otvorena: {peer}")
    try:
        async for message in websocket:
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                print(f"[ws] neispravan JSON, preskačem: {message[:200]}")
                continue
            writer.handle(event)
            lsl.push(event)
    finally:
        writer.close()
        print(f"[ws] veza zatvorena: {peer}")


class ApiHandler(http.server.SimpleHTTPRequestHandler):
    """Dodaje TACNO jednu rutu (/api/session-count) preko staticke posluge
    -- core/intro.js je koristi da odredi redni broj sesije (1/2/3) za
    unetu sifru, jer to jedino server moze da vidi (postojeci fajlovi u
    logs/). Sve ostalo ide na SimpleHTTPRequestHandler bez izmene."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/session-count":
            self._session_count(parsed)
            return
        super().do_GET()

    def _session_count(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        code = (qs.get("code") or [""])[0].strip().upper()
        count = 0
        if code and code != "DEMO" and LOGS_DIR.exists():
            count = sum(1 for p in LOGS_DIR.glob(f"{code}_*.jsonl") if p.is_file())
        body = json.dumps({"count": count}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_http_server(port: int):
    handler = functools.partial(ApiHandler, directory=str(STATIC_ROOT))

    class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"[http] staticki fajlovi na http://localhost:{port}/s3-demo/app/index.html")
    httpd.serve_forever()


async def run_ws_server(port: int):
    if websockets is None:
        print("[ws] UPOZORENJE: paket 'websockets' nije instaliran (pip install websockets). "
              "Log preko WebSocket-a nece raditi; app/task.js ce pasti na preuzimanje "
              ".jsonl fajla iz browsera.")
        while True:
            await asyncio.sleep(3600)

    lsl = LslForwarder()
    async with websockets.serve(functools.partial(ws_handler, lsl), "0.0.0.0", port):
        print(f"[ws] WebSocket prijem na ws://localhost:{port}")
        await asyncio.Future()  # zauvek


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--ws-port", type=int, default=8765)
    args = ap.parse_args()

    http_thread = threading.Thread(target=run_http_server, args=(args.http_port,), daemon=True)
    http_thread.start()

    try:
        asyncio.run(run_ws_server(args.ws_port))
    except KeyboardInterrupt:
        print("\nprekinuto")


if __name__ == "__main__":
    main()
