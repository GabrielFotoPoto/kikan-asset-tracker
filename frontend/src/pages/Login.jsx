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
import { api, errorText, setToken } from "../api.js";

// Motifs de refus renvoyes par la connexion Microsoft 365 (?sso_erreur=...).
const SSO_ERRORS = {
  role: "Votre compte Microsoft 365 n'a pas de role Kikan : demandez a l'administrateur de vous ajouter au groupe Kikan-IT ou Kikan-RH.",
  mfa: "L'authentification multifacteur Microsoft est requise pour acceder a Kikan.",
  compte: "Votre compte est desactive dans Kikan, inconnu, ou deja utilise par un autre compte : contactez l'administrateur.",
  jeton: "La reponse de Microsoft n'a pas pu etre verifiee. Reessayez ; si le probleme persiste, contactez l'administrateur.",
  session: "La connexion a expire ou a ete interrompue. Reessayez.",
  idp: "Microsoft a refuse ou annule la connexion.",
  echange: "L'echange avec Microsoft a echoue. Reessayez ou contactez l'administrateur.",
  reseau: "Microsoft est injoignable depuis le serveur Kikan. Contactez l'administrateur.",
  config: "La connexion Microsoft 365 n'est pas correctement configuree. Contactez l'administrateur.",
  trop_de_tentatives: "Trop de tentatives, reessayez dans quelques minutes.",
};

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState({ actif: false, mode_local: "autorise" });
  const [showLocal, setShowLocal] = useState(true);

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("sso_erreur");
    if (code) setErr(SSO_ERRORS[code] || "La connexion Microsoft 365 a echoue.");
    api.get("/auth/sso/config")
      .then((c) => { setSso(c); setShowLocal(!c.actif || c.mode_local === "autorise"); })
      .catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const res = await api.post("/auth/login", { username, password });
      setToken(res.access_token);
      onLogin({ username: res.username, role: res.role, mustChange: res.must_change_password });
    } catch (ex) {
      setErr(errorText(ex));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="card login">
        <h1 style={{ color: "var(--brand)", margin: "0 0 4px" }}>Kikan</h1>
        <p className="muted" style={{ marginTop: 0 }}>Suivi des actifs - connexion</p>
        {err && <p className="err">{err}</p>}

        {sso.actif && (
          <button type="button" onClick={() => { window.location.href = "/api/auth/sso/login"; }} style={{ width: "100%", marginBottom: 10 }}>
            Se connecter avec Microsoft 365
          </button>
        )}

        {showLocal ? (
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {sso.actif && <p className="muted" style={{ margin: "4px 0" }}>Compte de secours (mot de passe)</p>}
            <label>Identifiant
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus={!sso.actif} required />
            </label>
            <label>Mot de passe
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <button type="submit" disabled={busy} className={sso.actif ? "ghost" : ""} style={{ marginTop: 6 }}>
              {busy ? "Connexion..." : "Se connecter"}
            </button>
          </form>
        ) : (
          <p className="muted" style={{ textAlign: "center" }}>
            <a href="#" onClick={(e) => { e.preventDefault(); setShowLocal(true); }}>Connexion de secours (mot de passe)</a>
          </p>
        )}
      </div>
    </div>
  );
}
