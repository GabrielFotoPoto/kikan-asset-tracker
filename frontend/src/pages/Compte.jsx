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

import { useState } from "react";
import { api, errorText, setSession } from "../api.js";
import { useAuth } from "../auth.jsx";

export default function Compte() {
  const { user } = useAuth();
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    if (newPw !== confirm) { setErr("Les deux nouveaux mots de passe sont differents."); return; }
    try {
      const res = await api.post("/auth/change-password", { old_password: oldPw, new_password: newPw });
      setSession(true);  // les autres sessions de ce compte sont fermees : on garde celle-ci
      setMsg("Mot de passe modifie. Vos autres sessions ouvertes ont ete fermees.");
      setOldPw(""); setNewPw(""); setConfirm("");
    } catch (ex) {
      setErr(errorText(ex));
    }
  };

  return (
    <div>
      <h2>Mon compte</h2>
      <div className="card">
        <p>Connecte en tant que <b>{user.username}</b> (role : {user.role}).</p>
        <h3>Changer le mot de passe</h3>
        {err && <p className="err">{err}</p>}
        {msg && <p className="muted">{msg}</p>}
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 360 }}>
          <label>Mot de passe actuel<input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} required /></label>
          <label>Nouveau mot de passe (12 caracteres minimum)<input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} minLength={12} required /></label>
          <label>Confirmation<input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} minLength={12} required /></label>
          <div><button type="submit">Enregistrer</button></div>
        </form>
      </div>
    </div>
  );
}
