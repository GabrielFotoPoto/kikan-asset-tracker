import { useEffect, useState } from "react";
import { api } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";

export default function Rgpd() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "entites"); // informatique
  const [mois, setMois] = useState(36);
  const [preview, setPreview] = useState(null);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  useEffect(() => { api.get("/rgpd/retention").then((r) => setMois(r.mois)).catch((e) => setErr(e.message)); }, []);

  const saveMois = async () => {
    setErr(null); setMsg(null);
    try { const r = await api.put("/rgpd/retention", { mois: Number(mois) }); setMois(r.mois); setMsg("Duree enregistree."); }
    catch (e) { setErr(e.message); }
  };

  const doPreview = async () => {
    setErr(null); setMsg(null);
    try { setPreview(await api.get("/rgpd/purge-preview")); }
    catch (e) { setErr(e.message); }
  };

  const doPurge = async () => {
    if (!preview || preview.count === 0) return;
    if (!window.confirm(`Supprimer definitivement ${preview.count} salarie(s) sorti(s) et leurs donnees ? Action irreversible.`)) return;
    setErr(null);
    try {
      const r = await api.post("/rgpd/purge", {});
      setMsg(`${r.count} salarie(s) supprime(s).`);
      setPreview(null);
    } catch (e) { setErr(e.message); }
  };

  if (!writable) return <div><h2>Retention RGPD</h2><p className="muted">Reserve au role informatique.</p></div>;

  return (
    <div>
      <h2>Retention RGPD</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="muted">{msg}</p>}

      <div className="card">
        <h3>Duree de conservation apres sortie</h3>
        <div className="row">
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="number" min="0" value={mois} onChange={(e) => setMois(e.target.value)} style={{ width: 90 }} /> mois
          </label>
          <button onClick={saveMois}>Enregistrer</button>
          <span className="muted">Un salarie sorti est conserve jusqu'a sa date de sortie + cette duree.</span>
        </div>
      </div>

      <div className="card">
        <h3>Suppressions a venir</h3>
        <div className="row" style={{ marginBottom: 12 }}>
          <button className="ghost" onClick={doPreview}>Previsualiser</button>
          {preview && preview.count > 0 &&
            <button onClick={doPurge}>Supprimer definitivement ({preview.count})</button>}
        </div>
        {preview && (
          preview.count === 0 ? <p className="muted">Aucun salarie a supprimer pour l'instant.</p> : (
            <table>
              <thead><tr><th>Matricule</th><th>Salarie</th><th>Date de sortie</th><th>Suppression prevue</th></tr></thead>
              <tbody>
                {preview.candidats.map((c) => (
                  <tr key={c.id}>
                    <td>{c.matricule || "-"}</td>
                    <td>{c.prenom} {c.nom}</td>
                    <td>{c.date_sortie}</td>
                    <td>{c.suppression_prevue}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  );
}
