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
  ["mail", "E-mails"],
  ["integrations", "Integrations"],
  ["pdf", "Modele de PDF"],
  ["auth", "Authentification"],
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


const SSO_MOTIFS = {
  role: "aucun role Kikan (Kikan.IT ou Kikan.RH) dans le jeton",
  mfa: "la MFA n'apparait pas dans le jeton (reglage : exiger la MFA)",
  jeton: "le jeton n'a pas pu etre verifie",
  session: "la connexion a expire ou a ete interrompue",
  idp: "Microsoft a refuse la connexion",
  echange: "l'echange avec Microsoft a echoue",
  reseau: "Microsoft est injoignable depuis le serveur",
  compte: "compte inconnu ou desactive",
  config: "configuration incoherente",
};

// Connexion Microsoft 365 (SSO) : etat de la configuration, reglages, tests, activation.
function AuthSso({ setErr, setMsg }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);

  const load = async () => {
    const d = await api.get("/auth/sso/admin/etat");
    setData(d);
    setForm(d.reglages);
  };
  useEffect(() => {
    load().catch((e) => setErr(errorText(e)));
    const q = new URLSearchParams(window.location.search);
    if (q.get("sso_test") === "ok") setMsg("Test de connexion reussi : votre identite Microsoft 365 est reconnue avec le role informatique.");
    if (q.get("sso_test") === "refuse") setErr("Test de connexion refuse : " + (SSO_MOTIFS[q.get("motif")] || "motif inconnu") + ".");
    if (q.get("sso_test")) window.history.replaceState(null, "", "/parametres");
  }, []);

  const run = async (fn, okMsg) => {
    setErr(null); setMsg(null);
    try { const r = await fn(); if (okMsg) setMsg(typeof okMsg === "function" ? okMsg(r) : okMsg); await load(); } catch (ex) { setErr(errorText(ex)); }
  };

  if (!data || !form) return <div className="card"><p className="muted">Chargement...</p></div>;
  const c = data.config;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const t = data.test;

  return (
    <div>
      <div className="card">
        <h3>Etat de la connexion Microsoft 365</h3>
        <p>
          <span className={data.actif ? "badge ok" : "badge"}>{data.actif ? "SSO active" : "SSO desactive"}</span>{" "}
          <span className={c.configure ? "badge ok" : "badge bad"}>{c.configure ? "environnement configure" : "environnement incomplet"}</span>
        </p>
        {data.avertissement && <p className="warn">{data.avertissement}</p>}
        <table>
          <tbody>
            <tr><td>Tenant</td><td>{c.tenant || "non renseigne"}</td></tr>
            <tr><td>Identifiant client</td><td>{c.client_id || "non renseigne"}</td></tr>
            <tr><td>Secret du client</td><td>{c.secret_present ? "present dans .env (jamais affiche)" : "absent"}</td></tr>
            <tr><td>Autorite</td><td>{c.autorite}</td></tr>
            <tr><td>Adresse publique</td><td>{c.public_url || "non renseignee"}</td></tr>
            <tr><td>Adresse de retour a declarer dans Entra</td><td><code style={{ wordBreak: "break-all" }}>{c.redirect_uri || "-"}</code></td></tr>
          </tbody>
        </table>
        {c.manque.length > 0 && <p className="muted">Variables a renseigner dans <code>.env</code> : {c.manque.join(", ")} (voir docs/SSO.md).</p>}
      </div>

      <div className="card">
        <h3>Reglages</h3>
        <form className="grid" onSubmit={(e) => { e.preventDefault(); run(() => api.put("/auth/sso/admin/reglages", { ...form, ttl: Number(form.ttl) }), "Reglages enregistres."); }}>
          <label>Connexion par mot de passe (SSO actif)
            <select value={form.mode_local} onChange={set("mode_local")}>
              <option value="secours">Comptes de secours uniquement</option>
              <option value="autorise">Autorisee pour tous les comptes locaux</option>
            </select>
          </label>
          <label>Duree de session (minutes, 30 a 720)
            <input type="number" min={30} max={720} value={form.ttl} onChange={set("ttl")} />
          </label>
          <label>Role d'application : informatique<input value={form.role_it} maxLength={100} onChange={set("role_it")} /></label>
          <label>Role d'application : RH<input value={form.role_rh} maxLength={100} onChange={set("role_rh")} /></label>
          <label>Expiration du secret client (rappel)<input type="date" value={form.secret_expire} onChange={set("secret_expire")} /></label>
          <label className="check"><input type="checkbox" checked={form.creation_auto} onChange={set("creation_auto")} /><span>Creer automatiquement le compte a la premiere connexion</span></label>
          <label className="check"><input type="checkbox" checked={form.exiger_mfa} onChange={set("exiger_mfa")} /><span>Exiger que la MFA apparaisse dans le jeton Microsoft</span></label>
          <div style={{ alignSelf: "end" }}><button type="submit">Enregistrer</button></div>
        </form>
        <p className="muted">La duree de session s'applique a toutes les nouvelles connexions (locales et Microsoft 365). Comptes de secours : {data.comptes_secours}.</p>
      </div>

      <div className="card">
        <h3>Tests et activation</h3>
        <div className="row" style={{ marginBottom: 12 }}>
          <button className="ghost" disabled={!c.configure} onClick={() => run(() => api.post("/auth/sso/admin/tester-config", {}), (r) => `Configuration valide : ${r.cles} cle(s) de signature trouvee(s).`)}>
            Tester la configuration
          </button>
          <button className="ghost" disabled={!c.configure} onClick={async () => {
            setErr(null); setMsg(null);
            try { const r = await api.post("/auth/sso/admin/test-start", {}); window.location.href = r.url; } catch (ex) { setErr(errorText(ex)); }
          }}>
            Tester ma connexion Microsoft 365
          </button>
        </div>
        {t && (
          <p className="muted">
            Dernier test : {t.upn} (role {t.role}{t.mfa ? ", MFA presente" : ", MFA absente"}), par {t.par}, le {new Date(t.ts * 1000).toLocaleString("fr-FR")}.
          </p>
        )}
        {!data.actif && data.blocages.length > 0 && (
          <div className="warn" style={{ marginBottom: 12 }}>
            <b>Pour activer le SSO :</b>
            <ul style={{ margin: "6px 0 0 18px" }}>{data.blocages.map((b) => <li key={b}>{b}</li>)}</ul>
          </div>
        )}
        <div className="row">
          {!data.actif && (
            <button disabled={data.blocages.length > 0} onClick={() => run(() => api.post("/auth/sso/admin/activer", {}), "Connexion Microsoft 365 activee.")}>Activer le SSO</button>
          )}
          {data.actif && (
            <ConfirmButton confirmLabel="Confirmer la desactivation" onConfirm={() => run(() => api.post("/auth/sso/admin/desactiver", {}), "Connexion Microsoft 365 desactivee : la connexion par mot de passe est de nouveau ouverte.")}>
              Desactiver le SSO
            </ConfirmButton>
          )}
        </div>
        <p className="muted">
          Une activation demande un test de connexion reussi de votre part (moins de 30 minutes) et au moins un compte local de secours.
          Desactiver le SSO rend immediatement la connexion par mot de passe a tous les comptes locaux.
        </p>
      </div>
    </div>
  );
}

const row = { display: "flex", flexDirection: "row", alignItems: "center", gap: 8, margin: "4px 0" };
const num = { width: 70 };

// E-mails : serveur SMTP externe, rappels automatiques et rapport mensuel.
function Courriel({ setErr, setMsg }) {
  const [data, setData] = useState(null);
  const [f, setF] = useState(null);
  const [apercu, setApercu] = useState(null);

  const load = async () => {
    const d = await api.get("/mail/config");
    setData(d);
    setF(d.config);
  };
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, []);

  const run = async (fn, okMsg) => {
    setErr(null); setMsg(null);
    try { const r = await fn(); if (okMsg) setMsg(typeof okMsg === "function" ? okMsg(r) : okMsg); return r; } catch (ex) { setErr(errorText(ex)); }
  };

  if (!data || !f) return <div className="card"><p className="muted">Chargement...</p></div>;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const setN = (k) => (e) => setF({ ...f, [k]: Number(e.target.value) });
  const save = () => run(async () => { const d = await api.put("/mail/config", f); setData(d); setF(d.config); return d; }, "Reglages enregistres.");
  const summary = (r) => {
    const x = r.resultat || {};
    const parts = Object.entries(x).map(([k, v]) => `${k === "rapport" ? "rapport" : "rappels"} : ${v.envoyes} message(s)${v.erreurs.length ? `, ${v.erreurs.length} erreur(s)` : ""}`);
    return parts.length ? "Execution terminee - " + parts.join(" ; ") : "Rien a envoyer pour le moment.";
  };

  return (
    <div>
      <div className="card">
        <h3>Serveur de messagerie (SMTP)</h3>
        <p className="muted">
          Kikan n'embarque aucun serveur de messagerie : indiquez celui de votre entreprise. Un serveur interne sans
          authentification ni chiffrement est possible (securite « aucune ») ; preferez STARTTLS ou SSL des qu'il les propose.
        </p>
        <div className="grid">
          <label>Serveur<input value={f.hote} onChange={set("hote")} placeholder="smtp.entreprise.local" /></label>
          <label>Port<input type="number" min="1" max="65535" value={f.port} onChange={setN("port")} /></label>
          <label>Securite
            <select value={f.securite} onChange={set("securite")}>
              <option value="aucune">Aucune (reseau interne)</option>
              <option value="starttls">STARTTLS</option>
              <option value="ssl">SSL / TLS</option>
            </select>
          </label>
          <label>Identifiant (si le serveur en exige un)<input value={f.utilisateur} onChange={set("utilisateur")} autoComplete="off" /></label>
          <label>Adresse d'expedition<input value={f.expediteur} onChange={set("expediteur")} placeholder="kikan@entreprise.local" /></label>
          <label>Adresse de liste (en plus des comptes, recoit tout)<input value={f.liste} onChange={set("liste")} placeholder="informatique@entreprise.local" /></label>
        </div>
        <label style={row}><input type="checkbox" style={{ width: "auto" }} checked={f.verifier_cert} onChange={set("verifier_cert")} />
          Verifier le certificat du serveur (STARTTLS et SSL)</label>
        <p className="muted">
          Mot de passe SMTP : {data.mot_de_passe_defini ? <span className="badge ok">defini</span> : <span className="badge">non defini</span>}{" "}
          (variable <code>KIKAN_SMTP_PASSWORD</code> du fichier .env, jamais stocke en base ni affiche).
          {!data.lien_defini && " La variable KIKAN_PUBLIC_URL n'est pas definie : les e-mails n'auront pas de lien vers Kikan."}
        </p>
      </div>

      <div className="card">
        <h3>Rappels automatiques</h3>
        <p className="muted">
          Un recapitulatif par personne et par jour, a l'heure choisie. L'informatique et l'adresse de liste recoivent tout ; une RH
          ne recoit que les salaries de son perimetre. Un rappel deja envoye n'est renvoye qu'a l'echeance de relance.
        </p>
        <label style={row}><input type="checkbox" style={{ width: "auto" }} checked={f.renouv} onChange={set("renouv")} />
          Renouvellements : materiel dont l'echeance tombe dans les <input type="number" min="1" max="730" style={num} value={f.renouv_jours} onChange={setN("renouv_jours")} /> jours
          (informatique, relance tous les 30 jours)</label>
        <label style={row}><input type="checkbox" style={{ width: "auto" }} checked={f.depart} onChange={set("depart")} />
          Departs a venir : sortie dans les <input type="number" min="1" max="90" style={num} value={f.depart_jours} onChange={setN("depart_jours")} /> jours avec du materiel
          encore detenu (relance chaque semaine)</label>
        <label style={row}><input type="checkbox" style={{ width: "auto" }} checked={f.nonrestit} onChange={set("nonrestit")} />
          Materiel non restitue apres la date de sortie, relance toutes les <input type="number" min="1" max="12" style={num} value={f.nonrestit_sem} onChange={setN("nonrestit_sem")} /> semaine(s)</label>
        <label style={row}><input type="checkbox" style={{ width: "auto" }} checked={f.besoins} onChange={set("besoins")} />
          Besoins de materiel non traites pour des arrivees dans les <input type="number" min="1" max="90" style={num} value={f.besoins_jours} onChange={setN("besoins_jours")} /> jours
          (informatique, relance chaque semaine)</label>
        <label style={row}>Heure d'envoi :
          <input type="number" min="0" max="23" style={num} value={f.heure} onChange={setN("heure")} /> h (heure du serveur)</label>
      </div>

      <div className="card">
        <h3>Rapport mensuel</h3>
        <p className="muted">
          Un recapitulatif du parc, des remises et restitutions du mois, du materiel non restitue et des renouvellements, envoye a
          l'informatique et a l'adresse de liste, avec un lien vers les rapports de Kikan.
        </p>
        <label style={row}><input type="checkbox" style={{ width: "auto" }} checked={f.rapport} onChange={set("rapport")} />
          Envoyer le rapport chaque mois, a partir du jour <input type="number" min="1" max="28" style={num} value={f.rapport_jour} onChange={setN("rapport_jour")} /></label>
        <label style={row}>Piece jointe :
          <select style={{ width: "auto" }} value={f.rapport_pj} onChange={set("rapport_pj")}>
            <option value="aucune">Aucune (lien seulement, recommande)</option>
            <option value="xlsx">Excel (detentions par salarie)</option>
            <option value="pdf">PDF (detentions par salarie)</option>
          </select></label>
      </div>

      <div className="card">
        <label style={row}><input type="checkbox" style={{ width: "auto" }} checked={f.actif} onChange={set("actif")} />
          <strong>Activer l'envoi d'e-mails</strong></label>
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={save}>Enregistrer</button>
          <button className="ghost" onClick={() => run(() => api.post("/mail/test", {}), (r) => `Message de test envoye a ${r.destinataire}.`)}>
            Envoyer un e-mail de test</button>
          <button className="ghost" onClick={async () => { const r = await run(() => api.get("/mail/apercu")); if (r) setApercu(r); }}>
            Voir ce qui serait envoye</button>
          <ConfirmButton confirmLabel="Confirmer l'envoi" onConfirm={async () => { await run(() => api.post("/mail/executer", { rappels: true, rapport: false }), summary); load(); }}>
            Envoyer les rappels maintenant</ConfirmButton>
          <ConfirmButton confirmLabel="Confirmer l'envoi" onConfirm={async () => { await run(() => api.post("/mail/executer", { rappels: false, rapport: true }), summary); load(); }}>
            Envoyer le rapport maintenant</ConfirmButton>
        </div>
        <p className="muted">
          Le test est envoye a l'e-mail de votre compte (page Comptes), a defaut a l'adresse de liste. Enregistrez avant de tester.
          {" "}Derniere execution : {data.derniere_execution ? data.derniere_execution.replace("T", " ") : "jamais"}
          {data.dernier_resultat ? ` (${data.dernier_resultat})` : ""}.
        </p>
        {data.derniere_erreur && <p className="err">Derniere erreur : {data.derniere_erreur}</p>}
      </div>

      {apercu && (
        <div className="card">
          <h3>Apercu des envois</h3>
          {apercu.rappels.length === 0 ? <p className="muted">Aucun rappel a envoyer pour le moment.</p> : (
            <table>
              <thead><tr><th>Destinataire</th><th>Renouvellements</th><th>Departs</th><th>Non restitue</th><th>Besoins</th></tr></thead>
              <tbody>{apercu.rappels.map((d) => (
                <tr key={d.destinataire}><td>{d.destinataire}</td><td>{d.elements.renouv || 0}</td><td>{d.elements.depart || 0}</td><td>{d.elements.nonrestit || 0}</td><td>{d.elements.besoins || 0}</td></tr>
              ))}</tbody>
            </table>
          )}
          <p className="muted">Rapport mensuel : {apercu.rapport.length ? apercu.rapport.join(", ") : "aucun destinataire (renseignez l'e-mail d'un compte informatique ou l'adresse de liste)"}.</p>
        </div>
      )}
    </div>
  );
}

const DROITS_API = [
  ["assets_lecture", "Lire le materiel"], ["assets_ecriture", "Ecrire le materiel"],
  ["users_lecture", "Lire les salaries"], ["users_ecriture", "Ecrire les salaries"],
];
const fmtDate = (d) => (d ? String(d).replace("T", " ").slice(0, 16) : "jamais");

// Jetons de l'API d'integration (/v1) : un outil externe pousse du materiel et des salaries vers Kikan.
function JetonsApi({ setErr, setMsg }) {
  const emptyForm = { nom: "", source: "api", droits: ["assets_lecture", "assets_ecriture"], globale: false, entites: [], jours: 90 };
  const [tokens, setTokens] = useState([]);
  const [entites, setEntites] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [secret, setSecret] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = async () => {
    const [t, e] = await Promise.all([api.get("/integrations/tokens"), api.get("/entites")]);
    setTokens(t); setEntites(e);
  };
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, []);

  const toggle = (key, value) => setForm((f) => ({ ...f, [key]: f[key].includes(value) ? f[key].filter((x) => x !== value) : [...f[key], value] }));

  const create = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    try {
      const r = await api.post("/integrations/tokens", {
        nom: form.nom, source: form.source, droits: form.droits, portee_globale: form.globale,
        entites: form.globale ? [] : form.entites, jours: Number(form.jours) || 90,
      });
      setSecret({ nom: r.nom, jeton: r.jeton }); setCopied(false);
      setForm(emptyForm);
      setMsg(`Jeton « ${r.nom} » cree.`);
      await load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const revoke = async (t) => {
    setErr(null); setMsg(null);
    try { await api.post(`/integrations/tokens/${t.id}/revoquer`, {}); setMsg(`Jeton « ${t.nom} » revoque.`); await load(); } catch (ex) { setErr(errorText(ex)); }
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(secret.jeton); setCopied(true); } catch { setErr("Copie impossible : selectionnez le jeton a la main."); }
  };
  const scope = (t) => (t.portee_globale ? "Toute l'organisation" : t.entites.map((id) => entites.find((e) => e.id === id)?.nom || "?").join(", "));
  const etat = (t) => (!t.actif ? <span className="badge bad">revoque</span> : t.expire ? <span className="badge bad">expire</span> : <span className="badge ok">actif</span>);

  return (
    <div>
      {secret && (
        <div className="card" role="alert">
          <h3>Jeton « {secret.nom} »</h3>
          <p>Copiez-le maintenant : il ne sera <strong>plus jamais affiche</strong> (Kikan n'en garde que l'empreinte).</p>
          <p><code style={{ wordBreak: "break-all", fontSize: 15 }}>{secret.jeton}</code></p>
          <div className="row">
            <button onClick={copy}>{copied ? "Copie" : "Copier"}</button>
            <button className="ghost" onClick={() => setSecret(null)}>J'ai note le jeton, fermer</button>
          </div>
        </div>
      )}

      <div className="card">
        <h3>Jetons d'acces a l'API</h3>
        <p className="muted">
          Un jeton permet a un outil externe (inventaire, script...) d'envoyer du materiel et des salaries vers Kikan par
          l'API <code>/api/v1</code>, sans compte humain. Droits et perimetre limites, expiration obligatoire, revocable a tout
          moment. L'API ne supprime jamais rien et ne cree pas de remises signees (voir docs/API.md).
        </p>
        <form onSubmit={create}>
          <div className="grid">
            <label>Nom du jeton<input value={form.nom} minLength={3} maxLength={60} required placeholder="ex. Inventaire GLPI"
                                      onChange={(e) => setForm({ ...form, nom: e.target.value })} /></label>
            <label>Systeme d'origine (identifiant court)<input value={form.source} pattern="[a-z][a-z0-9_-]{1,29}" required
                                      onChange={(e) => setForm({ ...form, source: e.target.value })} /></label>
            <label>Duree de validite (jours, 730 au plus)<input type="number" min="1" max="730" value={form.jours}
                                      onChange={(e) => setForm({ ...form, jours: e.target.value })} /></label>
          </div>
          <strong>Droits</strong>
          <div>
            {DROITS_API.map(([k, l]) => (
              <label key={k} style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 6, margin: "2px 0" }}>
                <input type="checkbox" style={{ width: "auto" }} checked={form.droits.includes(k)} onChange={() => toggle("droits", k)} /> {l}
              </label>
            ))}
          </div>
          <strong>Perimetre</strong>
          <label style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 6, margin: "2px 0" }}>
            <input type="checkbox" style={{ width: "auto" }} checked={form.globale} onChange={(e) => setForm({ ...form, globale: e.target.checked })} />
            Toute l'organisation
          </label>
          {!form.globale && (
            <div style={{ columns: 2, marginLeft: 20 }}>
              {entites.map((e) => (
                <label key={e.id} style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 6, margin: "2px 0" }}>
                  <input type="checkbox" style={{ width: "auto" }} checked={form.entites.includes(e.id)} onChange={() => toggle("entites", e.id)} /> {e.nom}
                </label>
              ))}
            </div>
          )}
          <div style={{ marginTop: 10 }}><button type="submit" disabled={form.droits.length === 0}>Creer le jeton</button></div>
        </form>
      </div>

      <div className="card">
        {tokens.length === 0 ? <p className="muted">Aucun jeton.</p> : (
          <table>
            <thead><tr><th>Nom</th><th>Debut</th><th>Systeme</th><th>Droits</th><th>Perimetre</th><th>Expire le</th><th>Derniere utilisation</th><th>Etat</th><th></th></tr></thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td>{t.nom}</td>
                  <td><code>{t.prefixe}...</code></td>
                  <td>{t.source}</td>
                  <td>{t.droits.map((d) => DROITS_API.find(([k]) => k === d)?.[1] || d).join(", ")}</td>
                  <td>{scope(t)}</td>
                  <td>{t.expire_le}</td>
                  <td>{fmtDate(t.derniere_utilisation)}{t.utilisations ? ` (${t.utilisations})` : ""}</td>
                  <td>{etat(t)}</td>
                  <td>{t.actif && <ConfirmButton confirmLabel="Confirmer la revocation" onConfirm={() => revoke(t)}>Revoquer</ConfirmButton>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// Integrations : jetons d'API et connecteurs.
function Integrations({ setErr, setMsg }) {
  return (
    <div>
      <JetonsApi setErr={setErr} setMsg={setMsg} />
    </div>
  );
}

export default function Parametres() {
  const [tab, setTab] = useState(() => (new URLSearchParams(window.location.search).get("sso_test") ? "auth" : "types"));
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
      {tab === "mail" && <Courriel setErr={setErr} setMsg={setMsg} />}
      {tab === "integrations" && <Integrations setErr={setErr} setMsg={setMsg} />}
      {tab === "auth" && <AuthSso setErr={setErr} setMsg={setMsg} />}
      {tab === "etat" && <Etat setErr={setErr} />}
    </div>
  );
}
