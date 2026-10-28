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

"""Cree une remise SIGNEE (donc un PDF scelle dans le stockage local) pour tests/backup_check.py.

  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/backup_seed.py

Affiche une ligne "SEED:{json}" (reference, empreinte du PDF). Donnees ZZBK (nettoyage : tests/cleanup_test_data.sql).
ASCII uniquement.
"""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/app")
from PIL import Image, ImageDraw  # noqa: E402

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")


def call(method, path, payload=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(payload).encode() if payload is not None else None, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read()


s, t = call("POST", "/auth/login", {"username": os.environ["TEST_ADMIN_USER"], "password": os.environ["TEST_ADMIN_PASSWORD"]})
ADM = t["access_token"]
img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)], fill=(17, 17, 17, 255), width=7)
buf = io.BytesIO()
img.save(buf, "PNG")
SIGN = {"consent": True, "signature_image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), "strokes": 4, "duration_ms": 1800}

s, ent = call("POST", "/entites", {"code": "ZZBK-A", "nom": "ZZBK Filiale"}, ADM)
if s == 409:
    ent = next(e for e in call("GET", "/entites", token=ADM)[1] if e["code"] == "ZZBK-A")
s, u = call("POST", "/users", {"matricule": "ZZBK-1", "nom": "NomBK", "prenom": "ZZBKjean", "entite_id": ent["id"]}, ADM)
s, a = call("POST", "/assets", {"type": "ZZBK type", "marque": "ZZBK", "modele": "M1", "numero_serie": "ZZBK-SN-1", "identifiant_interne": "ZZBK-ID-1", "entite_id": ent["id"]}, ADM)
s, asg = call("POST", "/assignments", {"user_id": u["id"], "asset_ids": [a["id"]]}, ADM)
s, sg = call("POST", "/assignments/%d/sign" % asg["id"], SIGN, ADM)
print("SEED:" + json.dumps({"status": s, "reference": sg.get("ged_reference"), "empreinte": sg.get("empreinte_doc"), "signature": sg.get("id")}))
