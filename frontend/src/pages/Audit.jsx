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

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorText } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Feedback } from "../components/Notifications.jsx";
import Pagination from "../components/Pagination.jsx";
import { Empty, Loading } from "../components/State.jsx";
import ThTri from "../components/ThTri.jsx";
import { pagination } from "../tableau.js";
import { useTableau } from "../useTableau.js";

// Colonnes triables. Le journal est append-only et peut compter des milliers d'entrees : tri et pagination se font sur le
// serveur (GET /audit?limit&offset&tri&sens, nombre total dans X-Total-Count), la page ne charge que les lignes affichees.
// "Detail" n'est pas triable. Sans tri choisi : les plus recentes d'abord.
const COLONNES = [["ts", "Date (UTC)"], ["actor", "Compte"], ["action", "Action"], ["status", "Statut"], ["ip", "IP"]];

export default function Audit() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const { tri, sens, taille, page, changerTri, changerTaille, changerPage } = useTableau(params, setParams, COLONNES);
  // Filtres appliques (dans l'adresse) ; la saisie en cours reste locale jusqu'au bouton Filtrer ou a Entree.
  const compte = params.get("compte") || "";
  const action = params.get("action") || "";
  const [saisieCompte, setSaisieCompte] = useState(compte);
  const [saisieAction, setSaisieAction] = useState(action);
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState(null);
  const demande = useRef(0);

  useEffect(() => {
    if (user.role !== "informatique") return;
    // Une reponse tardive d'une ancienne demande ne doit pas ecraser la plus recente.
    const numero = ++demande.current;
    const p = new URLSearchParams({ limit: String(taille), offset: String((page - 1) * taille) });
    if (compte) p.set("actor", compte);
    if (action) p.set("action", action);
    if (tri) { p.set("tri", tri); p.set("sens", sens); }
    api.getPage("/audit?" + p.toString())
      .then(({ data, total: n }) => { if (numero === demande.current) { setRows(data); setTotal(n); setErr(null); } })
      .catch((e) => { if (numero === demande.current) setErr(errorText(e)); });
  }, [user.role, compte, action, tri, sens, taille, page]);

  // Page au-dela de la fin (adresse ancienne ou filtre plus etroit) : retour a la derniere page existante.
  const pag = pagination(total, page, taille);
  useEffect(() => {
    if (rows && total > 0 && page > pag.pages) changerPage(pag.pages);
  }, [rows, total, page, taille]);

  const filtrer = (e) => {
    e.preventDefault();
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      const c = saisieCompte.trim();
      const a = saisieAction.trim();
      if (c) p.set("compte", c); else p.delete("compte");
      if (a) p.set("action", a); else p.delete("action");
      p.delete("page");
      return p;
    }, { replace: true });
  };

  if (user.role !== "informatique") {
    return <div><h2>Journal d'audit</h2><p className="muted">Reserve au role informatique.</p></div>;
  }

  return (
    <div>
      <h2>Journal d'audit</h2>
      <Feedback err={err} />
      <div className="card">
        <form className="row" onSubmit={filtrer}>
          <label>Compte<input value={saisieCompte} onChange={(e) => setSaisieCompte(e.target.value)} /></label>
          <label>Action (debut)<input value={saisieAction} onChange={(e) => setSaisieAction(e.target.value)} placeholder="ex: POST, login" /></label>
          <div style={{ alignSelf: "end" }}><button type="submit">Filtrer</button></div>
        </form>
      </div>
      <div className="card">
        {rows === null ? <Loading label="Chargement du journal" />
          : rows.length === 0 ? <Empty title="Aucune entree ne correspond" hint="Verifiez le compte ou le debut de l'action." />
          : (
          <>
          <div className="table-scroll">
          <table>
            <thead><tr>
              {COLONNES.map(([c, libelle]) => <ThTri key={c} cle={c} tri={tri} sens={sens} onTri={changerTri}>{libelle}</ThTri>)}
              <th>Detail</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{(r.ts || "").replace("T", " ").slice(0, 19)}</td>
                  <td>{r.actor}</td>
                  <td>{r.action}{r.target ? ` (${r.target})` : ""}</td>
                  <td>{r.status ?? "-"}</td>
                  <td>{r.ip || "-"}</td>
                  <td>{r.detail || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <Pagination pag={pag} taille={taille} objet="entree(s)" onTaille={changerTaille} onPage={changerPage} />
          </>
          )}
      </div>
    </div>
  );
}
