import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, getToken, setToken } from "./api.js";
import { AuthContext } from "./auth.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Entites from "./pages/Entites.jsx";
import Users from "./pages/Users.jsx";
import Assets from "./pages/Assets.jsx";
import Assignments from "./pages/Assignments.jsx";
import Departures from "./pages/Departures.jsx";
import Reports from "./pages/Reports.jsx";
import Rgpd from "./pages/Rgpd.jsx";
import Acces from "./pages/Acces.jsx";
import Stats from "./pages/Stats.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const onUnauth = () => setUser(null);
    window.addEventListener("kikan-unauth", onUnauth);
    if (getToken()) {
      api.get("/auth/me")
        .then((a) => setUser({ username: a.username, role: a.role }))
        .catch(() => setToken(null))
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
    return () => window.removeEventListener("kikan-unauth", onUnauth);
  }, []);

  const logout = () => { setToken(null); setUser(null); };

  if (checking) return null;
  if (!user) return <Login onLogin={setUser} />;

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
            <NavLink to="/remises">Remises</NavLink>
            <NavLink to="/sorties">Sorties</NavLink>
            <NavLink to="/rapports">Rapports</NavLink>
            <NavLink to="/statistiques">Statistiques</NavLink>
            <NavLink to="/rgpd">RGPD</NavLink>
          </nav>
          <div className="account">
            <div className="who">{user.username}</div>
            <div className="role">{user.role}</div>
            <button className="ghost" onClick={logout}>Se deconnecter</button>
          </div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/entites" element={<Entites />} />
            <Route path="/utilisateurs" element={<Users />} />
            <Route path="/materiel" element={<Assets />} />
            <Route path="/acces" element={<Acces />} />
            <Route path="/remises" element={<Assignments />} />
            <Route path="/sorties" element={<Departures />} />
            <Route path="/rapports" element={<Reports />} />
            <Route path="/statistiques" element={<Stats />} />
            <Route path="/rgpd" element={<Rgpd />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </AuthContext.Provider>
  );
}
