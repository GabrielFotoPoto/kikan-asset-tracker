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

"""Stockage des PDF scelles : volume local, partage reseau (SMB) ou partage web (WebDAV).

Principes :
- Le PDF est TOUJOURS ecrit d'abord dans le volume local (tampon durable). Avec un backend
  distant, il est ensuite depose, relu et verifie (SHA-256), puis le tampon est purge.
- Si le partage est indisponible, la signature n'echoue pas : le document reste en local
  (reference "local:...") et sera depose plus tard (sync au demarrage ou POST /storage/sync).
- La base ne garde que la REFERENCE "<backend>:<cle>" (ex. smb:2026/remise_1_....pdf) et
  l'empreinte SHA-256 ; la cle est toujours rangee par annee (AAAA/...).
- Les identifiants du partage viennent de l'environnement, jamais de la base ni des journaux.
"""
import base64
import hashlib
import logging
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

log = logging.getLogger("kikan.filestore")

LOCAL_ROOT = os.environ.get("KIKAN_ARCHIVE_DIR", "/archive")
ACTIVE = os.environ.get("KIKAN_STORAGE_BACKEND", "local").strip().lower()
TIMEOUT = int(os.environ.get("KIKAN_STORAGE_TIMEOUT_SEC", "15"))
BACKENDS = ("local", "smb", "webdav")

_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")


class StorageError(Exception):
    """Erreur de stockage (message sans secret, affichable)."""


def safe_key(key: str) -> str:
    """Cle relative sure : pas de '..', pas de chemin absolu, caracteres restreints."""
    if not _KEY_RE.match(key or "") or any(part in (".", "..") for part in key.split("/")):
        raise StorageError("Cle de stockage invalide")
    return key


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- Backends ---

class LocalBackend:
    name = "local"

    def __init__(self, root: str = LOCAL_ROOT):
        self.root = os.path.realpath(root)

    def _path(self, key: str) -> str:
        path = os.path.realpath(os.path.join(self.root, safe_key(key)))
        if not path.startswith(self.root + os.sep):
            raise StorageError("Chemin hors du volume de stockage")
        return path

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except OSError as exc:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise StorageError(f"Ecriture locale impossible : {exc.strerror or exc}") from exc

    def read(self, key: str) -> bytes:
        try:
            with open(self._path(key), "rb") as f:
                return f.read()
        except FileNotFoundError as exc:
            raise StorageError("Document introuvable") from exc
        except OSError as exc:
            raise StorageError(f"Lecture locale impossible : {exc.strerror or exc}") from exc

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise StorageError(f"Suppression locale impossible : {exc.strerror or exc}") from exc


# Messages lisibles pour les erreurs SMB les plus courantes (reconnues par le nom de la classe).
_SMB_HINTS = {
    "LogonFailure": "authentification refusee (identifiant ou mot de passe)",
    "BadNetworkName": "partage introuvable",
    "AccessDenied": "acces refuse sur le partage",
    "ObjectPathNotFound": "dossier introuvable",
}


class SmbBackend:
    """Partage reseau Windows/Samba (SMB 2/3) en Python pur : aucun montage requis."""
    name = "smb"

    def __init__(self):
        self.server = _env("KIKAN_SMB_SERVER")
        self.share = _env("KIKAN_SMB_SHARE")
        self.base = _env("KIKAN_SMB_PATH").strip("/\\")
        self.user = _env("KIKAN_SMB_USER")
        self.password = os.environ.get("KIKAN_SMB_PASSWORD", "")
        self.domain = _env("KIKAN_SMB_DOMAIN")
        self.port = int(_env("KIKAN_SMB_PORT", "445"))
        # Chiffrement SMB 3 : active par defaut (desactiver seulement si le serveur ne le gere pas).
        self.encrypt = _env("KIKAN_SMB_ENCRYPT", "true").lower() not in ("0", "false", "non", "no")
        # La bibliotheque SMB peut attendre indefiniment (ex. partage inexistant) : delai global impose.
        self.deadline = int(_env("KIKAN_STORAGE_DEADLINE_SEC", str(TIMEOUT * 2)))
        if not (self.server and self.share and self.user):
            raise StorageError("Partage SMB non configure (KIKAN_SMB_SERVER, KIKAN_SMB_SHARE, KIKAN_SMB_USER)")
        if self.base:
            safe_key(self.base.replace("\\", "/"))
        self._registered = False
        self._lock = threading.Lock()

    def _smbclient(self):
        try:
            import smbclient
        except ImportError as exc:  # pragma: no cover
            raise StorageError("Bibliotheque SMB absente") from exc
        with self._lock:
            if not self._registered:
                username = f"{self.domain}\\{self.user}" if self.domain else self.user
                smbclient.register_session(
                    self.server, username=username, password=self.password, port=self.port,
                    encrypt=self.encrypt, connection_timeout=TIMEOUT,
                )
                self._registered = True
        return smbclient

    def _unc(self, key: str) -> str:
        parts = [self.server, self.share] + ([self.base] if self.base else []) + safe_key(key).split("/")
        return "\\\\" + "\\".join(parts)

    def _reset(self) -> None:
        """Ferme les connexions SMB (debloque aussi un appel reste en attente) et force une nouvelle session."""
        self._registered = False
        try:
            import smbclient
            smbclient.reset_connection_cache()
        except Exception:  # noqa: BLE001
            pass

    def _wrap(self, action: str, exc: Exception) -> StorageError:
        self._reset()
        name = type(exc).__name__
        detail = next((text for key, text in _SMB_HINTS.items() if key in name), name)
        return StorageError(f"Partage SMB : {action} impossible ({detail})")

    def _run(self, action: str, op):
        """Execute op dans un fil de travail avec un delai maximal."""
        box: dict = {}

        def target():
            try:
                box["value"] = op()
            except BaseException as exc:  # noqa: BLE001
                box["error"] = exc

        worker = threading.Thread(target=target, daemon=True, name="kikan-smb")
        worker.start()
        worker.join(self.deadline)
        if worker.is_alive():
            self._reset()
            raise StorageError(f"Partage SMB : {action} sans reponse apres {self.deadline} s "
                               "(verifier le nom du serveur et du partage)")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def _guarded(self, action: str, op):
        try:
            return self._run(action, op)
        except (StorageError, FileNotFoundError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(action, exc) from exc

    def write(self, key: str, data: bytes) -> None:
        def op():
            smb = self._smbclient()
            smb.makedirs(self._unc(key).rsplit("\\", 1)[0], exist_ok=True)
            with smb.open_file(self._unc(key), mode="wb") as f:
                f.write(data)

        self._guarded("ecriture", op)

    def read(self, key: str) -> bytes:
        def op():
            with self._smbclient().open_file(self._unc(key), mode="rb") as f:
                return f.read()

        try:
            return self._guarded("lecture", op)
        except FileNotFoundError as exc:
            raise StorageError("Document introuvable sur le partage SMB") from exc

    def delete(self, key: str) -> None:
        try:
            self._guarded("suppression", lambda: self._smbclient().remove(self._unc(key)))
        except FileNotFoundError:
            pass


class WebDavBackend:
    """Partage de fichiers web (WebDAV, HTTPS) : MKCOL / PUT / GET / DELETE."""
    name = "webdav"

    def __init__(self):
        self.base_url = _env("KIKAN_WEBDAV_URL").rstrip("/")
        token = os.environ.get("KIKAN_WEBDAV_TOKEN", "")
        user = _env("KIKAN_WEBDAV_USER")
        password = os.environ.get("KIKAN_WEBDAV_PASSWORD", "")
        if not self.base_url:
            raise StorageError("Partage WebDAV non configure (KIKAN_WEBDAV_URL)")
        scheme = urllib.parse.urlparse(self.base_url).scheme
        if scheme not in ("http", "https"):
            raise StorageError("KIKAN_WEBDAV_URL doit commencer par http:// ou https://")
        if scheme == "http" and _env("KIKAN_WEBDAV_ALLOW_HTTP", "false").lower() not in ("1", "true", "oui", "yes"):
            raise StorageError("WebDAV en HTTP refuse (identifiants en clair) : utilisez https:// "
                               "ou KIKAN_WEBDAV_ALLOW_HTTP=true sur un reseau de confiance")
        if token:
            self._auth = "Bearer " + token
        elif user:
            self._auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        else:
            self._auth = ""
        # La verification du certificat du serveur est TOUJOURS active. Il n'existe volontairement
        # aucune option pour la desactiver : pour une autorite interne ou un certificat auto-signe,
        # fournir l'autorite avec KIKAN_WEBDAV_CA_BUNDLE.
        if _env("KIKAN_WEBDAV_VERIFY_TLS").lower() in ("0", "false", "non", "no"):
            log.warning("KIKAN_WEBDAV_VERIFY_TLS a ete supprimee et est ignoree : la verification du "
                        "certificat reste active (utilisez KIKAN_WEBDAV_CA_BUNDLE).")
        self._ctx = ssl.create_default_context(cafile=_env("KIKAN_WEBDAV_CA_BUNDLE") or None)

    def _url(self, key: str) -> str:
        return self.base_url + "/" + "/".join(urllib.parse.quote(p) for p in safe_key(key).split("/"))

    def _request(self, method: str, url: str, data: bytes | None = None, ok=(200, 201, 204)) -> bytes:
        headers = {"User-Agent": "Kikan"}
        if self._auth:
            headers["Authorization"] = self._auth
        if data is not None:
            headers["Content-Type"] = "application/octet-stream"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=self._ctx) as resp:
                if resp.status not in ok:
                    raise StorageError(f"Partage WebDAV : reponse inattendue ({resp.status})")
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in ok:
                return b""
            if exc.code == 404:
                raise FileNotFoundError(url) from exc
            raise StorageError(f"Partage WebDAV : {method} refuse (HTTP {exc.code})") from exc
        except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise StorageError("Partage WebDAV : certificat du serveur non reconnu "
                                   "(fournir l'autorite avec KIKAN_WEBDAV_CA_BUNDLE)") from exc
            raise StorageError(f"Partage WebDAV injoignable ({type(reason).__name__})") from exc

    def _ensure_dirs(self, key: str) -> None:
        parts = safe_key(key).split("/")[:-1]
        for i in range(len(parts)):
            url = self._url("/".join(parts[: i + 1]))
            self._request("MKCOL", url, ok=(200, 201, 204, 301, 405))  # 405 = existe deja

    def write(self, key: str, data: bytes) -> None:
        self._ensure_dirs(key)
        self._request("PUT", self._url(key), data=data)

    def read(self, key: str) -> bytes:
        try:
            return self._request("GET", self._url(key), ok=(200,))
        except FileNotFoundError as exc:
            raise StorageError("Document introuvable sur le partage WebDAV") from exc

    def delete(self, key: str) -> None:
        try:
            self._request("DELETE", self._url(key), ok=(200, 202, 204))
        except FileNotFoundError:
            pass


# --- Acces aux backends ---

_instances: dict[str, object] = {}
_instances_lock = threading.Lock()


def get_backend(name: str):
    if name not in BACKENDS:
        raise StorageError(f"Backend de stockage inconnu : {name}")
    with _instances_lock:
        if name not in _instances:
            _instances[name] = {"local": LocalBackend, "smb": SmbBackend, "webdav": WebDavBackend}[name]()
        return _instances[name]


def active_name() -> str:
    if ACTIVE not in BACKENDS:
        raise StorageError(f"KIKAN_STORAGE_BACKEND invalide : {ACTIVE} (local, smb ou webdav)")
    return ACTIVE


# --- References ---

def make_reference(backend: str, key: str) -> str:
    return f"{backend}:{safe_key(key)}"


def parse_reference(ref: str) -> tuple[str, str]:
    """'smb:2026/x.pdf' -> ('smb', '2026/x.pdf'). Ancien format : chemin absolu local."""
    if not ref:
        raise StorageError("Aucune reference de document")
    head, sep, tail = ref.partition(":")
    if sep and head in BACKENDS:
        return head, safe_key(tail)
    if ref.startswith(LOCAL_ROOT.rstrip("/") + "/"):  # compatibilite avec les anciennes lignes
        return "local", safe_key(ref[len(LOCAL_ROOT.rstrip("/")) + 1:])
    raise StorageError("Reference de document non reconnue")


def is_pending(ref: str | None) -> bool:
    """Document encore dans le tampon local alors qu'un partage distant est configure."""
    if not ref or ACTIVE == "local":
        return False
    try:
        return parse_reference(ref)[0] == "local"
    except StorageError:
        return False


# --- API haut niveau ---

def _push_verified(backend_name: str, key: str, data: bytes) -> None:
    remote = get_backend(backend_name)
    remote.write(key, data)
    if sha256_hex(remote.read(key)) != sha256_hex(data):
        raise StorageError("Verification du depot echouee (empreinte differente)")


def store_document(key: str, data: bytes) -> str:
    """Enregistre un PDF scelle et renvoie sa reference (jamais d'echec si le local fonctionne)."""
    safe_key(key)
    local = get_backend("local")
    local.write(key, data)  # tampon durable : si ceci echoue, la signature doit echouer
    target = active_name()
    if target == "local":
        return make_reference("local", key)
    try:
        _push_verified(target, key, data)
    except Exception as exc:  # noqa: BLE001
        from .audit import audit
        log.error("Depot sur %s differe pour %s : %s", target, key, exc)
        audit("systeme", "depot_differe", target=key, detail=f"{target}: {exc}"[:500])
        return make_reference("local", key)
    local.delete(key)  # tampon purge uniquement apres depot verifie
    return make_reference(target, key)


def read_document(reference: str) -> bytes:
    backend, key = parse_reference(reference)
    return get_backend(backend).read(key)


def delete_document(reference: str) -> None:
    try:
        backend, key = parse_reference(reference)
        get_backend(backend).delete(key)
    except StorageError as exc:
        log.warning("Suppression du document impossible : %s", exc)


def check_active() -> dict:
    """Ecrit, relit et supprime un petit fichier de test sur le backend actif."""
    name = active_name()
    started = time.time()
    key = f"_kikan_test/{uuid.uuid4().hex}.txt"
    payload = b"kikan storage check " + uuid.uuid4().bytes
    try:
        backend = get_backend(name)
        backend.write(key, payload)
        ok = backend.read(key) == payload
        backend.delete(key)
        return {"backend": name, "ok": ok, "latency_ms": int((time.time() - started) * 1000),
                "detail": "ecriture, lecture et suppression reussies" if ok else "contenu relu different"}
    except StorageError as exc:
        return {"backend": name, "ok": False, "latency_ms": int((time.time() - started) * 1000), "detail": str(exc)}


def sync_pending(session) -> dict:
    """Depose sur le partage distant les documents restes dans le tampon local."""
    from sqlmodel import select
    from .models import Signature

    result = {"active": ACTIVE, "pending": 0, "synced": 0, "failed": 0, "errors": []}
    if ACTIVE == "local":
        return result
    for sig in session.exec(select(Signature)).all():
        if not is_pending(sig.ged_reference):
            continue
        result["pending"] += 1
        try:
            _, key = parse_reference(sig.ged_reference)
            data = get_backend("local").read(key)
            if sig.empreinte_doc and sha256_hex(data) != sig.empreinte_doc:
                raise StorageError("Empreinte du tampon local differente de celle enregistree")
            _push_verified(ACTIVE, key, data)
            sig.ged_reference = make_reference(ACTIVE, key)
            session.add(sig)
            session.commit()
            get_backend("local").delete(key)
            result["synced"] += 1
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            result["failed"] += 1
            result["errors"].append({"signature_id": sig.id, "detail": str(exc)[:200]})
    return result
