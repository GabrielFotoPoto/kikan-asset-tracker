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

"""Parametrage (informatique) : types d'actifs, services, fusion marques/modeles, modele de PDF, etat du scellement."""
import base64
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, update
from sqlmodel import Session, select

from .. import acces_remise, charte, pdf_template, signature_image, signing
from ..audit import audit
from ..auth import get_current_account, require_roles
from ..catalogs import MAX_NAME
from ..db import get_session
from ..filestore import active_name
from .branding import ICON_KEY
from ..models import Account, Asset, AssetType, Besoin, BesoinCategorie, CoutRemplacement, Service, Setting, User, utcnow
from ..pdfgen import build_receipt
from ..rules import audit_change, changed_fields, count, refuse_delete
from .import_data import MAX_IMPORT_BYTES, MAX_IMPORT_ROWS

router = APIRouter(
    prefix="/parametres", tags=["parametres"],
    dependencies=[Depends(require_roles("informatique"))],
)


class ItemIn(BaseModel):
    nom: str = Field(max_length=MAX_NAME)
    actif: bool = True


def _clean_name(value: str) -> str:
    name = re.sub(r"\s+", " ", (value or "")).strip()
    if not name:
        raise HTTPException(400, "Le nom est obligatoire")
    return name


# --- Types d'actifs et services : meme mecanique ---

def _usage(session: Session, kind: str, nom: str) -> int:
    if kind == "types":
        return count(session, Asset, func.lower(Asset.type) == nom.lower())
    if kind == "categories-besoin":
        return count(session, Besoin, func.lower(Besoin.type) == nom.lower())
    return count(session, User, func.lower(User.service) == nom.lower())


def _register(kind: str, model, usage_label: str) -> None:
    @router.get(f"/{kind}", name=f"liste_{kind}")
    def list_items(session: Session = Depends(get_session)):
        rows = session.exec(select(model)).all()
        rows.sort(key=lambda r: r.nom.lower())
        return [{"id": r.id, "nom": r.nom, "actif": r.actif, "utilise": _usage(session, kind, r.nom),
                 **({"gammes": list(r.gammes or [])} if kind == "categories-besoin" else {})} for r in rows]

    @router.post(f"/{kind}", status_code=201, name=f"creer_{kind}")
    def create_item(data: ItemIn, session: Session = Depends(get_session),
                    account: Account = Depends(get_current_account)):
        nom = _clean_name(data.nom)
        if session.exec(select(model).where(func.lower(model.nom) == nom.lower())).first():
            raise HTTPException(409, f"Deja present : {nom}")
        obj = model(nom=nom, actif=data.actif)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        audit(account.username, "parametrage", target=f"{kind}/{obj.id}", detail=f"ajout : {nom}")
        return {"id": obj.id, "nom": obj.nom, "actif": obj.actif, "utilise": 0}

    @router.put(f"/{kind}/{{item_id}}", name=f"modifier_{kind}")
    def update_item(item_id: int, data: ItemIn, session: Session = Depends(get_session),
                    account: Account = Depends(get_current_account)):
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(404, "Element introuvable")
        nom = _clean_name(data.nom)
        other = session.exec(select(model).where(func.lower(model.nom) == nom.lower(), model.id != obj.id)).first()
        if other:
            raise HTTPException(409, f"Deja present : {nom}")
        old = obj.nom
        fields = changed_fields(obj, {"nom": nom, "actif": data.actif})
        obj.nom, obj.actif = nom, data.actif
        session.add(obj)
        renamed = 0
        if nom != old:
            # Le renommage suit : toutes les fiches qui portaient l'ancien nom prennent le nouveau.
            if kind == "types":
                res = session.exec(update(Asset).where(func.lower(Asset.type) == old.lower()).values(type=nom))
                session.exec(update(CoutRemplacement).where(func.lower(CoutRemplacement.type) == old.lower()).values(type=nom))
            elif kind == "categories-besoin":
                res = session.exec(update(Besoin).where(func.lower(Besoin.type) == old.lower()).values(type=nom))
            else:
                res = session.exec(update(User).where(func.lower(User.service) == old.lower()).values(service=nom))
            renamed = res.rowcount or 0
        session.commit()
        audit_change(account.username, kind, obj.id, fields)
        return {"id": obj.id, "nom": obj.nom, "actif": obj.actif, "utilise": _usage(session, kind, obj.nom), "mis_a_jour": renamed}

    @router.delete(f"/{kind}/{{item_id}}", status_code=204, name=f"supprimer_{kind}")
    def delete_item(item_id: int, session: Session = Depends(get_session),
                    account: Account = Depends(get_current_account)):
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(404, "Element introuvable")
        refuse_delete(
            "cet element", {usage_label: _usage(session, kind, obj.nom)},
            "Desactivez-le plutot que de le supprimer, ou fusionnez-le avec un autre.",
        )
        nom = obj.nom
        if kind == "types":
            for cout in session.exec(select(CoutRemplacement).where(func.lower(CoutRemplacement.type) == nom.lower())).all():
                session.delete(cout)
        session.delete(obj)
        session.commit()
        audit(account.username, "parametrage", target=f"{kind}/{item_id}", detail=f"suppression : {nom}")


_register("types", AssetType, "actif(s)")
_register("services", Service, "salarie(s)")
_register("categories-besoin", BesoinCategorie, "besoin(s)")


class GammesIn(BaseModel):
    gammes: list[str] = Field(default_factory=list, max_length=10)


@router.put("/categories-besoin/{item_id}/gammes")
def set_gammes(item_id: int, data: GammesIn, session: Session = Depends(get_session),
               account: Account = Depends(get_current_account)):
    """Gammes proposees aux RH pour une categorie de besoin (ex. Normal, Pro, XL) ; liste vide = aucune gamme."""
    cat = session.get(BesoinCategorie, item_id)
    if not cat:
        raise HTTPException(404, "Categorie introuvable")
    propres, vus = [], set()
    for g in data.gammes:
        g = re.sub(r"[\x00-\x1f\x7f\s]+", " ", g or "").strip()
        if not g:
            continue
        if len(g) > 40:
            raise HTTPException(400, "Une gamme ne peut pas depasser 40 caracteres")
        if g.lower() not in vus:
            vus.add(g.lower())
            propres.append(g)
    cat.gammes = propres
    session.add(cat)
    session.commit()
    audit(account.username, "parametrage", target=f"categories-besoin/{cat.id}", detail=f"gammes : {len(propres)}")
    return {"id": cat.id, "nom": cat.nom, "gammes": propres}


# --- Couts de remplacement estimes (previsions de renouvellement, C3) ---

class CoutIn(BaseModel):
    type: str = Field(max_length=MAX_NAME)
    marque: str | None = Field(default=None, max_length=MAX_NAME)
    modele: str | None = Field(default=None, max_length=MAX_NAME)
    montant: Decimal = Field(ge=0, le=Decimal("1000000"), max_digits=9, decimal_places=2)


def _cout_sortie(session: Session, c: CoutRemplacement) -> dict:
    conditions = [func.lower(Asset.type) == c.type.lower()]
    if c.modele:
        conditions += [func.lower(Asset.marque) == (c.marque or "").lower(), func.lower(Asset.modele) == c.modele.lower()]
    return {"id": c.id, "type": c.type, "marque": c.marque, "modele": c.modele,
            "montant": float(Decimal(c.montant_centimes) / 100), "utilise": count(session, Asset, *conditions)}


@router.get("/couts")
def list_couts(session: Session = Depends(get_session)):
    rows = session.exec(select(CoutRemplacement)).all()
    rows.sort(key=lambda c: (c.type.lower(), (c.marque or "").lower(), (c.modele or "").lower()))
    return [_cout_sortie(session, c) for c in rows]


@router.put("/couts")
def set_cout(data: CoutIn, session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    """Cree ou remplace le cout d'un type (ou d'un modele precis de ce type)."""
    type_ = session.exec(select(AssetType).where(func.lower(AssetType.nom) == _clean_name(data.type).lower())).first()
    if not type_:
        raise HTTPException(400, "Type inconnu : ajoutez-le d'abord dans l'onglet Types")
    marque = re.sub(r"\s+", " ", data.marque or "").strip() or None
    modele = re.sub(r"\s+", " ", data.modele or "").strip() or None
    if bool(marque) != bool(modele):
        raise HTTPException(400, "Une exception vise un modele precis : indiquez la marque et le modele (ou ni l'un ni l'autre)")
    cle = (func.lower(CoutRemplacement.type) == type_.nom.lower(),
           func.lower(func.coalesce(CoutRemplacement.marque, "")) == (marque or "").lower(),
           func.lower(func.coalesce(CoutRemplacement.modele, "")) == (modele or "").lower())
    cout = session.exec(select(CoutRemplacement).where(*cle)).first()
    centimes = int((data.montant * 100).to_integral_value())
    if cout:
        cout.montant_centimes, cout.maj_le, cout.maj_par = centimes, utcnow(), account.username
        action = "modification"
    else:
        cout = CoutRemplacement(type=type_.nom, marque=marque, modele=modele, montant_centimes=centimes, maj_par=account.username)
        action = "ajout"
    session.add(cout)
    session.commit()
    session.refresh(cout)
    audit(account.username, "parametrage", target=f"couts/{cout.id}", detail=f"{action} : cout de remplacement ({type_.nom})")
    return _cout_sortie(session, cout)


@router.delete("/couts/{cout_id}", status_code=204)
def delete_cout(cout_id: int, session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    cout = session.get(CoutRemplacement, cout_id)
    if not cout:
        raise HTTPException(404, "Cout introuvable")
    session.delete(cout)
    session.commit()
    audit(account.username, "parametrage", target=f"couts/{cout_id}", detail="suppression : cout de remplacement")


# --- Fusion des marques et des modeles ---

class MergeIn(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=200)
    cible: str = Field(max_length=MAX_NAME)
    marque: str | None = None  # modeles : marque concernee
    apercu: bool = False


def _grouped(session: Session, column, *conditions) -> list[dict]:
    stmt = select(column, func.count()).where(column.is_not(None), *conditions).group_by(column)
    rows = session.exec(stmt).all()
    return sorted(({"nom": nom, "count": n} for nom, n in rows if nom and nom.strip()), key=lambda r: r["nom"].lower())


@router.get("/marques")
def list_marques(session: Session = Depends(get_session)):
    return _grouped(session, Asset.marque)


@router.get("/modeles")
def list_modeles(marque: str = Query(min_length=1), session: Session = Depends(get_session)):
    return _grouped(session, Asset.modele, Asset.marque == marque)


def _merge(session: Session, account: Account, data: MergeIn, column, extra, label: str):
    cible = _clean_name(data.cible)
    sources = sorted({s for s in data.sources if s and s.strip()})
    if not sources:
        raise HTTPException(400, "Aucune valeur a fusionner")
    where = (column.in_(sources), *extra)
    n = count(session, Asset, *where)
    if data.apercu:
        return {"apercu": True, "materiels": n, "cible": cible}
    session.exec(update(Asset).where(*where).values({column.key: cible, "maj_le": datetime.utcnow()}))
    session.commit()
    audit(account.username, "fusion_" + label, target=cible,
          detail=f"{len(sources)} valeur(s) vers {cible} ; {n} materiel(s)")
    return {"apercu": False, "materiels": n, "cible": cible}


@router.post("/marques/fusion")
def merge_marques(data: MergeIn, session: Session = Depends(get_session),
                  account: Account = Depends(get_current_account)):
    return _merge(session, account, data, Asset.marque, (), "marques")


@router.post("/modeles/fusion")
def merge_modeles(data: MergeIn, session: Session = Depends(get_session),
                  account: Account = Depends(get_current_account)):
    if not data.marque:
        raise HTTPException(400, "La marque est obligatoire")
    return _merge(session, account, data, Asset.modele, (Asset.marque == data.marque,), "modeles")


# --- Modele de PDF ---

class PdfIn(BaseModel):
    organisation: str = Field(default="", max_length=pdf_template.MAX_LEN["organisation"])
    mentions: str = Field(default="", max_length=pdf_template.MAX_LEN["mentions"])
    pied: str = Field(default="", max_length=pdf_template.MAX_LEN["pied"])
    inclure_acces: bool | None = None  # None = inchange


class LogoIn(BaseModel):
    image: str = Field(max_length=pdf_template.MAX_B64_CHARS)


def _set_setting(session: Session, key: str, value: str | None) -> None:
    row = session.get(Setting, key)
    if row:
        row.value = value
    else:
        row = Setting(key=key, value=value)
    session.add(row)


def _ctrl_clean(text: str) -> str:
    """Retire les caracteres de controle (hors retour a la ligne) ; les textes sont de toute facon echappes."""
    return "".join(c for c in text if c == "\n" or c >= " ").strip()


@router.get("/pdf")
def get_pdf_template(session: Session = Depends(get_session)):
    return {**pdf_template.public_view(pdf_template.load_template(session)),
            "inclure_acces": acces_remise.include_access(session)}


@router.put("/pdf")
def set_pdf_template(data: PdfIn, session: Session = Depends(get_session),
                     account: Account = Depends(get_current_account)):
    current = pdf_template.load_template(session)
    new = {k: _ctrl_clean(getattr(data, k)) for k in pdf_template.TEXT_KEYS}
    fields = [k for k, v in new.items() if current[k] != v]
    for name, key in pdf_template.TEXT_KEYS.items():
        _set_setting(session, key, new[name])
    if data.inclure_acces is not None:
        if data.inclure_acces != acces_remise.include_access(session):
            fields.append("inclure_acces")
        acces_remise.set_include_access(session, data.inclure_acces)
    session.commit()
    audit_change(account.username, "parametres/pdf", 0, fields)
    return {**pdf_template.public_view(pdf_template.load_template(session)),
            "inclure_acces": acces_remise.include_access(session)}


@router.post("/pdf/logo")
def upload_logo(data: LogoIn, session: Session = Depends(get_session),
                account: Account = Depends(get_current_account)):
    try:
        png, meta = pdf_template.sanitize_logo(data.image)
    except pdf_template.LogoError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_setting(session, pdf_template.LOGO_KEY, base64.b64encode(png).decode())
    session.commit()
    audit(account.username, "parametrage", target="parametres/pdf",
          detail=f"logo : {meta['largeur']}x{meta['hauteur']} sha256={meta['sha256'][:12]}")
    return meta


@router.put("/icone")
def set_icone(data: LogoIn, session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    """Icone de l'application (affichee sans connexion sur la page de connexion) : meme verification que le logo des PDF."""
    try:
        png, meta = pdf_template.sanitize_logo(data.image)
    except pdf_template.LogoError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_setting(session, ICON_KEY, base64.b64encode(png).decode())
    session.commit()
    audit(account.username, "parametrage", target="parametres/icone",
          detail=f"icone : {meta['largeur']}x{meta['hauteur']} sha256={meta['sha256'][:12]}")
    return meta


@router.delete("/icone", status_code=204)
def delete_icone(session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    _set_setting(session, ICON_KEY, None)
    session.commit()
    audit(account.username, "parametrage", target="parametres/icone", detail="icone supprimee")


@router.get("/pdf/logo")
def get_logo(session: Session = Depends(get_session)):
    logo = pdf_template.load_template(session)["logo"]
    if not logo:
        raise HTTPException(404, "Aucun logo")
    return Response(logo, media_type="image/png")


@router.delete("/pdf/logo", status_code=204)
def delete_logo(session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    _set_setting(session, pdf_template.LOGO_KEY, None)
    session.commit()
    audit(account.username, "parametrage", target="parametres/pdf", detail="logo supprime")


@router.get("/pdf/apercu")
def preview(format: str = Query("png", pattern="^(png|pdf)$"), session: Session = Depends(get_session)):
    """Accuse factice (non signe, non scelle) avec le modele courant."""
    template = pdf_template.load_template(session)
    pdf = build_receipt(
        user={"nom": "Exemple", "prenom": "Alice", "matricule": "E0000"},
        entite_nom="Entite d'exemple",
        assets=[{"type": "PC portable", "marque": "Marque", "modele": "Modele", "numero_serie": "SN-EXEMPLE",
                 "identifiant_interne": "PC-0000"}],
        title="Apercu - accuse de remise de materiel (document factice, non signe)",
        signataire="Alice Exemple",
        temoin="apercu",
        template=template,
    )
    if format == "pdf":
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'inline; filename="apercu.pdf"'})
    return Response(charte.render_page_png(pdf, 0), media_type="image/png")


# --- Etat du scellement et des limites (lecture seule) ---

@router.get("/etat")
def state():
    signing.ensure_self_signed_cert()
    with open(signing.CERT_PATH, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    now = datetime.utcnow()
    tsa = None
    if signing.TSA_URL:
        tsa = urlparse(signing.TSA_URL).hostname or "configuree"
    return {
        "certificat": {
            "sujet": cert.subject.rfc4514_string(),
            "emetteur": cert.issuer.rfc4514_string(),
            "auto_signe": cert.subject == cert.issuer,
            "valide_du": cert.not_valid_before_utc.date().isoformat(),
            "valide_au": cert.not_valid_after_utc.date().isoformat(),
            "jours_restants": (cert.not_valid_after_utc.replace(tzinfo=None) - now).days,
            "empreinte_sha256": cert.fingerprint(hashes.SHA256()).hex(),
        },
        "autorite_de_temps": tsa,
        "signature_manuscrite_obligatoire": signature_image.HANDWRITTEN_REQUIRED,
        "stockage": active_name(),
        "limites": {
            "import_mo": MAX_IMPORT_BYTES // 1024 // 1024,
            "import_lignes": MAX_IMPORT_ROWS,
            "charte_mo": charte.MAX_BYTES // 1024 // 1024,
            "charte_pages": charte.MAX_PAGES,
        },
    }
