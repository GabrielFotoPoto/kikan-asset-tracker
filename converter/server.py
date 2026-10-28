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

"""Conversion Word -> PDF par LibreOffice, derriere une API minimale (POST /convert, GET /health).

Le document est une donnee non fiable : une conversion a la fois, un profil LibreOffice jetable par
demande, delai maximal avec arret du groupe de processus, dossier de travail detruit dans tous les cas.
Ce service n'a aucun acces reseau (reseau Docker interne) et ne conserve rien.
"""
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_IN = 12 * 1024 * 1024
MAX_OUT = 60 * 1024 * 1024
TIMEOUT = int(os.environ.get("CONVERT_TIMEOUT_SEC", "60"))
LOCK = threading.Lock()


def convert(raw: bytes) -> bytes:
    work = tempfile.mkdtemp(prefix="conv-", dir="/tmp")
    try:
        src = os.path.join(work, "in.docx")
        out = os.path.join(work, "out")
        os.mkdir(out)
        with open(src, "wb") as f:
            f.write(raw)
        cmd = [
            "soffice", "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nologo",
            f"-env:UserInstallation=file://{work}/profile",
            "--convert-to", "pdf:writer_pdf_Export", "--outdir", out, src,
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env={"HOME": work, "PATH": os.environ.get("PATH", "")}, start_new_session=True)
        try:
            proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise TimeoutError("delai depasse")
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)  # processus orphelins eventuels
            except (ProcessLookupError, PermissionError):
                pass
        pdf_path = os.path.join(out, "in.pdf")
        if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) > MAX_OUT:
            raise ValueError("conversion impossible")
        with open(pdf_path, "rb") as f:
            data = f.read()
        if data[:5] != b"%PDF-":
            raise ValueError("conversion impossible")
        return data
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    timeout = 30  # lecture de la requete : limite les connexions qui trainent
    server_version = "kikan-converter"
    sys_version = ""

    def log_message(self, *args):  # pas de journal du contenu
        pass

    def _reply(self, status: int, body: bytes = b"", ctype: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(200, b"ok") if self.path == "/health" else self._reply(404)

    def do_POST(self):
        if self.path != "/convert":
            return self._reply(404)
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_IN:
            return self._reply(413, b"taille invalide")
        raw = self.rfile.read(length)
        if not LOCK.acquire(timeout=TIMEOUT):
            return self._reply(503, b"occupe")
        try:
            pdf = convert(raw)
        except TimeoutError:
            return self._reply(504, b"delai depasse")
        except Exception:  # noqa: BLE001
            return self._reply(422, b"conversion impossible")
        finally:
            LOCK.release()
        self._reply(200, pdf, "application/pdf")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
