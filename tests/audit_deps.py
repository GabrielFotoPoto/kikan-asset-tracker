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

"""Audit des dependances Python (vulnerabilites connues) via pip-audit.

Usage, depuis la racine du projet :
  docker run --rm -v "$PWD/backend/requirements.txt:/r.txt:ro" \
    -v "$PWD/tests/audit_deps.py:/a.py:ro" python:3.12-slim python /a.py
Code de sortie 1 si au moins une vulnerabilite est trouvee.
"""
import json
import subprocess
import sys

REQ = "/r.txt"

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--root-user-action=ignore", "pip-audit"],
               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
res = subprocess.run([sys.executable, "-m", "pip_audit", "-r", REQ, "--progress-spinner", "off",
                      "--format", "json"], capture_output=True, text=True)
try:
    data = json.loads(res.stdout)
except json.JSONDecodeError:
    sys.exit("pip-audit n'a pas produit de JSON :\n" + res.stdout + res.stderr)

found = 0
for dep in data["dependencies"]:
    vulns = dep.get("vulns") or []
    if vulns:
        found += len(vulns)
        fixes = sorted({f for v in vulns for f in v.get("fix_versions", [])})
        print(f"{dep['name']}=={dep['version']}: {len(vulns)} vulnerabilite(s), versions corrigees: {fixes}")
print("Aucune vulnerabilite connue." if not found else f"\n{found} vulnerabilite(s) au total.")
sys.exit(1 if found else 0)
