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

"""Tests du mot de passe oublie (lien a usage unique), instance de DEVELOPPEMENT.

Usage (adresse publique de test requise, voir tests/reset-test.override.yml) :
  docker compose -f docker-compose.yml -f tests/reset-test.override.yml up -d api
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/reset_check.py
  docker compose up -d api      # retour a la configuration normale

Le faux serveur SMTP tourne dans ce script (127.0.0.1:2525, meme conteneur que l'API). Cree des comptes sec_rs* (nettoyage :
tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
"""
import email
import email.policy
import hashlib
import json
import os
import re
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
NEW_PW = "Nouveau-Passw0rd-2027"
PORT = 2525
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:160] if detail else ""))


# ---------------------------------------------------------------- faux serveur SMTP
INBOX = []


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        def w(text):
            self.wfile.write((text + "\r\n").encode())

        w("220 fake ESMTP")
        rcpts = []
        while True:
            line = self.rfile.readline()
            if not line:
                break
            cmd = line.decode(errors="replace").strip()
            up = cmd.upper()
            if up.startswith(("EHLO", "HELO")):
                w("250 fake")
            elif up.startswith("MAIL FROM"):
                rcpts = []
                w("250 ok")
            elif up.startswith("RCPT TO"):
                rcpts.append(cmd[cmd.index("<") + 1:cmd.index(">")].lower())
                w("250 ok")
            elif up == "DATA":
                w("354 go")
                raw = []
                while True:
                    row = self.rfile.readline()
                    if row in (b".\r\n", b""):
                        break
                    raw.append(row[1:] if row.startswith(b"..") else row)
                msg = email.message_from_bytes(b"".join(raw), policy=email.policy.default)
                msg["X-Test-Rcpt"] = ",".join(rcpts)
                INBOX.append(msg)
                w("250 queued")
            elif up in ("RSET", "NOOP"):
                w("250 ok")
            elif up == "QUIT":
                w("221 bye")
                break
            else:
                w("502 unsupported")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


srv = Server(("127.0.0.1", PORT), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def mails_for(addr):
    return [m for m in INBOX if m["X-Test-Rcpt"] == addr]


def attendre(addr, n=1, secondes=10):
    """L'envoi part en tache de fond : on attend l'arrivee du message."""
    fin = time.time() + secondes
    while time.time() < fin and len(mails_for(addr)) < n:
        time.sleep(0.2)
    return mails_for(addr)


def corps(msg):
    part = msg.get_body(preferencelist=("plain",))
    return part.get_content() if part else ""


# ---------------------------------------------------------------- client HTTP
def call(method, path, payload=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def j(method, path, payload=None, token=None):
    s, b = call(method, path, payload, token)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def login(user, pw):
    s, r = j("POST", "/auth/login", {"username": user, "password": pw})
    return r if s == 200 else None


adm = login(ADMIN, ADMIN_PW)
if not adm:
    sys.exit("Connexion admin impossible")
ADM = adm["access_token"]

BASE = {"actif": True, "hote": "127.0.0.1", "port": PORT, "securite": "aucune", "utilisateur": "",
        "expediteur": "kikan@exemple.test", "verifier_cert": True, "liste": "", "heure": 7,
        "renouv": False, "renouv_jours": 30, "depart": False, "depart_jours": 14, "nonrestit": False, "nonrestit_sem": 2,
        "rapport": False, "rapport_jour": 1, "rapport_pj": "aucune"}


def account(name, role="rh", **extra):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True, **extra}, ADM)
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts", token=ADM)[1] if a["username"] == name.lower())
        j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **extra}, ADM)
        return acc["id"]
    return r["id"]


print("== Disponibilite ==")
j("PUT", "/mail/config", {**BASE, "actif": False}, ADM)
s, r = j("GET", "/auth/reset/config")
show("lien propose seulement si les e-mails sont actifs", s == 200 and r == {"disponible": False}, r)
j("PUT", "/mail/config", BASE, ADM)
s, r = j("GET", "/auth/reset/config")
show("lien propose quand e-mails et adresse publique sont configures", s == 200 and r == {"disponible": True}, r)

print("== Demande de lien ==")
a1 = account("sec_rs1", email="zzrs1@exemple.test")
a_noemail = account("sec_rs_sansmail")
a_off = account("sec_rs_off", email="zzrs_off@exemple.test")
j("PUT", "/auth/accounts/%d" % a_off, {"actif": False}, ADM)
s, inconnu = j("POST", "/auth/forgot", {"identifiant": "sec_rs_inexistant"})
s2, connu = j("POST", "/auth/forgot", {"identifiant": "SEC_RS1"})
show("reponse identique (202) pour un compte inconnu et un compte connu", s == 202 and s2 == 202 and inconnu == connu, (s, s2))
mails = attendre("zzrs1@exemple.test")
show("le lien arrive a l'adresse du compte", len(mails) == 1, len(mails))
txt = corps(mails[0]) if mails else ""
m = re.search(r"https://kikan\.test/reinitialisation\?token=([A-Za-z0-9_-]{20,})", txt)
show("le message contient un lien a l'adresse publique, valable 30 minutes", bool(m) and "30 minutes" in txt, txt[:200])
TOKEN = m.group(1) if m else "x" * 43
show("aucun mot de passe dans le message", PW not in txt and "mot de passe provisoire" not in txt.lower())
j("POST", "/auth/forgot", {"identifiant": "sec_rs_sansmail"})
j("POST", "/auth/forgot", {"identifiant": "sec_rs_off"})
time.sleep(1.5)
show("pas de message pour un compte inconnu, sans e-mail ou desactive",
     not [x for x in INBOX if x["X-Test-Rcpt"] not in ("zzrs1@exemple.test",)])
s, r = j("POST", "/auth/forgot", {"identifiant": "zzrs1@exemple.test"})
mails = attendre("zzrs1@exemple.test", 2)
show("recherche aussi par adresse e-mail ; un nouveau lien remplace le precedent", s == 202 and len(mails) == 2)
m2 = re.search(r"token=([A-Za-z0-9_-]{20,})", corps(mails[-1])) if len(mails) > 1 else None
TOKEN2 = m2.group(1) if m2 else "y" * 43
s, r = j("POST", "/auth/reset", {"token": TOKEN, "new_password": NEW_PW})
show("l'ancien lien est invalide", s == 400, (s, r))

print("== Choix du nouveau mot de passe ==")
old = login("sec_rs1", PW)
show("connexion avec l'ancien mot de passe avant la reinitialisation", bool(old))
s, r = j("POST", "/auth/reset", {"token": TOKEN2, "new_password": "court"})
show("mot de passe trop court refuse, le lien reste utilisable", s == 400, (s, r))
s, r = j("POST", "/auth/reset", {"token": TOKEN2, "new_password": NEW_PW})
show("reinitialisation par le lien", s == 200, (s, r))
new = login("sec_rs1", NEW_PW)
show("connexion avec le nouveau mot de passe", bool(new) and new["must_change_password"] is False, new)
show("l'ancien mot de passe ne fonctionne plus", login("sec_rs1", PW) is None)
s, r = call("GET", "/auth/me", token=old["access_token"]) if old else (0, b"")
show("les sessions ouvertes sont revoquees", s == 401, s)
s, r = j("POST", "/auth/reset", {"token": TOKEN2, "new_password": NEW_PW + "x"})
show("un lien utilise ne sert qu'une fois", s == 400, (s, r))

print("== Expiration et limites ==")
sys.path.insert(0, "/app")
from sqlmodel import Session, select  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import PasswordResetToken  # noqa: E402

with Session(engine) as ses:
    stocke = ses.exec(select(PasswordResetToken)).all()
    show("seule l'empreinte du lien est stockee", all(t.token_hash not in (TOKEN, TOKEN2) and len(t.token_hash) == 64 for t in stocke)
         and all(hashlib.sha256(x.encode()).hexdigest() != x for x in (TOKEN, TOKEN2)))
    brut = "expire-" + "z" * 40
    ses.add(PasswordResetToken(account_id=a1, token_hash=hashlib.sha256(brut.encode()).hexdigest(),
                               expire_le=datetime.utcnow() - timedelta(minutes=1)))
    ses.commit()
s, r = j("POST", "/auth/reset", {"token": brut, "new_password": NEW_PW + "y"})
show("un lien expire est refuse", s == 400, (s, r))
s, r = j("POST", "/auth/reset", {"token": "autre-" + "w" * 40, "new_password": NEW_PW + "y"})
show("trop d'essais de liens invalides : 429", s == 429, (s, r))
for _ in range(3):
    s, r = j("POST", "/auth/forgot", {"identifiant": "sec_rs_rafale"})
s, r = j("POST", "/auth/forgot", {"identifiant": "sec_rs_rafale"})
show("trop de demandes pour un meme identifiant : 429", s == 429, (s, r))
j("PUT", "/mail/config", {**BASE, "actif": False}, ADM)

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
