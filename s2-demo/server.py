"""Server za demonstrator Scenarija 2.

Radi dve stvari istovremeno (identicno s3-demo/server.py po strukturi):

1. Sluzi staticke fajlove (app/, data/) kao obican HTTP server.
2. Prima WebSocket vezu od app/task.js (ws://<host>:8766, RAZLICIT port
   od s3-demo-a namerno, da oba demoa mogu da rade istovremeno) i za svaku
   primljenu poruku:
     - upisuje red u odgovarajucu .jsonl datoteku u logs/ (ili
       logs/practice/ za variant=="practice"), sekcija 8 uputstva
     - ako je pylsl dostupan, prosledjuje dogadjaj kao LSL marker u tok
       "S2_markers" (tip "Markers")

Ako pylsl nije instaliran, server nastavlja da radi normalno.

Pokretanje:
    python server.py                    # http :8000, ws :8766
    python server.py --http-port 8080 --ws-port 8766
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import json
import socketserver
import threading
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
LOGS_DIR = ROOT / "logs"
LOGS_PRACTICE_DIR = LOGS_DIR / "practice"


class SessionLogWriter:
    """Jedan JSONL fajl po bloku (sekcija 8). Fajl se otvara na prvi
    "session" red te veze i zatvara kad se veza zatvori."""

    def __init__(self):
        self.file = None
        self.path = None

    def handle(self, event: dict):
        if event.get("type") == "session":
            self._open_for_session(event)
        if self.file is None:
            self._open_fallback()
        self.file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.file.flush()

    def _open_for_session(self, header: dict):
        participant = header.get("participant_id", "UNKNOWN")
        variant = header.get("variant", "unknown")
        n = header.get("n_fields", "x")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        folder = LOGS_PRACTICE_DIR if variant == "practice" else LOGS_DIR
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
            info = StreamInfo("S2_markers", "Markers", 1, 0, "string", "s2-demo-markers")
            self.outlet = StreamOutlet(info)
            print("[lsl] LSL tok 'S2_markers' pokrenut")
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
        except Exception as exc:
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


def run_http_server(port: int):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))

    class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"[http] staticki fajlovi na http://localhost:{port}/app/index.html")
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
    ap.add_argument("--ws-port", type=int, default=8766)
    args = ap.parse_args()

    http_thread = threading.Thread(target=run_http_server, args=(args.http_port,), daemon=True)
    http_thread.start()

    try:
        asyncio.run(run_ws_server(args.ws_port))
    except KeyboardInterrupt:
        print("\nprekinuto")


if __name__ == "__main__":
    main()
