"""Potpuno deterministican voz kroz S3b blok (server rezim), za poredjenje
loga pre/posle premestanja koda u jezgro. Iste radnje, isti redosled --
svaki put. Klika UVEK prvu ponudjenu opciju (ne testira se tacnost, nego
mehanizam), koristi dugme za ponovni uvid (peek) jednom po stavci, i
prihvata (accept) svaku sugestiju.

S3 NEMA "Spreman" dugme (za razliku od S2) -- faza kodiranja se ceka do
kraja, kao i pre refaktora; ovaj skript to namerno ne pokusava da preskoci,
da bi bazna linija odrazavala TRENUTNO ponasanje S3.

Usage: pw_reference_s3.py <http_base_url> <n> <out_log_path>
"""
import sys
from playwright.sync_api import sync_playwright

base_url = sys.argv[1]
n = sys.argv[2]
URL = f"{base_url}/app/index.html?participant=DEMO&variant=S3b&n={n}&demo=1"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    page.goto(URL)
    page.wait_for_selector("#screen-intro:not(.hidden)", timeout=5000)
    page.click("#btn-start")

    for item_no in range(1, 5):
        try:
            page.wait_for_selector("#verification-block:not(.hidden)", timeout=60000)
        except Exception:
            break

        # jedan uvid (peek) po stavci, na pocetku verifikacije
        page.click("#btn-peek")
        page.wait_for_timeout(3100)

        n_fields = int(n)
        for f in range(n_fields):
            page.wait_for_selector("#suggestion-buttons:not(.hidden)", timeout=5000)
            page.click("#btn-accept")
            page.wait_for_selector("#options-panel:not(.hidden)", timeout=3000)
            page.click("#options-list .option-btn >> nth=0")
            if f < n_fields - 1:
                page.wait_for_timeout(50)

        page.wait_for_selector("#screen-gap:not(.hidden)", timeout=5000)
        print(f"item {item_no} done (N={n})")

    page.wait_for_selector("#screen-end:not(.hidden)", timeout=20000)
    print("block ended")
    if errors:
        print("ERRORS:", errors)
        sys.exit(1)
    browser.close()
