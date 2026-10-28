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

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import NaiveDatetime
from sqlalchemy import Index, func, literal_column, text
from sqlmodel import JSON, Column, Field, SQLModel


def utcnow() -> datetime:
    """Heure UTC naive (stockage sans fuseau, coherent avec la base)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Enumerations ---

class EmployeeStatus(str, Enum):
    prevu = "prevu"
    actif = "actif"
    en_depart = "en_depart"
    sorti = "sorti"


class AssetStatus(str, Enum):
    stock = "stock"
    affecte = "affecte"
    rendu = "rendu"
    reforme = "reforme"


class Role(str, Enum):
    rh = "rh"
    informatique = "informatique"
    lecture = "lecture"


# --- Entites (filiales) ---

class EntiteBase(SQLModel):
    code: str = Field(index=True)
    nom: str
    code_parent: Optional[str] = None
    actif: bool = True


class Entite(EntiteBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


# --- Utilisateurs (salaries) ---

class UserBase(SQLModel):
    matricule: Optional[str] = Field(default=None, index=True)
    nom: str
    prenom: str
    entite_id: Optional[int] = Field(default=None, foreign_key="entite.id")
    email: Optional[str] = None
    service: Optional[str] = None
    statut: EmployeeStatus = EmployeeStatus.actif
    date_arrivee: Optional[date] = None
    date_sortie: Optional[date] = None


class User(UserBase, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    cree_le: NaiveDatetime = Field(default_factory=utcnow)
    maj_le: NaiveDatetime = Field(default_factory=utcnow)


# --- Actifs (materiel) ---

class AssetBase(SQLModel):
    identifiant_interne: Optional[str] = Field(default=None, index=True)
    type: Optional[str] = None
    marque: Optional[str] = Field(default=None, index=True)
    modele: Optional[str] = Field(default=None, index=True)
    numero_serie: Optional[str] = Field(default=None, index=True)
    date_achat: Optional[date] = None
    fin_garantie: Optional[date] = None
    echeance_renouvellement: Optional[date] = None
    statut: AssetStatus = AssetStatus.stock
    source: str = "manuel"
    id_externe: Optional[str] = None
    entite_id: Optional[int] = Field(default=None, foreign_key="entite.id")
    notes: Optional[str] = None


class Asset(AssetBase, table=True):
    __tablename__ = "assets"
    id: Optional[int] = Field(default=None, primary_key=True)
    cree_le: NaiveDatetime = Field(default_factory=utcnow)
    maj_le: NaiveDatetime = Field(default_factory=utcnow)


# --- Applications ---

class ApplicationBase(SQLModel):
    nom: str = Field(index=True)
    description: Optional[str] = None
    entite_id: Optional[int] = Field(default=None, foreign_key="entite.id")
    actif: bool = True


class Application(ApplicationBase, table=True):
    __tablename__ = "applications"
    id: Optional[int] = Field(default=None, primary_key=True)


# --- Acces applicatifs (relation plusieurs-a-plusieurs) ---

class UserApplication(SQLModel, table=True):
    __tablename__ = "user_applications"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    application_id: int = Field(foreign_key="applications.id", index=True)
    acces: bool = True
    note: Optional[str] = None
    attribue_par: Optional[str] = None
    date_maj: NaiveDatetime = Field(default_factory=utcnow)


# --- Affectations / remises ---

class Assignment(SQLModel, table=True):
    __tablename__ = "assignments"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date_remise: NaiveDatetime = Field(default_factory=utcnow)
    date_restitution: Optional[NaiveDatetime] = None
    policy_id: Optional[int] = Field(default=None, foreign_key="policies.id")
    statut: str = "en_cours"
    cree_par: Optional[str] = None


class AssignmentAsset(SQLModel, table=True):
    __tablename__ = "assignment_assets"
    assignment_id: int = Field(foreign_key="assignments.id", primary_key=True)
    asset_id: int = Field(foreign_key="assets.id", primary_key=True)


class Signature(SQLModel, table=True):
    __tablename__ = "signatures"
    id: Optional[int] = Field(default=None, primary_key=True)
    assignment_id: int = Field(foreign_key="assignments.id", index=True)
    signataire: Optional[str] = None
    methode: Optional[str] = None
    horodatage: Optional[NaiveDatetime] = None
    empreinte_doc: Optional[str] = None
    audit_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    ged_reference: Optional[str] = None


# --- Parametrage ---

class Policy(SQLModel, table=True):
    """Charte informatique deposee (PDF, Markdown ou Word). Portee : globale (entite_id vide) ou propre
    a une entite. Une seule version active par portee ; les anciennes sont archivees, jamais supprimees."""
    __tablename__ = "policies"
    __table_args__ = (
        Index("uq_policy_active_scope", func.coalesce(literal_column("entite_id"), 0), unique=True,
              postgresql_where=text("statut = 'active'")),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    version: str
    texte: Optional[str] = None  # ancien format (texte brut), conserve pour compatibilite
    date_version: Optional[date] = None
    titre: Optional[str] = None
    entite_id: Optional[int] = Field(default=None, foreign_key="entite.id")
    format_source: Optional[str] = None   # pdf | markdown | docx
    statut: str = "active"                # active | archivee
    fichier_ref: Optional[str] = None     # PDF normalise (reference de stockage)
    sha256: Optional[str] = None          # empreinte du PDF normalise
    source_ref: Optional[str] = None      # fichier d'origine tel que depose
    source_sha256: Optional[str] = None
    source_nom: Optional[str] = None
    nb_pages: Optional[int] = None
    depose_par: Optional[str] = None
    depose_le: Optional[NaiveDatetime] = None


class AssetType(SQLModel, table=True):
    """Type d'actif (liste de parametrage) : propose dans les menus, enrichie automatiquement."""
    __tablename__ = "asset_types"
    __table_args__ = (Index("uq_asset_types_nom_lower", func.lower(literal_column("nom")), unique=True),)
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str = Field(index=True)
    actif: bool = True


class Service(SQLModel, table=True):
    """Service ou departement (liste globale de parametrage)."""
    __tablename__ = "services"
    __table_args__ = (Index("uq_services_nom_lower", func.lower(literal_column("nom")), unique=True),)
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str = Field(index=True)
    actif: bool = True


class Account(SQLModel, table=True):
    __tablename__ = "accounts"
    __table_args__ = (Index("uq_accounts_username_lower", func.lower(literal_column("username")), unique=True),)
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    role: Role = Role.informatique
    actif: bool = True
    hashed_password: str = ""
    nom_affiche: Optional[str] = None            # compte nominatif : nom de la personne
    email: Optional[str] = None
    must_change_password: bool = False           # mot de passe provisoire a remplacer
    token_epoch: int = 0                         # incremente pour revoquer les sessions ouvertes
    derniere_connexion: Optional[NaiveDatetime] = None
    source_auth: str = "local"                   # local | sso (Microsoft 365)
    sso_oid: Optional[str] = Field(default=None, unique=True)  # identifiant stable Entra (jamais l'e-mail)
    sso_upn: Optional[str] = None                # nom d'utilisateur Microsoft (liaison ou dernier connu)
    secours: bool = False                        # compte local de secours (connexion par mot de passe autorisee)
    # Portee (comptes RH et lecture) : globale, ou limitee aux entites de `account_scopes` et a leurs sous-entites.
    # Les comptes informatique sont TOUJOURS globaux (administrateurs), quelle que soit cette valeur.
    portee_globale: bool = True

    @property
    def sso_lie(self) -> bool:
        return bool(self.sso_oid)


class AccountScope(SQLModel, table=True):
    """Entites auxquelles un compte RH ou lecture est limite (leurs sous-entites sont incluses)."""
    __tablename__ = "account_scopes"
    account_id: int = Field(foreign_key="accounts.id", primary_key=True)
    entite_id: int = Field(foreign_key="entite.id", primary_key=True)


class Besoin(SQLModel, table=True):
    """Besoin de materiel declare par les RH pour un salarie (arrivee), traite par l'informatique."""
    __tablename__ = "besoins"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    type: str
    quantite: int = 1
    commentaire: Optional[str] = None
    date_souhaitee: Optional[date] = None
    statut: str = Field(default="demande", index=True)   # demande, en_preparation, satisfait, annule
    cree_par: Optional[str] = None
    traite_par: Optional[str] = None
    assignment_id: Optional[int] = Field(default=None, foreign_key="assignments.id")  # remise qui a solde le besoin
    cree_le: NaiveDatetime = Field(default_factory=utcnow)
    maj_le: NaiveDatetime = Field(default_factory=utcnow)


class ReminderSent(SQLModel, table=True):
    """Rappels deja envoyes (par type, element et destinataire) : evite les doublons et fixe le rythme des relances."""
    __tablename__ = "reminder_sent"
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    cle: str = Field(index=True)
    destinataire: str = Field(index=True)
    envoye_le: NaiveDatetime = Field(default_factory=utcnow)


class Setting(SQLModel, table=True):
    __tablename__ = "settings"
    key: str = Field(primary_key=True)
    value: Optional[str] = None


# --- Journal d'audit (append-only : aucun endpoint de modification/suppression) ---

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: NaiveDatetime = Field(default_factory=utcnow, index=True)
    actor: str = Field(index=True)
    action: str = Field(index=True)
    target: Optional[str] = None
    status: Optional[int] = None
    ip: Optional[str] = None
    detail: Optional[str] = None
