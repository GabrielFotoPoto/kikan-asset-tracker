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

"""Scellement PAdES du PDF avec un certificat auto-signe de l'organisation.

Le certificat est genere au premier usage dans KIKAN_CERT_DIR (monte en volume,
hors image). Pour la production, remplacer par le certificat de l'organisation.
"""
import datetime
import io
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_DIR = os.environ.get("KIKAN_CERT_DIR", "/certs")
KEY_PATH = os.path.join(CERT_DIR, "kikan-key.pem")
CERT_PATH = os.path.join(CERT_DIR, "kikan-cert.pem")
TSA_URL = os.environ.get("KIKAN_TSA_URL")  # optionnel (RFC 3161) -> PAdES-B-T


def ensure_self_signed_cert(org: str = "Kikan Organisation") -> None:
    os.makedirs(CERT_DIR, exist_ok=True)
    if os.path.exists(KEY_PATH) and os.path.exists(CERT_PATH):
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Kikan Seal"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
    ])
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def seal_pdf(pdf_bytes: bytes, *, reason: str, name: str | None = None) -> bytes:
    """Scelle le PDF (PAdES). Horodatage RFC 3161 si KIKAN_TSA_URL est defini."""
    # Imports locaux : pyHanko n'est necessaire qu'ici.
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko.sign.fields import SigSeedSubFilter

    ensure_self_signed_cert()
    signer = signers.SimpleSigner.load(KEY_PATH, CERT_PATH)

    timestamper = None
    if TSA_URL:
        from pyhanko.sign.timestamps import HTTPTimeStamper

        timestamper = HTTPTimeStamper(TSA_URL)

    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
    meta = signers.PdfSignatureMetadata(
        field_name="SignatureKikan",
        subfilter=SigSeedSubFilter.PADES,
        reason=reason,
        name=name,
    )
    out = signers.sign_pdf(writer, meta, signer=signer, timestamper=timestamper)
    return out.getvalue()
