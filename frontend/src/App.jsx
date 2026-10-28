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
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, getToken, setToken } from "./api.js";
import { AuthContext } from "./auth.jsx";
import Login from "./pages/Login.jsx";
import ForcePassword from "./pages/ForcePassword.jsx";
import SsoReturn from "./pages/SsoReturn.jsx";
import Comptes from "./pages/Comptes.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Entites from "./pages/Entites.jsx";
import Users from "./pages/Users.jsx";
import Assets from "./pages/Assets.jsx";
import Assignments from "./pages/Assignments.jsx";
import Besoins from "./pages/Besoins.jsx";
import Policies from "./pages/Policies.jsx";
import Import from "./pages/Import.jsx";
import Parametres from "./pages/Parametres.jsx";
import Departures from "./pages/Departures.jsx";
import Reports from "./pages/Reports.jsx";
import Rgpd from "./pages/Rgpd.jsx";
import Acces from "./pages/Acces.jsx";
import Stats from "./pages/Stats.jsx";
import Audit from "./pages/Audit.jsx";
import Compte from "./pages/Compte.jsx";
import Stockage from "./pages/Stockage.jsx";
import Sauvegarde from "./pages/Sauvegarde.jsx";
import Sign from "./pages/Sign.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [portee, setPortee] = useState(null);

  useEffect(() => {
    const onUnauth = () => setUser(null);
    window.addEventListener("kikan-unauth", onUnauth);
    if (getToken()) {
      api.get("/auth/me")
        .then((a) => setUser({ username: a.username, role: a.role, mustChange: a.must_change_password }))
        .catch(() => setToken(null))
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
    return () => window.removeEventListener("kikan-unauth", onUnauth);
  }, []);

  // Portee effective du compte (relue apres connexion) : bandeau si aucun perimetre n'est defini.
  useEffect(() => {
    if (!user) { setPortee(null); return; }
    api.get("/auth/me").then((a) => setPortee(a.portee)).catch(() => {});
  }, [user?.username]);

  const logout = () => { setToken(null); setUser(null); };

  if (checking) return null;
  if (!user) return window.location.pathname === "/sso" ? <SsoReturn onLogin={setUser} /> : <Login onLogin={setUser} />;
  if (user.mustChange) {
    return <ForcePassword user={user} onDone={() => setUser({ ...user, mustChange: false })} onLogout={logout} />;
  }

  return (
    <AuthContext.Provider value={{ user }}>
      <div className="layout">
        <aside className="sidebar">
          <h1>Kikan</h1>
          <div className="sub">Suivi des actifs</div>
          <nav>
            <NavLink to="/" end>Tableau de bord</NavLink>
            <NavLink to="/entites">Entites</NavLink>
            <NavLink to="/utilisateurs">Utilisateurs</NavLink>
            <NavLink to="/materiel">Materiel</NavLink>
            <NavLink to="/acces">Acces applicatifs</NavLink>
            <NavLink to="/besoins">Besoins</NavLink>
            <NavLink to="/remises">Remises</NavLink>
            <NavLink to="/chartes">Chartes</NavLink>
            <NavLink to="/sorties">Sorties</NavLink>
            <NavLink to="/rapports">Rapports</NavLink>
            <NavLink to="/statistiques">Statistiques</NavLink>
            {user.role === "informatique" && <NavLink to="/rgpd">RGPD</NavLink>}
            {user.role === "informatique" && <NavLink to="/import">Import</NavLink>}
            {user.role === "informatique" && <NavLink to="/parametres">Parametrage</NavLink>}
            {user.role === "informatique" && <NavLink to="/comptes">Comptes</NavLink>}
            {user.role === "informatique" && <NavLink to="/stockage">Stockage</NavLink>}
            {user.role === "informatique" && <NavLink to="/sauvegarde">Sauvegarde</NavLink>}
            {user.role === "informatique" && <NavLink to="/journal">Journal d'audit</NavLink>}
            <NavLink to="/compte">Mon compte</NavLink>
          </nav>
          <div className="account">
            <div className="who">{user.username}</div>
            <div className="role">{user.role}</div>
            {user.role !== "informatique" && portee && !portee.vide && (
              <div className="role" title="Perimetre de votre compte">{portee.globale ? "toute l'organisation" : "perimetre limite"}</div>
            )}
            <button className="ghost" onClick={logout}>Se deconnecter</button>
          </div>
        </aside>
        <main className="main">
          {portee?.vide && (
            <div className="card" role="alert">
              <strong>Aucun perimetre n'est defini pour votre compte.</strong>{" "}
              Vous ne voyez aucune donnee : demandez a un administrateur informatique de definir vos entites.
            </div>
          )}
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/entites" element={<Entites />} />
            <Route path="/utilisateurs" element={<Users />} />
            <Route path="/materiel" element={<Assets />} />
            <Route path="/acces" element={<Acces />} />
            <Route path="/besoins" element={<Besoins />} />
            <Route path="/remises" element={<Assignments />} />
            <Route path="/chartes" element={<Policies />} />
            <Route path="/sorties" element={<Departures />} />
            <Route path="/signer/:mode/:id" element={<Sign />} />
            <Route path="/rapports" element={<Reports />} />
            <Route path="/statistiques" element={<Stats />} />
            <Route path="/rgpd" element={user.role === "informatique" ? <Rgpd /> : <Navigate to="/" />} />
            <Route path="/import" element={user.role === "informatique" ? <Import /> : <Navigate to="/" />} />
            <Route path="/parametres" element={user.role === "informatique" ? <Parametres /> : <Navigate to="/" />} />
            <Route path="/comptes" element={user.role === "informatique" ? <Comptes /> : <Navigate to="/" />} />
            <Route path="/stockage" element={<Stockage />} />
            <Route path="/sauvegarde" element={user.role === "informatique" ? <Sauvegarde /> : <Navigate to="/" />} />
            <Route path="/journal" element={<Audit />} />
            <Route path="/compte" element={<Compte />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </AuthContext.Provider>
  );
}
