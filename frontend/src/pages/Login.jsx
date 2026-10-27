import { useState } from "react";
import { api, setToken } from "../api.js";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const res = await api.post("/auth/login", { username, password });
      setToken(res.access_token);
      onLogin({ username: res.username, role: res.role });
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <h1 style={{ color: "var(--brand)", margin: "0 0 4px" }}>Kikan</h1>
        <p className="muted" style={{ marginTop: 0 }}>Suivi des actifs - connexion</p>
        {err && <p className="err">{err}</p>}
        <label>Identifiant
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        </label>
        <label>Mot de passe
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <button type="submit" disabled={busy} style={{ marginTop: 10 }}>
          {busy ? "Connexion..." : "Se connecter"}
        </button>
      </form>
    </div>
  );
}
