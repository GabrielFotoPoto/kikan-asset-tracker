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
import { useAuth } from "../auth.jsx";
import ConfirmButton from "../components/ConfirmButton.jsx";

const ROLES = [["informatique", "Informatique"], ["rh", "RH"], ["lecture", "Lecture seule"]];
const empty = { username: "", nom_affiche: "", email: "", role: "rh" };

const fmt = (d) => (d ? d.replace("T", " ").slice(0, 16) : "jamais");

// Gestion des comptes (informatique) : comptes nominatifs, mot de passe provisoire affiche une seule fois.
export default function Comptes() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [secret, setSecret] = useState(null);
  const [linking, setLinking] = useState(null);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = () => api.get("/auth/accounts").then(setItems).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, []);

  const clear = () => { setErr(null); setMsg(null); };
  const showSecret = (username, pwd) => { setSecret({ username, pwd }); setCopied(false); };

  const create = async (e) => {
    e.preventDefault();
    clear();
    try {
      const r = await api.post("/auth/accounts", {
        username: form.username, role: form.role,
        nom_affiche: form.nom_affiche || null, email: form.email || null,
      });
      setForm(empty);
      showSecret(r.username, r.mot_de_passe_provisoire);
      setMsg(`Compte ${r.username} cree.`);
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const update = async (a, patch, okMsg) => {
    clear();
    try {
      await api.put(`/auth/accounts/${a.id}`, patch);
      if (okMsg) setMsg(okMsg);
      setEditing(null);
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const reset = async (a) => {
    clear();
    try {
      const r = await api.post(`/auth/accounts/${a.id}/reset-password`, {});
      showSecret(a.username, r.mot_de_passe_provisoire);
      setMsg(`Mot de passe de ${a.username} reinitialise : ses sessions ouvertes sont fermees.`);
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const link = async (a, upn) => {
    clear();
    try {
      await api.post(`/auth/accounts/${a.id}/lier-sso`, { upn });
      setMsg(`Liaison preparee : la premiere connexion Microsoft 365 de ${upn} sera rattachee au compte ${a.username}.`);
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const unlink = async (a) => {
    clear();
    try { await api.post(`/auth/accounts/${a.id}/delier-sso`, {}); setMsg(`Compte ${a.username} delie de Microsoft 365.`); load(); } catch (ex) { setErr(errorText(ex)); }
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(secret.pwd); setCopied(true); } catch { setCopied(false); }
  };

  const generic = items.find((a) => a.username === "admin" && !a.nom_affiche && a.actif);

  return (
    <div>
      <h2>Comptes</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}

      {secret && (
        <div className="warn" style={{ marginBottom: 14 }}>
          <p style={{ margin: "0 0 6px" }}>
            Mot de passe provisoire de <b>{secret.username}</b> : il <b>n'est affiche qu'une seule fois</b>. Transmettez-le a la
            personne ; elle devra le remplacer a sa premiere connexion.
          </p>
          <div className="row">
            <code style={{ fontSize: 18, letterSpacing: 1 }}>{secret.pwd}</code>
            <button className="ghost" onClick={copy}>{copied ? "Copie" : "Copier"}</button>
            <button onClick={() => setSecret(null)}>J'ai note le mot de passe</button>
          </div>
        </div>
      )}

      {generic && (
        <p className="muted">
          Le compte generique « admin » existe encore. Creez des comptes nominatifs (un par personne), puis desactivez-le
          depuis un autre compte informatique.
        </p>
      )}

      <div className="card">
        <h3>Nouveau compte</h3>
        <form className="grid" onSubmit={create}>
          <label>Identifiant<input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                                  placeholder="prenom.nom" required /></label>
          <label>Nom de la personne<input value={form.nom_affiche} maxLength={120} onChange={(e) => setForm({ ...form, nom_affiche: e.target.value })} /></label>
          <label>E-mail<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <div style={{ alignSelf: "end" }}><button type="submit">Creer le compte</button></div>
        </form>
        <p className="muted">Identifiant : 3 a 64 caracteres, minuscules, chiffres et . _ - @ (non modifiable ensuite). Un mot de passe provisoire est genere.</p>
      </div>

      <div className="card">
        <table>
          <thead><tr><th>Identifiant</th><th>Nom</th><th>E-mail</th><th>Role</th><th>Origine</th><th>Secours</th><th>Etat</th><th>Derniere connexion</th><th></th></tr></thead>
          <tbody>
            {items.map((a) => {
              const me = a.username === user.username;
              const edit = editing && editing.id === a.id;
              return (
                <tr key={a.id}>
                  <td>{a.username}{me && <span className="badge" style={{ marginLeft: 6 }}>vous</span>}</td>
                  <td>{edit ? <input value={editing.nom_affiche} onChange={(e) => setEditing({ ...editing, nom_affiche: e.target.value })} /> : (a.nom_affiche || "-")}</td>
                  <td>{edit ? <input value={editing.email} onChange={(e) => setEditing({ ...editing, email: e.target.value })} /> : (a.email || "-")}</td>
                  <td>
                    {edit ? (
                      <select value={editing.role} disabled={a.sso_lie} title={a.sso_lie ? "Role gere par Microsoft 365" : ""} onChange={(e) => setEditing({ ...editing, role: e.target.value })}>
                        {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : (ROLES.find(([v]) => v === a.role)?.[1] || a.role)}
                  </td>
                  <td>
                    {a.source_auth === "sso" ? <span className="badge">Microsoft 365</span> : a.sso_lie ? <span className="badge">local + Microsoft 365</span> : <span className="badge">local</span>}
                    {a.sso_upn && <div className="muted">{a.sso_upn}{a.sso_lie ? "" : " (liaison en attente)"}</div>}
                  </td>
                  <td>
                    {a.source_auth === "sso" ? "-" : (
                      <input type="checkbox" checked={a.secours} title="Compte de secours : connexion par mot de passe autorisee quand le SSO est actif"
                             onChange={(e) => update(a, { secours: e.target.checked }, `Compte ${a.username} : secours ${e.target.checked ? "active" : "retire"}.`)} />
                    )}
                  </td>
                  <td>
                    <span className={a.actif ? "badge ok" : "badge bad"}>{a.actif ? "actif" : "desactive"}</span>
                    {a.must_change_password && <span className="badge" style={{ marginLeft: 6 }}>mot de passe a changer</span>}
                  </td>
                  <td>{fmt(a.derniere_connexion)}</td>
                  <td>
                    <div className="row">
                      {edit ? (
                        <>
                          <button onClick={() => update(a, { nom_affiche: editing.nom_affiche, email: editing.email, role: editing.role }, `Compte ${a.username} modifie.`)}>Enregistrer</button>
                          <button className="ghost" onClick={() => setEditing(null)}>Annuler</button>
                        </>
                      ) : (
                        <>
                          <button className="ghost" onClick={() => setEditing({ id: a.id, nom_affiche: a.nom_affiche || "", email: a.email || "", role: a.role })}>Modifier</button>
                          {a.source_auth !== "sso" && <ConfirmButton confirmLabel="Confirmer la reinitialisation" onConfirm={() => reset(a)}>Reinitialiser le mot de passe</ConfirmButton>}
                          {a.source_auth !== "sso" && !a.sso_lie && (linking && linking.id === a.id ? (
                            <span className="row">
                              <input value={linking.upn} placeholder="prenom.nom@domaine" onChange={(e) => setLinking({ ...linking, upn: e.target.value })} />
                              <button onClick={async () => { await link(a, linking.upn); setLinking(null); }}>Lier</button>
                              <button className="ghost" onClick={() => setLinking(null)}>Annuler</button>
                            </span>
                          ) : <button className="ghost" onClick={() => setLinking({ id: a.id, upn: a.sso_upn || "" })}>Lier a Microsoft 365</button>)}
                          {a.source_auth !== "sso" && (a.sso_lie || a.sso_upn) && (
                            <ConfirmButton confirmLabel="Confirmer" onConfirm={() => unlink(a)}>Delier de Microsoft 365</ConfirmButton>
                          )}
                          {a.actif
                            ? (!me && <ConfirmButton confirmLabel="Confirmer la desactivation" onConfirm={() => update(a, { actif: false }, `Compte ${a.username} desactive.`)}>Desactiver</ConfirmButton>)
                            : <button className="ghost" onClick={() => update(a, { actif: true }, `Compte ${a.username} reactive.`)}>Reactiver</button>}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="muted">
          Les comptes ne se suppriment pas (les journaux d'audit y font reference) : on les desactive. Changer le role, reinitialiser
          le mot de passe ou desactiver un compte ferme immediatement ses sessions ouvertes.
        </p>
      </div>
    </div>
  );
}
