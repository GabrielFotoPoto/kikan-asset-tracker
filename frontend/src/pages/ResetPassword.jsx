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

// Page ouverte depuis le lien recu par e-mail (/reinitialisation?token=...) : choix d'un nouveau mot de passe.
export default function ResetPassword() {
  const [token] = useState(() => new URLSearchParams(window.location.search).get("token") || "");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  // Le jeton ne reste pas dans la barre d'adresse ni dans l'historique du navigateur.
  useEffect(() => { window.history.replaceState(null, "", "/reinitialisation"); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    if (pw !== pw2) { setErr("Les deux mots de passe ne sont pas identiques."); return; }
    setBusy(true);
    try {
      await api.post("/auth/reset", { token, new_password: pw });
      setDone(true);
    } catch (ex) { setErr(errorText(ex)); } finally { setBusy(false); }
  };

  return (
    <div className="login-wrap">
      <div className="card login">
        <h1 style={{ color: "var(--brand)", margin: "0 0 4px" }}>Kikan</h1>
        <p className="muted" style={{ marginTop: 0 }}>Nouveau mot de passe</p>
        {done ? (
          <>
            <p className="ok-msg">Mot de passe modifie : vous pouvez vous connecter.</p>
            <a href="/">Aller a la connexion</a>
          </>
        ) : !token ? (
          <>
            <p className="err">Lien incomplet. Refaites une demande depuis l'ecran de connexion.</p>
            <a href="/">Retour a la connexion</a>
          </>
        ) : (
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {err && <p className="err">{err}</p>}
            <label>Nouveau mot de passe
              <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus required autoComplete="new-password" />
            </label>
            <label>Confirmation
              <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} required autoComplete="new-password" />
            </label>
            <button type="submit" disabled={busy}>{busy ? "Enregistrement..." : "Enregistrer"}</button>
          </form>
        )}
      </div>
    </div>
  );
}
