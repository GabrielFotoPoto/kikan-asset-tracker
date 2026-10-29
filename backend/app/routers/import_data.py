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

"""Import CSV (reprise de l'existant) : simulation, import, modeles. L'import ne fait que CREER."""
import hashlib
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlmodel import Session, select

from ..audit import audit
from ..auth import get_current_account, require_roles, writer_guard
from ..asset_catalog import AssetCatalog
from ..catalogs import canonical_service, canonical_type
from ..db import get_session
from .. import import_undo, xlsx_io
from ..importer import as_bool, as_date, as_str, read_csv
from ..models import (
    Account,
    Application,
    Asset,
    AssetStatus,
    Assignment,
    AssignmentAsset,
    EmployeeStatus,
    Entite,
    ImportLot,
    User,
    UserApplication,
)

router = APIRouter(
    prefix="/import", tags=["import"],
    dependencies=[Depends(writer_guard("informatique"))],
)

MAX_IMPORT_BYTES = int(os.environ.get("KIKAN_MAX_IMPORT_MB", "5")) * 1024 * 1024
MAX_IMPORT_ROWS = int(os.environ.get("KIKAN_MAX_IMPORT_ROWS", "20000"))
MAX_DETAILS = 1000  # lignes detaillees renvoyees (les compteurs restent exacts)


def col(nom: str, obligatoire: bool, aide: str) -> dict:
    return {"nom": nom, "obligatoire": obligatoire, "aide": aide}


# Source de verite des fichiers d'import : colonnes, aide affichee dans l'interface, modeles telechargeables.
SPECS: dict[str, dict] = {
    "entites": {
        "ordre": 1, "titre": "Entites / filiales",
        "description": "Les filiales et entites du groupe. Une entite dont le code existe deja est ignoree.",
        "colonnes": [
            col("code", True, "Code unique de l'entite (ex. FILIALE-A)"),
            col("nom", True, "Nom affiche"),
            col("code_parent", False, "Code de l'entite parente (vide pour la racine)"),
            col("actif", False, "oui ou non (oui par defaut)"),
        ],
        "exemples": [["GROUPE", "SICA Atlantique", "", "oui"], ["SICA-AT", "SICA Atlantique (siège)", "GROUPE", "oui"]],
    },
    "applications": {
        "ordre": 2, "titre": "Applications",
        "description": "Le catalogue des applications. Une application deja presente (meme nom, meme entite) est ignoree.",
        "colonnes": [
            col("nom", True, "Nom de l'application"),
            col("description", False, "Description libre"),
            col("code_entite", False, "Code de l'entite concernee (vide = toutes)"),
            col("actif", False, "oui ou non (oui par defaut)"),
        ],
        "exemples": [["ERP Cereo", "ERP de gestion", "GROUPE", "oui"], ["Messagerie", "Microsoft 365", "GROUPE", "oui"]],
    },
    "utilisateurs": {
        "ordre": 3, "titre": "Salaries",
        "description": "Les salaries. Un salarie dont le matricule existe deja est ignore. Les entites doivent exister.",
        "colonnes": [
            col("matricule", False, "Matricule unique (recommande : sert de lien avec les autres fichiers)"),
            col("nom", True, "Nom"),
            col("prenom", True, "Prenom"),
            col("email", False, "Adresse e-mail"),
            col("code_entite", False, "Code de l'entite (doit exister)"),
            col("service", False, "Service ou departement"),
            col("date_arrivee", False, "Date AAAA-MM-JJ"),
            col("statut", False, "actif, sorti ou en_depart (actif par defaut)"),
        ],
        "exemples": [
            ["E001", "Durand", "Claude", "claude.durand@exemple.fr", "SICA-AT", "Comptabilité", "2026-09-01", "actif"],
            ["E002", "Martin", "Dominique", "dominique.martin@exemple.fr", "FILIALE-A", "Logistique", "2026-10-15", "actif"],
        ],
    },
    "materiel": {
        "ordre": 4, "titre": "Materiel",
        "description": "Les actifs. Un numero de serie deja present est signale en erreur.",
        "colonnes": [
            col("identifiant_interne", False, "Identifiant interne unique (sert aux affectations)"),
            col("type", False, "PC portable, Smartphone, ..."),
            col("marque", False, "Marque"),
            col("modele", False, "Modele"),
            col("numero_serie", False, "Numero de serie (unique)"),
            col("date_achat", False, "Date AAAA-MM-JJ"),
            col("fin_garantie", False, "Date AAAA-MM-JJ"),
            col("echeance_renouvellement", False, "Date AAAA-MM-JJ"),
            col("statut", False, "stock, affecte, rendu... (stock par defaut)"),
            col("code_entite", False, "Code de l'entite (doit exister)"),
            col("notes", False, "Notes libres"),
        ],
        "exemples": [
            ["PC-0001", "PC portable", "Dell", "Latitude 5550", "SN-DELL-0001", "2025-06-10", "2028-06-10", "2029-06-10", "stock", "SICA-AT", ""],
            ["PC-0002", "PC portable", "Lenovo", "ThinkPad T14", "SN-LEN-0002", "2026-02-20", "2029-02-20", "2030-02-20", "stock", "FILIALE-A", ""],
        ],
    },
    "affectations": {
        "ordre": 5, "titre": "Affectations (qui detient quoi)",
        "description": "Un salarie recoit tous ses actifs en une affectation. Salaries et actifs doivent exister, l'actif ne doit pas deja etre affecte.",
        "colonnes": [
            col("matricule_utilisateur", True, "Matricule du salarie (doit exister)"),
            col("identifiant_interne_actif", True, "Identifiant interne de l'actif (doit exister)"),
            col("date_remise", False, "Date AAAA-MM-JJ"),
        ],
        "exemples": [["E001", "PC-0001", "2026-09-01"], ["E001", "TEL-0001", "2026-09-01"]],
    },
    "acces_applicatifs": {
        "ordre": 6, "titre": "Acces applicatifs",
        "description": "Les acces par salarie. Un acces deja present (meme salarie, meme application) est ignore.",
        "colonnes": [
            col("matricule_utilisateur", True, "Matricule du salarie (doit exister)"),
            col("application", True, "Nom de l'application (doit exister)"),
            col("acces", False, "oui ou non (oui par defaut)"),
            col("note", False, "Precision libre (ex. profil, droits)"),
        ],
        "exemples": [["E001", "ERP Cereo", "oui", "Utilisateur standard"], ["E001", "Messagerie", "oui", ""]],
    },
}
KINDS = list(SPECS)


class Report:
    def __init__(self, kind: str, dry_run: bool):
        self.kind = kind
        self.dry_run = dry_run
        self.total = 0
        self.imported = 0
        self.skipped = 0
        self.errors: list[dict] = []
        self.errors_total = 0
        self.lignes: list[dict] = []
        self.extra: dict = {}

    def _line(self, ligne: int, action: str, message: str):
        if len(self.lignes) < MAX_DETAILS:
            self.lignes.append({"ligne": ligne, "action": action, "message": message})

    def error(self, ligne: int, message: str):
        self.errors_total += 1
        if len(self.errors) < MAX_DETAILS:
            self.errors.append({"ligne": ligne, "message": message})

    def created(self, ligne: int, message: str):
        self._line(ligne, "creer", message)

    def skip(self, ligne: int, message: str):
        self.skipped += 1
        self._line(ligne, "ignorer", message)

    def remap(self, numbers: list[int]) -> None:
        """Remet les numeros de ligne du classeur (les lignes vides ignorees decalent la numerotation)."""
        def real(i: int) -> int:
            return numbers[i - 2] if 0 <= i - 2 < len(numbers) else i
        for e in self.errors:
            e["ligne"] = real(e["ligne"])
        for l in self.lignes:
            l["ligne"] = real(l["ligne"])

    def dict(self):
        return {
            "kind": self.kind,
            "dry_run": self.dry_run,
            "total": self.total,
            "imported": self.imported,
            "skipped": self.skipped,
            "errors": self.errors,
            "errors_total": self.errors_total,
            "lignes": self.lignes,
            "tronque": self.errors_total > len(self.errors) or (self.imported + self.skipped) > len(self.lignes),
            **self.extra,
        }


def _formula_row(rep: "Report", i: int, row: dict) -> bool:
    """Ligne dont une cellule est une formule sans valeur enregistree : jamais importee."""
    cols = row.get("__formule")
    if not cols:
        return False
    rep.error(i, f"formule sans valeur enregistree (colonne : {cols}) : ouvrez le classeur dans Excel, "
                 "enregistrez-le puis deposez-le de nouveau")
    return True


def _entite_map(session: Session) -> dict[str, int]:
    return {e.code: e.id for e in session.exec(select(Entite)).all()}


def _import_entites(rows, session, rep):
    existing = set(_entite_map(session).keys())
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        if _formula_row(rep, i, row):
            continue
        code = as_str(row.get("code"))
        nom = as_str(row.get("nom"))
        if not code or not nom:
            rep.error(i, "code et nom obligatoires")
            continue
        if code in existing:
            rep.skip(i, f"entite deja presente : {code}")
            continue
        obj = Entite(code=code, nom=nom, code_parent=as_str(row.get("code_parent")),
                     actif=as_bool(row.get("actif")))
        session.add(obj)
        existing.add(code)
        rep.imported += 1
        rep.created(i, f"{code} - {nom}")


def _import_applications(rows, session, rep):
    emap = _entite_map(session)
    existing = {((a.nom or "").lower(), a.entite_id) for a in session.exec(select(Application)).all()}
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        if _formula_row(rep, i, row):
            continue
        nom = as_str(row.get("nom"))
        if not nom:
            rep.error(i, "nom obligatoire")
            continue
        code_ent = as_str(row.get("code_entite"))
        entite_id = emap.get(code_ent) if code_ent else None
        if code_ent and entite_id is None:
            rep.error(i, f"entite inconnue: {code_ent}")
            continue
        if (nom.lower(), entite_id) in existing:
            rep.skip(i, f"application deja presente : {nom}")
            continue
        session.add(Application(nom=nom, description=as_str(row.get("description")),
                                entite_id=entite_id, actif=as_bool(row.get("actif"))))
        existing.add((nom.lower(), entite_id))
        rep.imported += 1
        rep.created(i, nom)


def _import_utilisateurs(rows, session, rep):
    emap = _entite_map(session)
    existing_mat = {u.matricule for u in session.exec(select(User)).all() if u.matricule}
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        if _formula_row(rep, i, row):
            continue
        nom, prenom = as_str(row.get("nom")), as_str(row.get("prenom"))
        if not nom or not prenom:
            rep.error(i, "nom et prenom obligatoires")
            continue
        matricule = as_str(row.get("matricule"))
        if matricule and matricule in existing_mat:
            rep.skip(i, f"matricule deja present : {matricule}")
            continue
        code_ent = as_str(row.get("code_entite"))
        entite_id = emap.get(code_ent) if code_ent else None
        if code_ent and entite_id is None:
            rep.error(i, f"entite inconnue: {code_ent}")
            continue
        try:
            statut = EmployeeStatus(as_str(row.get("statut")) or "actif")
        except ValueError:
            rep.error(i, f"statut invalide: {row.get('statut')}")
            continue
        try:
            date_arr = as_date(row.get("date_arrivee"))
        except ValueError:
            rep.error(i, "date_arrivee invalide (attendu AAAA-MM-JJ)")
            continue
        session.add(User(matricule=matricule, nom=nom, prenom=prenom, entite_id=entite_id,
                         email=as_str(row.get("email")), service=canonical_service(session, as_str(row.get("service"))),
                         statut=statut, date_arrivee=date_arr))
        if matricule:
            existing_mat.add(matricule)
        rep.imported += 1
        rep.created(i, f"{prenom} {nom}" + (f" ({matricule})" if matricule else ""))


def _import_materiel(rows, session, rep):
    emap = _entite_map(session)
    existing_sn = {a.numero_serie for a in session.exec(select(Asset)).all() if a.numero_serie}
    existing_id = {a.identifiant_interne for a in session.exec(select(Asset)).all() if a.identifiant_interne}
    catalog = AssetCatalog(session)  # un seul instantane pour tout le fichier : les variantes se rejoignent
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        if _formula_row(rep, i, row):
            continue
        sn = as_str(row.get("numero_serie"))
        ident = as_str(row.get("identifiant_interne"))
        if sn and sn in existing_sn:
            rep.error(i, f"numero de serie deja present: {sn}")
            continue
        if ident and ident in existing_id:
            rep.error(i, f"identifiant interne deja present: {ident}")
            continue
        code_ent = as_str(row.get("code_entite"))
        entite_id = emap.get(code_ent) if code_ent else None
        if code_ent and entite_id is None:
            rep.error(i, f"entite inconnue: {code_ent}")
            continue
        try:
            statut = AssetStatus(as_str(row.get("statut")) or "stock")
            d_achat = as_date(row.get("date_achat"))
            d_gar = as_date(row.get("fin_garantie"))
            d_ren = as_date(row.get("echeance_renouvellement"))
        except ValueError as exc:
            rep.error(i, f"valeur invalide: {exc}")
            continue
        marque = catalog.canon_marque(as_str(row.get("marque")))
        modele = catalog.canon_modele(marque, as_str(row.get("modele")))
        session.add(Asset(
            identifiant_interne=as_str(row.get("identifiant_interne")),
            type=canonical_type(session, as_str(row.get("type"))), marque=marque,
            modele=modele, numero_serie=sn,
            date_achat=d_achat, fin_garantie=d_gar, echeance_renouvellement=d_ren,
            statut=statut, entite_id=entite_id, notes=as_str(row.get("notes")),
            source="import",
        ))
        if sn:
            existing_sn.add(sn)
        if ident:
            existing_id.add(ident)
        rep.imported += 1
        rep.created(i, " ".join(x for x in (as_str(row.get("type")), as_str(row.get("marque")),
                                            as_str(row.get("modele")), sn) if x))


def _import_affectations(rows, session, rep):
    users = {u.matricule: u for u in session.exec(select(User)).all() if u.matricule}
    assets = {a.identifiant_interne: a for a in session.exec(select(Asset)).all() if a.identifiant_interne}
    # Regroupe par salarie : une affectation par salarie avec tous ses actifs.
    groupes: dict[str, dict] = {}
    seen: set[str] = set()
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        if _formula_row(rep, i, row):
            continue
        mat = as_str(row.get("matricule_utilisateur"))
        ident = as_str(row.get("identifiant_interne_actif"))
        if not mat or not ident:
            rep.error(i, "matricule_utilisateur et identifiant_interne_actif obligatoires")
            continue
        if mat not in users:
            rep.error(i, f"salarie inconnu: {mat}")
            continue
        if ident not in assets:
            rep.error(i, f"actif inconnu: {ident}")
            continue
        asset = assets[ident]
        if asset.statut == AssetStatus.affecte or ident in seen:
            rep.error(i, f"actif deja affecte: {ident}")
            continue
        try:
            d = as_date(row.get("date_remise"))
        except ValueError:
            rep.error(i, "date_remise invalide")
            continue
        seen.add(ident)
        g = groupes.setdefault(mat, {"user": users[mat], "assets": [], "date": None, "lignes": []})
        g["assets"].append(asset)
        g["lignes"].append((i, ident))
        if d and (g["date"] is None or d < g["date"]):
            g["date"] = d

    for mat, g in groupes.items():
        when = datetime.combine(g["date"], datetime.min.time()) if g["date"] else datetime.utcnow()
        assignment = Assignment(user_id=g["user"].id, date_remise=when,
                                statut="en_cours", cree_par="import")
        session.add(assignment)
        session.flush()  # pour obtenir l'id sans commit
        for asset in g["assets"]:
            asset.statut = AssetStatus.affecte
            session.add(asset)
            session.add(AssignmentAsset(assignment_id=assignment.id, asset_id=asset.id))
            rep.imported += 1
        for ligne, ident in g["lignes"]:
            rep.created(ligne, f"{ident} remis a {mat}")


def _import_acces(rows, session, rep):
    users = {u.matricule: u for u in session.exec(select(User)).all() if u.matricule}
    apps = {a.nom: a for a in session.exec(select(Application)).all()}
    existing = {(x.user_id, x.application_id) for x in session.exec(select(UserApplication)).all()}
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        if _formula_row(rep, i, row):
            continue
        mat = as_str(row.get("matricule_utilisateur"))
        app_nom = as_str(row.get("application"))
        if not mat or not app_nom:
            rep.error(i, "matricule_utilisateur et application obligatoires")
            continue
        if mat not in users:
            rep.error(i, f"salarie inconnu: {mat}")
            continue
        if app_nom not in apps:
            rep.error(i, f"application inconnue: {app_nom}")
            continue
        key = (users[mat].id, apps[app_nom].id)
        if key in existing:
            rep.skip(i, f"acces deja present : {mat} / {app_nom}")
            continue
        session.add(UserApplication(
            user_id=users[mat].id, application_id=apps[app_nom].id,
            acces=as_bool(row.get("acces")), note=as_str(row.get("note")),
            attribue_par="import",
        ))
        existing.add(key)
        rep.imported += 1
        rep.created(i, f"{mat} / {app_nom}")


HANDLERS = {
    "entites": _import_entites,
    "applications": _import_applications,
    "utilisateurs": _import_utilisateurs,
    "materiel": _import_materiel,
    "affectations": _import_affectations,
    "acces_applicatifs": _import_acces,
}


@router.get("/specs", dependencies=[Depends(require_roles("informatique"))])
def import_specs():
    """Description des fichiers d'import (ordre conseille, colonnes, aide)."""
    return [{"kind": k, **v} for k, v in sorted(SPECS.items(), key=lambda kv: kv[1]["ordre"])]


def _csv_cell(value: str) -> str:
    v = value or ""
    return f'"{v}"' if any(c in v for c in ';"\n') else v


def _choices(kind: str) -> dict[str, list[str]]:
    """Listes deroulantes du modele Excel."""
    choices = {"actif": ["oui", "non"], "acces": ["oui", "non"]}
    if kind == "utilisateurs":
        choices["statut"] = [s.value for s in EmployeeStatus]
    if kind == "materiel":
        choices["statut"] = [s.value for s in AssetStatus]
    return choices


@router.get("/modeles/{kind}", dependencies=[Depends(require_roles("informatique"))])
def import_template(kind: str, format: str = Query("csv", pattern="^(csv|xlsx)$")):
    """Modele CSV (UTF-8 avec BOM, separateur ;) ou classeur Excel, prets a remplir."""
    spec = SPECS.get(kind)
    if not spec:
        raise HTTPException(404, f"Type inconnu. Attendu: {', '.join(KINDS)}")
    if format == "xlsx":
        return Response(xlsx_io.build_template(spec, _choices(kind)), media_type=xlsx_io.XLSX_MIME,
                        headers={"Content-Disposition": f'attachment; filename="{kind}.xlsx"'})
    lines = [";".join(c["nom"] for c in spec["colonnes"])]
    lines += [";".join(_csv_cell(v) for v in ex) for ex in spec["exemples"]]
    body = "﻿" + "\r\n".join(lines) + "\r\n"
    return Response(body.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})


@router.post("/{kind}")
async def import_csv(
    kind: str,
    file: UploadFile = File(...),
    dry_run: bool = False,
    strict: bool = False,
    attendu: str | None = None,
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    """Simulation (dry_run) ou import reel.

    strict : si au moins une ligne est en erreur, rien n'est importe (tout ou rien).
    attendu : empreinte SHA-256 renvoyee par la simulation ; l'import est refuse si le fichier a change.
    """
    if kind not in HANDLERS:
        raise HTTPException(400, f"Type inconnu. Attendu: {', '.join(KINDS)}")
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(413, f"Fichier trop volumineux (maximum {MAX_IMPORT_BYTES // 1024 // 1024} Mo)")
    digest = hashlib.sha256(raw).hexdigest()
    if attendu and attendu != digest:
        raise HTTPException(409, "Le fichier a change depuis la simulation : relancez la simulation.")
    if xlsx_io.is_xlsx(raw) or xlsx_io.is_legacy_office(raw):
        try:
            rows, headers, info = xlsx_io.read_xlsx(raw, MAX_IMPORT_ROWS)
        except xlsx_io.XlsxError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001  (XML invalide, archive tronquee...)
            raise HTTPException(400, "Classeur Excel illisible ou corrompu.") from exc
    else:
        try:
            rows, headers, info = read_csv(raw)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"CSV illisible: {exc}")
    numbers = info.pop("numeros_lignes", None)
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(413, f"Trop de lignes (maximum {MAX_IMPORT_ROWS})")

    spec = SPECS[kind]
    known = {c["nom"] for c in spec["colonnes"]}
    missing = [c["nom"] for c in spec["colonnes"] if c["obligatoire"] and c["nom"] not in headers]
    if missing:
        raise HTTPException(400, "Colonnes obligatoires absentes : " + ", ".join(missing)
                            + ". Colonnes trouvees : " + (", ".join(headers) or "aucune"))
    if not rows:
        raise HTTPException(400, "Le fichier ne contient aucune ligne de donnees")

    rep = Report(kind, dry_run)
    rep.extra = {"sha256": digest, "colonnes_ignorees": [h for h in headers if h and h not in known], **info}
    tracker = None if dry_run else import_undo.Tracker(session)  # lignes creees par cet import (pour pouvoir l'annuler)
    statuts = import_undo.snapshot_statuts(session) if (tracker and kind == "affectations") else None
    try:
        HANDLERS[kind](rows, session, rep)
        if tracker:
            session.flush()
    finally:
        if tracker:
            tracker.close()
    if numbers is not None:
        rep.remap(numbers)

    if dry_run:
        session.rollback()
    elif strict and rep.errors_total:
        session.rollback()
        audit(account.username, "import_refuse", target=kind,
              detail=f"lignes={rep.total} erreurs={rep.errors_total} sha256={digest[:12]}")
        raise HTTPException(409, f"Import refuse : {rep.errors_total} ligne(s) en erreur. "
                                 "Corrigez le fichier puis relancez la simulation.")
    else:
        lot = import_undo.record(session, kind, account.username, digest, tracker, statuts)
        session.commit()
        if lot is not None:
            rep.extra["lot_id"] = lot.id
    audit(account.username, "import_simulation" if dry_run else "import_reel", target=kind,
          detail=f"lignes={rep.total} creees={rep.imported} ignorees={rep.skipped} "
                 f"erreurs={rep.errors_total} sha256={digest[:12]}")
    return rep.dict()


# --- Annulation d'un import ---

def _lot(session: Session, lot_id: int) -> ImportLot:
    lot = session.get(ImportLot, lot_id)
    if not lot:
        raise HTTPException(404, "Import introuvable")
    return lot


@router.get("/lots", dependencies=[Depends(require_roles("informatique"))])
def list_lots(limit: int = Query(30, ge=1, le=200), session: Session = Depends(get_session)):
    """Derniers imports reels (le plus recent d'abord)."""
    rows = session.exec(select(ImportLot).order_by(ImportLot.id.desc()).limit(limit)).all()
    return [{"id": r.id, "kind": r.kind, "titre": SPECS.get(r.kind, {}).get("titre", r.kind), "cree_le": r.cree_le,
             "cree_par": r.cree_par, "nb_creees": r.nb_creees, "statut": r.statut, "annule_le": r.annule_le,
             "annule_par": r.annule_par} for r in rows]


@router.get("/lots/{lot_id}/annulation", dependencies=[Depends(require_roles("informatique"))])
def simulate_undo(lot_id: int, session: Session = Depends(get_session)):
    """Ce que l'annulation supprimerait et ce qui l'empeche (aucune ecriture)."""
    return import_undo.analyser(session, _lot(session, lot_id))


@router.post("/lots/{lot_id}/annuler", dependencies=[Depends(require_roles("informatique"))])
def undo_import(lot_id: int, session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    """Annule un import : supprime ce qu'il a cree, tout ou rien ; refuse si un element est deja utilise ailleurs."""
    lot = _lot(session, lot_id)
    if lot.statut != "actif":
        raise HTTPException(409, "Cet import est deja annule")
    plan = import_undo.analyser(session, lot)
    if plan["bloquants"]:
        audit(account.username, "import_annulation_refusee", target=f"lot/{lot.id}", status=409, detail=lot.kind)
        raise HTTPException(409, "Annulation impossible : " + " ; ".join(plan["bloquants"])
                            + ". Ces elements sont deja utilises : annulez d'abord ce qui en depend, ou conservez-les.")
    result = import_undo.annuler(session, lot, account.username)
    audit(account.username, "import_annule", target=f"lot/{lot.id}", detail=f"{lot.kind} : {result['supprimes']} ligne(s) supprimee(s)")
    return {**result, "id": lot.id}
