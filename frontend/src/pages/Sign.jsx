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
import { useNavigate, useParams } from "react-router-dom";
import { api, downloadFile } from "../api.js";
import PolicyViewer from "../components/PolicyViewer.jsx";
import SignaturePad from "../components/SignaturePad.jsx";

// Ecran de signature sur tablette : /signer/remise/:id (id d'affectation) ou /signer/restitution/:id (id salarie).
export default function Sign() {
  const { mode, id } = useParams();
  const navigate = useNavigate();
  const pad = useRef(null);
  const [recap, setRecap] = useState(null);
  const [consent, setConsent] = useState(false);
  const [empty, setEmpty] = useState(true);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);

  const isRestitution = mode === "restitution";

  useEffect(() => {
    const path = isRestitution ? `/lifecycle/recap/${id}` : `/assignments/${id}/recap`;
    api.get(path).then(setRecap).catch((e) => setErr(e.message));
  }, [mode, id]);

  const message = (ex) => {
    try { return JSON.parse(ex.message).detail || ex.message; } catch { return ex.message; }
  };

  const submit = async () => {
    setErr(null);
    setBusy(true);
    try {
      const needDraw = recap.signature_obligatoire;
      const payload = {
        consent,
        signature_image: !empty ? pad.current.toDataURL() : null,
        strokes: pad.current.stats().strokes,
        duration_ms: pad.current.stats().durationMs,
      };
      if (needDraw && empty) throw new Error("Veuillez signer dans le cadre.");
      const res = isRestitution
        ? await api.post("/lifecycle/restituer", { user_id: Number(id), ...payload })
        : await api.post(`/assignments/${id}/sign`, payload);
      setDone({ assignmentId: res.assignment_id, methode: res.methode });
    } catch (ex) {
      setErr(message(ex));
    } finally {
      setBusy(false);
    }
  };

  if (err && !recap) return <div><h2>Signature</h2><p className="err">{err}</p></div>;
  if (!recap) return <div><h2>Signature</h2><p className="muted">Chargement...</p></div>;

  const s = recap.salarie;
  const titre = isRestitution ? "Restitution de materiel" : "Remise de materiel";

  if (done) {
    return (
      <div>
        <h2>{titre}</h2>
        <div className="card">
          <h3>Document signe et scelle</h3>
          <p className="muted">
            Signature enregistree pour {s.prenom} {s.nom}
            {done.methode === "confirmation" ? " (simple confirmation, sans signature manuscrite)." : "."}
          </p>
          <div className="row">
            {!isRestitution && (
              <button onClick={() => downloadFile(`/assignments/${id}/document`, `remise_${id}.pdf`)}>
                Telecharger le PDF scelle
              </button>
            )}
            <button className="ghost" onClick={() => navigate(isRestitution ? "/sorties" : "/remises")}>Retour</button>
          </div>
        </div>
      </div>
    );
  }

  if (!isRestitution && recap.deja_signe) {
    return (
      <div>
        <h2>{titre}</h2>
        <div className="card">
          <p>Cette remise est deja signee.</p>
          <div className="row">
            <button onClick={() => downloadFile(`/assignments/${id}/document`, `remise_${id}.pdf`)}>Telecharger le PDF scelle</button>
            <button className="ghost" onClick={() => navigate("/remises")}>Retour</button>
          </div>
        </div>
      </div>
    );
  }

  if (isRestitution && recap.materiel.length === 0) {
    return (
      <div>
        <h2>{titre}</h2>
        <div className="card">
          <p>Aucun materiel a restituer pour {s.prenom} {s.nom}.</p>
          <button className="ghost" onClick={() => navigate("/sorties")}>Retour</button>
        </div>
      </div>
    );
  }

  const declaration = isRestitution
    ? "Je reconnais avoir restitue le materiel ci-dessus."
    : "Je reconnais avoir recu le materiel ci-dessus" + (recap.charte ? " et j'accepte la charte informatique ci-dessus." : ".");

  return (
    <div>
      <h2>{titre}</h2>
      {err && <p className="err">{err}</p>}

      <div className="card">
        <h3>{s.prenom} {s.nom}</h3>
        <p className="muted">
          {[s.matricule && `Matricule ${s.matricule}`, s.entite, s.service].filter(Boolean).join(" - ")}
        </p>
        <table>
          <thead><tr><th>Type</th><th>Marque</th><th>Modele</th><th>N de serie</th><th>Id interne</th></tr></thead>
          <tbody>
            {recap.materiel.map((a, i) => (
              <tr key={i}>
                <td>{a.type || "-"}</td><td>{a.marque || "-"}</td><td>{a.modele || "-"}</td>
                <td>{a.numero_serie || "-"}</td><td>{a.identifiant_interne || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!isRestitution && recap.charte && (
        <div className="card">
          <h3>{recap.charte.titre || "Charte informatique"} (version {recap.charte.version}
            {recap.charte.nb_pages ? `, ${recap.charte.nb_pages} page(s)` : ""})</h3>
          <p className="muted">Faites defiler pour lire la charte avant de signer. Elle sera jointe au document signe.</p>
          {recap.charte.nb_pages
            ? <PolicyViewer policyId={recap.charte.id} nbPages={recap.charte.nb_pages} />
            : <div className="charte">{recap.charte.texte}</div>}
        </div>
      )}

      <div className="card">
        <label className="check">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>{declaration}</span>
        </label>
        <p className="muted" style={{ margin: "14px 0 6px" }}>
          {recap.signature_obligatoire ? "Signature de l'employe :" : "Signature de l'employe (facultative) :"}
        </p>
        <SignaturePad ref={pad} onChange={setEmpty} />
        <div className="row" style={{ marginTop: 14 }}>
          <button className="ghost" onClick={() => pad.current.clear()} disabled={busy || empty}>Effacer</button>
          <button
            onClick={submit}
            disabled={busy || !consent || (recap.signature_obligatoire && empty)}
          >
            {busy ? "Signature en cours..." : "Valider et signer"}
          </button>
          <button className="ghost" onClick={() => navigate(isRestitution ? "/sorties" : "/remises")} disabled={busy}>Annuler</button>
        </div>
      </div>
    </div>
  );
}
