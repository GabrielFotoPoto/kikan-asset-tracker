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

"""Commande de secours : nouveau mot de passe provisoire pour un compte local, hors de l'application.

    docker compose exec api python -m app.reset_admin <identifiant> [--activer]

A utiliser quand plus aucun administrateur ne peut se connecter. Il faut un acces au serveur (donc a la base). Le mot de
passe provisoire s'affiche UNE fois, le changement est impose a la prochaine connexion et les sessions ouvertes sont revoquees.
"""
import argparse
import sys

from sqlalchemy import func
from sqlmodel import Session, select

from .audit import audit
from .auth import generate_temp_password, hash_password
from .db import engine
from .models import Account


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.reset_admin", description=__doc__.split("\n")[0])
    parser.add_argument("identifiant", help="identifiant du compte (insensible a la casse)")
    parser.add_argument("--activer", action="store_true", help="reactive aussi le compte s'il est desactive")
    args = parser.parse_args(argv)
    with Session(engine) as session:
        account = session.exec(select(Account).where(func.lower(Account.username) == args.identifiant.strip().lower())).first()
        if not account:
            print("Compte introuvable : %s" % args.identifiant, file=sys.stderr)
            return 1
        if account.source_auth == "sso":
            print("Ce compte est gere par Microsoft 365 : pas de mot de passe local a reinitialiser.", file=sys.stderr)
            return 1
        if not account.actif and not args.activer:
            print("Ce compte est desactive : relancez avec --activer pour le reactiver.", file=sys.stderr)
            return 1
        provisional = generate_temp_password()
        account.hashed_password = hash_password(provisional)
        account.must_change_password = True
        account.token_epoch += 1
        if args.activer:
            account.actif = True
        session.add(account)
        session.commit()
        audit("systeme", "mot_de_passe_reinitialise_console", target=account.username)
        print("Compte : %s\nMot de passe provisoire : %s\n(a changer a la premiere connexion)" % (account.username, provisional))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
