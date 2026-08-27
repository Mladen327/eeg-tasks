"""Potpuno deterministican voz kroz S2 blok (server rezim), za poredjenje
loga pre/posle premestanja koda u jezgro. Iste radnje, isti redosled, ista
zakazana kasnjenja -- svaki put. NE zavisi od tacnih (referentnih)
vrednosti stavke, jer se ne testira tacnost nego mehanizam.

Deterministican obrazac po stavci:
  - saceka ENCODING_MIN_MS (3200ms), zavrsi kodiranje dugmetom "Spreman"
  - za polje 0: otkuca fiksnu vrednost, obriše 2 znaka (backspace), otkuca ih ponovo,
    zatim JEDNOM ode u Prozor A (F2) i vrati se (F2), pa nastavi
  - za ostala polja: otkuca fiksnu vrednost bez brisanja
  - potvrdi stavku

Usage: pw_reference_s2.py <http_base_url> <n> <out_log_path>
Napomena: log dolazi preko WS-a na server.py -- posle trcanja, pozivalac
kopira najnoviji fajl iz logs/ na <out_log_path>.
"""
import sys
from playwright.sync_api import sync_playwright

base_url = sys.argv[1]
n = sys.argv[2]
URL = f"{base_url}/app/index.html?participant=DEMO&n={n}&demo=1"


def value_for_header(h):
    if h == "PIB":
        return "123456789"
    if h == "Matični broj":
        return "12345678"
    if h == "Telefon":
        return "0601234567"
    return "referentna-vrednost"


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1000, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    page.goto(URL)
    page.wait_for_selector("#screen-intro:not(.hidden)", timeout=5000)
    page.click("#btn-start")

    for item_no in range(1, 5):
        try:
            page.wait_for_selector("#window-document:not(.hidden)", timeout=5000)
        except Exception:
            break
        page.wait_for_timeout(3200)
        page.click("#btn-encoding-ready")
        page.wait_for_selector("#window-spreadsheet:not(.hidden)", timeout=10000)

        headers = page.eval_on_selector_all("#sheet-header-row th", "els => els.map(e => e.textContent)")
        inputs = page.query_selector_all("#sheet-input-row input")

        for i, h in enumerate(headers):
            inputs[i].click()
            val = value_for_header(h)
            page.keyboard.type(val, delay=2)
            if i == 0:
                page.keyboard.press("Backspace")
                page.keyboard.press("Backspace")
                page.keyboard.type(val[-2:], delay=2)
                page.keyboard.press("F2")
                page.wait_for_selector("#window-document:not(.hidden)", timeout=3000)
                page.wait_for_timeout(150)
                page.keyboard.press("F2")
                page.wait_for_selector("#window-spreadsheet:not(.hidden)", timeout=3000)
                inputs = page.query_selector_all("#sheet-input-row input")

        page.wait_for_timeout(80)
        page.click("#btn-submit-item")
        print(f"item {item_no} submitted (N={n})")

    page.wait_for_selector("#screen-end:not(.hidden)", timeout=20000)
    print("block ended")
    if errors:
        print("ERRORS:", errors)
        sys.exit(1)
    browser.close()
