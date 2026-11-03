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


"""Garde des adresses de serveurs sortants (GLPI, SMTP) configurees par un administrateur.

Refuse les destinations sans usage legitime et dangereuses si le reglage est detourne : adresses link-local (dont les
metadonnees des fournisseurs cloud, 169.254.169.254), multicast, non specifiee, et quelques adresses de metadonnees
connues hors link-local. Les reseaux prives et le bouclage restent permis : un GLPI ou un serveur de messagerie
interne est le cas normal.

Un NOM de serveur est resolu et chacune de ses adresses est controlee, sinon un nom DNS pointant vers une adresse
refusee contournerait le filtre. Limite connue : le DNS est resolu a nouveau a la connexion (un attaquant qui maitrise
le DNS pourrait changer de reponse entre les deux) ; le filtre reste a jour a chaque envoi ou chaque synchronisation.
"""
import ipaddress
import socket

# Metadonnees hors link-local : Alibaba Cloud, Azure (service d'hote), AWS en IPv6.
_EXPLICITES = {ipaddress.ip_address(a) for a in ("100.100.100.200", "168.63.129.16", "fd00:ec2::254")}


def adresse_interdite(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip in _EXPLICITES


def probleme_hote(hote: str) -> str | None:
    """Motif de refus d'un nom de serveur ou d'une adresse IP (None si acceptable ou non resolvable ici)."""
    hote = (hote or "").strip().strip("[]")
    if not hote:
        return None
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        ip = None
    if ip is not None:
        return "Adresse de serveur non autorisee" if adresse_interdite(ip) else None
    try:
        infos = socket.getaddrinfo(hote, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return None  # injoignable : l'erreur de connexion le dira ; ce n'est pas une question de politique
    for info in infos:
        try:
            if adresse_interdite(ipaddress.ip_address(info[4][0].split("%")[0])):
                return "Adresse de serveur non autorisee (le nom pointe vers une adresse reservee)"
        except ValueError:
            continue
    return None
