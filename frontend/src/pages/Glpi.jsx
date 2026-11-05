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
import { api, errorText } from "../api.js";
import ConfirmButton from "../components/ConfirmButton.jsx";
import { ETATS_IMPORT_U, FILTRES_U_VIDES, cocherSalaries, entitesSalaries, filtrerSalaries, sansAccent, toutDecocherSalaries } from "../glpiSelection.js";

const ETATS_IMPORT = {
  nouveau: ["Nouveau", "badge ok"], correspondance: ["Existe dans Kikan (sera lie)", "badge"], homonyme: ["Homonyme dans Kikan", "badge bad"],
  deja_lie: ["Deja lie", "badge"], sans_serie: ["Sans numero de serie", "badge bad"], incomplet: ["Nom ou prenom manquant", "badge bad"],
};
const ETATS_EXPORT = {
  a_creer: ["A creer dans GLPI", "badge ok"], existe_dans_glpi: ["Existe dans GLPI (sera lie)", "badge"], deja_lie: ["Deja dans GLPI", "badge"],
  type_non_suivi: ["Type non suivi", "badge"], sans_serie: ["Sans numero de serie", "badge bad"], conflit: ["Deja lie a une autre fiche", "badge bad"],
  lien_perdu: ["Lien perdu (introuvable dans GLPI)", "badge bad"],
};
const RESULTATS = { cree: "cree", lie: "lie a l'existant", inchange: "deja a jour", conflit: "conflit (non modifie)", refuse: "refuse", erreur: "erreur", ignore: "ignore" };
const line = { display: "flex", flexDirection: "row", alignItems: "center", gap: 8, margin: "3px 0" };
const FILTRES_VIDES = { q: "", fab: "", sauf: false, etat: "", type: "" };

function Badge({ table, k }) {
  const [label, cls] = table[k] || [k, "badge"];
  return <span className={cls}>{label}</span>;
}

function Outcome({ outcome }) {
  if (!outcome) return null;
  const notable = outcome.resultats.filter((r) => ["conflit", "refuse", "erreur", "lie", "ignore"].includes(r.resultat) && r.message);
  return (
    <div className="card">
      <h3>Resultat</h3>
      <p>{Object.entries(outcome.resume).map(([k, v]) => `${k.replace("_", " : ")} = ${v}`).join(" ; ") || "Rien a faire."}</p>
      {notable.length > 0 && (
        <ul>{notable.map((r, i) => <li key={i}>{r.objet} {r.id_externe || r.id || ""} - {RESULTATS[r.resultat] || r.resultat} : {r.message}</li>)}</ul>
      )}
    </div>
  );
}

// Connecteur GLPI : reglages, import propose puis applique, export des utilisateurs et du materiel (numeros de serie compris).
export default function Glpi({ setErr, setMsg }) {
  const [data, setData] = useState(null);
  const [f, setF] = useState(null);
  const [types, setTypes] = useState([]);
  const [entites, setEntites] = useState([]);
  const [glpiEntites, setGlpiEntites] = useState([]);
  const [conn, setConn] = useState(null);
  const [imp, setImp] = useState(null);
  const [pickA, setPickA] = useState({});
  const [fa, setFa] = useState(FILTRES_VIDES);
  const [pickU, setPickU] = useState({});
  const [fu, setFu] = useState(FILTRES_U_VIDES);
  const [homonyme, setHomonyme] = useState({});
  const [impEntite, setImpEntite] = useState("");
  const [exp, setExp] = useState(null);
  const [pickX, setPickX] = useState({});
  const [outcome, setOutcome] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const [d, t, e, h] = await Promise.all([api.get("/glpi/config"), api.get("/assets/catalogue/types"), api.get("/entites"), api.get("/glpi/historique")]);
    setData(d); setF(d.config); setTypes(t); setEntites(e); setHistory(h);
  };
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, []);

  const run = async (fn, ok) => {
    setErr(null); setMsg(null); setBusy(true);
    try { const r = await fn(); if (ok) setMsg(typeof ok === "function" ? ok(r) : ok); return r; } catch (ex) { setErr(errorText(ex)); } finally { setBusy(false); }
  };

  if (!data || !f) return <div className="card"><p className="muted">Chargement...</p></div>;

  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const toggleType = (key, t) => {
    const other = key === "types_computer" ? "types_phone" : "types_computer";
    setF({ ...f, [key]: f[key].includes(t) ? f[key].filter((x) => x !== t) : [...f[key], t], [other]: f[other].filter((x) => x !== t) });
  };
  const save = () => run(async () => { const d = await api.put("/glpi/config", { ...f, entite_kikan: f.entite_kikan || null, entite_glpi: Number(f.entite_glpi) || 0 }); setData(d); setF(d.config); }, "Reglages GLPI enregistres.");
  const test = async () => {
    const r = await run(() => api.post("/glpi/tester", {}), (x) => `Connexion reussie : ${x.ordinateurs} ordinateur(s), ${x.telephones} telephone(s), ${x.utilisateurs} utilisateur(s).${x.profil_trouve ? "" : " Attention : le profil indique n'existe pas dans GLPI."}`);
    if (r) { setConn(r); setGlpiEntites(r.entites); }
  };
  const mapChamp = (champ, source) => setF({ ...f, champs: { ...f.champs, [champ]: source } });
  const mapEntite = (gid, kid) => {
    const entites_map = { ...f.entites };
    if (kid) entites_map[String(gid)] = Number(kid); else delete entites_map[String(gid)];
    setF({ ...f, entites: entites_map });
  };

  const preview = async () => {
    setOutcome(null);
    const r = await run(() => api.post("/glpi/import/apercu", {}));
    if (!r) return;
    setImp(r);
    setFa(FILTRES_VIDES);
    setFu(FILTRES_U_VIDES);
    setHomonyme({});
    setPickA(Object.fromEntries(r.actifs.filter((a) => a.importable && a.etat_import !== "sans_serie").map((a) => [a.externe_id, true])));
    setPickU(Object.fromEntries(r.salaries.filter((u) => u.importable && u.etat_import !== "homonyme").map((u) => [u.externe_id, true])));
  };
  const applyImport = async () => {
    const actifs = Object.keys(pickA).filter((k) => pickA[k]).map((externe_id) => ({ externe_id, entite_id: impEntite ? Number(impEntite) : null }));
    const salaries = Object.keys(pickU).filter((k) => pickU[k]).map((externe_id) => ({ externe_id, entite_id: impEntite ? Number(impEntite) : null, homonyme: homonyme[externe_id] || null }));
    const r = await run(() => api.post("/glpi/import/appliquer", { actifs, salaries }), "Import termine.");
    if (r) { setOutcome(r); setImp(null); load().catch(() => {}); }
  };

  const previewExport = async () => {
    setOutcome(null);
    const r = await run(() => api.post("/glpi/export/apercu", {}));
    if (!r) return;
    setExp(r);
    setPickX(Object.fromEntries(r.salaries.filter((u) => u.a_traiter && !["conflit", "lien_perdu"].includes(u.etat_export)).map((u) => [u.id, true])));
  };
  const applyExport = async () => {
    const ids = Object.keys(pickX).filter((k) => pickX[k]).map(Number);
    const r = await run(() => api.post("/glpi/export/appliquer", { user_ids: ids }), "Export termine.");
    if (r) { setOutcome(r); setExp(null); load().catch(() => {}); }
  };

  const nA = Object.values(pickA).filter(Boolean).length;
  const fabricants = imp ? [...new Set(imp.actifs.map((a) => a.fabricant).filter(Boolean))].sort((x, y) => x.localeCompare(y)) : [];
  const actifsVisibles = imp ? imp.actifs.filter((a) => {
    if (fa.type && a.itemtype !== fa.type) return false;
    if (fa.etat && a.etat_import !== fa.etat) return false;
    if (fa.fab && ((a.fabricant || "") === fa.fab) === fa.sauf) return false;
    const q = sansAccent(fa.q).trim();
    return !q || sansAccent([a.nom, a.serial, a.inventaire, a.fabricant, a.modele, a.utilisateur].join(" ")).includes(q);
  }) : [];
  const cocherVisibles = (valeur) => setPickA((cur) => {
    const next = { ...cur };
    actifsVisibles.filter((a) => a.importable).forEach((a) => { next[a.externe_id] = valeur; });
    return next;
  });
  const filtresActifs = JSON.stringify(fa) !== JSON.stringify(FILTRES_VIDES);
  const nU = Object.values(pickU).filter(Boolean).length;
  const entitesU = imp ? entitesSalaries(imp.salaries) : [];
  const salariesVisibles = imp ? filtrerSalaries(imp.salaries, fu) : [];
  const cocherSalariesVisibles = (valeur) => {
    const next = cocherSalaries(pickU, homonyme, salariesVisibles, valeur);
    setPickU(next.pickU);
    setHomonyme(next.homonyme);
  };
  const viderSalaries = () => {
    const next = toutDecocherSalaries();
    setPickU(next.pickU);
    setHomonyme(next.homonyme);
  };
  const filtresSalariesActifs = JSON.stringify(fu) !== JSON.stringify(FILTRES_U_VIDES);
  const nX = Object.values(pickX).filter(Boolean).length;

  return (
    <div>
      <div className="card">
        <h3>GLPI</h3>
        <p className="muted">
          Kikan lit et alimente GLPI par son API REST : import de ce qui existe dans GLPI (apres votre selection) et export des salaries et de
          leur materiel (numeros de serie compris), ce qui permettra ensuite de creer des tickets. Seuls les <strong>ordinateurs</strong> et les
          <strong> telephones</strong> sont suivis. Rien n'est jamais supprime ni ecrase ; la source de verite des salaries reste Kikan.
        </p>
        <div className="grid">
          <label>Adresse du serveur GLPI<input value={f.url} onChange={set("url")} placeholder="https://glpi.entreprise.local" /></label>
          <label>Entite Kikan par defaut pour l'import
            <select value={f.entite_kikan || ""} onChange={set("entite_kikan")}>
              <option value="">- (aucune)</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
          <label>Entite GLPI par defaut pour l'export (numero, 0 = racine)<input type="number" min="0" value={f.entite_glpi} onChange={set("entite_glpi")} /></label>
          <label>Profil GLPI donne aux utilisateurs crees (vide = aucun)<input value={f.profil} onChange={set("profil")} placeholder="Self-Service" /></label>
        </div>
        {data.probleme_url && <p className="err">{data.probleme_url}</p>}
        <label style={line}><input type="checkbox" style={{ width: "auto" }} checked={f.verifier_cert} onChange={set("verifier_cert")} /> Verifier le certificat du serveur (HTTPS)</label>
        <strong>Types Kikan correspondant a un ordinateur</strong>
        <div style={{ columns: 3 }}>{types.map((t) => (
          <label key={t} style={line}><input type="checkbox" style={{ width: "auto" }} checked={f.types_computer.includes(t)} onChange={() => toggleType("types_computer", t)} /> {t}</label>
        ))}</div>
        <strong>Types Kikan correspondant a un telephone</strong>
        <div style={{ columns: 3 }}>{types.map((t) => (
          <label key={t} style={line}><input type="checkbox" style={{ width: "auto" }} checked={f.types_phone.includes(t)} onChange={() => toggleType("types_phone", t)} /> {t}</label>
        ))}</div>
        <p className="muted">
          Jeton utilisateur GLPI : {data.jeton_defini ? <span className="badge ok">defini</span> : <span className="badge bad">non defini</span>}{" "}
          (variable <code>KIKAN_GLPI_USER_TOKEN</code>) ; jeton d'application : {data.jeton_application_defini ? <span className="badge ok">defini</span> : <span className="badge">non defini</span>}{" "}
          (<code>KIKAN_GLPI_APP_TOKEN</code>, si votre GLPI en exige un). Les jetons se placent uniquement dans le fichier .env et ne sont jamais affiches.
        </p>
        <label style={line}><input type="checkbox" style={{ width: "auto" }} checked={f.actif} onChange={set("actif")} /> <strong>Activer le connecteur GLPI</strong></label>
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={save} disabled={busy}>Enregistrer</button>
          <button className="ghost" onClick={test} disabled={busy}>Tester la connexion</button>
        </div>
      </div>

      <div className="card">
        <h3>Correspondance des champs</h3>
        <p className="muted">Champ GLPI qui alimente chaque champ Kikan a l'import. Enregistrez ensuite les reglages. Un identifiant interne deja utilise par un autre materiel est refuse a l'import.</p>
        <table>
          <thead><tr><th>Champ Kikan</th><th>Champ GLPI</th></tr></thead>
          <tbody><tr><td>Identifiant interne</td>
            <td><select value={f.champs?.identifiant_interne || "name"} onChange={(e) => mapChamp("identifiant_interne", e.target.value)}>
              <option value="name">Nom (nom du PC)</option>
              <option value="otherserial">Numero d'inventaire</option>
              <option value="serial">Numero de serie</option>
            </select></td></tr></tbody>
        </table>
      </div>

      {glpiEntites.length > 0 && (
        <div className="card">
          <h3>Correspondance des entites</h3>
          <p className="muted">Facultatif. Entite Kikan associee a chaque entite GLPI (import) ; l'inverse sert a l'export. Enregistrez ensuite les reglages.</p>
          <table>
            <thead><tr><th>Entite GLPI</th><th>Entite Kikan</th></tr></thead>
            <tbody>{glpiEntites.map((g) => (
              <tr key={g.id}><td>{g.nom} <span className="muted">(n° {g.id})</span></td>
                <td><select value={f.entites[String(g.id)] || ""} onChange={(e) => mapEntite(g.id, e.target.value)}>
                  <option value="">- (entite par defaut)</option>
                  {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
                </select></td></tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {data.config.actif && (
        <div className="card">
          <h3>Importer depuis GLPI</h3>
          <p className="muted">Kikan lit GLPI et vous propose les ordinateurs, telephones et utilisateurs. Rien n'est cree sans votre selection ; le materiel importe arrive en stock.</p>
          <div className="row"><button onClick={preview} disabled={busy}>Lire GLPI</button></div>
          {imp && (
            <div>
              <label style={{ ...line, marginTop: 10 }}>Entite Kikan des elements importes :
                <select style={{ width: "auto" }} value={impEntite} onChange={(e) => setImpEntite(e.target.value)}>
                  <option value="">Selon les reglages (correspondance ou entite par defaut)</option>
                  {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
                </select></label>
              <h4>Materiel ({filtresActifs ? `${actifsVisibles.length} affiches sur ` : ""}{imp.actifs.length}, {nA} selectionne(s))</h4>
              {imp.actifs.length > 0 && (
                <div>
                  <div className="row">
                    <input style={{ width: "auto", minWidth: 220 }} value={fa.q} onChange={(e) => setFa({ ...fa, q: e.target.value })} placeholder="Rechercher (nom, serie, modele, utilisateur...)" />
                    <select style={{ width: "auto" }} value={fa.type} onChange={(e) => setFa({ ...fa, type: e.target.value })}>
                      <option value="">Tous les types</option><option value="Computer">Ordinateurs</option><option value="Phone">Telephones</option>
                    </select>
                    <select style={{ width: "auto" }} value={fa.etat} onChange={(e) => setFa({ ...fa, etat: e.target.value })}>
                      <option value="">Tous les etats d'import</option>
                      {Object.entries(ETATS_IMPORT).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
                    </select>
                    <select style={{ width: "auto" }} value={fa.fab} onChange={(e) => setFa({ ...fa, fab: e.target.value })}>
                      <option value="">Tous les fabricants</option>
                      {fabricants.map((x) => <option key={x} value={x}>{x}</option>)}
                    </select>
                    <label style={line}><input type="checkbox" style={{ width: "auto" }} checked={fa.sauf} disabled={!fa.fab} onChange={(e) => setFa({ ...fa, sauf: e.target.checked })} /> Tous sauf ce fabricant</label>
                    {filtresActifs && <button className="ghost" onClick={() => setFa(FILTRES_VIDES)}>Effacer les filtres</button>}
                  </div>
                  <div className="row" style={{ marginTop: 6 }}>
                    <button className="ghost" onClick={() => cocherVisibles(true)}>Cocher les {actifsVisibles.length} affiches</button>
                    <button className="ghost" onClick={() => cocherVisibles(false)}>Decocher les affiches</button>
                    <button className="ghost" onClick={() => setPickA({})}>Tout decocher</button>
                  </div>
                </div>
              )}
              {imp.actifs.length === 0 ? <p className="muted">Aucun ordinateur ni telephone dans GLPI.</p> : actifsVisibles.length === 0 ? <p className="muted">Aucun materiel ne correspond aux filtres.</p> : (
                <table>
                  <thead><tr><th></th><th>Type</th><th>Nom</th><th>ID interne propose</th><th>Numero de serie</th><th>Fabricant, modele</th><th>Utilisateur GLPI</th><th>Etat</th></tr></thead>
                  <tbody>{actifsVisibles.map((a) => (
                    <tr key={a.externe_id}>
                      <td><input type="checkbox" disabled={!a.importable} checked={!!pickA[a.externe_id]} onChange={(e) => setPickA({ ...pickA, [a.externe_id]: e.target.checked })} /></td>
                      <td>{a.itemtype === "Computer" ? "Ordinateur" : "Telephone"}{!a.type_kikan && <div className="err">type Kikan non configure</div>}</td>
                      <td>{a.nom}</td><td>{a.id_interne_propose || "-"}</td><td>{a.serial || "-"}</td><td>{[a.fabricant, a.modele].filter(Boolean).join(" ") || "-"}</td><td>{a.utilisateur || "-"}</td>
                      <td><Badge table={ETATS_IMPORT} k={a.etat_import} /></td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
              <h4>Salaries ({filtresSalariesActifs ? `${salariesVisibles.length} affiches sur ` : ""}{imp.salaries.length}, {nU} selectionne(s))</h4>
              <p className="muted">Une fiche Kikan existante n'est jamais ecrasee : seuls ses champs vides sont completes.</p>
              {imp.salaries.length > 0 && (
                <div>
                  <div className="row">
                    <input style={{ width: "auto", minWidth: 220 }} value={fu.q} onChange={(e) => setFu({ ...fu, q: e.target.value })} placeholder="Rechercher (identifiant, nom, e-mail, matricule...)" />
                    <select style={{ width: "auto" }} value={fu.etat} onChange={(e) => setFu({ ...fu, etat: e.target.value })}>
                      <option value="">Tous les etats d'import</option>
                      {ETATS_IMPORT_U.map((k) => <option key={k} value={k}>{ETATS_IMPORT[k][0]}</option>)}
                    </select>
                    <select style={{ width: "auto" }} value={fu.entite} onChange={(e) => setFu({ ...fu, entite: e.target.value })}>
                      <option value="">Toutes les entites GLPI</option>
                      {entitesU.map((x) => <option key={x} value={x}>{x}</option>)}
                    </select>
                    <label style={line}><input type="checkbox" style={{ width: "auto" }} checked={fu.sauf} disabled={!fu.entite} onChange={(e) => setFu({ ...fu, sauf: e.target.checked })} /> Tous sauf cette entite</label>
                    {filtresSalariesActifs && <button className="ghost" onClick={() => setFu(FILTRES_U_VIDES)}>Effacer les filtres</button>}
                  </div>
                  <div className="row" style={{ marginTop: 6 }}>
                    <button className="ghost" onClick={() => cocherSalariesVisibles(true)}>Cocher les {salariesVisibles.length} affiches</button>
                    <button className="ghost" onClick={() => cocherSalariesVisibles(false)}>Decocher les affiches</button>
                    <button className="ghost" onClick={viderSalaries}>Tout decocher</button>
                  </div>
                </div>
              )}
              {imp.salaries.length === 0 ? <p className="muted">Aucun utilisateur actif dans GLPI.</p> : salariesVisibles.length === 0 ? <p className="muted">Aucun salarie ne correspond aux filtres.</p> : (
                <table>
                  <thead><tr><th></th><th>Identifiant GLPI</th><th>Nom</th><th>E-mail</th><th>Matricule</th><th>Etat</th><th></th></tr></thead>
                  <tbody>{salariesVisibles.map((u) => (
                    <tr key={u.externe_id}>
                      <td><input type="checkbox" disabled={!u.importable} checked={!!pickU[u.externe_id]} onChange={(e) => setPickU({ ...pickU, [u.externe_id]: e.target.checked })} /></td>
                      <td>{u.login}</td><td>{[u.prenom, u.nom].filter(Boolean).join(" ") || "-"}</td><td>{u.email || "-"}</td><td>{u.matricule || "-"}</td>
                      <td><Badge table={ETATS_IMPORT} k={u.etat_import} /></td>
                      <td>{u.etat_import === "homonyme" && (
                        <select style={{ width: "auto" }} value={homonyme[u.externe_id] || ""} onChange={(e) => { setHomonyme({ ...homonyme, [u.externe_id]: e.target.value }); setPickU({ ...pickU, [u.externe_id]: !!e.target.value }); }}>
                          <option value="">Ne pas importer</option>
                          <option value="lier">C'est la meme personne : lier</option>
                          <option value="creer">Autre personne : creer une fiche</option>
                        </select>)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
              <div style={{ marginTop: 10 }}>
                <ConfirmButton confirmLabel={`Confirmer l'import (${nA} materiel, ${nU} salarie(s))`} onConfirm={applyImport}>Importer la selection ({nA} + {nU})</ConfirmButton>
              </div>
            </div>
          )}
        </div>
      )}

      {data.config.actif && (
        <div className="card">
          <h3>Exporter vers GLPI</h3>
          <p className="muted">
            Kikan cree dans GLPI les salaries choisis (avec leur matricule, leur e-mail et le profil indique) et leur materiel affecte, avec
            les numeros de serie. Un utilisateur ou un materiel deja present dans GLPI est lie, jamais modifie ni duplique.
          </p>
          <div className="row"><button onClick={previewExport} disabled={busy}>Preparer l'export</button></div>
          {exp && (
            <div>
              {!exp.profil_trouve && <p className="err">Le profil « {exp.profil} » n'existe pas dans GLPI : les utilisateurs seraient crees sans profil.</p>}
              <table>
                <thead><tr><th></th><th>Salarie</th><th>Matricule</th><th>Dans GLPI</th><th>Materiel affecte</th></tr></thead>
                <tbody>{exp.salaries.map((u) => (
                  <tr key={u.id}>
                    <td><input type="checkbox" disabled={!u.a_traiter || ["conflit", "lien_perdu"].includes(u.etat_export)} checked={!!pickX[u.id]} onChange={(e) => setPickX({ ...pickX, [u.id]: e.target.checked })} /></td>
                    <td>{u.prenom} {u.nom}<div className="muted">{u.email || "sans e-mail"}</div></td><td>{u.matricule || "-"}</td>
                    <td><Badge table={ETATS_EXPORT} k={u.etat_export} /></td>
                    <td>{u.actifs.length === 0 ? "-" : u.actifs.map((a) => (
                      <div key={a.id}>{a.type} {a.marque} {a.modele} - {a.numero_serie || "sans n° de serie"} <Badge table={ETATS_EXPORT} k={a.etat_export} /></div>
                    ))}</td>
                  </tr>
                ))}</tbody>
              </table>
              <div style={{ marginTop: 10 }}>
                <ConfirmButton confirmLabel={`Confirmer l'export (${nX} salarie(s))`} onConfirm={applyExport}>Exporter la selection ({nX})</ConfirmButton>
              </div>
            </div>
          )}
        </div>
      )}

      <Outcome outcome={outcome} />

      {history.length > 0 && (
        <div className="card">
          <h3>Historique</h3>
          <table>
            <thead><tr><th>Date</th><th>Sens</th><th>Par</th><th>Resume</th></tr></thead>
            <tbody>{history.map((h) => (
              <tr key={h.id}><td>{String(h.debut).replace("T", " ").slice(0, 16)}</td><td>{h.sens === "import" ? "Import" : "Export"}</td><td>{h.lance_par}</td>
                <td>{Object.entries(h.resume).map(([k, v]) => `${k.replace("_", " : ")} = ${v}`).join(" ; ") || "-"}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
