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

"""Moteur de stockage DocuWare (Platform REST) pour les PDF scelles.

Compte de service (jeton OAuth2 par le service d'identite de DocuWare), depot dans une armoire avec des champs d'index.
Reference stockee : docuware:<identifiant du document>/<cle Kikan> (l'identifiant sert a relire et a supprimer). Les champs
d'index sont ceux que l'administrateur associe dans KIKAN_DOCUWARE_FIELDS : un champ non associe n'est jamais envoye
(les donnees nominatives ne partent que si vous le decidez). Identifiants dans l'environnement, certificat toujours verifie.
"""
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timezone

from .docname import cle_sans_nom
from .filestore import TIMEOUT, StorageError, _env, safe_key

LOGICAL_FIELDS = ("cle", "type", "annee", "entite", "numero", "matricule", "salarie", "date")
_ID_RE = re.compile(r"^(\d+)/(.+)$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def parse_fields(spec: str) -> dict[str, tuple[str, str]]:
    """KIKAN_DOCUWARE_FIELDS : JSON {"type": "TYPE_DOC", "date": {"champ": "DATE_REMISE", "type": "Date"}} -> {logique: (champ, type)}."""
    if not spec.strip():
        return {}
    try:
        raw = json.loads(spec)
        out = {}
        for logical, target in raw.items():
            if logical not in LOGICAL_FIELDS:
                raise ValueError(f"champ logique inconnu : {logical}")
            name, kind = (target, "String") if isinstance(target, str) else (target["champ"], target.get("type", "String"))
            if kind not in ("String", "Int", "Date") or not name or len(name) > 100:
                raise ValueError("champ ou type invalide")
            out[logical] = (name, kind)
        return out
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise StorageError(f"KIKAN_DOCUWARE_FIELDS invalide ({exc})") from exc


class DocuWareBackend:
    name = "docuware"

    def __init__(self):
        self.url = _env("KIKAN_DOCUWARE_URL").rstrip("/")      # ex. https://societe.docuware.cloud/DocuWare/Platform
        self.user = _env("KIKAN_DOCUWARE_USER")
        self.password = _env("KIKAN_DOCUWARE_PASSWORD") or ""
        self.cabinet = _env("KIKAN_DOCUWARE_CABINET")           # nom ou identifiant (GUID) de l'armoire
        missing = [n for n, v in (("KIKAN_DOCUWARE_URL", self.url), ("KIKAN_DOCUWARE_USER", self.user),
                                  ("KIKAN_DOCUWARE_PASSWORD", self.password), ("KIKAN_DOCUWARE_CABINET", self.cabinet)) if not v]
        if missing:
            raise StorageError("DocuWare non configure : " + ", ".join(missing))
        if urllib.parse.urlparse(self.url).scheme != "https" and _env("KIKAN_DOCUWARE_ALLOW_HTTP", "false").lower() not in ("1", "true", "oui", "yes"):
            raise StorageError("DocuWare en HTTP refuse (identifiants en clair) : utilisez https")
        self.fields = parse_fields(_env("KIKAN_DOCUWARE_FIELDS"))
        ctx = ssl.create_default_context(cafile=_env("KIKAN_DOCUWARE_CA_BUNDLE") or None)
        proxy = _env("KIKAN_DOCUWARE_PROXY")
        self._opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(context=ctx),
            urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_until = 0.0
        self._identity: str | None = None
        self._cabinet_id: str | None = None

    def describe(self) -> dict:
        return {"armoire": self.cabinet, "champs_associes": sorted(self.fields) or ["aucun"]}

    # ------------------------------------------------------------------ transport
    def _raw(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "Kikan", **(headers or {})})
        try:
            with self._opener.open(req, timeout=TIMEOUT) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read(1_000_000)
        except ssl.SSLError as exc:
            raise StorageError("DocuWare : echec TLS (certificat ou protocole ; KIKAN_DOCUWARE_CA_BUNDLE)") from exc
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise StorageError("DocuWare : certificat du serveur non reconnu (KIKAN_DOCUWARE_CA_BUNDLE)") from exc
            raise StorageError(f"DocuWare injoignable ({type(reason).__name__})") from exc

    def _identity_url(self) -> str:
        if self._identity:
            return self._identity
        status, _, raw = self._raw("GET", f"{self.url}/Home/IdentityServiceInfo", headers={"Accept": "application/json"})
        if status != 200:
            raise StorageError(f"DocuWare : service d'identite introuvable (HTTP {status} ; KIKAN_DOCUWARE_URL ?)")
        try:
            self._identity = json.loads(raw)["IdentityServiceUrl"].rstrip("/")
        except (ValueError, KeyError) as exc:
            raise StorageError("DocuWare : reponse du service d'identite inattendue") from exc
        return self._identity

    def _access_token(self, force: bool = False) -> str:
        with self._lock:
            if not force and self._token and time.time() < self._token_until - 60:
                return self._token
            body = urllib.parse.urlencode({"grant_type": "password", "scope": "docuware.platform", "client_id": "docuware.platform.net.client",
                                           "username": self.user, "password": self.password}).encode()
            status, _, raw = self._raw("POST", f"{self._identity_url()}/connect/token", body,
                                       {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
            if status != 200:
                raise StorageError("DocuWare : authentification refusee (compte de service, mot de passe ou droits)")
            try:
                payload = json.loads(raw)
                self._token = payload["access_token"]
                self._token_until = time.time() + int(payload.get("expires_in", 3600))
            except (ValueError, KeyError) as exc:
                raise StorageError("DocuWare : reponse d'authentification inattendue") from exc
            return self._token

    def _call(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None, ok=(200,)) -> tuple[int, dict, bytes]:
        for attempt in range(3):
            hdrs = {"Authorization": "Bearer " + self._access_token(), "Accept": "application/json", **(headers or {})}
            status, resp_headers, raw = self._raw(method, self.url + path, data, hdrs)
            if status == 401 and attempt == 0:
                self._access_token(force=True)
                continue
            if status in (429, 503) and attempt < 2:
                time.sleep(min(10, int(resp_headers.get("Retry-After", "2") or 2)))
                continue
            break
        if status in ok:
            return status, resp_headers, raw
        if status == 404:
            raise FileNotFoundError(path)
        if status in (401, 403):
            raise StorageError("DocuWare : droits insuffisants pour le compte de service sur cette armoire")
        detail = ""
        try:
            parsed = json.loads(raw)
            detail = str(parsed.get("Message") or parsed.get("message") or "")[:160]
        except (ValueError, AttributeError):
            pass
        raise StorageError(f"DocuWare : {method} refuse (HTTP {status}{' : ' + detail if detail else ''})")

    def _cabinet(self) -> str:
        if self._cabinet_id:
            return self._cabinet_id
        _, _, raw = self._call("GET", "/FileCabinets")
        for c in json.loads(raw).get("FileCabinet", []):
            if not c.get("IsBasket") and (c.get("Name", "").lower() == self.cabinet.lower() or c.get("Id", "").lower() == self.cabinet.lower()):
                self._cabinet_id = c["Id"]
                return self._cabinet_id
        raise StorageError(f"DocuWare : armoire « {self.cabinet} » introuvable (KIKAN_DOCUWARE_CABINET)")

    # ------------------------------------------------------------------ indexation
    def _index(self, key: str, meta: dict | None) -> dict:
        values = {"cle": cle_sans_nom(key), **(meta or {})}
        values.setdefault("annee", key.split("/")[0] if "/" in key else "")
        fields = []
        for logical, (name, kind) in self.fields.items():
            value = values.get(logical)
            if value in (None, ""):
                continue
            if kind == "Int":
                try:
                    fields.append({"FieldName": name, "Item": int(value), "ItemElementName": "Int"})
                except (TypeError, ValueError):
                    continue
            elif kind == "Date":
                try:
                    d = value if isinstance(value, date) else datetime.fromisoformat(str(value)).date()
                    ms = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
                    fields.append({"FieldName": name, "Item": f"/Date({ms})/", "ItemElementName": "Date"})
                except ValueError:
                    continue
            else:
                fields.append({"FieldName": name, "Item": str(value)[:250], "ItemElementName": "String"})
        return {"Fields": fields}

    @staticmethod
    def _multipart(index: dict, filename: str, data: bytes) -> tuple[bytes, str]:
        boundary = "kikan" + uuid.uuid4().hex
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"\r\nContent-Type: application/json\r\n\r\n"
                f"{json.dumps(index)}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file[]\"; filename=\"{filename}\"\r\n"
                "Content-Type: application/pdf\r\n\r\n").encode()
        return head + data + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"

    # ------------------------------------------------------------------ interface commune des moteurs
    def write(self, key: str, data: bytes, meta: dict | None = None) -> str | None:
        safe_key(key)
        body, ctype = self._multipart(self._index(key, meta), key.rsplit("/", 1)[-1], data)
        _, _, raw = self._call("POST", f"/FileCabinets/{self._cabinet()}/Documents", body, {"Content-Type": ctype}, ok=(200, 201))
        try:
            doc_id = int(json.loads(raw)["Id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise StorageError("DocuWare : identifiant du document absent de la reponse") from exc
        return f"{doc_id}/{key}"

    @staticmethod
    def _doc_id(key: str) -> int:
        m = _ID_RE.match(key or "")
        if not m:
            raise StorageError("Reference DocuWare sans identifiant de document")
        return int(m.group(1))

    def read(self, key: str) -> bytes:
        try:
            _, _, raw = self._call("GET", f"/FileCabinets/{self._cabinet()}/Documents/{self._doc_id(key)}/FileDownload?targetFileType=Auto",
                                   headers={"Accept": "application/pdf, application/octet-stream, */*"})
        except FileNotFoundError as exc:
            raise StorageError("Document introuvable dans DocuWare") from exc
        return raw

    def delete(self, key: str) -> None:
        try:
            self._call("DELETE", f"/FileCabinets/{self._cabinet()}/Documents/{self._doc_id(key)}", ok=(200, 204))
        except FileNotFoundError:
            pass
