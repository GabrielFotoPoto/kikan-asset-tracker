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

"""Connecteur GLPI : import (proposition) et export (utilisateurs et materiel avec numeros de serie).

API REST historique de GLPI (/apirest.php, disponible en 10.x, 11.x et 12.x). Seuls les ordinateurs et les telephones sont
suivis. Les jetons (jeton utilisateur GLPI, jeton d'application facultatif) viennent de l'environnement, jamais de la base ni
de l'interface. Regles : jamais de suppression, jamais d'ecrasement ; Kikan est la source de verite des salaries ; un element
deja connu (meme numero de serie, meme matricule ou e-mail) est lie et non duplique. L'import n'agit que sur les elements
choisis par l'administrateur, relus depuis GLPI au moment de l'application (le client ne fournit jamais les donnees).
"""
import ipaddress
import json
import os
import re
import socket
import ssl
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, select

from . import appsettings, integration
from .auth import IS_PROD
from .integration import clean
from .models import Asset, AssetStatus, Assignment, AssignmentAsset, EmployeeStatus, Entite, ExternalLink, User
from .scope import GLOBAL

SYSTEME = "glpi"
TIMEOUT_S = 20
PAGE = 100
MAX_ITEMS = 5000
ITEMTYPES = ("Computer", "Phone")
MODEL_TYPE = {"Computer": "ComputerModel", "Phone": "PhoneModel"}
MODEL_FIELD = {"Computer": "computermodels_id", "Phone": "phonemodels_id"}

DEFAULTS = {
    "glpi_actif": "0", "glpi_url": "", "glpi_verifier_cert": "1", "glpi_types_computer": "PC portable", "glpi_types_phone": "Smartphone",
    "glpi_entites": "{}", "glpi_entite_kikan": "", "glpi_entite_glpi": "0", "glpi_profil": "Self-Service",
}


SESSION_ERRORS = {
    "ERROR_APP_TOKEN_PARAMETERS_MISSING": "GLPI exige un jeton d'application : renseignez KIKAN_GLPI_APP_TOKEN",
    "ERROR_WRONG_APP_TOKEN_PARAMETER": "Le jeton d'application GLPI (KIKAN_GLPI_APP_TOKEN) est invalide",
    "ERROR_GLPI_LOGIN_USER_TOKEN": "Le jeton utilisateur GLPI (KIKAN_GLPI_USER_TOKEN) est invalide",
    "ERROR_NOT_ALLOWED_IP": "L'adresse IP de Kikan n'est pas autorisee par le client API de GLPI",
    "ERROR_API_DISABLED": "L'API REST de GLPI est desactivee (Configuration, General, API)",
}


class GlpiError(Exception):
    """Echec de l'echange avec GLPI, avec un message sans donnee sensible (jamais de jeton)."""


@dataclass
class GlpiConfig:
    actif: bool
    url: str
    verifier_cert: bool
    types_computer: list[str]
    types_phone: list[str]
    entites: dict[str, int]          # id d'entite GLPI -> id d'entite Kikan
    entite_kikan: int | None         # entite Kikan par defaut a l'import
    entite_glpi: int                 # entite GLPI par defaut a l'export
    profil: str                      # profil GLPI donne aux utilisateurs crees ("" = aucun)

    @property
    def pret(self) -> bool:
        return bool(self.url) and bool(user_token())


def user_token() -> str:
    return os.environ.get("KIKAN_GLPI_USER_TOKEN", "").strip()


def app_token() -> str:
    return os.environ.get("KIKAN_GLPI_APP_TOKEN", "").strip()


def _split(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split("|") if x.strip()]


def load_config(session: Session) -> GlpiConfig:
    def g(key: str) -> str:
        v = appsettings.get(session, key, DEFAULTS[key])
        return DEFAULTS[key] if v is None else v

    try:
        entites = {str(k): int(v) for k, v in json.loads(g("glpi_entites")).items()}
    except (ValueError, TypeError, AttributeError):
        entites = {}
    kikan = g("glpi_entite_kikan")
    try:
        glpi_default = int(g("glpi_entite_glpi"))
    except ValueError:
        glpi_default = 0
    return GlpiConfig(actif=g("glpi_actif") == "1", url=g("glpi_url").strip(), verifier_cert=g("glpi_verifier_cert") == "1",
                      types_computer=_split(g("glpi_types_computer")), types_phone=_split(g("glpi_types_phone")),
                      entites=entites, entite_kikan=int(kikan) if kikan.isdigit() else None, entite_glpi=glpi_default,
                      profil=g("glpi_profil").strip())


def url_problem(url: str) -> str | None:
    """Motif de refus d'une adresse de serveur GLPI (None si acceptable). HTTPS exige en production."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "Adresse invalide : http(s)://serveur attendu"
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "L'adresse ne doit contenir ni identifiants ni parametres"
    if parsed.scheme == "http" and IS_PROD and os.environ.get("KIKAN_GLPI_ALLOW_HTTP") != "1":
        return "HTTPS est exige en production (les jetons ne doivent pas circuler en clair)"
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            return "Adresse de serveur non autorisee"
    except ValueError:
        pass
    return None


def base_url(url: str) -> str:
    u = url.strip().rstrip("/")
    return (u[: -len("/apirest.php")] if u.endswith("/apirest.php") else u) + "/apirest.php"


class GlpiClient:
    """Session GLPI (initSession / killSession) et appels de l'API REST historique."""

    def __init__(self, cfg: GlpiConfig):
        problem = url_problem(cfg.url)
        if problem:
            raise GlpiError(problem)
        if not user_token():
            raise GlpiError("Le jeton utilisateur GLPI (KIKAN_GLPI_USER_TOKEN) n'est pas defini")
        self.cfg = cfg
        self.base = base_url(cfg.url)
        self.session_token: str | None = None
        ctx = ssl.create_default_context(cafile=os.environ.get("KIKAN_GLPI_CA_BUNDLE") or None)
        if not cfg.verifier_cert:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        proxy = os.environ.get("KIKAN_GLPI_PROXY", "")
        self._opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(context=ctx),
            urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))

    def _call(self, method: str, path: str, body: dict | None = None, auth: str | None = None) -> tuple[int, object]:
        headers = {"Accept": "application/json"}
        if app_token():
            headers["App-Token"] = app_token()
        if auth:
            headers["Authorization"] = auth
        elif self.session_token:
            headers["Session-Token"] = self.session_token
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=TIMEOUT_S) as resp:
                status, raw = resp.status, resp.read(20_000_000)
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read(2_000_000)
        except ssl.SSLError as exc:
            raise GlpiError("Echec TLS avec GLPI (certificat ou protocole)") from exc
        except (urllib.error.URLError, OSError, socket.timeout) as exc:
            raise GlpiError("GLPI injoignable (%s)" % type(getattr(exc, "reason", exc)).__name__) from exc
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            raise GlpiError("Reponse inattendue de GLPI (pas du JSON : adresse du serveur correcte ?)") from None
        return status, parsed

    def __enter__(self) -> "GlpiClient":
        status, body = self._call("GET", "/initSession", auth="user_token " + user_token())
        code = body[0] if isinstance(body, list) and body else ""
        if code in SESSION_ERRORS:
            raise GlpiError(SESSION_ERRORS[code])
        if status == 401 or status == 403:
            raise GlpiError("GLPI a refuse la connexion : jeton utilisateur ou jeton d'application invalide, ou adresse IP non autorisee")
        if status != 200 or not isinstance(body, dict) or "session_token" not in body:
            raise GlpiError("GLPI a refuse l'ouverture de session (API REST activee ?)")
        self.session_token = body["session_token"]
        return self

    def __exit__(self, *exc) -> None:
        if self.session_token:
            try:
                self._call("GET", "/killSession")
            except GlpiError:
                pass
            self.session_token = None

    def request(self, method: str, path: str, body: dict | None = None):
        status, parsed = self._call(method, path, body)
        if status >= 400:
            code = parsed[0] if isinstance(parsed, list) and parsed else ""
            detail = parsed[1] if isinstance(parsed, list) and len(parsed) > 1 else ""
            raise GlpiError("GLPI : %s %s" % (code, str(detail)[:160]) if code else "GLPI : erreur %d" % status)
        return parsed

    def list_all(self, itemtype: str, extra: str = "") -> list[dict]:
        rows: list[dict] = []
        start = 0
        while start < MAX_ITEMS:
            status, parsed = self._call("GET", f"/{itemtype}?range={start}-{start + PAGE - 1}{extra}")
            if status == 400 and isinstance(parsed, list) and parsed and parsed[0] == "ERROR_RANGE_EXCEED_TOTAL":
                break
            if status >= 400 or not isinstance(parsed, list):
                raise GlpiError("GLPI : lecture de %s impossible (erreur %d)" % (itemtype, status))
            rows.extend(parsed)
            if len(parsed) < PAGE:
                break
            start += PAGE
        return rows

    def create(self, itemtype: str, values: dict) -> int:
        parsed = self.request("POST", f"/{itemtype}", {"input": values})
        item = parsed[0] if isinstance(parsed, list) and parsed else parsed
        if not isinstance(item, dict) or "id" not in item:
            raise GlpiError("GLPI : creation de %s refusee" % itemtype)
        return int(item["id"])

    def update(self, itemtype: str, item_id: int, values: dict) -> None:
        self.request("PUT", f"/{itemtype}/{item_id}", {"input": {"id": item_id, **values}})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # une redirection inattendue est une erreur, jamais suivie
        return None


# --------------------------------------------------------------------------- lecture de GLPI

@dataclass
class Snapshot:
    items: dict[str, dict] = field(default_factory=dict)     # "Computer:12" -> element normalise
    users: dict[str, dict] = field(default_factory=dict)     # "User:7" -> utilisateur normalise
    entites: dict[int, str] = field(default_factory=dict)
    profils: dict[str, int] = field(default_factory=dict)
    dropdowns: dict[str, dict[int, str]] = field(default_factory=dict)


def _names(rows: list[dict]) -> dict[int, str]:
    return {int(r["id"]): str(r.get("name") or r.get("completename") or "") for r in rows if "id" in r}


def read_glpi(client: GlpiClient) -> Snapshot:
    snap = Snapshot()
    snap.entites = {int(r["id"]): str(r.get("completename") or r.get("name") or "") for r in client.list_all("Entity")}
    snap.profils = {v: k for k, v in _names(client.list_all("Profile")).items() if v}
    manufacturers = _names(client.list_all("Manufacturer"))
    states = _names(client.list_all("State"))
    models = {t: _names(client.list_all(MODEL_TYPE[t])) for t in ITEMTYPES}
    snap.dropdowns = {"manufacturers": manufacturers, "states": states, "ComputerModel": models["Computer"], "PhoneModel": models["Phone"]}

    emails: dict[int, str] = {}
    for r in client.list_all("UserEmail"):
        uid = int(r.get("users_id") or 0)
        if uid and (uid not in emails or r.get("is_default")):
            emails[uid] = str(r.get("email") or "")
    for r in client.list_all("User"):
        if r.get("is_deleted") or not r.get("is_active", 1):
            continue
        uid = int(r["id"])
        snap.users[f"User:{uid}"] = {
            "externe_id": f"User:{uid}", "glpi_id": uid, "login": r.get("name"), "nom": clean(r.get("realname")), "prenom": clean(r.get("firstname")),
            "email": emails.get(uid) or None, "matricule": clean(r.get("registration_number"), 50), "entite_id": r.get("entities_id")}
    for itemtype in ITEMTYPES:
        for r in client.list_all(itemtype):
            if r.get("is_deleted") or r.get("is_template"):
                continue
            uid = int(r.get("users_id") or 0)
            u = snap.users.get(f"User:{uid}")
            snap.items[f"{itemtype}:{int(r['id'])}"] = {
                "externe_id": f"{itemtype}:{int(r['id'])}", "glpi_id": int(r["id"]), "itemtype": itemtype, "nom": clean(r.get("name")),
                "serial": clean(r.get("serial"), 100), "inventaire": clean(r.get("otherserial"), 100),
                "fabricant": manufacturers.get(int(r.get("manufacturers_id") or 0)),
                "modele": models[itemtype].get(int(r.get(MODEL_FIELD[itemtype]) or 0)),
                "etat": states.get(int(r.get("states_id") or 0)), "users_id": uid,
                "utilisateur": (u["login"] if u else None), "entite_id": r.get("entities_id")}
    return snap


def type_for(cfg: GlpiConfig, itemtype: str) -> str | None:
    pool = cfg.types_computer if itemtype == "Computer" else cfg.types_phone
    return pool[0] if pool else None


def itemtype_of(cfg: GlpiConfig, kikan_type: str | None) -> str | None:
    t = (kikan_type or "").lower()
    if t in [x.lower() for x in cfg.types_computer]:
        return "Computer"
    if t in [x.lower() for x in cfg.types_phone]:
        return "Phone"
    return None


def entite_for(cfg: GlpiConfig, glpi_entity_id) -> int | None:
    mapped = cfg.entites.get(str(glpi_entity_id))
    return mapped if mapped is not None else cfg.entite_kikan


# --------------------------------------------------------------------------- import (proposition puis application)

def import_proposals(session: Session, cfg: GlpiConfig, snap: Snapshot) -> dict:
    assets, users = [], []
    serials = {(a.numero_serie or "").lower(): a for a in session.exec(select(Asset)).all() if a.numero_serie}
    for ext, it in sorted(snap.items.items(), key=lambda kv: (kv[1]["itemtype"], kv[1]["nom"] or "")):
        link = integration.get_link(session, SYSTEME, "asset", ext)
        found = serials.get((it["serial"] or "").lower()) if it["serial"] else None
        if link:
            state = "deja_lie"
        elif found:
            state = "correspondance"
        elif not it["serial"]:
            state = "sans_serie"
        else:
            state = "nouveau"
        kikan_type = type_for(cfg, it["itemtype"])
        assets.append({**it, "etat_import": state, "type_kikan": kikan_type, "kikan_id": (found.id if found else (link.kikan_id if link else None)),
                       "entite_glpi": snap.entites.get(int(it["entite_id"] or 0)), "importable": state != "deja_lie" and kikan_type is not None})
    for ext, u in sorted(snap.users.items(), key=lambda kv: (kv[1]["nom"] or kv[1]["login"] or "")):
        link = integration.get_link(session, SYSTEME, "user", ext)
        match, how = (None, None) if link else integration.match_user(session, u)
        if link:
            state = "deja_lie"
        elif how in ("matricule", "email"):
            state = "correspondance"
        elif how == "nom":
            state = "homonyme"
        elif not (u["nom"] and u["prenom"]):
            state = "incomplet"
        else:
            state = "nouveau"
        users.append({**u, "etat_import": state, "kikan_id": (match.id if match else (link.kikan_id if link else None)), "critere": how,
                      "entite_glpi": snap.entites.get(int(u["entite_id"] or 0)), "importable": state not in ("deja_lie", "incomplet")})
    return {"actifs": assets, "salaries": users}


def _asset_item(cfg: GlpiConfig, it: dict, entite_kikan: int | None) -> dict | None:
    kikan_type = type_for(cfg, it["itemtype"])
    if not kikan_type:
        return None
    note = "Importe de GLPI"
    if it["utilisateur"]:
        note += " (utilisateur GLPI : %s)" % it["utilisateur"]
    return {"id_externe": it["externe_id"], "type": kikan_type, "marque": it["fabricant"], "modele": it["modele"], "numero_serie": it["serial"],
            "identifiant_interne": it["inventaire"], "entite_id": entite_kikan, "notes": note}


def import_apply(session: Session, cfg: GlpiConfig, snap: Snapshot, actifs: list[dict], salaries: list[dict]) -> dict:
    results: list[dict] = []
    for sel in salaries:
        u = snap.users.get(sel.get("externe_id"))
        if u is None:
            results.append({"objet": "salarie", "id_externe": sel.get("externe_id"), "resultat": "refuse", "message": "Absent de GLPI"})
            continue
        entite = sel.get("entite_id") if sel.get("entite_id") is not None else entite_for(cfg, u["entite_id"])
        item = {**u, "id_externe": u["externe_id"], "entite_id": entite, "homonyme": sel.get("homonyme")}
        try:
            with session.begin_nested():
                res = integration.upsert_user(session, SYSTEME, GLOBAL, item)
        except Exception:  # noqa: BLE001
            res = {"id_externe": u["externe_id"], "resultat": "refuse", "message": "Donnees non traitables"}
        results.append({"objet": "salarie", **res})
    for sel in actifs:
        it = snap.items.get(sel.get("externe_id"))
        if it is None:
            results.append({"objet": "actif", "id_externe": sel.get("externe_id"), "resultat": "refuse", "message": "Absent de GLPI"})
            continue
        entite = sel.get("entite_id") if sel.get("entite_id") is not None else entite_for(cfg, it["entite_id"])
        item = _asset_item(cfg, it, entite)
        if item is None:
            results.append({"objet": "actif", "id_externe": it["externe_id"], "resultat": "refuse", "message": "Type Kikan non configure pour ce type GLPI"})
            continue
        try:
            with session.begin_nested():
                res = integration.upsert_asset(session, SYSTEME, GLOBAL, item, allow_update=False)
        except Exception:  # noqa: BLE001
            res = {"id_externe": it["externe_id"], "resultat": "refuse", "message": "Donnees non traitables"}
        results.append({"objet": "actif", **res})
    session.commit()
    return summarize(results)


def summarize(results: list[dict]) -> dict:
    resume: dict[str, int] = {}
    for r in results:
        key = f"{r['objet']}_{r['resultat']}"
        resume[key] = resume.get(key, 0) + 1
    return {"resume": resume, "resultats": results}


# --------------------------------------------------------------------------- export vers GLPI

def login_for(user: User, taken: set[str]) -> str:
    base = (user.email or "").split("@")[0] if user.email else f"{user.prenom}.{user.nom}"
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9._-]+", ".", base).strip(".")[:50] or "utilisateur"
    login, n = base, 1
    while login.lower() in taken:
        n += 1
        login = f"{base}{n}"
    return login


def assigned_assets(session: Session, user_id: int) -> list[Asset]:
    rows = session.exec(select(Asset).join(AssignmentAsset, AssignmentAsset.asset_id == Asset.id)
                        .join(Assignment, Assignment.id == AssignmentAsset.assignment_id)
                        .where(Assignment.user_id == user_id, Asset.statut == AssetStatus.affecte)).all()
    return list({a.id: a for a in rows}.values())


def find_glpi_user(snap: Snapshot, user: User) -> tuple[dict | None, str | None]:
    mat = (user.matricule or "").strip().lower()
    mail = (user.email or "").strip().lower()
    for u in snap.users.values():
        if mat and (u["matricule"] or "").lower() == mat:
            return u, "matricule"
    for u in snap.users.values():
        if mail and (u["email"] or "").lower() == mail:
            return u, "email"
    return None, None


def export_proposals(session: Session, cfg: GlpiConfig, snap: Snapshot) -> list[dict]:
    by_serial = {(i["serial"] or "").lower(): i for i in snap.items.values() if i["serial"]}
    out = []
    users = session.exec(select(User).where(User.statut != EmployeeStatus.sorti).order_by(User.nom, User.prenom)).all()
    for u in users:
        link = integration.link_of(session, SYSTEME, "user", u.id)
        glpi_user, how = (snap.users.get(link.externe_id), "lien") if link else find_glpi_user(snap, u)
        items = []
        for a in assigned_assets(session, u.id):
            itemtype = itemtype_of(cfg, a.type)
            alink = integration.link_of(session, SYSTEME, "asset", a.id)
            if itemtype is None:
                state = "type_non_suivi"
            elif not a.numero_serie:
                state = "sans_serie"
            elif alink:
                state = "deja_lie"
            elif a.numero_serie.lower() in by_serial:
                state = "existe_dans_glpi"
            else:
                state = "a_creer"
            items.append({"id": a.id, "type": a.type, "marque": a.marque, "modele": a.modele, "numero_serie": a.numero_serie,
                          "itemtype": itemtype, "etat_export": state})
        if glpi_user and not link and integration.get_link(session, SYSTEME, "user", glpi_user["externe_id"]):
            ustate = "conflit"          # cet utilisateur GLPI est deja lie a une autre fiche Kikan
        elif link and glpi_user:
            ustate = "deja_lie"
        elif link:
            ustate = "lien_perdu"       # lie a un utilisateur GLPI devenu introuvable ou inactif : a traiter a la main
        elif glpi_user:
            ustate = "existe_dans_glpi"
        else:
            ustate = "a_creer"
        todo = ustate in ("a_creer", "existe_dans_glpi") or (ustate == "deja_lie" and any(i["etat_export"] in ("a_creer", "existe_dans_glpi") for i in items))
        out.append({"id": u.id, "nom": u.nom, "prenom": u.prenom, "matricule": u.matricule, "email": u.email, "statut": u.statut.value,
                    "etat_export": ustate, "critere": how, "actifs": items, "a_traiter": todo})
    return out


def _ensure_dropdown(client: GlpiClient, itemtype: str, name: str | None, cache: dict) -> int:
    if not name:
        return 0
    key = (itemtype, name.lower())
    if key in cache:
        return cache[key]
    if ("loaded", itemtype) not in cache:  # une seule lecture de la liste par type
        for r in client.list_all(itemtype):
            cache[(itemtype, str(r.get("name") or "").lower())] = int(r["id"])
        cache[("loaded", itemtype)] = True
    if key not in cache:
        cache[key] = client.create(itemtype, {"name": name})
    return cache[key]


def export_apply(session: Session, cfg: GlpiConfig, client: GlpiClient, snap: Snapshot, user_ids: list[int]) -> dict:
    results: list[dict] = []
    cache: dict = {}
    taken = {str(u["login"] or "").lower() for u in snap.users.values()}
    by_serial = {(i["serial"] or "").lower(): i for i in snap.items.values() if i["serial"]}
    profil_id = snap.profils.get(cfg.profil) if cfg.profil else None
    for uid in user_ids:
        user = session.get(User, uid)
        if user is None or user.statut == EmployeeStatus.sorti:
            results.append({"objet": "salarie", "id_externe": None, "id": uid, "resultat": "refuse", "message": "Salarie inconnu ou sorti"})
            continue
        entite_glpi = next((int(g) for g, k in cfg.entites.items() if k == user.entite_id), cfg.entite_glpi)
        link = integration.link_of(session, SYSTEME, "user", user.id)
        glpi_user = snap.users.get(link.externe_id) if link else None
        if link and glpi_user is None:
            results.append({"objet": "salarie", "id_externe": link.externe_id, "id": user.id, "resultat": "erreur",
                            "message": "Lie a un utilisateur GLPI introuvable ou inactif : a verifier dans GLPI"})
            continue
        try:
            if glpi_user is None:
                glpi_user, how = find_glpi_user(snap, user)
                if glpi_user is not None and integration.get_link(session, SYSTEME, "user", glpi_user["externe_id"]):
                    results.append({"objet": "salarie", "id_externe": glpi_user["externe_id"], "id": user.id, "resultat": "conflit",
                                    "message": "Cet utilisateur GLPI (%s) est deja lie a une autre fiche Kikan" % how})
                    continue
                if glpi_user is not None:
                    session.add(ExternalLink(systeme=SYSTEME, objet="user", kikan_id=user.id, externe_id=glpi_user["externe_id"]))
                    session.flush()
                    results.append({"objet": "salarie", "id_externe": glpi_user["externe_id"], "id": user.id, "resultat": "lie",
                                    "message": "Utilisateur GLPI existant (%s) lie sans modification" % how})
                else:
                    login = login_for(user, taken)
                    values = {"name": login, "realname": user.nom, "firstname": user.prenom, "is_active": 1, "entities_id": entite_glpi}
                    if user.email:
                        values["_useremails"] = [user.email]
                    if user.matricule:
                        values["registration_number"] = user.matricule
                    if profil_id:
                        values["_profiles_id"] = profil_id
                        values["_entities_id"] = entite_glpi
                    gid = client.create("User", values)
                    taken.add(login.lower())
                    glpi_user = {"externe_id": f"User:{gid}", "glpi_id": gid, "login": login, "matricule": user.matricule, "email": user.email}
                    snap.users[glpi_user["externe_id"]] = glpi_user
                    session.add(ExternalLink(systeme=SYSTEME, objet="user", kikan_id=user.id, externe_id=glpi_user["externe_id"]))
                    session.flush()
                    results.append({"objet": "salarie", "id_externe": glpi_user["externe_id"], "id": user.id, "resultat": "cree"})
            else:
                results.append({"objet": "salarie", "id_externe": glpi_user["externe_id"], "id": user.id, "resultat": "inchange"})
        except GlpiError as exc:
            results.append({"objet": "salarie", "id_externe": None, "id": user.id, "resultat": "erreur", "message": str(exc)})
            continue

        for a in assigned_assets(session, user.id):
            itemtype = itemtype_of(cfg, a.type)
            if itemtype is None:
                results.append({"objet": "actif", "id": a.id, "resultat": "ignore", "message": "Type non suivi dans GLPI"})
                continue
            if not a.numero_serie:
                results.append({"objet": "actif", "id": a.id, "resultat": "ignore", "message": "Numero de serie absent : non exporte"})
                continue
            if integration.link_of(session, SYSTEME, "asset", a.id):
                results.append({"objet": "actif", "id": a.id, "resultat": "inchange"})
                continue
            try:
                existing = by_serial.get(a.numero_serie.lower())
                if existing is not None and integration.get_link(session, SYSTEME, "asset", existing["externe_id"]):
                    results.append({"objet": "actif", "id": a.id, "id_externe": existing["externe_id"], "resultat": "conflit",
                                    "message": "Ce materiel GLPI est deja lie a un autre materiel Kikan"})
                    continue
                if existing is not None:
                    session.add(ExternalLink(systeme=SYSTEME, objet="asset", kikan_id=a.id, externe_id=existing["externe_id"], empreinte=integration.asset_fp(a)))
                    session.flush()
                    msg = "Existe deja dans GLPI (meme numero de serie) : lie"
                    if not existing["users_id"]:
                        client.update(existing["itemtype"], existing["glpi_id"], {"users_id": glpi_user["glpi_id"]})
                        existing["users_id"] = glpi_user["glpi_id"]
                        msg += ", utilisateur renseigne"
                    elif existing["users_id"] != glpi_user["glpi_id"]:
                        msg += " (affecte a un autre utilisateur dans GLPI : non modifie)"
                    results.append({"objet": "actif", "id": a.id, "id_externe": existing["externe_id"], "resultat": "lie", "message": msg})
                    continue
                values = {"name": a.identifiant_interne or " ".join(x for x in (a.marque, a.modele) if x) or a.numero_serie, "serial": a.numero_serie,
                          "users_id": glpi_user["glpi_id"], "entities_id": entite_glpi, "comment": "Cree par Kikan"}
                if a.identifiant_interne:
                    values["otherserial"] = a.identifiant_interne
                if a.marque:
                    values["manufacturers_id"] = _ensure_dropdown(client, "Manufacturer", a.marque, cache)
                if a.modele:
                    values[MODEL_FIELD[itemtype]] = _ensure_dropdown(client, MODEL_TYPE[itemtype], a.modele, cache)
                gid = client.create(itemtype, values)
                ext = f"{itemtype}:{gid}"
                snap.items[ext] = {"externe_id": ext, "glpi_id": gid, "itemtype": itemtype, "serial": a.numero_serie, "users_id": glpi_user["glpi_id"]}
                by_serial[a.numero_serie.lower()] = snap.items[ext]
                session.add(ExternalLink(systeme=SYSTEME, objet="asset", kikan_id=a.id, externe_id=ext, empreinte=integration.asset_fp(a)))
                session.flush()
                results.append({"objet": "actif", "id": a.id, "id_externe": ext, "resultat": "cree"})
            except GlpiError as exc:
                results.append({"objet": "actif", "id": a.id, "resultat": "erreur", "message": str(exc)})
    session.commit()
    return summarize(results)
