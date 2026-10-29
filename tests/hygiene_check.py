# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Hygiene du depot : regles du projet verifiees automatiquement (sans Docker, sans base).

  python tests/hygiene_check.py

- aucun tiret long (cadratin, demi-cadratin) dans les fichiers texte versionnes : on ecrit "-" ;
- les tests (tests/*.py) restent en ASCII (independants du lanceur) ;
- en-tete de licence GPLv3 dans le code (backend, frontend, tests, outil de sauvegarde, scripts) ;
- aucun secret ni fichier sensible versionne (.env, cles privees, jetons) ;
- tout le code Python compile ; les fichiers YAML et JSON sont valides.
Code de sortie 1 si un controle echoue.
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = 0
EM, EN = chr(0x2014), chr(0x2013)   # cadratin et demi-cadratin (ecrits par code pour que ce fichier reste conforme)


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:300] if detail else ""))


files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
TEXT_EXT = {".py", ".js", ".jsx", ".md", ".yml", ".yaml", ".sh", ".ps1", ".sql", ".json", ".css", ".html", ".txt", ".example", ".toml", ".ini", ".conf", ".mako"}
SKIP_DASH = {"frontend/package-lock.json"}


def is_text(p: str) -> bool:
    name = Path(p).name
    return Path(p).suffix in TEXT_EXT or name in ("Dockerfile", ".gitignore", ".env.example", "LICENSE")


def read(p: str) -> str | None:
    try:
        return (ROOT / p).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


texts = {p: read(p) for p in files if is_text(p) and (ROOT / p).is_file()}

print("== Regles d'ecriture ==")
dashes = [f"{p}:{n}" for p, t in texts.items() if t and p not in SKIP_DASH and p != "LICENSE"
          for n, line in enumerate(t.splitlines(), 1) if EM in line or EN in line]
show("aucun tiret long (utiliser '-')", not dashes, dashes[:5])
non_ascii = [p for p in files if p.startswith("tests/") and p.endswith(".py") and texts.get(p) and not texts[p].isascii()]
show("les tests (tests/*.py) sont en ASCII", not non_ascii, non_ascii)

print("== Licence ==")
HEADER = "This program is free software"
need = [p for p in files if re.match(r"^(backend/app|backend/migrations|frontend/src|tests|backup|scripts)/", p)
        and Path(p).suffix in (".py", ".jsx", ".js", ".sh", ".ps1")]
missing = [p for p in need if texts.get(p) and HEADER not in texts[p][:1500] and "Licence GPLv3" not in texts[p][:1500]]
show("en-tete de licence dans le code", not missing, missing[:8])
show("fichier LICENSE present", (ROOT / "LICENSE").is_file())

print("== Secrets et fichiers sensibles ==")
forbidden = [p for p in files if re.search(r"(^|/)\.env$|\.pem$|\.key$|\.pfx$|identity\.txt$|recipient\.txt$|(^|/)backups/|restore-output/|\.dump$|\.age$", p)]
show("aucun fichier sensible versionne (.env, cles, sauvegardes)", not forbidden, forbidden)
PATTERNS = {
    "cle privee": r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "cle age": r"AGE-SECRET-KEY-[A-Z0-9]{20,}",
    "jeton Kikan": r"\bkik_[A-Za-z0-9_-]{40,}\b", "jeton GitHub": r"\bgh[pousr]_[A-Za-z0-9]{30,}\b", "cle AWS": r"\bAKIA[0-9A-Z]{16}\b",
    "secret Slack": r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
}
hits = [f"{p} ({label})" for p, t in texts.items() if t and p != "tests/hygiene_check.py"
        for label, rx in PATTERNS.items() if re.search(rx, t)]
show("aucun secret reconnaissable dans le code", not hits, hits[:5])

print("== Validite ==")
bad_py = []
for p in files:
    if p.endswith(".py") and texts.get(p):
        try:
            ast.parse(texts[p], filename=p)
        except SyntaxError as exc:
            bad_py.append(f"{p}:{exc.lineno}")
show("tout le code Python compile", not bad_py, bad_py)
bad_json = []
for p in files:
    if p.endswith(".json") and texts.get(p):
        try:
            json.loads(texts[p])
        except ValueError:
            bad_json.append(p)
show("les fichiers JSON sont valides", not bad_json, bad_json)
try:
    import yaml
    bad_yaml = []
    for p in files:
        if p.endswith((".yml", ".yaml")) and texts.get(p):
            try:
                list(yaml.safe_load_all(texts[p]))
            except yaml.YAMLError as exc:
                bad_yaml.append(f"{p}: {str(exc)[:80]}")
    show("les fichiers YAML sont valides", not bad_yaml, bad_yaml)
except ImportError:
    print("SKIP validation YAML (PyYAML absent)")

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
