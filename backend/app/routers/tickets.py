# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Gemini, Google DeepMind).
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

"""Routes API du module de tickets natif (lot G1 : reserve au role informatique).

Les roles rh et lecture recoivent 403 sur l'ensemble des routes /tickets*.
Toute la logique metier est deleguee a app/tickets.py.
"""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import attachments as att_svc, filestore, tickets as svc
from ..asset_catalog import fold
from ..audit import audit
from ..auth import audit_actor, demandeur_dep, require_roles
from ..db import get_session
from ..models import Account, Asset, Attachment, Entite, Role, Ticket, TicketComment, TicketNature, TicketSecurityDetail, User, utcnow
from .portail import actifs_detenus_salarie

router = APIRouter(tags=["tickets"])


class TicketCreate(BaseModel):
    nature_code: str
    titre: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    criticite: str = "moyenne"
    user_id: int | None = None
    asset_id: int | None = None
    assignment_id: int | None = None
    assigne_a_account_id: int | None = None
    signaler_securite: bool = False


class TicketUpdate(BaseModel):
    nature_code: str | None = None
    criticite: str | None = None
    assigne_a_account_id: int | None = None
    asset_id: int | None = None
    assignment_id: int | None = None
    demandeur_verifie: bool | None = None


class StatutUpdate(BaseModel):
    statut: str


class CommentCreate(BaseModel):
    contenu: str = Field(min_length=1, max_length=4000)
    interne: bool = False


class NatureCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    libelle: str = Field(min_length=1, max_length=100)
    signale_securite: bool = False
    actif: bool = True
    ordre: int = 100


class NatureUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=100)
    signale_securite: bool | None = None
    actif: bool | None = None
    ordre: int | None = None


class TicketsParametresUpdate(BaseModel):
    cloture_auto_jours: int = Field(ge=0, le=svc.CLOTURE_AUTO_MAX)
    delais_cibles_heures: dict[str, int] = Field(default_factory=dict)
    pj_taille_max_mio: int | None = Field(default=None, ge=att_svc.TAILLE_MAX_MIN_MIO, le=att_svc.TAILLE_MAX_MAX_MIO)
    pj_plafond_global_mio: int | None = Field(default=None, ge=att_svc.PLAFOND_GLOBAL_MIN_MIO, le=att_svc.PLAFOND_GLOBAL_MAX_MIO)


class SecuriteNiveauUpdate(BaseModel):
    niveau_securite: str
    sous_categorie: str | None = None


class SecuriteDetailUpdate(BaseModel):
    sous_categorie: str | None = None
    violation_donnees_potentielle: bool | None = None
    date_decouverte_violation: datetime | None = None
    notification_dpo_le: datetime | None = None
    notification_cnil_requise: str | None = None
    confine_le: datetime | None = None
    cause_racine: str | None = Field(default=None, max_length=3000)
    actions_correctives: str | None = Field(default=None, max_length=3000)


def _hors_delai(ticket: Ticket, delais: dict[str, int], now) -> bool:
    return svc.est_hors_delai(ticket, delais, now)


def _serialize_ticket(
    ticket: Ticket,
    *,
    users_map: dict[int, User],
    accounts_map: dict[int, Account],
    assets_map: dict[int, Asset],
    entites_map: dict[int, Entite],
    natures_map: dict[str, TicketNature],
    delais: dict[str, int],
    now,
) -> dict:
    u = users_map.get(ticket.user_id) if ticket.user_id else None
    ass = accounts_map.get(ticket.assigne_a_account_id) if ticket.assigne_a_account_id else None
    cre = accounts_map.get(ticket.cree_par_account_id) if ticket.cree_par_account_id else None
    ast = assets_map.get(ticket.asset_id) if ticket.asset_id else None
    ent = entites_map.get(ticket.entite_id) if ticket.entite_id else None
    nat = natures_map.get(ticket.nature_code)
    return {
        "id": ticket.id,
        "reference": ticket.reference,
        "entite_id": ticket.entite_id,
        "entite_nom": ent.nom if ent else None,
        "user_id": ticket.user_id,
        "user_nom": f"{u.prenom} {u.nom}".strip() if u else None,
        "cree_par_account_id": ticket.cree_par_account_id,
        "cree_par": (cre.nom_affiche or cre.username) if cre else None,
        "assigne_a_account_id": ticket.assigne_a_account_id,
        "assigne_a": (ass.nom_affiche or ass.username) if ass else None,
        "asset_id": ticket.asset_id,
        "asset_identifiant": ast.identifiant_interne if ast else None,
        "materiel_type": ticket.materiel_type,
        "materiel_marque": ticket.materiel_marque,
        "materiel_modele": ticket.materiel_modele,
        "assignment_id": ticket.assignment_id,
        "nature_code": ticket.nature_code,
        "nature_libelle": nat.libelle if nat else ticket.nature_code,
        "criticite_demandeur": ticket.criticite_demandeur,
        "criticite": ticket.criticite,
        "statut": ticket.statut,
        "titre": ticket.titre,
        "description": ticket.description,
        "canal": ticket.canal,
        "demandeur_verifie": ticket.demandeur_verifie,
        "niveau_securite": ticket.niveau_securite,
        "cree_le": ticket.cree_le.isoformat() if ticket.cree_le else None,
        "premiere_reponse_le": ticket.premiere_reponse_le.isoformat() if ticket.premiere_reponse_le else None,
        "en_attente_depuis": ticket.en_attente_depuis.isoformat() if ticket.en_attente_depuis else None,
        "duree_attente_sec": ticket.duree_attente_sec,
        "resolu_le": ticket.resolu_le.isoformat() if ticket.resolu_le else None,
        "ferme_le": ticket.ferme_le.isoformat() if ticket.ferme_le else None,
        "nb_reouvertures": ticket.nb_reouvertures,
        "mtta_sec": svc.calculer_mtta_sec(ticket),
        "mttr_sec": svc.calculer_mttr_sec(ticket),
        "hors_delai": _hors_delai(ticket, delais, now),
        "maj_le": ticket.maj_le.isoformat() if ticket.maj_le else None,
        "maj_publique_le": ticket.maj_publique_le.isoformat() if ticket.maj_publique_le else None,
    }


def _charger_maps(session: Session, rows: list[Ticket]):
    user_ids = {t.user_id for t in rows if t.user_id}
    acc_ids = {i for t in rows for i in (t.cree_par_account_id, t.assigne_a_account_id) if i}
    asset_ids = {t.asset_id for t in rows if t.asset_id}
    entite_ids = {t.entite_id for t in rows if t.entite_id}
    users_map = {u.id: u for u in session.exec(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    accounts_map = {a.id: a for a in session.exec(select(Account).where(Account.id.in_(acc_ids))).all()} if acc_ids else {}
    assets_map = {a.id: a for a in session.exec(select(Asset).where(Asset.id.in_(asset_ids))).all()} if asset_ids else {}
    entites_map = {e.id: e for e in session.exec(select(Entite).where(Entite.id.in_(entite_ids))).all()} if entite_ids else {}
    natures_map = {n.code: n for n in session.exec(select(TicketNature)).all()}
    return users_map, accounts_map, assets_map, entites_map, natures_map


def _serialize_ticket_portail(
    ticket: Ticket,
    *,
    natures_map: dict[str, TicketNature],
) -> dict:
    """Vue salarie : jamais de maj_le interne, jamais de niveau_securite detaille (seul booleen signalement_securite)."""
    nat = natures_map.get(ticket.nature_code)
    return {
        "id": ticket.id,
        "reference": ticket.reference,
        "asset_id": ticket.asset_id,
        "materiel_type": ticket.materiel_type,
        "materiel_marque": ticket.materiel_marque,
        "materiel_modele": ticket.materiel_modele,
        "nature_code": ticket.nature_code,
        "nature_libelle": nat.libelle if nat else ticket.nature_code,
        "criticite": ticket.criticite,
        "statut": ticket.statut,
        "titre": ticket.titre,
        "description": ticket.description,
        "signalement_securite": ticket.niveau_securite != "aucun",
        "cree_le": ticket.cree_le.isoformat() if ticket.cree_le else None,
        "resolu_le": ticket.resolu_le.isoformat() if ticket.resolu_le else None,
        "ferme_le": ticket.ferme_le.isoformat() if ticket.ferme_le else None,
        "maj_publique_le": ticket.maj_publique_le.isoformat() if ticket.maj_publique_le else None,
    }


@router.get("/tickets/natures", dependencies=[Depends(require_roles("informatique", "demandeur"))])
def list_natures(
    inclure_inactives: bool = False,
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    account, _ = ctx
    stmt = select(TicketNature)
    if not inclure_inactives or account.role == Role.demandeur:
        stmt = stmt.where(TicketNature.actif == True)  # noqa: E712
    rows = session.exec(stmt.order_by(TicketNature.ordre, TicketNature.id)).all()
    return [
        {"id": n.id, "code": n.code, "libelle": n.libelle, "signale_securite": n.signale_securite,
         "actif": n.actif, "ordre": n.ordre}
        for n in rows
    ]


@router.post("/tickets/natures", status_code=201, dependencies=[Depends(require_roles("informatique"))])
def create_nature(
    data: NatureCreate,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    return svc.creer_nature(
        session, admin.username, code=data.code, libelle=data.libelle,
        signale_securite=data.signale_securite, actif=data.actif, ordre=data.ordre,
    )


@router.put("/tickets/natures/{nature_id}", dependencies=[Depends(require_roles("informatique"))])
def update_nature(
    nature_id: int,
    data: NatureUpdate,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    return svc.modifier_nature(
        session, admin.username, nature_id,
        libelle=data.libelle, signale_securite=data.signale_securite,
        actif=data.actif, ordre=data.ordre,
    )


@router.get("/tickets/compteurs", dependencies=[Depends(require_roles("informatique"))])
def ticket_compteurs(session: Session = Depends(get_session)):
    now = utcnow()
    delais = svc.delais_cibles(session)
    rows = session.exec(
        select(Ticket).where(
            Ticket.anonymise_le == None,  # noqa: E711
            Ticket.statut.notin_(svc.STATUTS_FINAUX),
        )
    ).all()
    nouveaux = sum(1 for t in rows if t.statut == "nouveau")
    en_cours = sum(1 for t in rows if t.statut == "en_cours")
    en_attente = sum(1 for t in rows if t.statut == "en_attente")
    resolus = sum(1 for t in rows if t.statut == "resolu")
    securite_a_qualifier = sum(1 for t in rows if t.niveau_securite == "signale")
    hors_delai = sum(1 for t in rows if _hors_delai(t, delais, now))
    return {
        "nouveaux": nouveaux,
        "en_cours": en_cours,
        "en_attente": en_attente,
        "resolus": resolus,
        "ouverts": nouveaux + en_cours + en_attente,
        "securite_a_qualifier": securite_a_qualifier,
        "hors_delai": hors_delai,
    }


@router.get("/tickets", dependencies=[Depends(require_roles("informatique", "demandeur"))])
def list_tickets(
    statut: str | None = None,
    nature: str | None = None,
    criticite: str | None = None,
    canal: str | None = None,
    niveau_securite: str | None = None,
    user_id: int | None = None,
    asset_id: int | None = None,
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    account, dem_user = ctx
    stmt = select(Ticket).where(Ticket.anonymise_le == None)  # noqa: E711
    if account.role == Role.demandeur:
        # Regle 1 §2 : filtre SQL strict sur user_id, jamais apres chargement
        stmt = stmt.where(Ticket.user_id == dem_user.id)
    else:
        if canal:
            stmt = stmt.where(Ticket.canal == canal)
        if niveau_securite:
            stmt = stmt.where(Ticket.niveau_securite == niveau_securite)
        if user_id is not None:
            stmt = stmt.where(Ticket.user_id == user_id)
        if asset_id is not None:
            stmt = stmt.where(Ticket.asset_id == asset_id)
    if statut:
        stmt = stmt.where(Ticket.statut == statut)
    if nature:
        stmt = stmt.where(Ticket.nature_code == nature)
    if criticite:
        stmt = stmt.where(Ticket.criticite == criticite)

    rows = session.exec(stmt.order_by(Ticket.cree_le.desc(), Ticket.id.desc())).all()
    if account.role == Role.demandeur:
        natures_map = {n.code: n for n in session.exec(select(TicketNature)).all()}
        termes = [t for t in fold(q).split(" ") if t]
        if termes:
            rows = [
                t for t in rows
                if all(terme in fold(" ".join(filter(None, [t.reference, t.titre, t.materiel_marque, t.materiel_modele]))) for terme in termes)
            ]
        total = len(rows)
        page = rows[offset:offset + limit]
        return {
            "items": [_serialize_ticket_portail(t, natures_map=natures_map) for t in page],
            "total": total,
        }

    users_map, accounts_map, assets_map, entites_map, natures_map = _charger_maps(session, rows)
    now = utcnow()
    delais = svc.delais_cibles(session)

    termes = [t for t in fold(q).split(" ") if t]
    if termes:
        filtrees = []
        for t in rows:
            u = users_map.get(t.user_id) if t.user_id else None
            meule = fold(" ".join(filter(None, [
                t.reference, t.titre, u.nom if u else "", u.prenom if u else "",
                t.materiel_marque, t.materiel_modele,
            ])))
            if all(terme in meule for terme in termes):
                filtrees.append(t)
        rows = filtrees

    total = len(rows)
    page = rows[offset:offset + limit]
    return {
        "items": [
            _serialize_ticket(
                t, users_map=users_map, accounts_map=accounts_map, assets_map=assets_map,
                entites_map=entites_map, natures_map=natures_map, delais=delais, now=now,
            )
            for t in page
        ],
        "total": total,
    }


@router.post("/tickets", status_code=201, dependencies=[Depends(require_roles("informatique", "demandeur"))])
def create_ticket(
    data: TicketCreate,
    background: BackgroundTasks,
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    account, dem_user = ctx
    if account.role == Role.demandeur:
        asset_id = data.asset_id
        if asset_id is not None:
            mes_actifs = {a.id for a, _ in actifs_detenus_salarie(session, dem_user.id)}
            if asset_id not in mes_actifs:
                raise HTTPException(404, "Materiel introuvable")
        ticket = svc.creer_ticket(
            session,
            account,
            nature_code=data.nature_code,
            titre=data.titre,
            description=data.description,
            criticite=data.criticite,
            user_id=dem_user.id,
            asset_id=asset_id,
            assignment_id=None,
            assigne_a_account_id=None,
            canal="portail",
            demandeur_verifie=True,
            signaler_securite=data.signaler_securite,
        )
        if ticket.niveau_securite == "signale":
            dests = svc.destinataires_alerte_securite(session)
            if dests:
                background.add_task(
                    svc.alerter_securite_en_fond, ticket.id, ticket.reference, ticket.criticite,
                    "Evenement de securite signale", dests,
                )
        natures_map = {n.code: n for n in session.exec(select(TicketNature)).all()}
        return _serialize_ticket_portail(ticket, natures_map=natures_map)

    ticket = svc.creer_ticket(
        session,
        account,
        nature_code=data.nature_code,
        titre=data.titre,
        description=data.description,
        criticite=data.criticite,
        user_id=data.user_id,
        asset_id=data.asset_id,
        assignment_id=data.assignment_id,
        assigne_a_account_id=data.assigne_a_account_id,
        canal="it",
        demandeur_verifie=True,
        signaler_securite=data.signaler_securite,
    )
    if ticket.user_id:
        user = session.get(User, ticket.user_id)
        if user and user.email:
            background.add_task(
                svc.envoyer_notification_ticket,
                ticket.id, ticket.reference, ticket.criticite, "Ticket ouvert par l'informatique", user.email,
            )
    if ticket.niveau_securite == "signale":
        dests = svc.destinataires_alerte_securite(session)
        if dests:
            background.add_task(
                svc.alerter_securite_en_fond, ticket.id, ticket.reference, ticket.criticite,
                "Evenement de securite signale", dests,
            )
    users_map, accounts_map, assets_map, entites_map, natures_map = _charger_maps(session, [ticket])
    return _serialize_ticket(
        ticket, users_map=users_map, accounts_map=accounts_map, assets_map=assets_map,
        entites_map=entites_map, natures_map=natures_map, delais=svc.delais_cibles(session), now=utcnow(),
    )


@router.get("/tickets/{ticket_id}", dependencies=[Depends(require_roles("informatique", "demandeur"))])
def get_ticket(
    ticket_id: int,
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    account, dem_user = ctx
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.anonymise_le == None)  # noqa: E711
    if account.role == Role.demandeur:
        stmt = stmt.where(Ticket.user_id == dem_user.id)
    ticket = session.exec(stmt).first()
    if not ticket:
        raise HTTPException(404, "Ticket introuvable")

    c_stmt = select(TicketComment).where(TicketComment.ticket_id == ticket.id)
    if account.role == Role.demandeur:
        c_stmt = c_stmt.where(TicketComment.interne == False)  # noqa: E712
    comments = session.exec(c_stmt.order_by(TicketComment.cree_le, TicketComment.id)).all()

    pjs = [
        {
            "id": a.id,
            "display_name": a.display_name,
            "mime_type": a.mime_type,
            "size_bytes": a.size_bytes,
            "sha256": a.sha256,
            "cree_le": a.cree_le.isoformat() if a.cree_le else None,
        }
        for a in att_svc.lister_pieces_jointes(session, "ticket", ticket.id)
    ]

    if account.role == Role.demandeur:
        natures_map = {n.code: n for n in session.exec(select(TicketNature)).all()}
        out = _serialize_ticket_portail(ticket, natures_map=natures_map)
        out["commentaires"] = [
            {
                "id": c.id,
                "auteur": "Vous" if c.auteur_account_id == account.id else "Support informatique",
                "contenu": c.contenu,
                "cree_le": c.cree_le.isoformat() if c.cree_le else None,
            }
            for c in comments
        ]
        out["pieces_jointes"] = pjs
        return out

    users_map, accounts_map, assets_map, entites_map, natures_map = _charger_maps(session, [ticket])
    c_acc_ids = {c.auteur_account_id for c in comments if c.auteur_account_id and c.auteur_account_id not in accounts_map}
    if c_acc_ids:
        for a in session.exec(select(Account).where(Account.id.in_(c_acc_ids))).all():
            accounts_map[a.id] = a

    out = _serialize_ticket(
        ticket, users_map=users_map, accounts_map=accounts_map, assets_map=assets_map,
        entites_map=entites_map, natures_map=natures_map, delais=svc.delais_cibles(session), now=utcnow(),
    )
    out["commentaires"] = [
        {
            "id": c.id,
            "auteur_account_id": c.auteur_account_id,
            "auteur": (accounts_map[c.auteur_account_id].nom_affiche or accounts_map[c.auteur_account_id].username)
            if c.auteur_account_id in accounts_map else None,
            "interne": c.interne,
            "contenu": c.contenu,
            "cree_le": c.cree_le.isoformat() if c.cree_le else None,
        }
        for c in comments
    ]
    out["pieces_jointes"] = pjs
    return out


@router.put("/tickets/{ticket_id}", dependencies=[Depends(require_roles("informatique"))])
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    fields = data.model_fields_set
    avant = session.get(Ticket, ticket_id)
    niveau_avant = avant.niveau_securite if avant else None
    ticket = svc.modifier_ticket(
        session,
        admin,
        ticket_id,
        nature_code=data.nature_code if "nature_code" in fields else None,
        criticite=data.criticite if "criticite" in fields else None,
        assigne_a_account_id=data.assigne_a_account_id,
        assigne_fourni="assigne_a_account_id" in fields,
        asset_id=data.asset_id,
        asset_fourni="asset_id" in fields,
        assignment_id=data.assignment_id,
        assignment_fourni="assignment_id" in fields,
        demandeur_verifie=data.demandeur_verifie if "demandeur_verifie" in fields else None,
    )
    if niveau_avant == "aucun" and ticket.niveau_securite == "signale":
        dests = svc.destinataires_alerte_securite(session)
        if dests:
            background.add_task(
                svc.alerter_securite_en_fond,
                ticket.id, ticket.reference, ticket.criticite, "Signalement securite", dests,
            )
    users_map, accounts_map, assets_map, entites_map, natures_map = _charger_maps(session, [ticket])
    return _serialize_ticket(
        ticket, users_map=users_map, accounts_map=accounts_map, assets_map=assets_map,
        entites_map=entites_map, natures_map=natures_map, delais=svc.delais_cibles(session), now=utcnow(),
    )


@router.post("/tickets/{ticket_id}/statut", dependencies=[Depends(require_roles("informatique", "demandeur"))])
def update_ticket_status(
    ticket_id: int,
    data: StatutUpdate,
    background: BackgroundTasks,
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    account, dem_user = ctx
    ticket = svc.changer_statut(
        session, account, ticket_id, data.statut,
        demandeur_user_id=dem_user.id if dem_user else None,
    )
    if account.role == Role.demandeur:
        natures_map = {n.code: n for n in session.exec(select(TicketNature)).all()}
        return _serialize_ticket_portail(ticket, natures_map=natures_map)
    if ticket.statut == "resolu" and ticket.user_id:
        user = session.get(User, ticket.user_id)
        if user and user.email:
            cloture_j = svc.cloture_auto_jours(session)
            background.add_task(
                svc.envoyer_notification_ticket,
                ticket.id, ticket.reference, ticket.criticite, "Ticket resolu", user.email,
                cloture_jours=cloture_j if ticket.niveau_securite not in ("signale", "incident") else None,
            )
    users_map, accounts_map, assets_map, entites_map, natures_map = _charger_maps(session, [ticket])
    return _serialize_ticket(
        ticket, users_map=users_map, accounts_map=accounts_map, assets_map=assets_map,
        entites_map=entites_map, natures_map=natures_map, delais=svc.delais_cibles(session), now=utcnow(),
    )


@router.post("/tickets/{ticket_id}/commentaires", status_code=201, dependencies=[Depends(require_roles("informatique", "demandeur"))])
def add_ticket_comment(
    ticket_id: int,
    data: CommentCreate,
    background: BackgroundTasks,
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    account, dem_user = ctx
    ticket, comment = svc.ajouter_commentaire(
        session, account, ticket_id, contenu=data.contenu, interne=data.interne,
        demandeur_user_id=dem_user.id if dem_user else None,
    )
    if account.role == Role.demandeur:
        if ticket.assigne_a_account_id:
            ass = session.get(Account, ticket.assigne_a_account_id)
            if ass and ass.email:
                background.add_task(
                    svc.envoyer_notification_ticket,
                    ticket.id, ticket.reference, ticket.criticite, "Nouvelle reponse du salarie", ass.email, est_it=True,
                )
        return {
            "id": comment.id,
            "ticket_id": comment.ticket_id,
            "auteur": "Vous",
            "contenu": comment.contenu,
            "cree_le": comment.cree_le.isoformat() if comment.cree_le else None,
        }
    # Une note interne ne declenche jamais d'e-mail vers le salarie.
    if not comment.interne and ticket.user_id:
        user = session.get(User, ticket.user_id)
        if user and user.email:
            background.add_task(
                svc.envoyer_notification_ticket,
                ticket.id, ticket.reference, ticket.criticite, "Nouvelle reponse de l'informatique", user.email,
            )
    return {
        "id": comment.id,
        "ticket_id": comment.ticket_id,
        "auteur_account_id": comment.auteur_account_id,
        "auteur": account.nom_affiche or account.username,
        "interne": comment.interne,
        "contenu": comment.contenu,
        "cree_le": comment.cree_le.isoformat() if comment.cree_le else None,
    }


@router.post("/tickets/{ticket_id}/pieces-jointes", status_code=201, dependencies=[Depends(require_roles("informatique", "demandeur"))])
def upload_ticket_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    account, dem_user = ctx
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    if dem_user is not None:
        stmt = stmt.where(Ticket.user_id == dem_user.id)
    ticket = session.exec(stmt.with_for_update()).first()
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    if ticket.statut in svc.STATUTS_FINAUX:
        raise HTTPException(409, "Impossible d'ajouter une piece jointe sur un ticket ferme ou annule")
    max_read = (att_svc.taille_max_mio(session) * 1024 * 1024) + 1
    data = file.file.read(max_read)
    att = att_svc.ajouter_piece_jointe(
        session,
        account,
        entity_type="ticket",
        entity_id=ticket.id,
        filename=file.filename,
        data=data,
        target_audit=ticket.reference,
    )
    now = utcnow()
    ticket.maj_le = now
    ticket.maj_publique_le = now
    session.add(ticket)
    session.commit()
    return {
        "id": att.id,
        "display_name": att.display_name,
        "mime_type": att.mime_type,
        "size_bytes": att.size_bytes,
        "sha256": att.sha256,
        "cree_le": att.cree_le.isoformat() if att.cree_le else None,
    }


@router.get("/tickets/{ticket_id}/pieces-jointes/{pj_id}", dependencies=[Depends(require_roles("informatique", "demandeur"))])
def download_ticket_attachment(
    ticket_id: int,
    pj_id: int,
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    _, dem_user = ctx
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.anonymise_le == None)  # noqa: E711
    if dem_user is not None:
        stmt = stmt.where(Ticket.user_id == dem_user.id)
    ticket = session.exec(stmt).first()
    if not ticket:
        raise HTTPException(404, "Ticket introuvable")
    att = session.get(Attachment, pj_id)
    if not att or att.entity_type != "ticket" or att.entity_id != ticket.id:
        raise HTTPException(404, "Piece jointe introuvable")
    data = filestore.read_attachment(att.storage_ref)
    safe_name = att.display_name.replace('"', "_")
    return Response(
        content=data,
        media_type=att.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/tickets/{ticket_id}/pieces-jointes/{pj_id}", status_code=204, dependencies=[Depends(require_roles("informatique"))])
def delete_ticket_attachment(
    ticket_id: int,
    pj_id: int,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    ticket = session.exec(select(Ticket).where(Ticket.id == ticket_id).with_for_update()).first()
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    if ticket.statut in svc.STATUTS_FINAUX:
        raise HTTPException(409, "Impossible de supprimer une piece jointe sur un ticket ferme ou annule")
    att = session.get(Attachment, pj_id)
    if not att or att.entity_type != "ticket" or att.entity_id != ticket.id:
        raise HTTPException(404, "Piece jointe introuvable")
    att_svc.supprimer_piece_jointe(session, admin, att, ticket.reference)


def _serialize_securite(sec: TicketSecurityDetail, niveau_securite: str) -> dict:
    return {
        "ticket_id": sec.ticket_id,
        "niveau_securite": niveau_securite,
        "signale_le": sec.signale_le.isoformat() if sec.signale_le else None,
        "signale_par": sec.signale_par,
        "qualifie_le": sec.qualifie_le.isoformat() if sec.qualifie_le else None,
        "qualification_sec": sec.qualification_sec,
        "qualifie_par_account_id": sec.qualifie_par_account_id,
        "sous_categorie": sec.sous_categorie,
        "escalade_le": sec.escalade_le.isoformat() if sec.escalade_le else None,
        "escalade_par_account_id": sec.escalade_par_account_id,
        "violation_donnees_potentielle": sec.violation_donnees_potentielle,
        "date_decouverte_violation": sec.date_decouverte_violation.isoformat() if sec.date_decouverte_violation else None,
        "notification_dpo_le": sec.notification_dpo_le.isoformat() if sec.notification_dpo_le else None,
        "notification_cnil_requise": sec.notification_cnil_requise,
        "confine_le": sec.confine_le.isoformat() if sec.confine_le else None,
        "cause_racine": sec.cause_racine,
        "actions_correctives": sec.actions_correctives,
    }


@router.get("/tickets/{ticket_id}/securite", dependencies=[Depends(require_roles("informatique"))])
def get_ticket_securite(
    ticket_id: int,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    sec = session.get(TicketSecurityDetail, ticket.id)
    if not sec:
        return {"ticket_id": ticket.id, "niveau_securite": ticket.niveau_securite, "dossier": None}
    audit(audit_actor(admin), "ticket_securite_lecture", target=ticket.reference)
    return _serialize_securite(sec, ticket.niveau_securite)


@router.put("/tickets/{ticket_id}/securite", dependencies=[Depends(require_roles("informatique"))])
def put_ticket_securite(
    ticket_id: int,
    data: SecuriteDetailUpdate,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    sec = svc.modifier_dossier_securite(
        session,
        admin,
        ticket_id,
        fields_set=data.model_fields_set,
        sous_categorie=data.sous_categorie,
        violation_donnees_potentielle=data.violation_donnees_potentielle,
        date_decouverte_violation=data.date_decouverte_violation,
        notification_dpo_le=data.notification_dpo_le,
        notification_cnil_requise=data.notification_cnil_requise,
        confine_le=data.confine_le,
        cause_racine=data.cause_racine,
        actions_correctives=data.actions_correctives,
    )
    ticket = session.get(Ticket, ticket_id)
    return _serialize_securite(sec, ticket.niveau_securite)


@router.post("/tickets/{ticket_id}/securite/niveau", dependencies=[Depends(require_roles("informatique"))])
def post_ticket_securite_niveau(
    ticket_id: int,
    data: SecuriteNiveauUpdate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    avant = session.get(Ticket, ticket_id)
    niveau_avant = avant.niveau_securite if avant else None
    ticket, sec = svc.changer_niveau_securite(
        session, admin, ticket_id, data.niveau_securite, sous_categorie=data.sous_categorie,
    )
    # Alerte uniquement a la montee (aucun -> signale/incident, ou signale/sans_suite -> incident),
    # jamais lors d'une retrogradation incident -> signale.
    montee_securite = (
        (ticket.niveau_securite == "incident" and niveau_avant != "incident")
        or (ticket.niveau_securite == "signale" and niveau_avant == "aucun")
    )
    if montee_securite:
        dests = svc.destinataires_alerte_securite(session)
        if dests:
            evt = "Incident de securite confirme" if ticket.niveau_securite == "incident" else "Evenement de securite signale"
            background.add_task(
                svc.alerter_securite_en_fond, ticket.id, ticket.reference, ticket.criticite, evt, dests,
            )
    return _serialize_securite(sec, ticket.niveau_securite)


@router.get("/parametres/tickets", dependencies=[Depends(require_roles("informatique"))])
def get_tickets_parametres(session: Session = Depends(get_session)):
    return svc.charger_parametres(session)


@router.put("/parametres/tickets", dependencies=[Depends(require_roles("informatique"))])
def put_tickets_parametres(
    data: TicketsParametresUpdate,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    return svc.sauver_parametres(
        session,
        admin.username,
        data.cloture_auto_jours,
        data.delais_cibles_heures,
        pj_taille_max_mio=data.pj_taille_max_mio,
        pj_plafond_global_mio=data.pj_plafond_global_mio,
    )
