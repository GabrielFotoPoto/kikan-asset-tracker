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

"""Tests de l'import CSV : simulation, import reel, tout ou rien, modeles (instance de DEVELOPPEMENT).

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/import_check.py

Cree des donnees ZZIM et des comptes sec_im* (nettoyage : tests/cleanup_test_data.sql).
Code de sortie 1 si un test echoue.
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/app")

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:150] if detail else ""))


def call(method, path, body=None, token=None, raw=None, ctype="application/json"):
    h = {"Content-Type": ctype}
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def login(user, pw):
    s, b, _ = call("POST", "/auth/login", {"username": user, "password": pw})
    return json.loads(b)["access_token"] if s == 200 else None


ADM = login(ADMIN, ADMIN_PW)
if not ADM:
    sys.exit("Connexion admin impossible")


def j(method, path, body=None, token=None):
    s, b, _ = call(method, path, body, token or ADM)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def post_import(kind, content, query="", token=None):
    bd = "----kikanIM"
    body = (f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\n'
            "Content-Type: text/csv\r\n\r\n").encode() + content + f"\r\n--{bd}--\r\n".encode()
    s, b, _ = call("POST", f"/import/{kind}{query}", token=token or ADM, raw=body,
                   ctype="multipart/form-data; boundary=" + bd)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def sim(kind, content):
    return post_import(kind, content, "?dry_run=true")


def ensure_account(name, role):
    s, b, _ = call("POST", "/auth/accounts", {"username": name, "password": PW, "role": role}, ADM)
    if s == 409:
        accs = json.loads(call("GET", "/auth/accounts", token=ADM)[1])
        acc = next(a for a in accs if a["username"] == name)
        call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": role, "password": PW}, ADM)
        return acc["id"]
    return json.loads(b)["id"]


def codes(path, key):
    s, lst = j("GET", path)
    return {x[key] for x in lst}


print("== Preparation et roles ==")
ids = [ensure_account("sec_imrh", "rh"), ensure_account("sec_imlect", "lecture")]
RH, LECT = login("sec_imrh", PW), login("sec_imlect", PW)
EN = b"code;nom;code_parent;actif\nZZIM-A;ZZIM Groupe;;oui\nZZIM-B;ZZIM Filiale;ZZIM-A;oui\n"
for name, tok in (("RH", RH), ("lecture", LECT)):
    show(f"{name} : simulation refusee (403)", post_import("entites", EN, "?dry_run=true", tok)[0] == 403)
    show(f"{name} : import reel refuse (403)", post_import("entites", EN, "", tok)[0] == 403)
    show(f"{name} : modele refuse (403)", call("GET", "/import/modeles/entites", token=tok)[0] == 403)
show("sans jeton : refuse (401)", call("GET", "/import/specs")[0] == 401)

print("== Specifications et modeles ==")
s, specs = j("GET", "/import/specs")
show("6 types, dans l'ordre conseille", s == 200 and [x["kind"] for x in specs] ==
     ["entites", "applications", "utilisateurs", "materiel", "affectations", "acces_applicatifs"])
show("chaque type decrit ses colonnes (nom, obligatoire, aide)", all(x["colonnes"] and all({"nom", "obligatoire", "aide"} <= set(c) for c in x["colonnes"]) for x in specs))
from app.importer import read_csv  # noqa: E402
for sp in specs:
    s, body, h = call("GET", f"/import/modeles/{sp['kind']}", token=ADM)
    rows, headers, info = read_csv(body)
    show(f"modele {sp['kind']} : BOM UTF-8, en-tetes = colonnes, exemples lisibles",
         s == 200 and body[:3] == b"\xef\xbb\xbf" and headers == [c["nom"] for c in sp["colonnes"]] and len(rows) == len(sp["exemples"])
         and info["separateur"] == ";" and "attachment" in h.get("Content-Disposition", ""))
show("modele d'un type inconnu -> 404", call("GET", "/import/modeles/inconnu", token=ADM)[0] == 404)

print("== Simulation : rien n'est ecrit ==")
before = codes("/entites", "code")
s, r = sim("entites", EN)
show("simulation : 2 a creer, 0 erreur", s == 200 and r["dry_run"] and r["imported"] == 2 and r["errors_total"] == 0, r if s != 200 else "")
show("simulation : empreinte, encodage et separateur renvoyes", r["sha256"] == hashlib.sha256(EN).hexdigest()
     and r["encodage"] == "UTF-8" and r["separateur"] == ";")
show("simulation : detail ligne par ligne", [x["ligne"] for x in r["lignes"]] == [2, 3] and all(x["action"] == "creer" for x in r["lignes"]))
show("simulation : aucune ecriture en base", codes("/entites", "code") == before and not ({"ZZIM-A", "ZZIM-B"} & codes("/entites", "code")))

print("== Import reel verifie par empreinte ==")
s, r2 = post_import("entites", EN, "?attendu=" + "0" * 64)
show("fichier different de la simulation -> 409", s == 409, f"HTTP {s}")
show("... et rien n'a ete cree", "ZZIM-A" not in codes("/entites", "code"))
s, real = post_import("entites", EN, "?strict=true&attendu=" + r["sha256"])
show("import reel identique a la simulation", s == 200 and real["imported"] == r["imported"] and real["errors_total"] == 0 and not real["dry_run"], real if s != 200 else "")
show("entites creees en base", {"ZZIM-A", "ZZIM-B"} <= codes("/entites", "code"))
s, again = sim("entites", EN)
show("reimport du meme fichier : tout est ignore (idempotent)", again["imported"] == 0 and again["skipped"] == 2
     and all(x["action"] == "ignorer" and "deja" in x["message"] for x in again["lignes"]))

print("== Tout ou rien (strict) ==")
APPS = (b"nom;description;code_entite;actif\nZZIM-App1;ok;ZZIM-A;oui\nZZIM-App2;mauvaise entite;ZZIM-NOPE;oui\n"
        b"ZZIM-App3;ok;;oui\n")
s, r = sim("applications", APPS)
show("simulation : 2 valides, 1 erreur localisee", r["imported"] == 2 and r["errors_total"] == 1 and r["errors"][0]["ligne"] == 3
     and "ZZIM-NOPE" in r["errors"][0]["message"], r["errors"])
s, rr = post_import("applications", APPS, "?strict=true&attendu=" + r["sha256"])
show("import strict avec erreur -> 409, rien n'est cree", s == 409 and "ZZIM-App1" not in {a["nom"] for a in j("GET", "/applications")[1]}, f"HTTP {s}")
s, part = post_import("applications", APPS)
show("sans strict : import partiel (comportement historique)", s == 200 and part["imported"] == 2 and part["errors_total"] == 1)
s, again = sim("applications", APPS)
show("reimport d'applications : plus de doublon, ignorees", again["imported"] == 0 and again["skipped"] == 2)
dup = b"nom;description;code_entite;actif\nZZIM-AppDup;a;;oui\nzzim-appdup;b;;oui\n"
s, r = sim("applications", dup)
show("doublon dans le meme fichier (casse differente) detecte", r["imported"] == 1 and r["skipped"] == 1)

print("== Salaries, materiel, affectations, acces ==")
USERS = (b"matricule;nom;prenom;email;code_entite;service;date_arrivee;statut\n"
         b"ZZIM-U1;Dupont;Alice;a@exemple.fr;ZZIM-B;Compta;2026-01-05;actif\n"
         b"ZZIM-U2;Martin;Bob;;ZZIM-B;;2026-13-45;actif\n"
         b"ZZIM-U3;Durand;Carl;;ZZIM-B;;;inconnu\n")
s, r = sim("utilisateurs", USERS)
show("salaries : date et statut invalides signales", r["imported"] == 1 and {e["ligne"] for e in r["errors"]} == {3, 4}, r["errors"])
s, r = post_import("utilisateurs", USERS.split(b"\n")[0] + b"\n" + USERS.split(b"\n")[1] + b"\n")
show("import du salarie valide", s == 200 and r["imported"] == 1)
ASSETS = (b"identifiant_interne;type;marque;modele;numero_serie;statut;code_entite\n"
          b"ZZIM-PC1;PC portable;ZZIM-Dell;L5550;ZZIM-SN1;stock;ZZIM-B\nZZIM-PC2;Smartphone;ZZIM-Samsung;S24;ZZIM-SN2;stock;ZZIM-B\n"
          b"ZZIM-PC3;PC;ZZIM-HP;E;ZZIM-SN1;stock;\n")
s, r = sim("materiel", ASSETS)
show("materiel : numero de serie en double dans le fichier signale", r["imported"] == 2 and r["errors"][0]["ligne"] == 4 and "ZZIM-SN1" in r["errors"][0]["message"])
post_import("materiel", ASSETS.rsplit(b"\n", 2)[0] + b"\n")
AFF = (b"matricule_utilisateur;identifiant_interne_actif;date_remise\nZZIM-U1;ZZIM-PC1;2026-02-01\nZZIM-U1;ZZIM-PC2;2026-02-03\n"
       b"ZZIM-U1;ZZIM-PC1;2026-02-01\nZZIM-U9;ZZIM-PC2;\nZZIM-U1;ZZIM-INCONNU;\n")
s, r = sim("affectations", AFF)
show("affectations : doublon, salarie et actif inconnus signales", r["imported"] == 2 and {e["ligne"] for e in r["errors"]} == {4, 5, 6}, r["errors"])
show("affectations : simulation sans effet", all(a["statut"] != "affecte" for a in j("GET", "/assets?statut=stock")[1] if a["numero_serie"] in ("ZZIM-SN1", "ZZIM-SN2")))
good = AFF.split(b"\n")
s, r = post_import("affectations", b"\n".join(good[:3]) + b"\n", "?strict=true")
show("affectations : import reel (une affectation, deux actifs)", s == 200 and r["imported"] == 2, r if s != 200 else "")
s, asg = j("GET", "/assignments")
show("l'affectation existe, creee par 'import'", any(a["cree_par"] == "import" for a in asg))
s, r = sim("affectations", b"\n".join(good[:3]) + b"\n")
show("rejouer : actifs deja affectes -> erreurs", r["imported"] == 0 and r["errors_total"] == 2)
ACC = b"matricule_utilisateur;application;acces;note\nZZIM-U1;ZZIM-App1;oui;standard\nZZIM-U1;ZZIM-App1;non;doublon\nZZIM-U1;Inexistante;oui;\n"
s, r = sim("acces_applicatifs", ACC)
show("acces : doublon ignore, application inconnue en erreur", r["imported"] == 1 and r["skipped"] == 1 and r["errors_total"] == 1, r)
s, r = post_import("acces_applicatifs", ACC.rsplit(b"\n", 2)[0] + b"\n")
s, r2 = sim("acces_applicatifs", ACC.rsplit(b"\n", 2)[0] + b"\n")
show("acces : reimport sans doublon", r2["imported"] == 0 and r2["skipped"] == 2)

print("== Formats de fichier ==")
ACCENTS = "D" + chr(233) + "p" + chr(244) + "t Ouest " + chr(224) + " Nantes"  # independant de l'encodage du lanceur
WIN = f"code;nom;code_parent;actif\nZZIM-W;{ACCENTS};;oui\n".encode("cp1252")
s, r = post_import("entites", WIN)
show("Windows-1252 (Excel) detecte et lu", s == 200 and r["encodage"] == "Windows-1252" and r["imported"] == 1, r.get("encodage"))
show("accents conserves en base", ACCENTS in {e["nom"] for e in j("GET", "/entites")[1]})
COMMA = b"code,nom,code_parent,actif\nZZIM-C,Virgule,,oui\n"
s, r = sim("entites", COMMA)
show("separateur virgule detecte", s == 200 and r["separateur"] == "," and r["imported"] == 1)
s, r = sim("entites", b"code;nom;code_parent;actif;colonne_en_trop\nZZIM-X;X;;oui;truc\n")
show("colonnes inconnues signalees et ignorees", r["colonnes_ignorees"] == ["colonne_en_trop"] and r["imported"] == 1)
s, r = sim("entites", b"code;nom;code_parent;actif;colonne_en_trop\nZZIM-Y;Y;;oui;a;b;c\n")
show("ligne avec trop de cellules : pas d'erreur 500", s == 200, f"HTTP {s}")

print("== Fichiers invalides ou hostiles ==")
def refused(name, kind, content, codes=(400,)):
    s, r = sim(kind, content)
    show(name, s in codes, f"HTTP {s} {r.get('detail') if isinstance(r, dict) else ''}")

refused("colonne obligatoire absente -> message precis", "entites", b"code;libelle\nA;B\n")
refused("fichier sans ligne de donnees", "entites", b"code;nom;code_parent;actif\n")
refused("fichier vide", "entites", b"")
refused("fichier binaire", "entites", b"\x00\x01\x02" + os.urandom(200))
refused("type inconnu", "inconnu", EN)
refused("plus de 20000 lignes -> 413", "entites", b"code;nom\n" + b"".join(b"ZZIM-N%d;N\n" % i for i in range(20001)), codes=(413,))
refused("fichier de plus de 5 Mo -> 413", "entites", b"code;nom\n" + b"x" * (6 * 1024 * 1024), codes=(413,))
s, r = sim("entites", b"code;nom\n" + b"".join(b"ZZIM-E%d;\n" % i for i in range(1500)))
show("1500 erreurs : compteur exact, detail plafonne a 1000", s == 200 and r["errors_total"] == 1500 and len(r["errors"]) == 1000 and r["tronque"])
HOSTILE = "matricule;nom;prenom\nZZIM-H1;=HYPERLINK(\"http://evil\");<script>alert(1)</script>\n".encode()
s, r = post_import("utilisateurs", HOSTILE)
s2, users = j("GET", "/users")
hs = next((u for u in users if u["matricule"] == "ZZIM-H1"), None)
show("formule et balise HTML : stockees telles quelles, sans erreur 500", s == 200 and hs and hs["prenom"] == "<script>alert(1)</script>", f"HTTP {s}")
s, csvb, _ = call("GET", "/reports/holdings?format=csv", token=ADM)
show("l'export CSV neutralise les formules importees", b"=HYPERLINK" not in csvb or b"'=HYPERLINK" in csvb)

print("== Journal d'audit ==")
s, log = j("GET", "/audit?limit=200")
acts = {x["action"] for x in log} if s == 200 else set()
show("simulation, import reel et refus journalises", {"import_simulation", "import_reel", "import_refuse"} <= acts, sorted(acts)[:8])
imp = [x for x in log if x["action"] in ("import_simulation", "import_reel", "import_refuse")]
show("journal : type, compteurs et empreinte, sans contenu du fichier",
     imp and all("lignes=" in (x["detail"] or "") and "sha256=" in x["detail"] for x in imp)
     and not any("Dupont" in (x["detail"] or "") or "ZZIM" in (x["detail"] or "") for x in imp))

for aid in ids:
    call("PUT", f"/auth/accounts/{aid}", {"actif": False}, ADM)
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
