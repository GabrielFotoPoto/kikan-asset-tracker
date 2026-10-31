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

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorText } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";
import Autocomplete from "../components/Autocomplete.jsx";
import ConfirmButton from "../components/ConfirmButton.jsx";
import { Feedback, useNotify } from "../components/Notifications.jsx";
import { Empty, Loading } from "../components/State.jsx";

// Recherche sans accent ni casse, comme l'autocompletion du catalogue.
const fold = (v) => (v || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const FILTRES = ["stock", "affecte", "rendu", "reforme"];
// Les statuts affecte et rendu viennent de la remise et de la restitution, jamais d'une saisie manuelle.
const SAISISSABLES = ["stock", "reforme"];
const DATES = ["date_achat", "fin_garantie", "echeance_renouvellement"];
const TEXTES = ["identifiant_interne", "type", "marque", "modele", "numero_serie", "notes"];
const empty = {
  identifiant_interne: "", type: "", marque: "", modele: "", numero_serie: "",
  date_achat: "", fin_garantie: "", echeance_renouvellement: "", statut: "stock", entite_id: "", notes: "",
};

export default function Assets() {
  const { user } = useAuth();
  const writable = canWrite(user.role, "materiel");
  const notify = useNotify();
  // Les filtres vivent dans l'adresse : un lien copie retrouve la meme vue ; ?asset=ID ouvre un actif (lien des etiquettes QR).
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const filtre = params.get("statut") || "";
  const filtreType = params.get("type") || "";
  const filtreEntite = params.get("entite") || "";
  const idCible = Number(params.get("asset")) || null;
  const [items, setItems] = useState(null);
  const [entites, setEntites] = useState([]);
  const [types, setTypes] = useState([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = () => api.get("/assets").then(setItems).catch((e) => setErr(errorText(e)));
  useEffect(() => { api.get("/entites").then(setEntites); }, []);
  useEffect(() => { load(); }, []);
  useEffect(() => { api.get("/assets/catalogue/types").then(setTypes).catch(() => {}); }, [items]);

  const lockedStatus = editing && editing.statut === "affecte";
  const options = editing && editing.statut === "rendu" ? ["rendu", ...SAISISSABLES] : SAISISSABLES;

  const startEdit = (a) => {
    setEditing(a);
    const f = { ...empty, statut: a.statut, entite_id: a.entite_id ?? "" };
    for (const k of [...TEXTES, ...DATES]) f[k] = a[k] || "";
    setForm(f);
    setErr(null); setMsg(null);
    window.scrollTo({ top: 0 });
  };
  const cancel = () => { setEditing(null); setForm(empty); setErr(null); };

  const submit = async (e) => {
    e.preventDefault();
    setErr(null); setMsg(null);
    const payload = { ...form, entite_id: form.entite_id ? Number(form.entite_id) : null };
    for (const k of [...DATES, ...TEXTES]) if (payload[k] === "") payload[k] = null;
    // Champs non affiches dans le formulaire : conserves tels quels a la modification.
    if (editing) { payload.source = editing.source; payload.id_externe = editing.id_externe; }
    try {
      if (editing) {
        await api.put(`/assets/${editing.id}`, payload);
        setMsg("Materiel modifie.");
      } else {
        await api.post("/assets", payload);
        setMsg("Materiel ajoute.");
      }
      cancel();
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const remove = async (a) => {
    setErr(null); setMsg(null);
    try {
      await api.del(`/assets/${a.id}`);
      setMsg("Materiel supprime.");
      if (editing && editing.id === a.id) cancel();
      load();
    } catch (ex) { setErr(errorText(ex)); }
  };

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  // Forme fonctionnelle : une mise a jour differee (frappe) ne ramene pas un autre filtre a son ancienne valeur.
  const setParam = (cle, valeur) => setParams((prev) => {
    const p = new URLSearchParams(prev);
    if (valeur) p.set(cle, valeur); else p.delete(cle);
    return p;
  }, { replace: true });

  // La saisie reste dans un etat local (sinon la valeur du champ suit l'adresse avec du retard et perd des lettres)
  // et gagne l'adresse apres 250 ms ; l'adresse ne reecrase la saisie que si elle change de l'exterieur.
  const [saisie, setSaisie] = useState(q);
  const poussee = useRef(q);
  useEffect(() => {
    if (q !== poussee.current) { poussee.current = q; setSaisie(q); }
  }, [q]);
  useEffect(() => {
    if (saisie === poussee.current) return undefined;
    const t = setTimeout(() => { poussee.current = saisie; setParam("q", saisie); }, 250);
    return () => clearTimeout(t);
  }, [saisie]);

  const retirer = (cle) => {
    if (cle === "q") { poussee.current = ""; setSaisie(""); }
    setParam(cle, "");
  };
  const clearFilters = () => {
    poussee.current = ""; setSaisie("");
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      ["q", "statut", "type", "entite"].forEach((k) => p.delete(k));
      return p;
    }, { replace: true });
  };
  const copyLink = () => navigator.clipboard?.writeText(window.location.href)
    .then(() => notify.ok("Lien copie."))
    .catch(() => notify.err("Copie impossible : copiez l'adresse dans la barre du navigateur."));

  const typesDispos = useMemo(
    () => [...new Set((items || []).map((a) => a.type).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr")),
    [items]);
  const visibles = useMemo(() => {
    const termes = fold(saisie).split(/\s+/).filter(Boolean);
    return (items || []).filter((a) => {
      if (filtre && a.statut !== filtre) return false;
      if (filtreType && a.type !== filtreType) return false;
      if (filtreEntite && String(a.entite_id ?? "") !== filtreEntite) return false;
      if (!termes.length) return true;
      const meule = fold([a.identifiant_interne, a.type, a.marque, a.modele, a.numero_serie, a.notes].filter(Boolean).join(" "));
      return termes.every((t) => meule.includes(t));
    });
  }, [items, saisie, filtre, filtreType, filtreEntite]);
  const chips = [
    saisie.trim() && { cle: "q", texte: `Recherche : ${saisie.trim()}` },
    filtre && { cle: "statut", texte: `Statut : ${filtre}` },
    filtreType && { cle: "type", texte: `Type : ${filtreType}` },
    filtreEntite && { cle: "entite", texte: `Entite : ${entites.find((e) => String(e.id) === filtreEntite)?.nom || filtreEntite}` },
  ].filter(Boolean);

  // Lien profond ?asset=ID : un compte qui peut ecrire ouvre l'actif en modification, les autres le voient repere dans la liste.
  const cibleTraitee = useRef(false);
  useEffect(() => {
    if (!idCible || !items || cibleTraitee.current) return;
    cibleTraitee.current = true;
    const a = items.find((x) => x.id === idCible);
    if (!a) { setErr("Ce materiel n'existe pas ou n'est pas dans votre perimetre."); return; }
    if (writable) startEdit(a);
    else requestAnimationFrame(() => document.getElementById(`actif-${a.id}`)?.scrollIntoView({ block: "center" }));
  }, [idCible, items]);

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h2>Materiel</h2>
        {user.role === "informatique" && <Link to="/import" style={{ fontSize: "0.9em" }}>Importer un fichier</Link>}
      </div>
      <Feedback err={err} msg={msg} />
      {writable && (
      <div className="card">
        <h3>{editing ? `Modifier : ${editing.type || "materiel"} ${editing.numero_serie || editing.identifiant_interne || ""}` : "Ajouter"}</h3>
        <form className="grid" onSubmit={submit}>
          <label>Id interne<input value={form.identifiant_interne} onChange={set("identifiant_interne")} /></label>
          <label>Type
            <Autocomplete value={form.type} items={types} placeholder="PC portable, Smartphone..." nouveau="Nouveau type"
                          onChange={(v) => setForm({ ...form, type: v })} />
          </label>
          <label>Marque
            <Autocomplete value={form.marque} nouveau="Nouvelle marque"
                          fetcher={(q) => api.get(`/assets/catalogue/marques?detail=true&q=${encodeURIComponent(q)}`)}
                          onChange={(v) => setForm({ ...form, marque: v })} />
          </label>
          <label>Modele
            <Autocomplete value={form.modele} nouveau="Nouveau modele"
                          placeholder={form.marque ? "Modeles de cette marque" : "Choisissez d'abord la marque"}
                          fetcher={(q) => api.get(`/assets/catalogue/modeles?detail=true&marque=${encodeURIComponent(form.marque || "")}&type=${encodeURIComponent(form.type || "")}&q=${encodeURIComponent(q)}`)}
                          onChange={(v) => setForm({ ...form, modele: v })} />
          </label>
          <label>N de serie<input value={form.numero_serie} onChange={set("numero_serie")} /></label>
          <label>Statut
            <select value={form.statut} disabled={lockedStatus} onChange={set("statut")}>
              {lockedStatus ? <option value={form.statut}>{form.statut}</option> : options.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Date d'achat<input type="date" value={form.date_achat} onChange={set("date_achat")} /></label>
          <label>Fin de garantie<input type="date" value={form.fin_garantie} onChange={set("fin_garantie")} /></label>
          <label>Echeance renouvellement<input type="date" value={form.echeance_renouvellement} onChange={set("echeance_renouvellement")} /></label>
          <label>Filiale / entite
            <select value={form.entite_id} onChange={set("entite_id")}>
              <option value="">-</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
          <label>Notes<input value={form.notes} onChange={set("notes")} /></label>
          <div className="row" style={{ alignSelf: "end" }}>
            <button type="submit">{editing ? "Enregistrer" : "Ajouter"}</button>
            {editing && <button type="button" className="ghost" onClick={cancel}>Annuler</button>}
          </div>
        </form>
        {lockedStatus && (
          <p className="muted">Ce materiel est affecte : il se libere par la restitution du salarie (page Sorties).</p>
        )}
      </div>
      )}
      <div className="card">
        <div className="filtres">
          <label>Recherche
            <input type="search" value={saisie} onChange={(e) => setSaisie(e.target.value)} placeholder="N de serie, marque, modele, id interne" />
          </label>
          <label>Statut
            <select value={filtre} onChange={(e) => setParam("statut", e.target.value)}>
              <option value="">tous</option>
              {FILTRES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Type
            <select value={filtreType} onChange={(e) => setParam("type", e.target.value)}>
              <option value="">tous</option>
              {typesDispos.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>Filiale / entite
            <select value={filtreEntite} onChange={(e) => setParam("entite", e.target.value)}>
              <option value="">toutes</option>
              {entites.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
            </select>
          </label>
        </div>
        {chips.length > 0 && (
          <div className="row chips">
            <span className="muted">Filtres actifs :</span>
            {chips.map((c) => (
              <button key={c.cle} type="button" className="chip" aria-label={`Retirer le filtre ${c.texte}`} onClick={() => retirer(c.cle)}>
                {c.texte} <span aria-hidden="true">{"×"}</span>
              </button>
            ))}
            <button type="button" className="ghost" onClick={clearFilters}>Tout effacer</button>
            <button type="button" className="ghost" onClick={copyLink}>Copier le lien</button>
          </div>
        )}
        {items && <p className="muted" role="status"><strong>{visibles.length} resultat(s)</strong> sur {items.length} actif(s)</p>}
        {items === null ? <Loading label="Chargement du materiel" />
          : items.length === 0 ? <Empty title="Aucun materiel enregistre" hint="Ajoutez un equipement avec le formulaire ci-dessus ou importez un fichier." />
          : visibles.length === 0 ? (
            <Empty title="Aucun materiel ne correspond" hint="Verifiez l'orthographe ou retirez un filtre.">
              <button type="button" className="ghost" onClick={clearFilters}>Effacer les filtres</button>
            </Empty>
          ) : (
        <div className="table-scroll">
        <table>
          <thead><tr><th>Id interne</th><th>Type</th><th>Marque</th><th>Modele</th><th>N serie</th><th>Statut</th>{writable && <th></th>}</tr></thead>
          <tbody>
            {visibles.map((a) => (
              <tr key={a.id} id={`actif-${a.id}`} className={a.id === idCible ? "row-cible" : undefined} aria-current={a.id === idCible ? "true" : undefined}>
                <td>{a.identifiant_interne || "-"}</td>
                <td>{a.type || "-"}</td>
                <td>{a.marque || "-"}</td>
                <td>{a.modele || "-"}</td>
                <td>{a.numero_serie || "-"}</td>
                <td><span className="badge">{a.statut}</span></td>
                {writable && (
                  <td>
                    <div className="row">
                      <button className="ghost" onClick={() => startEdit(a)}>Modifier</button>
                      {a.statut === "affecte" && <Link to={`/renouveler?asset=${a.id}`} className="ghost" style={{ padding: "6px 10px" }}>Renouveler</Link>}
                      <ConfirmButton onConfirm={() => remove(a)}>Supprimer</ConfirmButton>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
          )}
      </div>
    </div>
  );
}
