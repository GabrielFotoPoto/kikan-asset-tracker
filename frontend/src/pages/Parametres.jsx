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
import { api, downloadFile, errorText, fetchDataUrl } from "../api.js";
import ConfirmButton from "../components/ConfirmButton.jsx";

const TABS = [
  ["types", "Types d'actifs"],
  ["services", "Services"],
  ["marques", "Marques et modeles"],
  ["pdf", "Modele de PDF"],
  ["etat", "Etat du scellement"],
];

// Liste de parametrage (types d'actifs, services) : ajout, renommage, activation, suppression protegee.
function ListEditor({ kind, label, help, setErr, setMsg }) {
  const [items, setItems] = useState([]);
  const [nom, setNom] = useState("");
  const [editing, setEditing] = useState(null);

  const load = () => api.get(`/parametres/${kind}`).then(setItems).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, [kind]);

  const add = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    try {
      await api.post(`/parametres/${kind}`, { nom, actif: true });
      setNom("");
      setMsg(`${label} ajoute.`);
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const save = async (item, patch) => {
    setErr(null); setMsg(null);
    try {
      const r = await api.put(`/parametres/${kind}/${item.id}`, { nom: item.nom, actif: item.actif, ...patch });
      if (r.mis_a_jour) setMsg(`Renomme : ${r.mis_a_jour} fiche(s) mise(s) a jour.`);
      setEditing(null);
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const remove = async (item) => {
    setErr(null); setMsg(null);
    try { await api.del(`/parametres/${kind}/${item.id}`); setMsg(`${item.nom} supprime.`); load(); } catch (ex) { setErr(errorText(ex)); }
  };

  return (
    <div className="card">
      <p className="muted" style={{ marginTop: 0 }}>{help}</p>
      <form className="row" onSubmit={add} style={{ marginBottom: 12 }}>
        <input value={nom} maxLength={100} placeholder={`Nouveau ${label.toLowerCase()}`} onChange={(e) => setNom(e.target.value)} required />
        <button type="submit">Ajouter</button>
      </form>
      <table>
        <thead><tr><th>Nom</th><th>Actif</th><th>Utilise par</th><th></th></tr></thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.id}>
              <td>
                {editing && editing.id === it.id
                  ? <input value={editing.nom} maxLength={100} onChange={(e) => setEditing({ ...editing, nom: e.target.value })} />
                  : it.nom}
              </td>
              <td><input type="checkbox" checked={it.actif} onChange={(e) => save(it, { actif: e.target.checked })} /></td>
              <td>{it.utilise}</td>
              <td>
                <div className="row">
                  {editing && editing.id === it.id ? (
                    <>
                      <button onClick={() => save(it, { nom: editing.nom })}>Enregistrer</button>
                      <button className="ghost" onClick={() => setEditing(null)}>Annuler</button>
                    </>
                  ) : (
                    <>
                      <button className="ghost" onClick={() => setEditing({ id: it.id, nom: it.nom })}>Renommer</button>
                      <ConfirmButton onConfirm={() => remove(it)}>Supprimer</ConfirmButton>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {items.length === 0 && <p className="muted">Liste vide : elle se remplit aussi toute seule a la saisie et a l'import.</p>}
    </div>
  );
}

// Cle de rapprochement : "Dell", "DELL" et "dell." sont probablement la meme marque.
const proche = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

function MergeTool({ setErr, setMsg }) {
  const [mode, setMode] = useState("marques");
  const [marques, setMarques] = useState([]);
  const [marque, setMarque] = useState("");
  const [rows, setRows] = useState([]);
  const [picked, setPicked] = useState([]);
  const [cible, setCible] = useState("");
  const [apercu, setApercu] = useState(null);

  const loadMarques = () => api.get("/parametres/marques").then(setMarques).catch((e) => setErr(errorText(e)));
  useEffect(() => { loadMarques(); }, []);

  const loadRows = async () => {
    setPicked([]); setCible(""); setApercu(null);
    if (mode === "marques") { setRows(marques); return; }
    if (!marque) { setRows([]); return; }
    try { setRows(await api.get(`/parametres/modeles?marque=${encodeURIComponent(marque)}`)); } catch (ex) { setErr(errorText(ex)); }
  };
  useEffect(() => { loadRows(); }, [mode, marque, marques]);

  const groups = {};
  for (const r of rows) (groups[proche(r.nom)] ||= []).push(r);
  const suspects = Object.values(groups).filter((g) => g.length > 1);

  const select = (g) => {
    setPicked(g.map((x) => x.nom));
    setCible([...g].sort((a, b) => b.count - a.count)[0].nom);
    setApercu(null);
  };
  const toggle = (n) => { setPicked((p) => (p.includes(n) ? p.filter((x) => x !== n) : [...p, n])); setApercu(null); };

  const body = (dry) => ({ sources: picked, cible, apercu: dry, ...(mode === "modeles" ? { marque } : {}) });
  const run = async (dry) => {
    setErr(null); setMsg(null);
    try {
      const r = await api.post(`/parametres/${mode}/fusion`, body(dry));
      if (dry) { setApercu(r); return; }
      setMsg(`Fusion terminee : ${r.materiels} materiel(s) rattache(s) a ${r.cible}.`);
      setPicked([]); setCible(""); setApercu(null);
      if (mode === "marques") loadMarques(); else loadRows();
    } catch (ex) { setErr(errorText(ex)); }
  };

  return (
    <div className="card">
      <p className="muted" style={{ marginTop: 0 }}>
        Regroupez les variantes d'une meme marque ou d'un meme modele (ex. Dell, DELL, Dell Technologies) sous un nom unique.
        Tout le materiel concerne est mis a jour, en une seule operation.
      </p>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className={mode === "marques" ? "" : "ghost"} onClick={() => { setMode("marques"); setMarque(""); }}>Marques</button>
        <button className={mode === "modeles" ? "" : "ghost"} onClick={() => setMode("modeles")}>Modeles</button>
        {mode === "modeles" && (
          <select value={marque} onChange={(e) => setMarque(e.target.value)}>
            <option value="">Choisir la marque...</option>
            {marques.map((m) => <option key={m.nom} value={m.nom}>{m.nom} ({m.count})</option>)}
          </select>
        )}
      </div>

      {suspects.length > 0 && (
        <div className="warn" style={{ marginBottom: 12 }}>
          <b>Variantes probables :</b>
          {suspects.map((g, i) => (
            <div key={i} className="row" style={{ marginTop: 6 }}>
              <span>{g.map((x) => `${x.nom} (${x.count})`).join("  /  ")}</span>
              <button className="ghost" onClick={() => select(g)}>Selectionner</button>
            </div>
          ))}
        </div>
      )}

      <table>
        <thead><tr><th></th><th>{mode === "marques" ? "Marque" : "Modele"}</th><th>Materiels</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.nom}>
              <td><input type="checkbox" checked={picked.includes(r.nom)} onChange={() => toggle(r.nom)} /></td>
              <td>{r.nom}</td><td>{r.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="muted">{mode === "modeles" && !marque ? "Choisissez une marque." : "Aucune valeur."}</p>}

      {picked.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <label style={{ maxWidth: 360 }}>Nom retenu
            <input value={cible} maxLength={100} onChange={(e) => { setCible(e.target.value); setApercu(null); }} />
          </label>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="ghost" disabled={!cible.trim()} onClick={() => run(true)}>Apercu</button>
            {apercu && <ConfirmButton confirmLabel={`Fusionner ${apercu.materiels} materiel(s)`} onConfirm={() => run(false)}>Fusionner</ConfirmButton>}
          </div>
          {apercu && (
            <p className="muted">{picked.length} valeur(s) deviendront <b>{apercu.cible}</b> ; {apercu.materiels} materiel(s) concerne(s).</p>
          )}
        </div>
      )}
    </div>
  );
}

function PdfTemplate({ setErr, setMsg }) {
  const [form, setForm] = useState({ organisation: "", mentions: "", pied: "", inclure_acces: false });
  const [logo, setLogo] = useState(null);
  const [apercu, setApercu] = useState(null);
  const [version, setVersion] = useState(0);

  const load = async () => {
    const t = await api.get("/parametres/pdf");
    setForm({ organisation: t.organisation, mentions: t.mentions, pied: t.pied, inclure_acces: !!t.inclure_acces });
    setLogo(t.logo ? await fetchDataUrl("/parametres/pdf/logo") : null);
  };
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, []);
  useEffect(() => { fetchDataUrl("/parametres/pdf/apercu?format=png").then(setApercu).catch(() => setApercu(null)); }, [version]);

  const save = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    try { await api.put("/parametres/pdf", form); setMsg("Modele enregistre. Il s'applique aux prochains documents."); setVersion((v) => v + 1); } catch (ex) { setErr(errorText(ex)); }
  };

  const upload = (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setErr(null); setMsg(null);
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        await api.post("/parametres/pdf/logo", { image: reader.result });
        setMsg("Logo enregistre.");
        await load();
        setVersion((v) => v + 1);
      } catch (ex) { setErr(errorText(ex)); }
    };
    reader.readAsDataURL(file);
  };

  const removeLogo = async () => {
    setErr(null); setMsg(null);
    try { await api.del("/parametres/pdf/logo"); setLogo(null); setMsg("Logo supprime."); setVersion((v) => v + 1); } catch (ex) { setErr(errorText(ex)); }
  };

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          S'applique a l'accuse de remise, a l'accuse de restitution et au rapport PDF. Chaque document signe conserve le
          modele en vigueur le jour de la signature (empreinte enregistree) : modifier ce modele ne change aucun document existant.
        </p>
        <form className="grid" onSubmit={save}>
          <label>Nom de l'organisation (en-tete)<input value={form.organisation} maxLength={120} onChange={set("organisation")} /></label>
          <label>Pied de page (une ligne)<input value={form.pied} maxLength={300} onChange={set("pied")} /></label>
          <label style={{ gridColumn: "1 / -1" }}>Mentions legales
            <textarea rows={4} value={form.mentions} maxLength={1500} onChange={set("mentions")} />
          </label>
          <label className="check" style={{ gridColumn: "1 / -1" }}>
            <input type="checkbox" checked={form.inclure_acces} onChange={(e) => setForm({ ...form, inclure_acces: e.target.checked })} />
            <span>Inclure les acces applicatifs du salarie dans l'accuse de remise (liste figee au moment de la signature)</span>
          </label>
          <div style={{ alignSelf: "end" }}><button type="submit">Enregistrer</button></div>
        </form>
      </div>

      <div className="card">
        <h3>Logo</h3>
        <p className="muted" style={{ marginTop: 0 }}>PNG ou JPEG, 300 Ko et 1000 x 400 pixels au maximum. L'image est controlee et re-encodee par le serveur.</p>
        {logo && <img src={logo} alt="Logo actuel" style={{ maxWidth: 260, maxHeight: 100, display: "block", marginBottom: 10, background: "#fff", border: "1px solid #d7dde6" }} />}
        <div className="row">
          <input type="file" accept="image/png,image/jpeg" onChange={upload} />
          {logo && <ConfirmButton onConfirm={removeLogo}>Supprimer le logo</ConfirmButton>}
        </div>
      </div>

      <div className="card">
        <h3>Apercu</h3>
        <p className="muted" style={{ marginTop: 0 }}>Exemplaire factice, non signe, avec le modele enregistre.</p>
        {apercu && <img src={apercu} alt="Apercu de l'accuse" className="policy-page" style={{ maxWidth: 520, margin: "0 0 10px" }} />}
        <button className="ghost" onClick={() => downloadFile("/parametres/pdf/apercu?format=pdf", "apercu.pdf")}>Telecharger l'apercu en PDF</button>
      </div>
    </div>
  );
}

function Etat({ setErr }) {
  const [etat, setEtat] = useState(null);
  useEffect(() => { api.get("/parametres/etat").then(setEtat).catch((e) => setErr(errorText(e))); }, []);
  if (!etat) return <div className="card"><p className="muted">Chargement...</p></div>;
  const c = etat.certificat;
  return (
    <div>
      <div className="card">
        <h3>Certificat de scellement</h3>
        <table>
          <tbody>
            <tr><td>Sujet</td><td>{c.sujet}</td></tr>
            <tr><td>Emetteur</td><td>{c.emetteur} {c.auto_signe && <span className="badge">auto-signe</span>}</td></tr>
            <tr><td>Validite</td><td>du {c.valide_du} au {c.valide_au} ({c.jours_restants} jours restants)</td></tr>
            <tr><td>Empreinte SHA-256</td><td><code style={{ wordBreak: "break-all" }}>{c.empreinte_sha256}</code></td></tr>
            <tr><td>Autorite de temps</td><td>{etat.autorite_de_temps || "non configuree"}</td></tr>
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>Reglages de deploiement</h3>
        <table>
          <tbody>
            <tr><td>Signature manuscrite obligatoire</td><td>{etat.signature_manuscrite_obligatoire ? "oui" : "non (simple confirmation acceptee)"}</td></tr>
            <tr><td>Stockage des documents</td><td>{etat.stockage} (voir la page Stockage)</td></tr>
            <tr><td>Import</td><td>{etat.limites.import_mo} Mo, {etat.limites.import_lignes} lignes</td></tr>
            <tr><td>Chartes</td><td>{etat.limites.charte_mo} Mo, {etat.limites.charte_pages} pages</td></tr>
          </tbody>
        </table>
        <p className="muted">
          Ces reglages ne se modifient pas depuis l'interface : ils touchent a la valeur probante des documents et se changent
          par le deploiement (fichier .env, voir SECURITY.md).
        </p>
      </div>
    </div>
  );
}

export default function Parametres() {
  const [tab, setTab] = useState("types");
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const go = (t) => { setTab(t); setErr(null); setMsg(null); };

  return (
    <div>
      <h2>Parametrage</h2>
      <div className="row" style={{ marginBottom: 14 }}>
        {TABS.map(([k, label]) => <button key={k} className={tab === k ? "" : "ghost"} onClick={() => go(k)}>{label}</button>)}
      </div>
      {err && <p className="err">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}
      {tab === "types" && (
        <ListEditor kind="types" label="Type" setErr={setErr} setMsg={setMsg}
          help="Types proposes dans le formulaire materiel. La liste s'enrichit aussi a la saisie et a l'import ; renommer un type met a jour tout le materiel concerne." />
      )}
      {tab === "services" && (
        <ListEditor kind="services" label="Service" setErr={setErr} setMsg={setMsg}
          help="Services proposes dans la fiche salarie (liste commune a toutes les entites). Renommer un service met a jour toutes les fiches concernees." />
      )}
      {tab === "marques" && <MergeTool setErr={setErr} setMsg={setMsg} />}
      {tab === "pdf" && <PdfTemplate setErr={setErr} setMsg={setMsg} />}
      {tab === "etat" && <Etat setErr={setErr} />}
    </div>
  );
}
