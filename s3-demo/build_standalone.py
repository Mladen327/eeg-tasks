"""Pravi samostalan index.html (sve podatke i kod u jednom fajlu, radi
dvoklikom preko file://, bez servera i bez fetch() poziva ka drugim
fajlovima -- fetch lokalnih fajlova je preko file:// blokiran CORS
politikom pregledaca).

Ulaz: app/index.html, app/style.css, app/task.js,
      data/contract_template.html, data/items_S3a.json,
      data/items_S3b.json, data/suggestions.json, data/companies.json
      (svi moraju vec postojati -- pokrenuti prvo generate_stimuli.py).

Izlaz: standalone/index.html

Pokretanje:
    python build_standalone.py
    python build_standalone.py --out standalone/index.html
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).parent


def sha256_of_file(path: Path) -> str:
    """Isti format kao app/task.js (bufToHashHex): 'sha256:' + hex, nad
    sirovim bajtovima fajla. Racuna se OVDE (u trenutku pravljenja
    standalone/index.html) jer se u file:// rezimu fajlovi vise ne
    fetch-uju -- videti dopunu uputstva o hesovima u session redu loga."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def escape_close_script(text: str) -> str:
    """Sprecava da bilo koji '</' unutar ugradjenog sadrzaja prevremeno
    zatvori okruzujuci <script> tag. Sigurno i za JSON i za HTML tekst koji
    se ubacuje u JS string literal (\\/ je validan escape i u JSON i u JS
    stringu, znaci isto sto i obican /)."""
    return text.replace("</", "<\\/")


def js_string_literal(text: str) -> str:
    """Python string -> JS dvostruko navedeni string literal."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "")
    )
    return f'"{escape_close_script(escaped)}"'


CORE_SCRIPT_RE = re.compile(r'<script src="((?:\.\./)+core/[^"]+\.js)"></script>')


def inline_core_scripts(index_html: str, root: Path) -> tuple[str, int]:
    """Zamenjuje svaki <script src="../../core/X.js"></script> ugradjenim
    sadrzajem tog core/ fajla (uputstvo za spajanje jezgra, korak 8: samostalna
    verzija nema server, pa relativne putanje ka core/ ne bi radile preko
    file://). Redosled tagova u index.html se ne dira -- zamena je in-place,
    pa je izvrsni redosled skripti identican serverskoj verziji."""
    def replace(m: re.Match) -> str:
        rel_path = m.group(1)
        js_path = (root / "app" / rel_path).resolve()
        content = js_path.read_text(encoding="utf-8")
        return f"<script>\n{content}\n</script>"

    return CORE_SCRIPT_RE.subn(replace, index_html)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "standalone" / "index.html")
    args = ap.parse_args()

    index_html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
    style_css = (ROOT / "app" / "style.css").read_text(encoding="utf-8")
    task_js = (ROOT / "app" / "task.js").read_text(encoding="utf-8")
    template_html = (ROOT / "data" / "contract_template.html").read_text(encoding="utf-8")
    items_s3a_path = ROOT / "data" / "items_S3a.json"
    items_s3b_path = ROOT / "data" / "items_S3b.json"
    companies_path = ROOT / "data" / "companies.json"
    items_s3a = items_s3a_path.read_text(encoding="utf-8")
    items_s3b = items_s3b_path.read_text(encoding="utf-8")
    suggestions = (ROOT / "data" / "suggestions.json").read_text(encoding="utf-8")
    items_s3a_hash = sha256_of_file(items_s3a_path)
    items_s3b_hash = sha256_of_file(items_s3b_path)
    companies_hash = sha256_of_file(companies_path)
    # instructions.json je zajednicko za sva tri scenarija -- zivi u
    # korenu eeg-tasks/data/, ne u s3-demo/data/ (core/intro.js).
    instructions_json = (ROOT.parent / "data" / "instructions.json").read_text(encoding="utf-8")

    # 0) core/*.js -> ugradjen sadrzaj (mora pre koraka 2, koji trazi
    # preostali <script src="task.js">).
    index_html, n_core = inline_core_scripts(index_html, ROOT)
    if n_core == 0:
        raise RuntimeError('nisam nasao nijedan <script src=".../core/*.js"> u app/index.html')

    # 1) <link rel="stylesheet" href="style.css"> -> <style>...</style>
    # NAPOMENA: replacement mora biti funkcija/lambda, ne obican string --
    # re.sub() obican string tretira kao template i INTERPRETIRA "\n", "\g<..>"
    # i slicne sekvence unutar njega (npr. pretvara doslovno "\n" u pravi
    # newline bajt), sto bi ovde tiho pokvarilo escape-ovan sadrzaj.
    index_html, n = re.subn(
        r'<link rel="stylesheet" href="style\.css">',
        lambda _m: f"<style>\n{style_css}\n</style>",
        index_html,
    )
    if n != 1:
        raise RuntimeError("nisam nasao <link rel=stylesheet> u app/index.html")

    # 2) ugradjeni podaci + task.js, umesto <script src="task.js"></script>
    #    JSON fajlovi se ubacuju direktno kao JS objekat/niz literal (validan
    #    JSON je validan JS), sablon kao string literal. "</" se svuda
    #    bezbednosno escape-uje (escape_close_script / js_string_literal).
    embedded_js = f"""
window.__S3_EMBEDDED__ = {{
  template: {js_string_literal(template_html)},
  items: {{
    S3a: {escape_close_script(items_s3a)},
    S3b: {escape_close_script(items_s3b)}
  }},
  items_hash: {{
    S3a: {js_string_literal(items_s3a_hash)},
    S3b: {js_string_literal(items_s3b_hash)}
  }},
  companies_hash: {js_string_literal(companies_hash)},
  suggestions: {escape_close_script(suggestions)}
}};
window.__INSTRUCTIONS_EMBEDDED__ = {escape_close_script(instructions_json)};
""".strip()

    combined_script = f"<script>\n{embedded_js}\n</script>\n<script>\n{task_js}\n</script>"

    index_html, n = re.subn(
        r'<script src="task\.js"></script>',
        lambda _m: combined_script,
        index_html,
    )
    if n != 1:
        raise RuntimeError('nisam nasao <script src="task.js"></script> u app/index.html')

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(index_html, encoding="utf-8")

    size_mb = args.out.stat().st_size / (1024 * 1024)
    print(f"OK: {args.out}  ({size_mb:.1f} MB)")
    print("Otvoriti dvoklikom, ili: file://" + str(args.out.resolve()).replace("\\", "/"))


if __name__ == "__main__":
    main()
