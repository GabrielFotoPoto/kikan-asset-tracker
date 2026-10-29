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

// Ecran affiche seul tant que le mot de passe est provisoire : rien d'autre n'est accessible avant.
export default function ForcePassword({ user, onDone, onLogout }) {
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    if (newPw !== confirm) { setErr("Les deux nouveaux mots de passe sont differents."); return; }
    setBusy(true);
    try {
      const res = await api.post("/auth/change-password", { old_password: oldPw, new_password: newPw });
      setSession(true);
      onDone();
    } catch (ex) {
      setErr(errorText(ex));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <h1 style={{ color: "var(--brand)", margin: "0 0 4px" }}>Kikan</h1>
        <p style={{ marginTop: 0 }}>
          Bonjour <b>{user.username}</b>. Votre mot de passe est provisoire : choisissez-en un nouveau pour continuer.
        </p>
        {err && <p className="err">{err}</p>}
        <label>Mot de passe provisoire
          <input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} autoFocus required />
        </label>
        <label>Nouveau mot de passe (12 caracteres minimum)
          <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} minLength={12} required />
        </label>
        <label>Confirmation
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} minLength={12} required />
        </label>
        <div className="row" style={{ marginTop: 10 }}>
          <button type="submit" disabled={busy}>{busy ? "Enregistrement..." : "Enregistrer et continuer"}</button>
          <button type="button" className="ghost" onClick={onLogout}>Se deconnecter</button>
        </div>
      </form>
    </div>
  );
}
