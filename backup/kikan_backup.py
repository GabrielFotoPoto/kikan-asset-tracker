#!/usr/bin/env python3
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

"""Sauvegarde et restauration de Kikan : base PostgreSQL, PDF scelles, cles de scellement, certificat HTTPS et fichier .env.

Une sauvegarde est UNE archive chiffree (age, cle publique) : kikan-AAAAMMJJ-HHMMSS.tar.gz.age, avec un manifeste (empreintes
SHA-256 de chaque element). Elle est deposee sur un partage reseau (SMB) ou dans un dossier, relue et comparee, puis les
anciennes sont supprimees selon la retention (tout ce qui a moins de N jours, plus la premiere sauvegarde de chaque mois pendant
M mois ; la plus recente n'est jamais supprimee). La cle privee n'est jamais sur le serveur.

  kikan_backup.py keygen --out /keys
  kikan_backup.py backup
  kikan_backup.py list
  kikan_backup.py restore <archive> --identity /keys/identity.txt [--force]
  kikan_backup.py verify
  kikan_backup.py status
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

VERSION = 1
NAME_RE = re.compile(r"^kikan-(\d{8})-(\d{6})\.tar\.gz\.age$")
RECIPIENT_RE = re.compile(r"^age1[0-9a-z]{50,}$")
KIKAN_UID = 10001


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def roots() -> dict:
    base = Path(env("KIKAN_BACKUP_DATA_ROOT", "/data"))
    return {"archive": base / "archive", "certs": base / "certs", "webcerts": base / "webcerts"}


def say(msg: str) -> None:
    print(msg, flush=True)


class BackupError(Exception):
    """Echec de sauvegarde ou de restauration (message sans secret)."""


# ----------------------------------------------------------------------------- retention (fonction pure, testee)

def parse_name(name: str) -> dt.datetime | None:
    m = NAME_RE.match(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def select_deletions(names: list[str], now: dt.datetime, keep_days: int = 30, keep_months: int = 12) -> list[str]:
    """Noms a supprimer. On garde : tout ce qui a moins de `keep_days` jours ; la PREMIERE sauvegarde de chaque mois civil, tant que ce
    mois a au plus `keep_months` mois ; la plus recente dans tous les cas. Les noms inconnus ne sont jamais supprimes."""
    dated = sorted((parse_name(n), n) for n in names if parse_name(n))
    if not dated:
        return []
    keep = {dated[-1][1]}
    first_of_month: dict[tuple[int, int], str] = {}
    for when, name in dated:
        first_of_month.setdefault((when.year, when.month), name)
    cutoff = now - dt.timedelta(days=keep_days)
    month_index = now.year * 12 + now.month
    for when, name in dated:
        if when >= cutoff:
            keep.add(name)
        elif month_index - (when.year * 12 + when.month) <= keep_months and first_of_month[(when.year, when.month)] == name:
            keep.add(name)
    return [name for _, name in dated if name not in keep]


# ----------------------------------------------------------------------------- destinations

class LocalDest:
    label = "dossier"

    def __init__(self, path: str):
        self.root = Path(path)
        if not self.root.is_dir():
            raise BackupError(f"Dossier de destination introuvable : {path}")

    def list(self) -> list[tuple[str, int]]:
        return [(p.name, p.stat().st_size) for p in self.root.iterdir() if p.is_file()]

    def put(self, name: str, src: Path) -> None:
        tmp = self.root / (name + ".partial")
        shutil.copyfile(src, tmp)
        tmp.replace(self.root / name)

    def get(self, name: str, dst: Path) -> None:
        shutil.copyfile(self.root / name, dst)

    def sha256(self, name: str) -> str:
        return file_sha256(self.root / name)

    def delete(self, name: str) -> None:
        (self.root / name).unlink(missing_ok=True)

    def describe(self) -> str:
        return f"dossier {self.root}"


class SmbDest:
    label = "partage reseau"

    def __init__(self):
        self.server = env("KIKAN_BACKUP_SMB_SERVER")
        self.share = env("KIKAN_BACKUP_SMB_SHARE")
        self.base = env("KIKAN_BACKUP_SMB_PATH").strip("/\\")
        self.user = env("KIKAN_BACKUP_SMB_USER")
        self.password = os.environ.get("KIKAN_BACKUP_SMB_PASSWORD", "")
        self.domain = env("KIKAN_BACKUP_SMB_DOMAIN")
        self.port = int(env("KIKAN_BACKUP_SMB_PORT", "445"))
        self.encrypt = env("KIKAN_BACKUP_SMB_ENCRYPT", "true").lower() not in ("0", "false", "non", "no")
        if not (self.server and self.share and self.user):
            raise BackupError("Partage de sauvegarde non configure (KIKAN_BACKUP_SMB_SERVER, _SHARE, _USER)")
        if re.search(r"[^A-Za-z0-9_.\-/\\ ]", self.base):
            raise BackupError("KIKAN_BACKUP_SMB_PATH invalide")
        import smbclient
        self.smb = smbclient
        username = f"{self.domain}\\{self.user}" if self.domain else self.user
        try:
            smbclient.register_session(self.server, username=username, password=self.password, port=self.port,
                                       encrypt=self.encrypt, connection_timeout=15)
        except Exception as exc:  # noqa: BLE001
            raise BackupError(f"Connexion au partage impossible ({type(exc).__name__}) : serveur, compte ou chiffrement SMB") from exc

    def _unc(self, name: str = "") -> str:
        parts = [self.server, self.share] + ([self.base] if self.base else []) + ([name] if name else [])
        return "\\\\" + "\\".join(parts)

    def _wrap(self, action: str, exc: Exception) -> BackupError:
        return BackupError(f"Partage de sauvegarde : {action} impossible ({type(exc).__name__})")

    def list(self) -> list[tuple[str, int]]:
        try:
            self.smb.makedirs(self._unc(), exist_ok=True)
            return [(e.name, e.stat().st_size) for e in self.smb.scandir(self._unc()) if e.is_file()]
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("lecture du dossier", exc) from exc

    def put(self, name: str, src: Path) -> None:
        try:
            self.smb.makedirs(self._unc(), exist_ok=True)
            with open(src, "rb") as fin, self.smb.open_file(self._unc(name + ".partial"), mode="wb") as fout:
                shutil.copyfileobj(fin, fout, 1024 * 1024)
            try:
                self.smb.remove(self._unc(name))
            except Exception:  # noqa: BLE001
                pass
            self.smb.rename(self._unc(name + ".partial"), self._unc(name))
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("depot", exc) from exc

    def get(self, name: str, dst: Path) -> None:
        try:
            with self.smb.open_file(self._unc(name), mode="rb") as fin, open(dst, "wb") as fout:
                shutil.copyfileobj(fin, fout, 1024 * 1024)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("lecture", exc) from exc

    def sha256(self, name: str) -> str:
        h = hashlib.sha256()
        try:
            with self.smb.open_file(self._unc(name), mode="rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("relecture", exc) from exc
        return h.hexdigest()

    def delete(self, name: str) -> None:
        try:
            self.smb.remove(self._unc(name))
        except Exception as exc:  # noqa: BLE001
            raise self._wrap("suppression", exc) from exc

    def describe(self) -> str:
        return f"partage \\\\{self.server}\\{self.share}" + (f"\\{self.base}" if self.base else "")


def make_dest():
    if env("KIKAN_BACKUP_SMB_SERVER"):
        return SmbDest()
    return LocalDest(env("KIKAN_BACKUP_DEST_DIR", "/backups"))


# ----------------------------------------------------------------------------- utilitaires

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def db_params() -> dict:
    return {"host": env("KIKAN_BACKUP_DB_HOST", "db"), "port": env("KIKAN_BACKUP_DB_PORT", "5432"),
            "user": env("KIKAN_BACKUP_DB_USER", "kikan"), "name": env("KIKAN_BACKUP_DB_NAME", "kikan"),
            "password": os.environ.get("POSTGRES_PASSWORD", "")}


def pg_env() -> dict:
    return {**os.environ, "PGPASSWORD": db_params()["password"]}


def pg_args(prog: str) -> list[str]:
    p = db_params()
    return [prog, "-h", p["host"], "-p", p["port"], "-U", p["user"]]


def run(cmd: list[str], what: str, env_vars: dict | None = None) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, env=env_vars or os.environ, timeout=3600)
    except FileNotFoundError as exc:
        raise BackupError(f"Outil manquant : {cmd[0]}") from exc
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "").strip().splitlines()[-1:] or [""]
        raise BackupError(f"{what} : echec ({tail[0][:200]})")
    return res.stdout


def status_path() -> Path:
    return Path(env("KIKAN_BACKUP_STATUS_DIR", "/status")) / "status.json"


def write_status(update: dict) -> None:
    path = status_path()
    try:
        current = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        current = {}
    current.update(update)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, indent=1))
        tmp.replace(path)
    except OSError:
        say("Avertissement : etat de la sauvegarde non enregistre (dossier d'etat inaccessible)")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# ----------------------------------------------------------------------------- keygen

def cmd_keygen(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    identity = out / "identity.txt"
    if identity.exists():
        raise BackupError(f"{identity} existe deja : cle non remplacee (une cle perdue rend les sauvegardes illisibles)")
    run(["age-keygen", "-o", str(identity)], "Generation de la cle")
    os.chmod(identity, 0o600)
    public = next((line.split(":", 1)[1].strip() for line in identity.read_text().splitlines() if line.startswith("# public key:")), "")
    if not RECIPIENT_RE.match(public):
        raise BackupError("Cle publique introuvable dans le fichier genere")
    (out / "recipient.txt").write_text(public + "\n")
    say("Cle generee.")
    say(f"  Cle PRIVEE (a conserver HORS du serveur, ex. coffre de mots de passe) : {identity}")
    say(f"  Cle PUBLIQUE a placer dans .env : KIKAN_BACKUP_RECIPIENT={public}")
    say("  Sans la cle privee, aucune sauvegarde ne peut etre restauree. Ne la perdez pas, ne la laissez pas sur le serveur.")
    return 0


# ----------------------------------------------------------------------------- backup

def build_manifest(work: Path, sources: list[tuple[str, Path]], pg_version: str) -> dict:
    files = {}
    for arc, path in sources:
        if path.is_dir():
            for p in sorted(path.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    files[f"{arc}/{p.relative_to(path).as_posix()}"] = {"sha256": file_sha256(p), "taille": p.stat().st_size}
        elif path.is_file():
            files[arc] = {"sha256": file_sha256(path), "taille": path.stat().st_size}
    return {"format": VERSION, "cree_le": now_utc().isoformat(timespec="seconds"), "postgresql": pg_version, "fichiers": files}


def cmd_backup(args) -> int:
    started = time.time()
    recipient = env("KIKAN_BACKUP_RECIPIENT")
    try:
        if not RECIPIENT_RE.match(recipient):
            raise BackupError("KIKAN_BACKUP_RECIPIENT absente ou invalide (generer la cle avec : backup keygen)")
        dest = make_dest()
        keep_days = int(env("KIKAN_BACKUP_KEEP_DAYS", "30"))
        keep_months = int(env("KIKAN_BACKUP_KEEP_MONTHS", "12"))
        stamp = now_utc().strftime("%Y%m%d-%H%M%S")
        name = f"kikan-{stamp}.tar.gz.age"
        work = Path(env("KIKAN_BACKUP_WORK", "/work")) / f"run-{stamp}"
        work.mkdir(parents=True, exist_ok=True)
        try:
            say("1/5 Export de la base de donnees (pg_dump)...")
            dump = work / "db.dump"
            run(pg_args("pg_dump") + ["-Fc", "-d", db_params()["name"], "-f", str(dump)], "Export de la base", pg_env())
            run(["pg_restore", "-l", str(dump)], "Controle de l'export", pg_env())
            version = run(pg_args("psql") + ["-d", db_params()["name"], "-tAc", "show server_version"], "Version PostgreSQL", pg_env()).strip()

            say("2/5 Rassemblement des fichiers (PDF scelles, cles, certificat, .env)...")
            sources: list[tuple[str, Path]] = [("db.dump", dump)]
            for arc, path in roots().items():
                if path.is_dir():
                    sources.append((arc, path))
            env_file = Path(env("KIKAN_BACKUP_ENV_FILE", "/config/.env"))
            if env_file.is_file():
                sources.append(("env", env_file))
            manifest = build_manifest(work, sources, version)
            manifest_path = work / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=1))
            plain = work / "kikan.tar.gz"
            with tarfile.open(plain, "w:gz") as tar:
                for arc, path in sources:
                    tar.add(path, arcname=arc, recursive=True)
                tar.add(manifest_path, arcname="manifest.json")

            say("3/5 Chiffrement (age)...")
            enc = work / name
            run(["age", "-r", recipient, "-o", str(enc), str(plain)], "Chiffrement")
            plain.unlink()
            digest = file_sha256(enc)
            sidecar = work / (name + ".sha256")
            sidecar.write_text(f"{digest}  {name}\n")

            say(f"4/5 Depot sur le {dest.describe()}...")
            dest.put(name, enc)
            dest.put(name + ".sha256", sidecar)
            if dest.sha256(name) != digest:
                raise BackupError("Verification du depot echouee (empreinte differente apres relecture)")
            size = enc.stat().st_size
        finally:
            shutil.rmtree(work, ignore_errors=True)

        say("5/5 Retention...")
        listing = [n for n, _ in dest.list()]
        archives = [n for n in listing if NAME_RE.match(n)]
        removed = select_deletions(archives, now_utc(), keep_days, keep_months)
        for old in removed:
            dest.delete(old)
            if old + ".sha256" in listing:
                dest.delete(old + ".sha256")
        kept = len(archives) - len(removed)
        write_status({"dernier_succes": now_utc().isoformat(timespec="seconds"), "fichier": name, "taille": size, "conserves": kept,
                      "supprimees": len(removed), "destination": dest.describe(), "duree_s": int(time.time() - started),
                      "dernier_echec": None, "message": None, "retention": f"{keep_days} jours + 1 par mois sur {keep_months} mois"})
        say(f"Sauvegarde terminee : {name} ({size // 1024} Kio), {kept} sauvegarde(s) conservee(s), {len(removed)} supprimee(s).")
        return 0
    except BackupError as exc:
        write_status({"dernier_echec": now_utc().isoformat(timespec="seconds"), "message": str(exc)[:300]})
        say(f"ECHEC de la sauvegarde : {exc}")
        return 1


def cmd_list(args) -> int:
    dest = make_dest()
    rows = sorted((n, s) for n, s in dest.list() if NAME_RE.match(n))
    if not rows:
        say("Aucune sauvegarde.")
    for name, size in rows:
        when = parse_name(name)
        say(f"{name}  {size // 1024:>8} Kio  ({(now_utc() - when).days} jour(s))")
    return 0


def cmd_status(args) -> int:
    path = status_path()
    say(path.read_text() if path.exists() else "Aucune sauvegarde enregistree.")
    return 0


# ----------------------------------------------------------------------------- restauration et verification

def verify_manifest(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("format") != VERSION:
        raise BackupError("Format de sauvegarde inconnu")
    for rel, info in manifest["fichiers"].items():
        path = root / rel
        if not path.is_file() or file_sha256(path) != info["sha256"]:
            raise BackupError(f"Contenu altere ou manquant dans la sauvegarde : {rel}")
    return manifest


def db_has_tables() -> bool:
    out = run(pg_args("psql") + ["-d", db_params()["name"], "-tAc",
                                 "select count(*) from information_schema.tables where table_schema='public'"], "Lecture de la base", pg_env())
    return int(out.strip() or 0) > 0


def dir_has_files(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def cmd_restore(args) -> int:
    try:
        archive = Path(args.archive)
        work = Path(env("KIKAN_BACKUP_WORK", "/work")) / "restore"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        try:
            if not archive.is_file():
                name = args.archive
                if not NAME_RE.match(name):
                    raise BackupError(f"Archive introuvable : {args.archive}")
                say("Telechargement depuis le partage de sauvegarde...")
                archive = work / name
                make_dest().get(name, archive)
            sidecar = archive.with_name(archive.name + ".sha256")
            if sidecar.is_file():
                expected = sidecar.read_text().split()[0]
                if file_sha256(archive) != expected:
                    raise BackupError("Archive alteree (empreinte differente de celle enregistree)")
            say("1/5 Dechiffrement...")
            if not Path(args.identity).is_file():
                raise BackupError(f"Cle privee introuvable : {args.identity}")
            plain = work / "kikan.tar.gz"
            run(["age", "-d", "-i", args.identity, "-o", str(plain), str(archive)], "Dechiffrement (cle privee incorrecte ou archive alteree)")
            say("2/5 Verification du contenu (manifeste et empreintes)...")
            extract = work / "extract"
            extract.mkdir()
            with tarfile.open(plain, "r:gz") as tar:
                tar.extractall(extract, filter="data")
            manifest = verify_manifest(extract)
            say(f"    sauvegarde du {manifest['cree_le']} (PostgreSQL {manifest['postgresql']}), {len(manifest['fichiers'])} fichier(s) conforme(s)")

            say("3/5 Controle de la destination...")
            targets = roots()
            problems = []
            if db_has_tables():
                problems.append("la base de destination n'est pas vide")
            problems += [f"le dossier {t} n'est pas vide" for t in targets.values() if dir_has_files(t)]
            if problems and not args.force:
                raise BackupError("Restauration refusee : " + " ; ".join(problems) +
                                  ". Faites d'abord une sauvegarde de l'etat actuel, puis relancez avec --force pour ecraser.")

            say("4/5 Restauration de la base...")
            run(pg_args("pg_restore") + ["-d", db_params()["name"], "--clean", "--if-exists", "--no-owner", "--no-privileges",
                                         "--single-transaction", str(extract / "db.dump")], "Restauration de la base", pg_env())
            say("    restauration des fichiers...")
            for arc, target in targets.items():
                src = extract / arc
                if not src.is_dir():
                    continue
                target.mkdir(parents=True, exist_ok=True)
                for child in list(target.iterdir()):
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                shutil.copytree(src, target, dirs_exist_ok=True)
                if arc in ("archive", "certs"):  # appartiennent a l'utilisateur de l'API
                    for p in [target, *target.rglob("*")]:
                        os.chown(p, KIKAN_UID, KIKAN_UID)
            out = Path(env("KIKAN_BACKUP_OUT", "/out"))
            if (extract / "env").is_file() and out.is_dir():
                shutil.copyfile(extract / "env", out / "env.restored")
                os.chmod(out / "env.restored", 0o600)
                say(f"    fichier .env de la sauvegarde ecrit dans {out / 'env.restored'} (a comparer avec votre .env, jamais remplace automatiquement)")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        say("5/5 Verification apres restauration...")
        return cmd_verify(args)
    except BackupError as exc:
        say(f"ECHEC de la restauration : {exc}")
        return 1
    except (tarfile.TarError, OSError, ValueError, KeyError) as exc:
        say(f"ECHEC de la restauration : archive illisible ({type(exc).__name__})")
        return 1


def cmd_verify(args) -> int:
    """Controle d'integrite : base lisible, migrations, et chaque PDF scelle local relu et compare a son empreinte enregistree."""
    import psycopg2

    p = db_params()
    try:
        conn = psycopg2.connect(host=p["host"], port=p["port"], user=p["user"], dbname=p["name"], password=p["password"], connect_timeout=10)
    except Exception as exc:  # noqa: BLE001
        say(f"Verification impossible : base inaccessible ({type(exc).__name__})")
        return 1
    problems: list[str] = []
    report: dict = {}
    with conn, conn.cursor() as cur:
        cur.execute("select version_num from alembic_version")
        row = cur.fetchone()
        report["migration"] = row[0] if row else None
        if not row:
            problems.append("version de migration absente")
        for table in ("accounts", "users", "assets", "assignments", "signatures"):
            # Faux positif B608 : le nom de table vient du tuple ci-dessus, jamais d'une saisie.
            cur.execute(f"select count(*) from {table}")  # nosec B608
            report[table] = cur.fetchone()[0]
        cur.execute("select id, ged_reference, empreinte_doc from signatures where ged_reference is not null")
        local = external = bad = 0
        archive_root = roots()["archive"]
        for sig_id, ref, digest in cur.fetchall():
            backend, _, key = ref.partition(":")
            if backend == "local" or ref.startswith("/archive/"):
                key = key if backend == "local" else ref[len("/archive/"):]
                path = archive_root / key
                local += 1
                if not path.is_file():
                    bad += 1
                    problems.append(f"PDF manquant (signature {sig_id})")
                elif digest and file_sha256(path) != digest:
                    bad += 1
                    problems.append(f"PDF altere : empreinte differente (signature {sig_id})")
            else:
                external += 1
        report.update({"pdf_locaux_verifies": local, "pdf_alteres_ou_manquants": bad, "pdf_sur_stockage_externe": external})
    conn.close()
    say("Verification : " + json.dumps(report))
    if external:
        say(f"    {external} document(s) sont sur un stockage externe (SMB, WebDAV, SharePoint, DocuWare) : non restaure par cette sauvegarde, a verifier dans Kikan (page Stockage).")
    if problems:
        say("PROBLEMES : " + " ; ".join(problems[:10]))
        return 1
    say("Verification reussie.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="kikan-backup")
    sub = parser.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out", default="/keys")
    sub.add_parser("backup")
    sub.add_parser("list")
    sub.add_parser("status")
    sub.add_parser("verify")
    r = sub.add_parser("restore")
    r.add_argument("archive")
    r.add_argument("--identity", default="/keys/identity.txt")
    r.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        return {"keygen": cmd_keygen, "backup": cmd_backup, "list": cmd_list, "status": cmd_status,
                "verify": cmd_verify, "restore": cmd_restore}[args.cmd](args)
    except BackupError as exc:
        say(f"ERREUR : {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
