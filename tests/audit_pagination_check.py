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

"""Journal d'audit (GET /audit) : pagination (limit, offset, en-tete X-Total-Count), tri et compatibilite.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/audit_pagination_check.py

Genere des entrees du journal par des requetes POST /assets invalides (422 : rien n'est cree). Aucune donnee a nettoyer.
Code de sortie 1 si un test echoue. Ce fichier reste en ASCII (independant du lanceur).
"""
import json
import os
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:160] if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def login(user, pw):
    s, b, _ = call("POST", "/auth/login", {"username": user, "password": pw})
    return json.loads(b)["access_token"] if s == 200 else None


TOK = login(ADMIN, ADMIN_PW)
if not TOK:
    sys.exit("Connexion admin impossible")


def audit(**params):
    """GET /audit : (statut HTTP, lignes, total annonce par X-Total-Count ou None)."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    s, b, h = call("GET", "/audit" + ("?" + q if q else ""), token=TOK)
    try:
        rows = json.loads(b) if s == 200 else None
    except ValueError:
        rows = None
    total = h.get("X-Total-Count")
    return s, rows, (int(total) if total is not None and total.isdigit() else None)


# --- Entrees de test : 45 refus de validation (422) journalises, sans rien creer ---
FILTRE = {"actor": ADMIN, "action": "POST%20/assets"}
_, _, avant = audit(limit=1, **FILTRE)
for _ in range(45):
    s, _, _ = call("POST", "/assets", {"statut": "pas-un-statut"}, TOK)
    if s != 422:
        sys.exit(f"POST /assets invalide attendu en 422, recu {s} : jeu de test impossible")
s, _, apres = audit(limit=1, **FILTRE)
show("X-Total-Count present et numerique", avant is not None and apres is not None, f"{avant} -> {apres}")
show("X-Total-Count augmente de 45 apres 45 entrees", apres == (avant or 0) + 45, f"{avant} -> {apres}")

# --- Compatibilite : sans parametre, une liste, les plus recentes d'abord (comme avant) ---
s, rows, total = audit()
ids = [r["id"] for r in rows or []]
show("sans parametre : HTTP 200, une liste", s == 200 and isinstance(rows, list) and len(rows) > 0)
show("sans parametre : plus recentes d'abord (id decroissant)", ids == sorted(ids, reverse=True))
show("sans parametre : au plus 200 lignes", len(ids) <= 200, len(ids))
s, rows, _ = audit(limit=7)
show("limit seul : exactement 7 lignes", s == 200 and len(rows) == 7, len(rows or []))

# --- Pagination : les pages mises bout a bout redonnent la liste complete, sans trou ni doublon ---
_, tout, total = audit(limit=50, **FILTRE)
reference = [r["id"] for r in tout]
pages = []
for n in range(5):
    _, page, _ = audit(limit=10, offset=10 * n, **FILTRE)
    pages += [r["id"] for r in page]
show("5 pages de 10 = les 50 premieres lignes", pages == reference, f"{len(pages)} lignes")
show("aucun doublon entre les pages", len(set(pages)) == len(pages))
dernier = ((apres or 0) // 10) * 10
_, fin, t = audit(limit=10, offset=dernier, **FILTRE)
show("derniere page : au plus 10 lignes, total inchange", 0 < len(fin) <= 10 and t == apres, f"{len(fin)} lignes, total {t}")
s, vide, t = audit(limit=10, offset=(apres or 0) + 1000, **FILTRE)
show("offset au-dela du total : liste vide, total conserve", s == 200 and vide == [] and t == apres, f"HTTP {s}, total {t}")

# --- Filtres et total ---
s, rien, t = audit(actor="zz-personne-ne-porte-ce-nom")
show("filtre sans resultat : liste vide, total 0", s == 200 and rien == [] and t == 0, f"total {t}")
s, deb, t = audit(action="POST", limit=1)
show("filtre sur le debut de l'action : total coherent", s == 200 and t is not None and t >= apres, f"total {t}")

# --- Tri ---
# Texte (compte, action, IP) : PostgreSQL le classe selon la langue de la base (casse, ponctuation), pas selon l'ordre des
# caracteres de Python. On ne presume donc pas l'ordre alphabetique : on verifie que les valeurs identiques sont regroupees,
# que les valeurs vides sont en fin de liste et que le sens decroissant est l'inverse du croissant.
# Nombres et dates (id, date, statut) : ordre strict.
def distinctes(valeurs):
    vues = []
    for v in valeurs:
        if v not in vues:
            vues.append(v)
    return vues


def regroupees(valeurs):
    """Chaque valeur forme un bloc continu : aucune ne reapparait apres qu'une autre a commence."""
    pleines = [v for v in valeurs if v is not None]
    blocs = [v for i, v in enumerate(pleines) if i == 0 or v != pleines[i - 1]]
    return len(blocs) == len(set(blocs))


for tri in ("id", "ts", "status", "actor", "action", "ip"):
    s, asc, total = audit(tri=tri, sens="asc", limit=1000)
    s2, desc, _ = audit(tri=tri, sens="desc", limit=1000)
    ok = s == 200 and s2 == 200 and len(asc) > 0 and len(desc) > 0
    detail = ""
    if ok:
        va = [r[tri] for r in asc]
        vd = [r[tri] for r in desc]
        if tri in ("id", "ts", "status"):
            pa, pd = [v for v in va if v is not None], [v for v in vd if v is not None]
            ok = pa == sorted(pa) and pd == sorted(pd, reverse=True)
        else:
            ok = regroupees(va) and regroupees(vd)
            if total is not None and total <= 1000:  # liste complete : le sens decroissant est l'inverse du croissant
                ok = ok and distinctes([v for v in vd if v is not None]) == list(reversed(distinctes([v for v in va if v is not None])))
        for valeurs in (va, vd):  # valeurs vides toujours en fin de liste
            vide = False
            for v in valeurs:
                if v is None:
                    vide = True
                elif vide:
                    ok, detail = False, "valeur non vide apres une valeur vide"
    show(f"tri par {tri} : croissant et decroissant coherents, vides en fin", ok, detail)
s, a, _ = audit(tri="ts", sens="asc", limit=5)
s, d, _ = audit(tri="ts", sens="desc", limit=5)
show("tri par date : croissant (anciennes) et decroissant (recentes) different", s == 200 and a[0]["id"] != d[0]["id"])
# Tri et pagination ensemble : page 2 d'un tri par compte = lignes 11 a 20 du meme tri
_, tout, _ = audit(tri="actor", sens="asc", limit=20)
_, page2, _ = audit(tri="actor", sens="asc", limit=10, offset=10)
show("tri + pagination : page 2 = lignes 11 a 20 du meme tri", [r["id"] for r in page2] == [r["id"] for r in tout[10:20]])

# --- Validation des parametres : refus net, jamais d'erreur serveur ---
for nom, params in [("tri inconnu", {"tri": "mot_de_passe"}), ("sens inconnu", {"sens": "aleatoire"}),
                    ("offset negatif", {"offset": -1}), ("limit nul", {"limit": 0}), ("limit trop grand", {"limit": 1001}),
                    ("offset non numerique", {"offset": "abc"}),
                    ("injection dans le tri", {"tri": "id%3BDROP%20TABLE%20audit_log"})]:
    s, _, _ = audit(**params)
    show(f"{nom} : refuse (422)", s == 422, f"HTTP {s}")
s, rows, _ = audit(limit=1)
show("la table d'audit existe toujours apres ces essais", s == 200 and len(rows) == 1)

# --- Acces : sans jeton, refus ---
s, _, _ = call("GET", "/audit?limit=1")
show("sans session : refuse", s in (401, 403), f"HTTP {s}")

print("\nECHECS : %d" % fails)
sys.exit(1 if fails else 0)
