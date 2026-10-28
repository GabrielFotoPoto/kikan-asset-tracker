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

"""Garde-fous des backends SMB et WebDAV (configuration erronee, serveur absent, delais).

A lancer avec les serveurs de test demarres (tests/storage-test-servers.yml) et le certificat
de test monte dans l'API (tests/storage-test.override.yml) :
  docker exec -i kikan-api python - < tests/storage_guards.py
Code de sortie 1 si un test echoue.
"""
import os
import sys
import time

sys.path.insert(0, "/app")
from app import filestore  # noqa: E402

SMB = {"KIKAN_SMB_SERVER": "kikan-test-smb", "KIKAN_SMB_SHARE": "kikan", "KIKAN_SMB_PATH": "remises",
       "KIKAN_SMB_USER": "kikan", "KIKAN_SMB_PASSWORD": "kikan-test-pw-12345", "KIKAN_STORAGE_DEADLINE_SEC": "10"}
CA = os.environ.get("TEST_WEBDAV_CA", "/testca/webdav.crt")
DAV = {"KIKAN_WEBDAV_URL": "https://kikan-test-webdav:8443", "KIKAN_WEBDAV_USER": "kikan",
       "KIKAN_WEBDAV_PASSWORD": "kikan-test-pw-12345", "KIKAN_WEBDAV_CA_BUNDLE": CA}
ALL_KEYS = set(SMB) | set(DAV) | {"KIKAN_WEBDAV_VERIFY_TLS", "KIKAN_WEBDAV_ALLOW_HTTP", "KIKAN_WEBDAV_TOKEN",
                                  "KIKAN_SMB_DOMAIN", "KIKAN_SMB_ENCRYPT"}
fails = 0


def attempt(cls, base, **changes):
    """Construit le backend avec cette configuration et tente ecriture + suppression."""
    try:  # la bibliotheque SMB garde une session par serveur : on repart de zero a chaque cas
        import smbclient
        smbclient.reset_connection_cache()
    except Exception:  # noqa: BLE001
        pass
    for k in ALL_KEYS:
        os.environ.pop(k, None)
    env = dict(base)
    env.update({k: v for k, v in changes.items() if v is not None})
    for k in [k for k, v in changes.items() if v is None]:
        env.pop(k, None)
    os.environ.update(env)
    started = time.time()
    try:
        backend = cls()
        backend.write("_kikan_test/garde-fou.txt", b"x")
        backend.delete("_kikan_test/garde-fou.txt")
        return True, "accepte", time.time() - started
    except filestore.StorageError as exc:
        return False, str(exc), time.time() - started


def expect(name, cls, base, accepted, contains=None, max_seconds=None, **changes):
    global fails
    ok, message, elapsed = attempt(cls, base, **changes)
    good = ok == accepted
    if contains and not accepted:
        good = good and contains.lower() in message.lower()
    if max_seconds is not None:
        good = good and elapsed <= max_seconds
    if not good:
        fails += 1
    print(("PASS " if good else "FAIL ") + f"{name} | {message[:110]} ({elapsed:.1f} s)")


print("== SMB ==")
S = filestore.SmbBackend
expect("configuration normale (SMB 3 chiffre)", S, SMB, True)
expect("mauvais mot de passe refuse, message clair", S, SMB, False, contains="authentification", KIKAN_SMB_PASSWORD="mauvais")
expect("partage inexistant : refuse dans le delai (plus de blocage)", S, SMB, False, max_seconds=16, KIKAN_SMB_SHARE="inexistant")
expect("configuration incomplete refusee", S, SMB, False, contains="non configure", KIKAN_SMB_SERVER=None)
expect("chemin de base dangereux refuse", S, SMB, False, contains="invalide", KIKAN_SMB_PATH="../etc")
expect("serveur inconnu refuse", S, SMB, False, max_seconds=16, KIKAN_SMB_SERVER="serveur-inexistant.invalid")
# Apres un delai depasse, le backend doit rester utilisable (connexions reinitialisees).
expect("apres un echec, la configuration normale refonctionne", S, SMB, True)

print("== WebDAV ==")
W = filestore.WebDavBackend
expect("configuration normale (HTTPS + autorite)", W, DAV, True)
expect("HTTP sans autorisation explicite refuse", W, DAV, False, contains="http refuse", KIKAN_WEBDAV_URL="http://kikan-test-webdav:8443")
expect("mauvais mot de passe refuse", W, DAV, False, contains="401", KIKAN_WEBDAV_PASSWORD="mauvais")
expect("certificat inconnu : message explicite", W, DAV, False, contains="certificat", KIKAN_WEBDAV_CA_BUNDLE=None)
expect("verification TLS desactivee explicitement acceptee", W, DAV, True, KIKAN_WEBDAV_CA_BUNDLE=None, KIKAN_WEBDAV_VERIFY_TLS="false")
expect("schema ftp:// refuse", W, DAV, False, contains="http", KIKAN_WEBDAV_URL="ftp://kikan-test-webdav")
expect("serveur inconnu refuse", W, DAV, False, contains="injoignable", KIKAN_WEBDAV_URL="https://serveur-inexistant.invalid")

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
