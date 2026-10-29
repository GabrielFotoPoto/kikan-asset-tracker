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
import { api, errorText, setSession } from "../api.js";

// Retour de Microsoft 365 : le ticket a usage unique (dans l'adresse) est echange contre la session.
export default function SsoReturn({ onLogin }) {
  const [err, setErr] = useState(null);
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;  // le ticket ne sert qu'une fois : pas de double appel en mode developpement
    done.current = true;
    const ticket = new URLSearchParams(window.location.search).get("ticket");
    window.history.replaceState(null, "", "/sso");  // le ticket ne reste pas dans l'historique
    if (!ticket) { setErr("Connexion Microsoft 365 incomplete."); return; }
    api.post("/auth/sso/exchange", { ticket })
      .then((res) => {
        setSession(true);
        window.history.replaceState(null, "", "/");
        onLogin({ username: res.username, role: res.role, mustChange: false });
      })
      .catch((ex) => setErr(errorText(ex)));
  }, []);

  return (
    <div className="login-wrap">
      <div className="card login">
        <h1 style={{ color: "var(--brand)", margin: "0 0 4px" }}>Kikan</h1>
        {err ? (
          <>
            <p className="err">{err}</p>
            <a href="/">Retour a la connexion</a>
          </>
        ) : <p className="muted">Connexion en cours...</p>}
      </div>
    </div>
  );
}
