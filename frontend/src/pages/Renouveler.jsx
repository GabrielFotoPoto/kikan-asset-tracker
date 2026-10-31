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
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, downloadFile } from "../api.js";
import PolicyViewer from "../components/PolicyViewer.jsx";
import SignaturePad from "../components/SignaturePad.jsx";
import { Feedback } from "../components/Notifications.jsx";

const DEVENIRS = { rendu: "Rendu (a traiter ensuite)", stock: "Retour en stock", reforme: "A reformer" };

const message = (ex) => {
  try { return JSON.parse(ex.message).detail || ex.message; } catch { return ex.message; }
};

function Materiel({ a }) {
  return <>{a.type || "-"} {a.marque || ""} {a.modele || ""} <span className="muted">({a.numero_serie || a.identifiant_interne || a.id})</span></>;
}

function Tableau({ lignes }) {
  return (
    <table>
      <thead><tr><th>Type</th><th>Marque</th><th>Modele</th><th>N de serie</th><th>Id interne</th></tr></thead>
      <tbody>
        {lignes.map((a) => (
          <tr key={a.id}><td>{a.type || "-"}</td><td>{a.marque || "-"}</td><td>{a.modele || "-"}</td><td>{a.numero_serie || "-"}</td><td>{a.identifiant_interne || "-"}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

// Renouvellement du materiel d'un salarie en poste : le nouveau materiel est remis et l'ancien restitue en une seule operation,
// avec un seul document signe sur la tablette. Reserve a l'informatique ; la date d'echeance n'est qu'un repere.
export default function Renouveler() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const pad = useRef(null);
  const [users, setUsers] = useState([]);
  const [stock, setStock] = useState([]);
  const [userId, setUserId] = useState(params.get("user") || "");
  const [recap, setRecap] = useState(null);
  const [anciens, setAnciens] = useState({});     // { idActif: devenir }
  const [nouveaux, setNouveaux] = useState([]);   // ids a remettre
  const [recherche, setRecherche] = useState("");
  const [charte, setCharte] = useState(false);
  const [besoinIds, setBesoinIds] = useState([]);
  const [note, setNote] = useState("");
  const [etape, setEtape] = useState("preparer");
  const [consent, setConsent] = useState(false);
  const [vide, setVide] = useState(true);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.get("/users").then((u) => setUsers(u.filter((x) => x.statut === "actif"))).catch((e) => setErr(message(e)));
    api.get("/assets?statut=stock").then(setStock).catch((e) => setErr(message(e)));
    const asset = params.get("asset");
    if (asset && !params.get("user")) {
      api.get(`/assignments/detenteur/${asset}`).then((d) => { setUserId(String(d.user_id)); setAnciens({ [Number(asset)]: "rendu" }); })
        .catch((e) => setErr(message(e)));
    } else if (asset) {
      setAnciens({ [Number(asset)]: "rendu" });
    }
  }, []);

  const chargerRecap = () => {
    if (!userId) { setRecap(null); return Promise.resolve(); }
    return api.get(`/assignments/echange/recap?user_id=${userId}`).then((r) => {
      setRecap(r);
      setBesoinIds(r.besoins.map((b) => b.id));
      setAnciens((cur) => Object.fromEntries(Object.entries(cur).filter(([id]) => r.detenus.some((d) => d.id === Number(id)))));
    }).catch((e) => { setRecap(null); setErr(message(e)); });
  };
  useEffect(() => { setErr(null); setEtape("preparer"); chargerRecap(); }, [userId]);

  const basculerAncien = (id) => setAnciens((cur) => {
    if (id in cur) { const { [id]: _retire, ...reste } = cur; return reste; }
    return { ...cur, [id]: "rendu" };
  });
  const basculerNouveau = (id) => setNouveaux((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const filtre = recherche.trim().toLowerCase();
  const stockFiltre = stock.filter((a) => !filtre || [a.type, a.marque, a.modele, a.numero_serie, a.identifiant_interne].some((v) => (v || "").toLowerCase().includes(filtre)));
  const prets = Object.keys(anciens).length > 0 && nouveaux.length > 0;

  const valider = async () => {
    setErr(null);
    setBusy(true);
    try {
      if (recap.signature_obligatoire && vide) throw new Error("Veuillez signer dans le cadre.");
      const res = await api.post("/assignments/echange", {
        user_id: Number(userId),
        nouveaux_ids: nouveaux,
        anciens: Object.entries(anciens).map(([id, destination]) => ({ asset_id: Number(id), destination })),
        joindre_charte: charte && !!recap.charte,
        policy_id: charte && recap.charte ? recap.charte.id : null,
        besoin_ids: besoinIds,
        note: note.trim() || null,
        consent,
        signature_image: !vide ? pad.current.toDataURL() : null,
        strokes: pad.current.stats().strokes,
        duration_ms: pad.current.stats().durationMs,
        ...(recap.acces_remise ? { acces_empreinte: recap.acces_remise.empreinte } : {}),
      });
      setDone({ assignmentId: res.assignment_id, methode: res.methode });
    } catch (ex) {
      const m = message(ex);
      setErr(m);
      if (/ont change/.test(m)) chargerRecap();   // acces modifies pendant l'affichage : on recharge
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div>
        <h2>Renouvellement du materiel</h2>
        <div className="card">
          <h3>Echange signe et scelle</h3>
          <p className="muted">
            Signature enregistree pour {recap.salarie.prenom} {recap.salarie.nom}
            {done.methode === "confirmation" ? " (simple confirmation, sans signature manuscrite)." : "."} Le nouveau materiel est affecte, l'ancien est rendu comme indique.
          </p>
          <div className="row">
            <button onClick={() => downloadFile(`/assignments/${done.assignmentId}/document?type=echange`, `echange_${done.assignmentId}.pdf`)}>Telecharger le PDF scelle</button>
            <button className="ghost" onClick={() => navigate("/materiel")}>Retour au materiel</button>
          </div>
        </div>
      </div>
    );
  }

  const choisis = recap ? recap.detenus.filter((d) => d.id in anciens) : [];
  const remis = stock.filter((a) => nouveaux.includes(a.id));
  const s = recap?.salarie;

  return (
    <div>
      <h2>Renouveler le materiel d'un salarie</h2>
      <p className="muted">
        Le nouveau materiel est remis et l'ancien restitue en une seule operation, avec un seul document signe. L'echeance de renouvellement n'est
        qu'un repere : vous renouvelez quand vous le decidez, avant comme apres.
      </p>
      <Feedback err={err} />

      <div className="card">
        <label>Salarie en poste
          <select value={userId} onChange={(e) => { setUserId(e.target.value); setAnciens({}); setNouveaux([]); }}>
            <option value="">-</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.prenom} {u.nom}{u.matricule ? ` (${u.matricule})` : ""}</option>)}
          </select>
        </label>
      </div>

      {recap && etape === "preparer" && (
        <>
          <div className="row" style={{ alignItems: "flex-start" }}>
            <div className="card" style={{ flex: 1, minWidth: 320 }}>
              <h3>Materiel a recuperer</h3>
              {recap.detenus.length === 0 && <p className="muted">Ce salarie ne detient aucun materiel.</p>}
              {recap.detenus.map((a) => (
                <div key={a.id} style={{ marginBottom: 8 }}>
                  <label className="check">
                    <input type="checkbox" checked={a.id in anciens} onChange={() => basculerAncien(a.id)} />
                    <span><Materiel a={a} />{a.echeance_renouvellement && <span className="muted"> - echeance {a.echeance_renouvellement}</span>}</span>
                  </label>
                  {a.id in anciens && (
                    <select aria-label={`Devenir : ${a.type || ""} ${a.numero_serie || a.id}`} style={{ marginLeft: 26 }} value={anciens[a.id]}
                            onChange={(e) => setAnciens({ ...anciens, [a.id]: e.target.value })}>
                      {Object.entries(DEVENIRS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  )}
                </div>
              ))}
            </div>

            <div className="card" style={{ flex: 1, minWidth: 320 }}>
              <h3>Nouveau materiel a remettre</h3>
              <input style={{ width: "100%" }} value={recherche} placeholder="Rechercher (type, marque, modele, serie...)" onChange={(e) => setRecherche(e.target.value)} />
              <div style={{ maxHeight: 280, overflowY: "auto", marginTop: 8 }}>
                {stockFiltre.length === 0 && <p className="muted">Aucun materiel en stock{filtre ? " pour cette recherche" : ""}.</p>}
                {stockFiltre.map((a) => (
                  <label key={a.id} className="check" style={{ marginBottom: 4 }}>
                    <input type="checkbox" checked={nouveaux.includes(a.id)} onChange={() => basculerNouveau(a.id)} /><span><Materiel a={a} /></span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            {recap.besoins.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <strong>Besoins ouverts de ce salarie</strong>
                <p className="muted" style={{ margin: "4px 0" }}>Les cases cochees seront soldees par cet echange.</p>
                {recap.besoins.map((b) => (
                  <label key={b.id} className="row" style={{ gap: 8 }}>
                    <input type="checkbox" checked={besoinIds.includes(b.id)}
                           onChange={() => setBesoinIds((p) => (p.includes(b.id) ? p.filter((x) => x !== b.id) : [...p, b.id]))} />
                    {b.quantite} x {b.type}{b.gamme ? ` - gamme ${b.gamme}` : ""}{b.commentaire ? ` (${b.commentaire})` : ""}
                  </label>
                ))}
              </div>
            )}
            {recap.charte ? (
              <label className="check" style={{ marginBottom: 12 }}>
                <input type="checkbox" checked={charte} onChange={(e) => setCharte(e.target.checked)} />
                Joindre la charte informatique ({recap.charte.titre}, version {recap.charte.version}) : utile si elle a change depuis la remise precedente
              </label>
            ) : <p className="muted">Aucune charte ne s'applique a ce salarie.</p>}
            <label>Motif du renouvellement (facultatif)
              <input value={note} maxLength={500} placeholder="ex. fin de garantie, besoin modifie, materiel defaillant" onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className="row" style={{ marginTop: 12 }}>
              <button disabled={!prets} onClick={() => { setErr(null); setConsent(false); setEtape("signer"); }}>Continuer vers la signature</button>
              {!prets && <span className="muted">Choisissez au moins un materiel a recuperer et un materiel a remettre.</span>}
            </div>
          </div>
        </>
      )}

      {recap && etape === "signer" && (
        <>
          <div className="card">
            <h3>{s.prenom} {s.nom}</h3>
            <p className="muted">{[s.matricule && `Matricule ${s.matricule}`, s.entite, s.service].filter(Boolean).join(" - ")}</p>
            <h4>Materiel remis</h4>
            <Tableau lignes={remis} />
            <h4>Materiel restitue</h4>
            <Tableau lignes={choisis} />
          </div>
          {recap.acces_remise && (
            <div className="card">
              <h3>Acces applicatifs accordes</h3>
              {recap.acces_remise.liste.length === 0 ? <p className="muted">Aucun acces applicatif enregistre a ce jour.</p> : (
                <table>
                  <thead><tr><th>Application</th><th>Niveau / precision</th></tr></thead>
                  <tbody>{recap.acces_remise.liste.map((a, i) => <tr key={i}><td>{a.application}</td><td>{a.niveau || "-"}</td></tr>)}</tbody>
                </table>
              )}
              <p className="muted">Cette liste sera reproduite dans le document signe.</p>
            </div>
          )}
          {charte && recap.charte && (
            <div className="card">
              <h3>{recap.charte.titre || "Charte informatique"} (version {recap.charte.version}{recap.charte.nb_pages ? `, ${recap.charte.nb_pages} page(s)` : ""})</h3>
              <p className="muted">Faites defiler pour lire la charte avant de signer. Elle sera jointe au document signe.</p>
              {recap.charte.nb_pages && <PolicyViewer policyId={recap.charte.id} nbPages={recap.charte.nb_pages} />}
            </div>
          )}
          <div className="card">
            <label className="check">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>
                Je reconnais avoir recu le materiel remis et avoir restitue l'ancien materiel, tels qu'indiques ci-dessus
                {recap.acces_remise ? " et avoir pris connaissance des acces applicatifs qui m'ont ete accordes" : ""}
                {charte && recap.charte ? (recap.acces_remise ? "," : "") + " et j'accepte la charte informatique" : ""}.
              </span>
            </label>
            <p className="muted" style={{ margin: "14px 0 6px" }}>{recap.signature_obligatoire ? "Signature de l'employe :" : "Signature de l'employe (facultative) :"}</p>
            <SignaturePad ref={pad} onChange={setVide} />
            <div className="row" style={{ marginTop: 14 }}>
              <button className="ghost" onClick={() => pad.current.clear()} disabled={busy || vide}>Effacer</button>
              <button className="ghost" onClick={() => setEtape("preparer")} disabled={busy}>Retour</button>
              <button onClick={valider} disabled={busy || !consent || (recap.signature_obligatoire && vide)}>{busy ? "Enregistrement..." : "Valider l'echange"}</button>
            </div>
            <p className="muted">Rien ne change tant que l'echange n'est pas valide : les statuts du materiel ne sont modifies qu'a la signature.</p>
          </div>
        </>
      )}
    </div>
  );
}
