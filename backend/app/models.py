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

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import JSON, Column, Field, SQLModel


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
    cree_le: datetime = Field(default_factory=datetime.utcnow)
    maj_le: datetime = Field(default_factory=datetime.utcnow)


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
    cree_le: datetime = Field(default_factory=datetime.utcnow)
    maj_le: datetime = Field(default_factory=datetime.utcnow)


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
    date_maj: datetime = Field(default_factory=datetime.utcnow)


# --- Affectations / remises ---

class Assignment(SQLModel, table=True):
    __tablename__ = "assignments"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date_remise: datetime = Field(default_factory=datetime.utcnow)
    date_restitution: Optional[datetime] = None
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
    horodatage: Optional[datetime] = None
    empreinte_doc: Optional[str] = None
    audit_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    ged_reference: Optional[str] = None


# --- Parametrage ---

class Policy(SQLModel, table=True):
    __tablename__ = "policies"
    id: Optional[int] = Field(default=None, primary_key=True)
    version: str
    texte: Optional[str] = None
    date_version: Optional[date] = None


class AssetType(SQLModel, table=True):
    __tablename__ = "asset_types"
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str = Field(index=True)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    role: Role = Role.informatique
    actif: bool = True
    hashed_password: str = ""


class Setting(SQLModel, table=True):
    __tablename__ = "settings"
    key: str = Field(primary_key=True)
    value: Optional[str] = None
