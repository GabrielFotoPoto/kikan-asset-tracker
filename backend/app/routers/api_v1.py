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

"""API d'integration /v1 : un outil externe pousse du materiel et des salaries vers Kikan avec un jeton.

Authentification par jeton d'API uniquement (pas de session). Idempotent (cle : id_externe), jamais de suppression, lots de
100 elements au plus, simulation avec ?dry_run=1. Voir docs/API.md.
"""
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlmodel import Session, select

from .. import attachments as att_svc, integration, tickets as tickets_svc
from ..apitoken import MAX_BATCH, ApiAuth, api_auth
from ..audit import audit
from ..db import get_session
from ..models import Asset, EmployeeStatus, Entite, ExternalLink, Ticket, TicketComment, TicketNature, User

router = APIRouter(prefix="/v1", tags=["api-v1"])


class AssetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_externe: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    marque: str | None = Field(default=None, max_length=100)
    modele: str | None = Field(default=None, max_length=100)
    numero_serie: str | None = Field(default=None, max_length=100)
    identifiant_interne: str | None = Field(default=None, max_length=100)
    date_achat: date | None = None
    fin_garantie: date | None = None
    echeance_renouvellement: date | None = None
    entite_code: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_externe: str = Field(min_length=1, max_length=100)
    matricule: str | None = Field(default=None, max_length=50)
    nom: str | None = Field(default=None, max_length=200)
    prenom: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    service: str | None = Field(default=None, max_length=100)
    date_arrivee: date | None = None
    entite_code: str | None = Field(default=None, max_length=100)
    homonyme: str | None = Field(default=None, pattern="^(lier|creer)$")  # decision si un salarie porte deja ce nom


class AssetPut(AssetIn):
    id_externe: str | None = Field(default=None, max_length=100)   # l'identifiant est dans l'adresse


class UserPut(UserIn):
    id_externe: str | None = Field(default=None, max_length=100)


class AssetBatch(BaseModel):
    items: list[AssetIn] = Field(min_length=1, max_length=MAX_BATCH)


class UserBatch(BaseModel):
    items: list[UserIn] = Field(min_length=1, max_length=MAX_BATCH)


def _run(session: Session, auth: ApiAuth, kind: str, items: list[dict], dry_run: bool) -> dict:
    fn = integration.upsert_asset if kind == "asset" else integration.upsert_user
    results = []
    for item in items:
        try:
            with session.begin_nested():
                results.append(fn(session, auth.systeme, auth.scope, item))
        except Exception:  # noqa: BLE001  (un element en erreur n'arrete pas le lot)
            results.append({"id_externe": item.get("id_externe"), "resultat": "refuse", "message": "Donnees non traitables"})
    if dry_run:
        session.rollback()
        for r in results:
            r["id"] = None
    else:
        session.commit()
    summary: dict[str, int] = {}
    for r in results:
        summary[r["resultat"]] = summary.get(r["resultat"], 0) + 1
    audit(auth.actor, f"api_{kind}s_{'simulation' if dry_run else 'import'}", detail=", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    return {"simulation": dry_run, "resume": summary, "resultats": results}


@router.get("/me")
def me(auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    codes = sorted(e.code for e in session.exec(select(Entite)).all() if auth.scope.allows(e.id))
    return {"nom": auth.token.nom, "source": auth.token.source, "droits": auth.token.droits.split(","),
            "expire_le": auth.token.expire_le, "perimetre": "global" if auth.scope.globale else codes}


@router.get("/assets")
def list_assets(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("assets_lecture")
    stmt = auth.scope.where(select(Asset), Asset.entite_id).order_by(Asset.id).offset(offset).limit(limit)
    assets = session.exec(stmt).all()
    ents = {e.id: e.code for e in session.exec(select(Entite)).all()}
    links = {l.kikan_id: l.externe_id for l in session.exec(select(ExternalLink).where(
        ExternalLink.systeme == auth.systeme, ExternalLink.objet == "asset")).all()}
    return [{"id": a.id, "id_externe": links.get(a.id), "type": a.type, "marque": a.marque, "modele": a.modele,
             "numero_serie": a.numero_serie, "identifiant_interne": a.identifiant_interne, "statut": a.statut.value,
             "entite_code": ents.get(a.entite_id)} for a in assets]


@router.get("/users")
def list_users(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("users_lecture")
    stmt = auth.scope.users(select(User)).order_by(User.id).offset(offset).limit(limit)
    users = session.exec(stmt).all()
    ents = {e.id: e.code for e in session.exec(select(Entite)).all()}
    links = {l.kikan_id: l.externe_id for l in session.exec(select(ExternalLink).where(
        ExternalLink.systeme == auth.systeme, ExternalLink.objet == "user")).all()}
    return [{"id": u.id, "id_externe": links.get(u.id), "matricule": u.matricule, "nom": u.nom, "prenom": u.prenom,
             "email": u.email, "service": u.service, "statut": u.statut.value, "entite_code": ents.get(u.entite_id)} for u in users]


@router.post("/assets/_batch")
def put_assets(data: AssetBatch, dry_run: bool = False, auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("assets_ecriture")
    return _run(session, auth, "asset", [i.model_dump() for i in data.items], dry_run)


@router.put("/assets/{id_externe}")
def put_asset(id_externe: str, data: AssetPut, dry_run: bool = False, auth: ApiAuth = Depends(api_auth),
              session: Session = Depends(get_session)):
    auth.need("assets_ecriture")
    item = data.model_dump()
    item["id_externe"] = id_externe
    return _run(session, auth, "asset", [item], dry_run)["resultats"][0]


@router.post("/users/_batch")
def put_users(data: UserBatch, dry_run: bool = False, auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("users_ecriture")
    return _run(session, auth, "user", [i.model_dump() for i in data.items], dry_run)


@router.put("/users/{id_externe}")
def put_user(id_externe: str, data: UserPut, dry_run: bool = False, auth: ApiAuth = Depends(api_auth),
             session: Session = Depends(get_session)):
    auth.need("users_ecriture")
    item = data.model_dump()
    item["id_externe"] = id_externe
    return _run(session, auth, "user", [item], dry_run)["resultats"][0]


# --- Tickets (/v1/tickets*, lot G7) ---

class TicketPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nature_code: str = Field(min_length=1, max_length=40)
    titre: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    criticite: str = Field(default="moyenne", max_length=20)
    canal: str = Field(default="api", pattern="^(api|email)$")
    signaler_securite: bool = False
    demandeur_email: str | None = Field(default=None, max_length=200)
    demandeur_matricule: str | None = Field(default=None, max_length=50)
    demandeur_id_externe: str | None = Field(default=None, max_length=100)
    asset_id_externe: str | None = Field(default=None, max_length=100)
    asset_identifiant: str | None = Field(default=None, max_length=100)
    materiel_hors_affectation: bool = False
    entite_code: str | None = Field(default=None, max_length=100)


class TicketStatutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statut: str = Field(min_length=1, max_length=20)


class TicketCommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contenu: str = Field(min_length=1, max_length=4000)
    interne: bool = False
    auteur_type: Literal["demandeur", "it"] = "demandeur"


def _ticket_by_ref(session: Session, auth: ApiAuth, reference: str) -> Ticket:
    ref = (reference or "").strip().upper()
    ticket = session.exec(
        select(Ticket).where(func.upper(Ticket.reference) == ref, Ticket.anonymise_le.is_(None))
    ).first()
    if not ticket or not auth.scope.allows(ticket.entite_id):
        raise HTTPException(404, "Ticket introuvable")
    return ticket


def _ticket_v1_dict(
    ticket: Ticket,
    *,
    ents: dict[int, str],
    id_externe: str | None = None,
    comments: list[TicketComment] | None = None,
) -> dict:
    sensible = ticket.niveau_securite in ("signale", "incident")
    out = {
        "id": ticket.id,
        "reference": ticket.reference,
        "id_externe": id_externe,
        "entite_code": ents.get(ticket.entite_id) if ticket.entite_id is not None else None,
        "nature_code": ticket.nature_code,
        "criticite": ticket.criticite,
        "statut": ticket.statut,
        "canal": ticket.canal,
        "demandeur_verifie": ticket.demandeur_verifie,
        "niveau_securite": ticket.niveau_securite,
        "texte_masque": sensible,
        "titre": None if sensible else ticket.titre,
        "description": None if sensible else ticket.description,
        "cree_le": ticket.cree_le,
        "resolu_le": ticket.resolu_le,
        "ferme_le": ticket.ferme_le,
        "maj_le": ticket.maj_le,
        "maj_publique_le": ticket.maj_publique_le,
    }
    if comments is not None:
        out["commentaires"] = (
            []
            if sensible
            else [
                {"id": c.id, "interne": c.interne, "contenu": c.contenu, "cree_le": c.cree_le}
                for c in comments
            ]
        )
    return out


def _resolve_v1_demandeur(session: Session, auth: ApiAuth, data: TicketPut) -> User | None:
    provided = sum(1 for v in (data.demandeur_email, data.demandeur_matricule, data.demandeur_id_externe) if v)
    if provided == 0:
        return None
    if provided > 1:
        raise HTTPException(422, "Indiquez un seul identifiant de demandeur (email, matricule ou id_externe)")
    if data.demandeur_email:
        email = data.demandeur_email.strip().lower()
        matches = session.exec(
            auth.scope.users(
                select(User).where(func.lower(User.email) == email, User.statut == EmployeeStatus.actif)
            )
        ).all()
        if len(matches) != 1:
            raise HTTPException(422, "Salarie actif introuvable ou ambigu pour cette adresse e-mail")
        return matches[0]
    if data.demandeur_matricule:
        mat = data.demandeur_matricule.strip().lower()
        user = session.exec(
            auth.scope.users(
                select(User).where(func.lower(User.matricule) == mat, User.statut == EmployeeStatus.actif)
            )
        ).first()
        if not user:
            raise HTTPException(422, "Salarie actif introuvable dans le perimetre")
        return user
    link = integration.get_link(session, auth.systeme, "user", data.demandeur_id_externe.strip())
    user = session.get(User, link.kikan_id) if link else None
    if not user or user.statut != EmployeeStatus.actif or not auth.scope.allows(user.entite_id):
        raise HTTPException(422, "Salarie actif introuvable dans le perimetre")
    return user


def _resolve_v1_asset(session: Session, auth: ApiAuth, data: TicketPut) -> Asset | None:
    if data.asset_id_externe and data.asset_identifiant:
        raise HTTPException(422, "Indiquez un seul identifiant de materiel")
    if data.asset_id_externe:
        link = integration.get_link(session, auth.systeme, "asset", data.asset_id_externe.strip())
        asset = session.get(Asset, link.kikan_id) if link else None
        if not asset or not auth.scope.allows(asset.entite_id):
            raise HTTPException(422, "Materiel introuvable dans le perimetre")
        return asset
    if data.asset_identifiant:
        ident = data.asset_identifiant.strip().lower()
        asset = session.exec(
            auth.scope.where(select(Asset), Asset.entite_id).where(func.lower(Asset.identifiant_interne) == ident)
        ).first()
        if not asset:
            raise HTTPException(422, "Materiel introuvable dans le perimetre")
        return asset
    return None


@router.get("/tickets/natures")
def list_ticket_natures(auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("tickets_lecture")
    rows = session.exec(
        select(TicketNature).where(TicketNature.actif == True).order_by(TicketNature.ordre, TicketNature.id)  # noqa: E712
    ).all()
    return [{"code": n.code, "libelle": n.libelle, "signale_securite": n.signale_securite} for n in rows]


@router.get("/tickets")
def list_tickets(
    statut: str | None = None,
    nature: str | None = None,
    criticite: str | None = None,
    modifie_depuis: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: ApiAuth = Depends(api_auth),
    session: Session = Depends(get_session),
):
    auth.need("tickets_lecture")
    stmt = auth.scope.where(select(Ticket), Ticket.entite_id).where(Ticket.anonymise_le.is_(None))
    if statut:
        if statut not in tickets_svc.STATUTS:
            raise HTTPException(422, "Statut invalide")
        stmt = stmt.where(Ticket.statut == statut)
    if nature:
        stmt = stmt.where(Ticket.nature_code == nature.strip().lower())
    if criticite:
        if criticite not in tickets_svc.CRITICITES:
            raise HTTPException(422, "Criticite invalide")
        stmt = stmt.where(Ticket.criticite == criticite)
    if modifie_depuis is not None:
        stmt = stmt.where(Ticket.maj_le >= tickets_svc._to_utc_naive(modifie_depuis))
    rows = session.exec(stmt.order_by(Ticket.id).offset(offset).limit(limit)).all()
    ents = {e.id: e.code for e in session.exec(select(Entite)).all()}
    links = {
        l.kikan_id: l.externe_id
        for l in session.exec(
            select(ExternalLink).where(ExternalLink.systeme == auth.systeme, ExternalLink.objet == "ticket")
        ).all()
    }
    return [_ticket_v1_dict(t, ents=ents, id_externe=links.get(t.id)) for t in rows]


@router.get("/tickets/{reference}")
def get_ticket_v1(reference: str, auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("tickets_lecture")
    ticket = _ticket_by_ref(session, auth, reference)
    ents = {e.id: e.code for e in session.exec(select(Entite)).all()}
    link = integration.link_of(session, auth.systeme, "ticket", ticket.id)
    include_internal = auth.has("tickets_interne")
    c_stmt = select(TicketComment).where(TicketComment.ticket_id == ticket.id)
    if not include_internal:
        c_stmt = c_stmt.where(TicketComment.interne == False)  # noqa: E712
    comments = session.exec(c_stmt.order_by(TicketComment.cree_le, TicketComment.id)).all()
    return _ticket_v1_dict(ticket, ents=ents, id_externe=link.externe_id if link else None, comments=comments)


@router.put("/tickets/{id_externe}")
def put_ticket_v1(
    id_externe: str,
    data: TicketPut,
    background: BackgroundTasks,
    dry_run: bool = False,
    auth: ApiAuth = Depends(api_auth),
    session: Session = Depends(get_session),
):
    auth.need("tickets_ecriture")
    ext_id = (id_externe or "").strip()
    if not ext_id or len(ext_id) > 100:
        raise HTTPException(422, "id_externe invalide (1 a 100 caracteres)")

    existing_link = integration.get_link(session, auth.systeme, "ticket", ext_id)
    if existing_link is not None:
        ticket = session.get(Ticket, existing_link.kikan_id)
        if not ticket or ticket.anonymise_le is not None or not auth.scope.allows(ticket.entite_id):
            raise HTTPException(404, "Ticket introuvable")
        if ticket.statut in tickets_svc.STATUTS_FINAUX or ticket.niveau_securite in ("signale", "incident"):
            return {
                "simulation": dry_run, "resultat": "inchange", "id": None if dry_run else ticket.id,
                "reference": ticket.reference, "id_externe": ext_id,
                "canal": ticket.canal, "demandeur_verifie": ticket.demandeur_verifie,
            }
        asset_upd = _resolve_v1_asset(session, auth, data)
        asset_fourni = bool(data.asset_id_externe or data.asset_identifiant)
        asset_changed = asset_fourni and ((asset_upd.id if asset_upd else None) != ticket.asset_id)
        changed = (data.nature_code != ticket.nature_code) or (data.criticite != ticket.criticite) or asset_changed
        if not changed:
            return {
                "simulation": dry_run, "resultat": "inchange", "id": None if dry_run else ticket.id,
                "reference": ticket.reference, "id_externe": ext_id,
                "canal": ticket.canal, "demandeur_verifie": ticket.demandeur_verifie,
            }
        niveau_avant = ticket.niveau_securite
        hors_aff_upd = False
        if asset_changed and asset_upd is not None and ticket.user_id is not None:
            from ..detentions import detenteur_actuel_actif
            det = detenteur_actuel_actif(session, asset_upd.id)
            hors_aff_upd = bool(det is not None and det != ticket.user_id and data.materiel_hors_affectation)
        with session.begin_nested():
            tickets_svc.modifier_ticket(
                session, None, ticket.id,
                nature_code=data.nature_code, criticite=data.criticite,
                asset_id=asset_upd.id if asset_upd else None,
                asset_fourni=asset_changed,
                materiel_hors_affectation=data.materiel_hors_affectation,
                actor_name=auth.actor, commit=False,
            )
        if dry_run:
            session.rollback()
        else:
            session.commit()
            session.refresh(ticket)
            audit(auth.actor, "ticket_maj", target=ticket.reference, detail=f"id_externe={ext_id}")
            if hors_aff_upd and ticket.asset_id is not None and ticket.user_id is not None:
                tickets_svc.auditer_materiel_hors_affectation(auth.actor, ticket.reference, ticket.asset_id, ticket.user_id)
            if niveau_avant == "aucun" and ticket.niveau_securite == "signale":
                dests = tickets_svc.destinataires_alerte_securite(session)
                if dests:
                    background.add_task(
                        tickets_svc.alerter_securite_en_fond,
                        ticket.id, ticket.reference, ticket.criticite, "Signalement securite (API)", dests,
                    )
        return {
            "simulation": dry_run, "resultat": "modifie", "id": None if dry_run else ticket.id,
            "reference": ticket.reference, "id_externe": ext_id,
            "canal": ticket.canal, "demandeur_verifie": ticket.demandeur_verifie,
        }

    user = _resolve_v1_demandeur(session, auth, data)
    asset = _resolve_v1_asset(session, auth, data)
    ent_override: int | None = None
    if data.entite_code:
        ent = session.exec(select(Entite).where(func.lower(Entite.code) == data.entite_code.strip().lower())).first()
        if not ent or not auth.scope.allows(ent.id):
            raise HTTPException(404, "Entite introuvable")
        ent_override = ent.id

    effective_ent = (
        (user.entite_id if user and user.entite_id is not None else None)
        or (asset.entite_id if asset and asset.entite_id is not None else None)
        or ent_override
    )
    if not auth.scope.allows(effective_ent):
        raise HTTPException(404, "Entite hors perimetre du jeton")

    demandeur_verifie = data.canal == "api"
    hors_aff_crea = False
    if user is not None and asset is not None and data.materiel_hors_affectation:
        from ..detentions import detenteur_actuel_actif
        det = detenteur_actuel_actif(session, asset.id)
        hors_aff_crea = bool(det is not None and det != user.id)
    with session.begin_nested():
        ticket = tickets_svc.creer_ticket(
            session, None,
            nature_code=data.nature_code,
            titre=data.titre,
            description=data.description,
            criticite=data.criticite,
            user_id=user.id if user else None,
            asset_id=asset.id if asset else None,
            canal=data.canal,
            demandeur_verifie=demandeur_verifie,
            signaler_securite=data.signaler_securite,
            materiel_hors_affectation=data.materiel_hors_affectation,
            entite_id_override=ent_override,
            actor_name=auth.actor,
            commit=False,
        )
        session.add(ExternalLink(systeme=auth.systeme, objet="ticket", externe_id=ext_id, kikan_id=ticket.id))
        session.flush()
    if dry_run:
        session.rollback()
        return {
            "simulation": True, "resultat": "cree", "id": None, "reference": None,
            "id_externe": ext_id, "canal": data.canal, "demandeur_verifie": demandeur_verifie,
        }
    session.commit()
    session.refresh(ticket)
    audit(auth.actor, "ticket_creation", target=ticket.reference, detail=f"canal={ticket.canal} nature={ticket.nature_code}")
    if hors_aff_crea and asset is not None and user is not None:
        tickets_svc.auditer_materiel_hors_affectation(auth.actor, ticket.reference, asset.id, user.id)
    if user and user.email:
        background.add_task(
            tickets_svc.envoyer_notification_ticket,
            ticket.id, ticket.reference, ticket.criticite, "Ticket cree", user.email,
        )
    if ticket.niveau_securite == "signale":
        dests = tickets_svc.destinataires_alerte_securite(session)
        if dests:
            background.add_task(
                tickets_svc.alerter_securite_en_fond,
                ticket.id, ticket.reference, ticket.criticite, "Signalement securite (API)", dests,
            )
    return {
        "simulation": False, "resultat": "cree", "id": ticket.id, "reference": ticket.reference,
        "id_externe": ext_id, "canal": ticket.canal, "demandeur_verifie": ticket.demandeur_verifie,
    }


@router.post("/tickets/{reference}/statut")
def change_ticket_statut_v1(
    reference: str,
    data: TicketStatutIn,
    background: BackgroundTasks,
    auth: ApiAuth = Depends(api_auth),
    session: Session = Depends(get_session),
):
    auth.need("tickets_ecriture")
    ticket = _ticket_by_ref(session, auth, reference)
    updated = tickets_svc.changer_statut(session, None, ticket.id, data.statut, actor_name=auth.actor)
    if updated.statut == "resolu" and updated.user_id:
        user = session.get(User, updated.user_id)
        if user and user.email:
            cloture_j = tickets_svc.cloture_auto_jours(session)
            background.add_task(
                tickets_svc.envoyer_notification_ticket,
                updated.id, updated.reference, updated.criticite, "Ticket resolu", user.email,
                cloture_jours=cloture_j if updated.niveau_securite not in ("signale", "incident") else None,
            )
    ents = {e.id: e.code for e in session.exec(select(Entite)).all()}
    link = integration.link_of(session, auth.systeme, "ticket", updated.id)
    return _ticket_v1_dict(updated, ents=ents, id_externe=link.externe_id if link else None)


@router.post("/tickets/{reference}/commentaires", status_code=201)
def add_ticket_comment_v1(
    reference: str,
    data: TicketCommentIn,
    background: BackgroundTasks,
    auth: ApiAuth = Depends(api_auth),
    session: Session = Depends(get_session),
):
    auth.need("tickets_ecriture")
    if data.interne:
        auth.need("tickets_interne")
    ticket = _ticket_by_ref(session, auth, reference)
    est_reponse_it = (not data.interne) and (data.auteur_type == "it")
    est_reponse_demandeur = (not data.interne) and (data.auteur_type == "demandeur")
    updated, comment = tickets_svc.ajouter_commentaire(
        session, None, ticket.id, contenu=data.contenu, interne=data.interne,
        actor_name=auth.actor, compter_premiere_reponse=est_reponse_it,
        reprendre_si_en_attente=est_reponse_demandeur,
    )
    if not comment.interne:
        if data.auteur_type == "it" and updated.user_id:
            user = session.get(User, updated.user_id)
            if user and user.email:
                background.add_task(
                    tickets_svc.envoyer_notification_ticket,
                    updated.id, updated.reference, updated.criticite, "Nouvelle reponse de l'informatique", user.email,
                )
        elif data.auteur_type == "demandeur" and updated.assigne_a_account_id:
            from ..models import Account as _Acc
            ass = session.get(_Acc, updated.assigne_a_account_id)
            if ass and ass.email:
                background.add_task(
                    tickets_svc.envoyer_notification_ticket,
                    updated.id, updated.reference, updated.criticite, "Nouvelle reponse du salarie", ass.email, est_it=True,
                )
    return {"id": comment.id, "interne": comment.interne, "cree_le": comment.cree_le}


@router.get("/tickets/{reference}/pieces-jointes")
def list_ticket_attachments_v1(reference: str, auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("tickets_lecture")
    ticket = _ticket_by_ref(session, auth, reference)
    if ticket.niveau_securite in ("signale", "incident"):
        return []
    rows = att_svc.lister_pieces_jointes(session, "ticket", ticket.id)
    return [
        {"id": a.id, "nom": a.display_name, "mime_type": a.mime_type, "taille": a.size_bytes, "cree_le": a.cree_le}
        for a in rows
    ]


@router.post("/tickets/{reference}/pieces-jointes", status_code=201)
def upload_ticket_attachment_v1(
    reference: str,
    file: UploadFile = File(...),
    auth: ApiAuth = Depends(api_auth),
    session: Session = Depends(get_session),
):
    auth.need("tickets_ecriture")
    ticket = _ticket_by_ref(session, auth, reference)
    locked = session.exec(select(Ticket).where(Ticket.id == ticket.id).with_for_update()).first()
    if not locked or locked.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    if locked.statut in tickets_svc.STATUTS_FINAUX:
        raise HTTPException(409, "Impossible d'ajouter une piece jointe a un ticket ferme ou annule")
    max_bytes = att_svc.taille_max_mio(session) * 1024 * 1024
    raw = file.file.read(max_bytes + 1)
    att = att_svc.ajouter_piece_jointe(
        session, None, entity_type="ticket", entity_id=locked.id,
        filename=file.filename, data=raw, target_audit=locked.reference, actor_name=auth.actor,
    )
    locked.maj_le = att.cree_le
    locked.maj_publique_le = att.cree_le
    session.add(locked)
    session.commit()
    return {"id": att.id, "nom": att.display_name, "mime_type": att.mime_type, "taille": att.size_bytes, "cree_le": att.cree_le}
