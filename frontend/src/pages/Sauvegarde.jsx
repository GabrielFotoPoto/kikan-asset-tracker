/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Claude, Anthropic).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

import { useEffect, useState } from "react";
import { api, errorText } from "../api.js";

const fmt = (d) => (d ? String(d).replace("T", " ").slice(0, 16) + " (UTC)" : "jamais");
const size = (n) => (n == null ? "-" : n > 1048576 ? `${(n / 1048576).toFixed(1)} Mio` : `${Math.max(1, Math.round(n / 1024))} Kio`);

// Etat de la sauvegarde (lecture seule) : l'outil de sauvegarde ecrit son etat, Kikan l'affiche et alerte si elle est ancienne.
export default function Sauvegarde() {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get("/backup/status").then(setS).catch((e) => setErr(errorText(e))); }, []);

  return (
    <div>
      <h2>Sauvegarde</h2>
      {err && <p className="err">{err}</p>}
      {s && (
        <div className="card">
          <h3>Derniere sauvegarde {s.alerte ? <span className="badge bad">a verifier</span> : <span className="badge ok">a jour</span>}</h3>
          {!s.configure ? (
            <p className="err">{s.message}</p>
          ) : (
            <table>
              <tbody>
                <tr><td>Derniere sauvegarde reussie</td><td>{fmt(s.dernier_succes)}{s.age_heures != null && ` - il y a ${s.age_heures} h`}</td></tr>
                <tr><td>Fichier</td><td>{s.fichier || "-"} ({size(s.taille)})</td></tr>
                <tr><td>Destination</td><td>{s.destination || "-"}</td></tr>
                <tr><td>Retention</td><td>{s.retention || "-"} ; {s.conserves ?? "-"} sauvegarde(s) conservee(s)</td></tr>
                <tr><td>Duree</td><td>{s.duree_s != null ? `${s.duree_s} s` : "-"}</td></tr>
                {s.dernier_echec && <tr><td>Dernier echec</td><td className="err">{fmt(s.dernier_echec)} : {s.message}</td></tr>}
              </tbody>
            </table>
          )}
          <p className="muted" style={{ marginTop: 12 }}>
            Alerte si la derniere sauvegarde date de plus de {s.seuil_heures} h ou si la derniere tentative a echoue. Kikan ne lance pas les
            sauvegardes : elles sont planifiees sur le serveur (docs/SAUVEGARDE.md). La cle privee de dechiffrement doit etre conservee
            <strong> hors du serveur</strong> : sans elle, aucune sauvegarde ne peut etre restauree.
          </p>
        </div>
      )}
    </div>
  );
}
