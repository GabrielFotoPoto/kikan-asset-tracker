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

"""Moteur de stockage SharePoint Online (Microsoft Graph) pour les PDF scelles.

Application Entra ID (client credentials) avec la permission Sites.Selected limitee au seul site choisi. Les PDF sont
deposes dans une bibliotheque de documents, sous <dossier>/<annee>/<fichier>. Jusqu'a 4 Mio : envoi direct ; au-dela : session
de televersement par blocs. Le secret vient de l'environnement (jamais de la base ni des journaux). Le certificat du serveur
est toujours verifie ; l'adresse de telechargement fournie par Graph est appelee SANS l'en-tete d'autorisation.
"""
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .filestore import TIMEOUT, StorageError, _env, safe_key

SMALL_MAX = 4 * 1024 * 1024          # au-dela : session de televersement
CHUNK = 320 * 1024 * 32              # 10 Mio, multiple de 320 Kio comme l'exige Graph


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # les redirections sont suivies a la main (sans jeton vers un autre hote)
        return None


class SharePointBackend:
    name = "sharepoint"

    def __init__(self):
        self.tenant = _env("KIKAN_SHAREPOINT_TENANT_ID")
        self.client_id = _env("KIKAN_SHAREPOINT_CLIENT_ID")
        self.client_secret = _env("KIKAN_SHAREPOINT_CLIENT_SECRET")
        self.site = _env("KIKAN_SHAREPOINT_SITE")          # "contoso.sharepoint.com:/sites/Kikan" ou identifiant de site
        self.library = _env("KIKAN_SHAREPOINT_LIBRARY", "Documents")
        self.folder = _env("KIKAN_SHAREPOINT_FOLDER", "Kikan").strip("/")
        self.authority = _env("KIKAN_SHAREPOINT_AUTHORITY", "https://login.microsoftonline.com").rstrip("/")
        self.graph = _env("KIKAN_SHAREPOINT_GRAPH", "https://graph.microsoft.com/v1.0").rstrip("/")
        missing = [n for n, v in (("KIKAN_SHAREPOINT_TENANT_ID", self.tenant), ("KIKAN_SHAREPOINT_CLIENT_ID", self.client_id),
                                  ("KIKAN_SHAREPOINT_CLIENT_SECRET", self.client_secret), ("KIKAN_SHAREPOINT_SITE", self.site)) if not v]
        if missing:
            raise StorageError("SharePoint non configure : " + ", ".join(missing))
        for url in (self.authority, self.graph):
            if urllib.parse.urlparse(url).scheme != "https" and _env("KIKAN_SHAREPOINT_ALLOW_HTTP", "false").lower() not in ("1", "true", "oui", "yes"):
                raise StorageError("SharePoint en HTTP refuse : utilisez https (KIKAN_SHAREPOINT_ALLOW_HTTP uniquement pour un essai)")
        if any(part in ("", ".", "..") for part in self.folder.split("/")) and self.folder:
            raise StorageError("KIKAN_SHAREPOINT_FOLDER invalide")
        ctx = ssl.create_default_context(cafile=_env("KIKAN_SHAREPOINT_CA_BUNDLE") or None)
        proxy = _env("KIKAN_SHAREPOINT_PROXY")
        self._opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(context=ctx),
            urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_until = 0.0
        self._drive: str | None = None

    def describe(self) -> dict:
        return {"site": self.site, "bibliotheque": self.library, "dossier": self.folder or "(racine)"}

    # ------------------------------------------------------------------ transport
    def _raw(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "Kikan", **(headers or {})})
        try:
            with self._opener.open(req, timeout=TIMEOUT) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read(1_000_000)
        except ssl.SSLError as exc:
            raise StorageError("SharePoint : echec TLS (certificat ou protocole ; KIKAN_SHAREPOINT_CA_BUNDLE)") from exc
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise StorageError("SharePoint : certificat du serveur non reconnu (KIKAN_SHAREPOINT_CA_BUNDLE)") from exc
            raise StorageError(f"SharePoint injoignable ({type(reason).__name__})") from exc

    def _access_token(self, force: bool = False) -> str:
        with self._lock:
            if not force and self._token and time.time() < self._token_until - 60:
                return self._token
            body = urllib.parse.urlencode({"client_id": self.client_id, "client_secret": self.client_secret,
                                           "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}).encode()
            status, _, raw = self._raw("POST", f"{self.authority}/{urllib.parse.quote(self.tenant)}/oauth2/v2.0/token", body,
                                       {"Content-Type": "application/x-www-form-urlencoded"})
            if status != 200:
                raise StorageError("SharePoint : authentification refusee (verifiez l'application Entra : identifiant, secret, consentement)")
            try:
                payload = json.loads(raw)
                self._token = payload["access_token"]
                self._token_until = time.time() + int(payload.get("expires_in", 3600))
            except (ValueError, KeyError) as exc:
                raise StorageError("SharePoint : reponse d'authentification inattendue") from exc
            return self._token

    def _graph(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None,
               ok=(200,), url: str | None = None) -> tuple[int, dict, bytes]:
        target = url or (self.graph + path)
        for attempt in range(3):
            hdrs = {"Authorization": "Bearer " + self._access_token(), **(headers or {})}
            status, resp_headers, raw = self._raw(method, target, data, hdrs)
            if status == 401 and attempt == 0:
                self._access_token(force=True)       # jeton expire ou revoque : un seul renouvellement
                continue
            if status in (429, 503) and attempt < 2:
                time.sleep(min(10, int(resp_headers.get("Retry-After", "2") or 2)))
                continue
            break
        if status in ok:
            return status, resp_headers, raw
        if status == 404:
            raise FileNotFoundError(target)
        if status == 401:
            raise StorageError("SharePoint : acces refuse (jeton rejete)")
        if status == 403:
            raise StorageError("SharePoint : droits insuffisants (permission Sites.Selected accordee au site ? role ecriture ?)")
        detail = ""
        try:
            detail = json.loads(raw).get("error", {}).get("code", "")
        except (ValueError, AttributeError):
            pass
        raise StorageError(f"SharePoint : {method} refuse (HTTP {status}{' ' + detail if detail else ''})")

    # ------------------------------------------------------------------ site et bibliotheque
    def _drive_id(self) -> str:
        if self._drive:
            return self._drive
        try:
            _, _, raw = self._graph("GET", "/sites/" + urllib.parse.quote(self.site, safe=":/,"))
        except FileNotFoundError as exc:
            raise StorageError("SharePoint : site introuvable (KIKAN_SHAREPOINT_SITE)") from exc
        site_id = json.loads(raw)["id"]
        _, _, raw = self._graph("GET", f"/sites/{urllib.parse.quote(site_id, safe=',')}/drives?$select=id,name")
        for d in json.loads(raw).get("value", []):
            if d.get("name", "").lower() == self.library.lower() or d.get("id") == self.library:
                self._drive = d["id"]
                return self._drive
        raise StorageError(f"SharePoint : bibliotheque « {self.library} » introuvable sur le site (KIKAN_SHAREPOINT_LIBRARY)")

    def _path(self, key: str) -> str:
        full = (self.folder + "/" if self.folder else "") + safe_key(key)
        return "/".join(urllib.parse.quote(p, safe="") for p in full.split("/"))

    def _item(self, key: str) -> str:
        return f"/drives/{urllib.parse.quote(self._drive_id(), safe='')}/root:/{self._path(key)}:"

    # ------------------------------------------------------------------ interface commune des moteurs
    def write(self, key: str, data: bytes, meta: dict | None = None) -> str | None:
        item = self._item(key)
        if len(data) <= SMALL_MAX:
            self._graph("PUT", f"{item}/content?@microsoft.graph.conflictBehavior=replace", data,
                        {"Content-Type": "application/octet-stream"}, ok=(200, 201))
            return None
        _, _, raw = self._graph("POST", f"{item}/createUploadSession",
                                json.dumps({"item": {"@microsoft.graph.conflictBehavior": "replace"}}).encode(),
                                {"Content-Type": "application/json"}, ok=(200,))
        upload_url = json.loads(raw)["uploadUrl"]
        if urllib.parse.urlparse(upload_url).scheme != urllib.parse.urlparse(self.graph).scheme:
            raise StorageError("SharePoint : adresse de televersement inattendue")
        total, start = len(data), 0
        while start < total:
            end = min(start + CHUNK, total)
            status, _, _ = self._raw("PUT", upload_url, data[start:end],   # l'adresse est deja autorisee : pas d'en-tete Authorization
                                     {"Content-Length": str(end - start), "Content-Range": f"bytes {start}-{end - 1}/{total}"})
            if status not in (200, 201, 202):
                raise StorageError(f"SharePoint : televersement par blocs refuse (HTTP {status})")
            start = end
        return None

    def read(self, key: str) -> bytes:
        try:
            status, headers, raw = self._graph("GET", f"{self._item(key)}/content", ok=(200, 302))
        except FileNotFoundError as exc:
            raise StorageError("Document introuvable sur SharePoint") from exc
        if status == 302:
            location = headers.get("Location") or headers.get("location")
            if not location or urllib.parse.urlparse(location).scheme not in ("http", "https"):
                raise StorageError("SharePoint : adresse de telechargement invalide")
            status, _, raw = self._raw("GET", location)   # adresse pre-autorisee : jamais d'en-tete Authorization
            if status != 200:
                raise StorageError(f"SharePoint : telechargement refuse (HTTP {status})")
        return raw

    def delete(self, key: str) -> None:
        try:
            self._graph("DELETE", self._item(key), ok=(200, 204))
        except FileNotFoundError:
            pass
