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
import ConfirmButton from "../components/ConfirmButton.jsx";
import { Feedback } from "../components/Notifications.jsx";

const LABELS = {
  local: "Volume local",
  smb: "Lecteur reseau (SMB)",
  webdav: "Partage web (WebDAV)",
  sharepoint: "SharePoint Online",
  docuware: "DocuWare",
};
const DESC = { site: "Site", bibliotheque: "Bibliotheque", dossier: "Dossier", armoire: "Armoire", champs_associes: "Champs d'index associes" };

export default function Stockage() {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [test, setTest] = useState(null);
  const [sync, setSync] = useState(null);
  const [copy, setCopy] = useState(null);
  const [pjTest, setPjTest] = useState(null);
  const [pjSync, setPjSync] = useState(null);
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
  const doPjTest = () => run(async () => { setPjTest(await api.post("/storage/pieces-jointes/test", {})); });
  const doPjSync = () => run(async () => { setPjSync(await api.post("/storage/pieces-jointes/sync", {})); await load(); });

  const doCopy = (dry) => run(async () => { setCopy(await api.post(`/storage/migrer?dry_run=${dry}`, {})); if (!dry) await load(); });

  const pending = status?.documents?.en_attente_de_depot ?? 0;
  const pj = status?.pieces_jointes;
  const pjPending = pj?.en_attente_de_depot ?? 0;
  const fmtMio = (b) => `${((b || 0) / (1024 * 1024)).toFixed(1)} Mio`;

  return (
    <div>
      <h2>Stockage des documents</h2>
      <Feedback err={err} />

      {status && (
        <div className="card">
          <h3>Stockage actif : {LABELS[status.active] || status.active}</h3>
          <p className="muted">
            Les PDF scelles sont ranges par annee (AAAA/). La configuration se fait dans le fichier .env
            du serveur (KIKAN_STORAGE_BACKEND et variables associees), jamais dans l'interface.
          </p>
          {status.documents_seulement && (
            <p className="muted">
              Ce service ne recoit que les <strong>PDF scelles</strong> (remises et restitutions) ; les chartes restent dans le volume local de Kikan.
            </p>
          )}
          {status.description && Object.keys(status.description).length > 0 && (
            <p className="muted">
              {Object.entries(status.description).map(([k, v]) => (
                <span key={k} style={{ marginRight: 16 }}>{DESC[k] || k} : <strong>{Array.isArray(v) ? v.join(", ") : String(v)}</strong></span>
              ))}
            </p>
          )}
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
        {status && status.active !== "local" && (
          <div style={{ marginTop: 16 }}>
            <strong>Copier vers le stockage actif</strong>
            <p className="muted">
              Copie les documents rangés sur un autre emplacement distant (SMB, WebDAV...) vers le stockage actif. Chaque copie est relue et
              comparee a l'empreinte enregistree ; rien n'est supprime de l'ancien emplacement. Les anciens emplacements doivent rester configures.
            </p>
            <div className="row">
              <button className="ghost" onClick={() => doCopy(true)} disabled={busy}>Voir ce qui serait copie</button>
              <ConfirmButton confirmLabel="Confirmer la copie" onConfirm={() => doCopy(false)}>Copier maintenant</ConfirmButton>
            </div>
            {copy && (
              <p className={copy.echecs ? "err" : "muted"} style={{ marginTop: 8 }}>
                {copy.simulation ? `Simulation : ${copy.a_copier} document(s) a copier.` : `Copie : ${copy.copies} document(s) copie(s), ${copy.echecs} echec(s) sur ${copy.a_copier}.`}
                {copy.erreurs?.map((e, i) => <span key={i} className="err"> [{e.signature_id ? `signature ${e.signature_id} : ` : ""}{e.detail}]</span>)}
              </p>
            )}
          </div>
        )}
        {sync && (
          <p className="muted" style={{ marginTop: 12 }}>
            Reprise : {sync.synced} depose(s), {sync.failed} echec(s) sur {sync.pending} en attente.
            {sync.errors?.map((e, i) => <span key={i} className="err"> [{e.signature_id || e.attachment_id}: {e.detail}]</span>)}
          </p>
        )}
      </div>

      {pj && (
        <div className="card">
          <h3>Stockage des pieces jointes : {LABELS[pj.active] || pj.active}</h3>
          <p className="muted">
            Configure independamment par <code>KIKAN_ATTACHMENTS_BACKEND</code> et <code>KIKAN_ATTACHMENTS_*</code> dans le fichier .env
            (local, SMB, WebDAV, SharePoint ou DocuWare). Volume utilise : <strong>{fmtMio(pj.volume_octets)}</strong> / <strong>{fmtMio(pj.plafond_octets)}</strong> ({pj.total} fichier(s)).
          </p>
          {pj.description && Object.keys(pj.description).length > 0 && (
            <p className="muted">
              {Object.entries(pj.description).map(([k, v]) => (
                <span key={k} style={{ marginRight: 16 }}>{DESC[k] || k} : <strong>{Array.isArray(v) ? v.join(", ") : String(v)}</strong></span>
              ))}
            </p>
          )}
          {pjPending > 0 && (
            <p className="err">{pjPending} piece(s) jointe(s) en attente de depot sur le partage (conservees dans le tampon local).</p>
          )}
          <div className="row">
            <button onClick={doPjTest} disabled={busy}>Tester la connexion PJ</button>
            <button className="ghost" onClick={doPjSync} disabled={busy || pjPending === 0}>Reprendre les depots PJ</button>
          </div>
          {pjTest && (
            <p className={pjTest.ok ? "muted" : "err"} style={{ marginTop: 10 }}>
              {pjTest.ok ? "OK" : "Echec"} - {LABELS[pjTest.backend] || pjTest.backend} : {pjTest.detail} ({pjTest.latency_ms} ms)
            </p>
          )}
          {pjSync && (
            <p className="muted" style={{ marginTop: 10 }}>
              Reprise PJ : {pjSync.synced} depose(s), {pjSync.failed} echec(s) sur {pjSync.pending} en attente.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
