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
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import attachments as att_svc, filestore, tickets as svc
from ..asset_catalog import fold
from ..auth import require_roles
from ..db import get_session
from ..models import Account, Asset, Attachment, Entite, Ticket, TicketComment, TicketNature, User, utcnow

router = APIRouter(
    tags=["tickets"],
    dependencies=[Depends(require_roles("informatique"))],
)


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


@router.get("/tickets/natures")
def list_natures(inclure_inactives: bool = False, session: Session = Depends(get_session)):
    stmt = select(TicketNature)
    if not inclure_inactives:
        stmt = stmt.where(TicketNature.actif == True)  # noqa: E712
    rows = session.exec(stmt.order_by(TicketNature.ordre, TicketNature.id)).all()
    return [
        {"id": n.id, "code": n.code, "libelle": n.libelle, "signale_securite": n.signale_securite,
         "actif": n.actif, "ordre": n.ordre}
        for n in rows
    ]


@router.post("/tickets/natures", status_code=201)
def create_nature(
    data: NatureCreate,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    return svc.creer_nature(
        session, admin.username, code=data.code, libelle=data.libelle,
        signale_securite=data.signale_securite, actif=data.actif, ordre=data.ordre,
    )


@router.put("/tickets/natures/{nature_id}")
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


@router.get("/tickets/compteurs")
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


@router.get("/tickets")
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
    session: Session = Depends(get_session),
):
    stmt = select(Ticket).where(Ticket.anonymise_le == None)  # noqa: E711
    if statut:
        stmt = stmt.where(Ticket.statut == statut)
    if nature:
        stmt = stmt.where(Ticket.nature_code == nature)
    if criticite:
        stmt = stmt.where(Ticket.criticite == criticite)
    if canal:
        stmt = stmt.where(Ticket.canal == canal)
    if niveau_securite:
        stmt = stmt.where(Ticket.niveau_securite == niveau_securite)
    if user_id is not None:
        stmt = stmt.where(Ticket.user_id == user_id)
    if asset_id is not None:
        stmt = stmt.where(Ticket.asset_id == asset_id)

    rows = session.exec(stmt.order_by(Ticket.cree_le.desc(), Ticket.id.desc())).all()
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


@router.post("/tickets", status_code=201)
def create_ticket(
    data: TicketCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    ticket = svc.creer_ticket(
        session,
        admin,
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
    users_map, accounts_map, assets_map, entites_map, natures_map = _charger_maps(session, [ticket])
    return _serialize_ticket(
        ticket, users_map=users_map, accounts_map=accounts_map, assets_map=assets_map,
        entites_map=entites_map, natures_map=natures_map, delais=svc.delais_cibles(session), now=utcnow(),
    )


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    comments = session.exec(
        select(TicketComment).where(TicketComment.ticket_id == ticket.id).order_by(TicketComment.cree_le, TicketComment.id)
    ).all()
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
    out["pieces_jointes"] = [
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
    return out


@router.put("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    fields = data.model_fields_set
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
    users_map, accounts_map, assets_map, entites_map, natures_map = _charger_maps(session, [ticket])
    return _serialize_ticket(
        ticket, users_map=users_map, accounts_map=accounts_map, assets_map=assets_map,
        entites_map=entites_map, natures_map=natures_map, delais=svc.delais_cibles(session), now=utcnow(),
    )


@router.post("/tickets/{ticket_id}/statut")
def update_ticket_status(
    ticket_id: int,
    data: StatutUpdate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    ticket = svc.changer_statut(session, admin, ticket_id, data.statut)
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


@router.post("/tickets/{ticket_id}/commentaires", status_code=201)
def add_ticket_comment(
    ticket_id: int,
    data: CommentCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    ticket, comment = svc.ajouter_commentaire(
        session, admin, ticket_id, contenu=data.contenu, interne=data.interne,
    )
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
        "auteur": admin.nom_affiche or admin.username,
        "interne": comment.interne,
        "contenu": comment.contenu,
        "cree_le": comment.cree_le.isoformat() if comment.cree_le else None,
    }


@router.post("/tickets/{ticket_id}/pieces-jointes", status_code=201)
async def upload_ticket_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    if ticket.statut in svc.STATUTS_FINAUX:
        raise HTTPException(409, "Impossible d'ajouter une piece jointe sur un ticket ferme ou annule")
    # Lecture bornee pour ne pas charger un fichier gigantesque en RAM
    max_read = (att_svc.taille_max_mio(session) * 1024 * 1024) + 1
    data = await file.read(max_read)
    att = att_svc.ajouter_piece_jointe(
        session,
        admin,
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


@router.get("/tickets/{ticket_id}/pieces-jointes/{pj_id}")
def download_ticket_attachment(
    ticket_id: int,
    pj_id: int,
    session: Session = Depends(get_session),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.anonymise_le is not None:
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


@router.delete("/tickets/{ticket_id}/pieces-jointes/{pj_id}", status_code=204)
def delete_ticket_attachment(
    ticket_id: int,
    pj_id: int,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    if ticket.statut in svc.STATUTS_FINAUX:
        raise HTTPException(409, "Impossible de supprimer une piece jointe sur un ticket ferme ou annule")
    att = session.get(Attachment, pj_id)
    if not att or att.entity_type != "ticket" or att.entity_id != ticket.id:
        raise HTTPException(404, "Piece jointe introuvable")
    att_svc.supprimer_piece_jointe(session, admin, att, ticket.reference)


@router.get("/parametres/tickets")
def get_tickets_parametres(session: Session = Depends(get_session)):
    return svc.charger_parametres(session)


@router.put("/parametres/tickets")
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
