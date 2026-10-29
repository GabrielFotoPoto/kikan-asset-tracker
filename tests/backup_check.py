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

"""Sauvegarde et restauration (E7), de bout en bout : sauvegarde reelle, restauration dans une instance VIERGE (reprise apres
sinistre), verification des empreintes, cas d'echec, retention et partage reseau Samba.

A lancer DEPUIS LA MACHINE HOTE, a la racine du projet, pile de DEVELOPPEMENT demarree (la sauvegarde ne modifie rien ; la
restauration se fait dans des conteneurs et volumes jetables kikan-dr-*) :

  python tests/backup_check.py

Cree des donnees ZZBK (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue. ASCII uniquement.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp-backup-test"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:170] if detail else ""), flush=True)


def sh(cmd, env=None, stdin=None, timeout=900):
    full = {**os.environ, **(env or {})}
    r = subprocess.run(cmd, cwd=ROOT, env=full, input=stdin, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def dotenv(key):
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


PG_PW = dotenv("POSTGRES_PASSWORD")
ADMIN_PW = dotenv("KIKAN_ADMIN_PASSWORD")
posix = lambda p: Path(p).as_posix()  # noqa: E731


def psql(container, query, user="kikan", db="kikan"):
    rc, out = sh(["docker", "exec", container, "psql", "-U", user, "-d", db, "-tAc", query])
    return out.strip() if rc == 0 else None


def compose_backup(args, env, extra=None):
    return sh(["docker", "compose", "--profile", "backup", "run", "--rm"] + (extra or []) + ["backup"] + args, env=env)


def dr_restore(args, backups_dir, keys_dir, out_dir, extra_env=None, net="kikan_default", db_host="kikan-dr-db"):
    cmd = ["docker", "run", "--rm", "--network", net, "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER",
           "-e", "POSTGRES_PASSWORD=drpass", "-e", "KIKAN_BACKUP_DB_HOST=" + db_host,
           "-v", "kikan_dr_archive:/data/archive", "-v", "kikan_dr_certs:/data/certs", "-v", "kikan_dr_webcerts:/data/webcerts", "-v", "kikan_dr_work:/work",
           "-v", f"{posix(backups_dir)}:/backups:ro", "-v", f"{posix(keys_dir)}:/keys:ro", "-v", f"{posix(out_dir)}:/out"]
    for k, v in (extra_env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    return sh(cmd + ["kikan-backup"] + args)


def newest(directory):
    files = sorted(p for p in Path(directory).glob("kikan-*.tar.gz.age"))
    return files[-1] if files else None


print("== Preparation ==")
def purge_tmp():
    """Supprime le dossier temporaire, y compris les fichiers crees par les conteneurs (proprietaire root sous Linux)."""
    if TMP.exists():
        sh(["docker", "run", "--rm", "-v", f"{posix(TMP)}:/t", "alpine", "sh", "-c", "rm -rf /t/* /t/.[!.]* 2>/dev/null; true"])
    shutil.rmtree(TMP, ignore_errors=True)


purge_tmp()
TMP.mkdir(exist_ok=True)
for d in ("keys", "keys2", "backups", "backups_bad", "out", "out2"):
    (TMP / d).mkdir(parents=True)
rc, out = sh(["docker", "compose", "--profile", "backup", "build", "backup"])
show("image de sauvegarde construite", rc == 0, out[-200:])
rc, out = sh(["docker", "run", "--rm", "--entrypoint", "python", "kikan-backup", "-m", "unittest", "test_retention"])
show("tests unitaires de la retention", rc == 0 and "OK" in out, out[-120:])

rc, out = sh(["docker", "run", "--rm", "-v", f"{posix(TMP / 'keys')}:/keys", "kikan-backup", "keygen", "--out", "/keys"])
recipient = (TMP / "keys" / "recipient.txt").read_text().strip() if (TMP / "keys" / "recipient.txt").exists() else ""
show("generation de la paire de cles (la cle privee n'est pas affichee)", rc == 0 and recipient.startswith("age1") and "AGE-SECRET-KEY" not in out, out[-150:])
rc, out = sh(["docker", "run", "--rm", "-v", f"{posix(TMP / 'keys')}:/keys", "kikan-backup", "keygen", "--out", "/keys"])
show("la cle existante n'est jamais remplacee", rc != 0 and "existe deja" in out, out[-120:])
rc, out = sh(["docker", "run", "--rm", "-v", f"{posix(TMP / 'keys2')}:/keys", "kikan-backup", "keygen", "--out", "/keys"])

rc, out = sh(["docker", "exec", "-i", "-e", "TEST_ADMIN_USER=admin", "-e", f"TEST_ADMIN_PASSWORD={ADMIN_PW}", "kikan-api", "python", "-"],
             stdin=(ROOT / "tests" / "backup_seed.py").read_text(encoding="utf-8"))
seed = json.loads(re.search(r"SEED:(\{.*\})", out).group(1)) if "SEED:" in out else {}
show("remise signee creee (PDF scelle dans le stockage local)", seed.get("status") == 201 and str(seed.get("reference", "")).startswith("local:"), out[-200:])
KEY = seed["reference"].split(":", 1)[1]
SHA = seed["empreinte"]
COUNTS = {t: psql("kikan-db", f"select count(*) from {t}") for t in ("accounts", "users", "assets", "assignments", "signatures")}
MIG = psql("kikan-db", "select version_num from alembic_version")
show("etat de reference releve", all(v is not None for v in COUNTS.values()) and MIG, (COUNTS, MIG))

print("== Sauvegarde vers un dossier ==")
BENV = {"KIKAN_BACKUP_RECIPIENT": recipient, "KIKAN_BACKUP_DIR": posix(TMP / "backups")}
t0 = time.time()
rc, out = compose_backup(["backup"], BENV)
show("sauvegarde reussie", rc == 0 and "Sauvegarde terminee" in out, out[-250:])
arch = newest(TMP / "backups")
show("archive chiffree et empreinte deposees", arch is not None and (arch.parent / (arch.name + ".sha256")).exists() and arch.stat().st_size > 1000, arch)
blob = arch.read_bytes() if arch else b""
show("l'archive ne contient rien en clair (ni PDF, ni export de base, ni secret)",
     b"%PDF" not in blob and b"PGDMP" not in blob and PG_PW.encode() not in blob and b"POSTGRES_PASSWORD" not in blob and b"manifest" not in blob)
show("empreinte enregistree = empreinte de l'archive", arch and (arch.parent / (arch.name + ".sha256")).read_text().split()[0] == hashlib.sha256(blob).hexdigest())
show("aucune trace de la cle privee dans la sortie", "AGE-SECRET-KEY" not in out and PG_PW not in out)
rc, out = compose_backup(["list"], BENV)
show("liste des sauvegardes", rc == 0 and arch.name in out, out[-150:])
rc, out2 = sh(["docker", "exec", "kikan-api", "python", "-c",
               "import json,urllib.request as u;"
               "t=json.loads(u.urlopen(u.Request('http://localhost:8000/auth/login',data=json.dumps({'username':'admin','password':'%s'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token'];"
               "print(u.urlopen(u.Request('http://localhost:8000/backup/status',headers={'Authorization':'Bearer '+t})).read().decode())" % ADMIN_PW])
st = json.loads(out2) if rc == 0 else {}
show("l'application affiche l'etat de la sauvegarde (a jour, pas d'alerte)", st.get("configure") is True and st.get("alerte") is False and st.get("fichier") == arch.name, out2[:200])

print("== Restauration dans une instance vierge (reprise apres sinistre) ==")
sh(["docker", "rm", "-f", "kikan-dr-db"])
for v in ("kikan_dr_archive", "kikan_dr_certs", "kikan_dr_webcerts", "kikan_dr_work"):
    sh(["docker", "volume", "rm", "-f", v])
rc, out = sh(["docker", "run", "-d", "--name", "kikan-dr-db", "--network", "kikan_default", "-e", "POSTGRES_PASSWORD=drpass", "-e", "POSTGRES_USER=kikan",
              "-e", "POSTGRES_DB=kikan", "postgres:16"])
for _ in range(40):
    if sh(["docker", "exec", "kikan-dr-db", "pg_isready", "-U", "kikan", "-d", "kikan"])[0] == 0:
        break
    time.sleep(2)
time.sleep(3)
show("instance vierge demarree", psql("kikan-dr-db", "select count(*) from information_schema.tables where table_schema='public'") == "0")
rc, out = dr_restore(["restore", f"/backups/{arch.name}", "--identity", "/keys/identity.txt"], TMP / "backups", TMP / "keys", TMP / "out")
show("restauration reussie et verifiee", rc == 0 and "Verification reussie" in out, out[-300:])
rest = {t: psql("kikan-dr-db", f"select count(*) from {t}") for t in COUNTS}
show("memes volumes de donnees que la source", rest == COUNTS, (rest, COUNTS))
show("meme version de migration", psql("kikan-dr-db", "select version_num from alembic_version") == MIG)
rc, shaout = sh(["docker", "run", "--rm", "-v", "kikan_dr_archive:/a:ro", "alpine", "sha256sum", f"/a/{KEY}"])
show("le PDF scelle restaure est identique a l'original (empreinte)", rc == 0 and shaout.split()[0] == SHA, shaout[:100])
# le fichier restaure appartient a root (0600) : on le relit par un conteneur, pas depuis l'hote
rc, envsha = sh(["docker", "run", "--rm", "-v", f"{posix(TMP / 'out')}:/o:ro", "alpine", "sha256sum", "/o/env.restored"])
show("le fichier .env de la sauvegarde est restitue a part, sans remplacer le votre",
     rc == 0 and envsha.split()[0] == hashlib.sha256((ROOT / ".env").read_bytes()).hexdigest(), envsha[:80])
rc, o = sh(["docker", "run", "--rm", "-v", "kikan_dr_certs:/c:ro", "alpine", "sh", "-c", "ls -ln /c | head -5; ls /c | wc -l"])
show("les cles de scellement sont restaurees (propriete de l'utilisateur de l'API)", rc == 0 and "10001" in o, o[:150])

print("== Garde-fous de la restauration ==")
rc, out = dr_restore(["restore", f"/backups/{arch.name}", "--identity", "/keys/identity.txt"], TMP / "backups", TMP / "keys", TMP / "out")
show("restauration sur une base non vide refusee sans --force", rc != 0 and "refusee" in out and "--force" in out, out[-200:])
show("rien n'a ete modifie par le refus", {t: psql("kikan-dr-db", f"select count(*) from {t}") for t in COUNTS} == COUNTS)
rc, out = dr_restore(["restore", f"/backups/{arch.name}", "--identity", "/keys/identity.txt", "--force"], TMP / "backups", TMP / "keys", TMP / "out")
show("avec --force : restauration reussie", rc == 0 and "Verification reussie" in out, out[-200:])
rc, out = dr_restore(["restore", f"/backups/{arch.name}", "--identity", "/keys/identity.txt", "--force"], TMP / "backups", TMP / "keys2", TMP / "out")
show("mauvaise cle privee : refus clair, aucune modification", rc != 0 and "Dechiffrement" in out and {t: psql("kikan-dr-db", f"select count(*) from {t}") for t in COUNTS} == COUNTS, out[-200:])
bad = bytearray(blob)
bad[len(bad) // 2] ^= 0xFF
(TMP / "backups_bad" / arch.name).write_bytes(bytes(bad))
rc, out = dr_restore(["restore", f"/backups/{arch.name}", "--identity", "/keys/identity.txt", "--force"], TMP / "backups_bad", TMP / "keys", TMP / "out")
show("archive alteree sans empreinte : detectee au dechiffrement", rc != 0 and "ECHEC" in out, out[-200:])
(TMP / "backups_bad" / (arch.name + ".sha256")).write_text((arch.parent / (arch.name + ".sha256")).read_text())
rc, out = dr_restore(["restore", f"/backups/{arch.name}", "--identity", "/keys/identity.txt", "--force"], TMP / "backups_bad", TMP / "keys", TMP / "out")
show("archive alteree avec empreinte : detectee avant tout", rc != 0 and "alteree" in out, out[-200:])
rc, out = dr_restore(["restore", "/backups/inexistante.tar.gz.age", "--identity", "/keys/identity.txt", "--force"], TMP / "backups", TMP / "keys", TMP / "out")
show("archive introuvable : message clair", rc != 0 and "introuvable" in out.lower(), out[-150:])

print("== Verification d'integrite ==")
rc, out = dr_restore(["verify"], TMP / "backups", TMP / "keys", TMP / "out")
show("verification d'une instance saine", rc == 0 and '"pdf_locaux_verifies": 1' in out and "Verification reussie" in out, out[-250:])
sh(["docker", "run", "--rm", "-v", "kikan_dr_archive:/a", "alpine", "sh", "-c", f"printf x >> /a/{KEY}"])
rc, out = dr_restore(["verify"], TMP / "backups", TMP / "keys", TMP / "out")
show("un PDF scelle altere est detecte (empreinte differente)", rc != 0 and "PDF altere" in out, out[-250:])
sh(["docker", "run", "--rm", "-v", "kikan_dr_archive:/a", "alpine", "rm", "-f", f"/a/{KEY}"])
rc, out = dr_restore(["verify"], TMP / "backups", TMP / "keys", TMP / "out")
show("un PDF scelle manquant est detecte", rc != 0 and "PDF manquant" in out, out[-250:])
rc, out = dr_restore(["restore", f"/backups/{arch.name}", "--identity", "/keys/identity.txt", "--force"], TMP / "backups", TMP / "keys", TMP / "out")
show("une restauration repare l'instance", rc == 0 and "Verification reussie" in out, out[-150:])

print("== Echec de sauvegarde et alerte ==")
rc, out = compose_backup(["backup"], {**BENV, "KIKAN_BACKUP_RECIPIENT": ""})
show("cle publique absente : echec explicite", rc != 0 and "KIKAN_BACKUP_RECIPIENT" in out, out[-200:])
rc, out = compose_backup(["backup"], {**BENV, "KIKAN_BACKUP_RECIPIENT": "age1pasunevraiecle"})
show("cle publique invalide : echec explicite", rc != 0 and "invalide" in out, out[-200:])
rc, out = compose_backup(["backup"], BENV, ["-e", "KIKAN_BACKUP_DEST_DIR=/destination-inexistante"])
show("destination inexistante : echec explicite", rc != 0 and "introuvable" in out and "ECHEC" in out, out[-200:])
rc, out2 = sh(["docker", "exec", "kikan-api", "python", "-c",
               "import json,urllib.request as u;"
               "t=json.loads(u.urlopen(u.Request('http://localhost:8000/auth/login',data=json.dumps({'username':'admin','password':'%s'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token'];"
               "print(u.urlopen(u.Request('http://localhost:8000/backup/status',headers={'Authorization':'Bearer '+t})).read().decode())" % ADMIN_PW])
st = json.loads(out2) if rc == 0 else {}
show("l'application signale l'echec (alerte)", st.get("alerte") is True and st.get("dernier_echec") and st.get("dernier_succes"), out2[:250])

print("== Retention ==")
now = datetime.utcnow()
old = (now - timedelta(days=400)).replace(day=15, hour=2, minute=0, second=0)
base = now - timedelta(days=80)
first, second = base.replace(day=1, hour=2, minute=0, second=0), base.replace(day=2, hour=2, minute=0, second=0)
recent = (now - timedelta(days=5)).replace(hour=2, minute=0, second=0)
names = {}
for label, when in (("old", old), ("first", first), ("second", second), ("recent", recent)):
    n = when.strftime("kikan-%Y%m%d-%H%M%S.tar.gz.age")
    names[label] = n
    (TMP / "backups" / n).write_bytes(b"x" * 10)
    (TMP / "backups" / (n + ".sha256")).write_text("0  " + n + "\n")
(TMP / "backups" / "notes-de-l-admin.txt").write_text("a ne pas toucher")
rc, out = compose_backup(["backup"], BENV)
left = {p.name for p in (TMP / "backups").iterdir()}
show("sauvegarde avec retention", rc == 0 and "supprimee(s)" in out, out[-200:])
show("plus d'un an : supprimee (avec son empreinte)", names["old"] not in left and names["old"] + ".sha256" not in left, sorted(left))
show("premiere sauvegarde d'un mois ancien : conservee", names["first"] in left)
show("autre sauvegarde ancienne du meme mois : supprimee", names["second"] not in left)
show("sauvegarde de moins de 30 jours : conservee", names["recent"] in left)
show("fichier etranger jamais touche", "notes-de-l-admin.txt" in left)
show("la plus recente est toujours la", newest(TMP / "backups") is not None and newest(TMP / "backups").stat().st_size > 1000)

print("== Partage reseau (Samba) ==")
sh(["docker", "compose", "-f", "tests/storage-test-servers.yml", "up", "-d", "smb"])
time.sleep(8)
SMB = {"KIKAN_BACKUP_RECIPIENT": recipient, "KIKAN_BACKUP_SMB_SERVER": "kikan-test-smb", "KIKAN_BACKUP_SMB_SHARE": "kikan", "KIKAN_BACKUP_SMB_PATH": "sauvegardes-test",
       "KIKAN_BACKUP_SMB_USER": "kikan", "KIKAN_BACKUP_SMB_PASSWORD": "kikan-test-pw-12345"}
rc, out = compose_backup(["backup"], SMB)
show("sauvegarde vers le partage reseau", rc == 0 and "partage" in out and "Sauvegarde terminee" in out, out[-250:])
rc, out = compose_backup(["list"], SMB)
smb_name = re.findall(r"kikan-\d{8}-\d{6}\.tar\.gz\.age", out)
show("la sauvegarde est visible sur le partage", rc == 0 and len(smb_name) == 1, out[-150:])
rc, out = compose_backup(["backup"], {**SMB, "KIKAN_BACKUP_SMB_PASSWORD": "mauvais"})
show("mauvais mot de passe du partage : echec clair, sans le mot de passe", rc != 0 and "mauvais" not in out and "kikan-test-pw-12345" not in out and "Connexion" in out, out[-200:])
sh(["docker", "run", "--rm", "-v", "kikan_dr_archive:/a", "-v", "kikan_dr_certs:/c", "alpine", "sh", "-c", "rm -rf /a/* /c/*"])
rc, out = dr_restore(["restore", smb_name[0], "--identity", "/keys/identity.txt", "--force"], TMP / "backups", TMP / "keys", TMP / "out",
                     extra_env={k: v for k, v in SMB.items() if k.startswith("KIKAN_BACKUP_SMB")})
show("restauration directement depuis le partage reseau", rc == 0 and "Verification reussie" in out, out[-250:])
rc, shaout = sh(["docker", "run", "--rm", "-v", "kikan_dr_archive:/a:ro", "alpine", "sha256sum", f"/a/{KEY}"])
show("le PDF restaure depuis le partage est identique", rc == 0 and shaout.split()[0] == SHA)

print("== Nettoyage ==")
sh(["docker", "rm", "-f", "kikan-dr-db"])
for v in ("kikan_dr_archive", "kikan_dr_certs", "kikan_dr_webcerts", "kikan_dr_work"):
    sh(["docker", "volume", "rm", "-f", v])
sh(["docker", "compose", "-f", "tests/storage-test-servers.yml", "down", "-v"])
purge_tmp()
print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
