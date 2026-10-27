import { useEffect, useState } from "react";
import { api, downloadFile } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";

export default function Assignments() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "remises");
  const [users, setUsers] = useState([]);
  const [stock, setStock] = useState([]);
  const [items, setItems] = useState([]);
  const [signed, setSigned] = useState({});
  const [userId, setUserId] = useState("");
  const [picked, setPicked] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = async () => {
    const [u, s, a] = await Promise.all([
      api.get("/users"), api.get("/assets?statut=stock"), api.get("/assignments"),
    ]);
    setUsers(u); setStock(s); setItems(a);
  };
  useEffect(() => { load().catch((e) => setErr(e.message)); }, []);

  const userName = (id) => {
    const u = users.find((x) => x.id === id);
    return u ? `${u.prenom} ${u.nom}` : `#${id}`;
  };

  const toggle = (id) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const create = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    if (!userId || picked.length === 0) { setErr("Choisir un salarie et au moins un actif."); return; }
    try {
      await api.post("/assignments", { user_id: Number(userId), asset_ids: picked, cree_par: "informatique" });
      setUserId(""); setPicked([]);
      setMsg("Affectation creee.");
      await load();
    } catch (ex) { setErr(ex.message); }
  };

  const sign = async (id) => {
    const signataire = window.prompt("Nom du signataire (salarie) :");
    if (!signataire) return;
    setErr(null);
    try {
      await api.post(`/assignments/${id}/sign`, { signataire, methode: "manuscrite_ecran" });
      setSigned((s) => ({ ...s, [id]: true }));
      setMsg("Document signe et scelle.");
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <div>
      <h2>Remises de materiel</h2>
      {err && <p className="err">{err}</p>}
      {msg && <p className="muted">{msg}</p>}

      {writable && (
      <div className="card">
        <h3>Nouvelle remise</h3>
        <form onSubmit={create}>
          <label style={{ maxWidth: 360 }}>Salarie
            <select value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">-</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.prenom} {u.nom}</option>)}
            </select>
          </label>
          <p className="muted" style={{ marginBottom: 6 }}>Materiel en stock a remettre :</p>
          {stock.length === 0 && <p className="muted">Aucun actif en stock.</p>}
          {stock.map((a) => (
            <label key={a.id} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={picked.includes(a.id)} onChange={() => toggle(a.id)} />
              {a.type} {a.marque} {a.modele} ({a.numero_serie || a.identifiant_interne || a.id})
            </label>
          ))}
          <div style={{ marginTop: 12 }}><button type="submit">Creer l'affectation</button></div>
        </form>
      </div>
      )}

      <div className="card">
        <h3>Affectations</h3>
        <table>
          <thead><tr><th>#</th><th>Salarie</th><th>Statut</th><th>Remise</th><th>Document</th></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>{a.id}</td>
                <td>{userName(a.user_id)}</td>
                <td><span className="badge">{a.statut}</span></td>
                <td>{(a.date_remise || "").slice(0, 10)}</td>
                <td>
                  <div className="row">
                    {writable && <button className="ghost" onClick={() => sign(a.id)}>Signer</button>}
                    <button className="ghost" onClick={() => downloadFile(`/assignments/${a.id}/document`, `remise_${a.id}.pdf`)}>PDF scelle</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
