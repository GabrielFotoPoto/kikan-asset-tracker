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
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const LABELS = {
  local: "Volume local",
  smb: "Lecteur reseau (SMB)",
  webdav: "Partage web (WebDAV)",
};

export default function Stockage() {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [test, setTest] = useState(null);
  const [sync, setSync] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = () => api.get("/storage/status").then(setStatus).catch((e) => setErr(e.message));
  useEffect(() => { if (user.role === "informatique") load(); }, []);

  if (user.role !== "informatique") {
    return <div><h2>Stockage des documents</h2><p className="muted">Reserve au role informatique.</p></div>;
  }

  const run = async (fn) => {
    setErr(null); setBusy(true);
    try { await fn(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  const doTest = () => run(async () => { setTest(await api.post("/storage/test", {})); });
  const doSync = () => run(async () => { setSync(await api.post("/storage/sync", {})); await load(); });

  const pending = status?.documents?.en_attente_de_depot ?? 0;

  return (
    <div>
      <h2>Stockage des documents</h2>
      {err && <p className="err">{err}</p>}

      {status && (
        <div className="card">
          <h3>Stockage actif : {LABELS[status.active] || status.active}</h3>
          <p className="muted">
            Les PDF scelles sont ranges par annee (AAAA/). La configuration se fait dans le fichier .env
            du serveur (KIKAN_STORAGE_BACKEND et variables associees), jamais dans l'interface.
          </p>
          <table>
            <thead><tr><th>Emplacement</th><th>Documents</th></tr></thead>
            <tbody>
              {Object.keys(LABELS).map((b) => (
                <tr key={b}>
                  <td>{LABELS[b]}</td>
                  <td>{status.documents.par_backend[b] || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pending > 0 && (
            <p className="err" style={{ marginTop: 12 }}>
              {pending} document(s) en attente de depot sur le partage (conserves en local).
            </p>
          )}
        </div>
      )}

      <div className="card">
        <h3>Actions</h3>
        <div className="row">
          <button onClick={doTest} disabled={busy}>Tester la connexion</button>
          <button className="ghost" onClick={doSync} disabled={busy || pending === 0}>
            Reprendre les depots en attente
          </button>
        </div>
        {test && (
          <p className={test.ok ? "muted" : "err"} style={{ marginTop: 12 }}>
            {test.ok ? "OK" : "Echec"} - {LABELS[test.backend] || test.backend} : {test.detail} ({test.latency_ms} ms)
          </p>
        )}
        {sync && (
          <p className="muted" style={{ marginTop: 12 }}>
            Reprise : {sync.synced} depose(s), {sync.failed} echec(s) sur {sync.pending} en attente.
            {sync.errors?.map((e) => <span key={e.signature_id} className="err"> [{e.signature_id}: {e.detail}]</span>)}
          </p>
        )}
      </div>
    </div>
  );
}
