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
import Pagination from "../components/Pagination.jsx";
import { Empty, Loading } from "../components/State.jsx";
import ThTri from "../components/ThTri.jsx";
import { fold, paginer, trier } from "../tableau.js";
import { useTableau } from "../useTableau.js";

const FILTRES = ["stock", "affecte", "rendu", "reforme"];
// Les statuts affecte et rendu viennent de la remise et de la restitution, jamais d'une saisie manuelle.
const SAISISSABLES = ["stock", "reforme"];
const DATES = ["date_achat", "fin_garantie", "echeance_renouvellement"];
const TEXTES = ["identifiant_interne", "type", "marque", "modele", "numero_serie", "notes"];
// Colonnes triables, dans l'ordre du tableau. Sans tri choisi : les derniers ajoutes d'abord (id decroissant).
const COLONNES = [
  ["identifiant_interne", "Id interne"], ["type", "Type"], ["marque", "Marque"],
  ["modele", "Modele"], ["numero_serie", "N serie"], ["statut", "Statut"],
];
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
  const filtreTypeSauf = params.get("typesauf") === "1";   // vrai : tous les types sauf celui choisi
  const filtreRetour = params.get("retour") === "1";       // vrai : seulement les retours en stock (deja remis, restitues)
  const filtreEntite = params.get("entite") || "";
  const idCible = Number(params.get("asset")) || null;
  // Tri, sens, nombre de lignes et page vivent dans l'adresse (voir useTableau.js) ; les filtres ci-dessus aussi.
  const { tri, sens, taille, page, setParam, changerTri, choisirTri, inverserSens, changerTaille, changerPage } =
    useTableau(params, setParams, COLONNES);
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
  // Retours en stock : materiels deja remis puis restitues, remis en stock (id -> date du dernier retour). Calcule par le serveur.
  const [retours, setRetours] = useState({});
  useEffect(() => {
    api.get("/assets/retours-stock").then((r) => setRetours(Object.fromEntries(r.map((x) => [x.asset_id, x.retour_le])))).catch(() => {});
  }, [items]);

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

  // Selection multiple (informatique) : portee sur toute la liste filtree, pas seulement la page affichee.
  // La suppression passe toujours par un apercu (simulation) qui liste ce qui serait supprime ou refuse.
  const [sel, setSel] = useState(() => new Set());
  const [lot, setLot] = useState(null);
  const [lotBusy, setLotBusy] = useState(false);
  const basculer = (id) => setSel((cur) => { const n = new Set(cur); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const cocher = (liste, valeur) => setSel((cur) => { const n = new Set(cur); liste.forEach((a) => (valeur ? n.add(a.id) : n.delete(a.id))); return n; });
  // action : "suppression" ou "reforme" (mise au rebut) ; les deux passent par un apercu (simulation) avant d'agir.
  const ROUTES_LOT = { suppression: "/assets/suppression-lot", reforme: "/assets/reforme-lot" };
  const apercuLot = async (action) => {
    setErr(null); setMsg(null); setLotBusy(true);
    try {
      const r = await api.post(ROUTES_LOT[action], { ids: [...sel], simulation: true });
      setLot({ ...r, action, ok: action === "reforme" ? r.reformes : r.supprimes });
    } catch (ex) { setErr(errorText(ex)); } finally { setLotBusy(false); }
  };
  const appliquerLot = async () => {
    const { action } = lot;
    setErr(null); setMsg(null); setLotBusy(true);
    try {
      const r = await api.post(ROUTES_LOT[action], { ids: [...sel], simulation: false });
      const n = (action === "reforme" ? r.reformes : r.supprimes).length;
      setMsg(`${n} materiel(s) ${action === "reforme" ? "reforme(s)" : "supprime(s)"}${r.refuses.length ? `, ${r.refuses.length} refuse(s)` : ""}.`);
      setSel(new Set()); setLot(null); load();
    } catch (ex) { setErr(errorText(ex)); } finally { setLotBusy(false); }
  };


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
    if (cle === "type") setParam("typesauf", "");
    setParam(cle, "");
  };
  const clearFilters = () => {
    poussee.current = ""; setSaisie("");
    setParams((prev) => {
      const p = new URLSearchParams(prev);
      ["q", "statut", "type", "typesauf", "retour", "entite", "page"].forEach((k) => p.delete(k));
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
      if (filtreType && (a.type === filtreType) === filtreTypeSauf) return false;
      if (filtreEntite && String(a.entite_id ?? "") !== filtreEntite) return false;
      if (filtreRetour && !retours[a.id]) return false;
      if (!termes.length) return true;
      const meule = fold([a.identifiant_interne, a.type, a.marque, a.modele, a.numero_serie, a.notes].filter(Boolean).join(" "));
      return termes.every((t) => meule.includes(t));
    });
  }, [items, saisie, filtre, filtreType, filtreTypeSauf, filtreEntite, filtreRetour, retours]);
  // Tri puis decoupage en pages : seules les lignes de la page affichee sont rendues (la recherche et les filtres,
  // eux, portent sur toute la liste). Le tri par defaut montre les derniers ajoutes en premier.
  const triees = useMemo(() => (tri ? trier(visibles, tri, sens) : trier(visibles, "id", "desc")), [visibles, tri, sens]);
  const pag = useMemo(() => paginer(triees, page, taille), [triees, page, taille]);
  const selNb = sel.size;
  const pageToute = writable && pag.tranche.length > 0 && pag.tranche.every((a) => sel.has(a.id));
  const filtreToute = triees.length > 0 && triees.every((a) => sel.has(a.id));
  const chips = [
    saisie.trim() && { cle: "q", texte: `Recherche : ${saisie.trim()}` },
    filtre && { cle: "statut", texte: `Statut : ${filtre}` },
    filtreType && { cle: "type", texte: `Type : ${filtreTypeSauf ? "tous sauf " : ""}${filtreType}` },
    filtreRetour && { cle: "retour", texte: "Retours en stock" },
    filtreEntite && { cle: "entite", texte: `Entite : ${entites.find((e) => String(e.id) === filtreEntite)?.nom || filtreEntite}` },
  ].filter(Boolean);

  // Actions d'une ligne : memes boutons dans le tableau et dans les cartes.
  const actionsDe = (a) => (
    <div className="row">
      <button className="ghost" onClick={() => startEdit(a)}>Modifier</button>
      {a.statut === "affecte" && <Link to={`/renouveler?asset=${a.id}`} className="ghost" style={{ padding: "6px 10px" }}>Renouveler</Link>}
      <ConfirmButton onConfirm={() => remove(a)}>Supprimer</ConfirmButton>
    </div>
  );

  // Lien profond ?asset=ID : un compte qui peut ecrire ouvre l'actif en modification, les autres le voient repere dans la liste.
  // Avec la pagination, l'actif vise peut etre sur une autre page : on affiche d'abord la page qui le contient.
  const cibleTraitee = useRef(false);
  const adefiler = useRef(null);
  useEffect(() => {
    if (!idCible || !items || cibleTraitee.current) return;
    cibleTraitee.current = true;
    const a = items.find((x) => x.id === idCible);
    if (!a) { setErr("Ce materiel n'existe pas ou n'est pas dans votre perimetre."); return; }
    if (writable) { startEdit(a); return; }
    const rang = triees.findIndex((x) => x.id === a.id);
    if (rang >= 0) setParam("page", String(Math.floor(rang / taille) + 1));
    adefiler.current = a.id;
  }, [idCible, items]);
  useEffect(() => {
    if (adefiler.current === null) return;
    const ligne = document.getElementById(`actif-${adefiler.current}`);
    if (!ligne) return;
    adefiler.current = null;
    requestAnimationFrame(() => ligne.scrollIntoView({ block: "center" }));
  }, [pag.page, items]);

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
          <label>Retours
            <span className="row" style={{ gap: 6, alignItems: "center", marginTop: 4 }}>
              <input type="checkbox" style={{ width: "auto" }} id="retours-stock" checked={filtreRetour}
                     onChange={(e) => setParam("retour", e.target.checked ? "1" : "")} />
              <label htmlFor="retours-stock" style={{ margin: 0 }}>Retours en stock ({Object.keys(retours).length})</label>
            </span>
          </label>
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
            <span className="row" style={{ gap: 6, alignItems: "center", marginTop: 4 }}>
              <input type="checkbox" style={{ width: "auto" }} id="type-sauf" checked={filtreTypeSauf} disabled={!filtreType}
                     onChange={(e) => setParam("typesauf", e.target.checked ? "1" : "")} />
              <label htmlFor="type-sauf" style={{ margin: 0 }}>Tous sauf ce type</label>
            </span>
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
        {writable && items && items.length > 0 && visibles.length > 0 && (
          <div className="row" style={{ alignItems: "center", gap: 8 }}>
            <button type="button" className="ghost" onClick={() => cocher(triees, !filtreToute)}>
              {filtreToute ? "Decocher les" : "Cocher les"} {triees.length} resultat(s)
            </button>
            {selNb > 0 && <>
              <strong>{selNb} selectionne(s)</strong>
              <button type="button" className="ghost" onClick={() => { setSel(new Set()); setLot(null); }}>Vider la selection</button>
              <button type="button" className="ghost" onClick={() => apercuLot("reforme")} disabled={lotBusy || selNb > 500}>Reformer la selection...</button>
              <button type="button" onClick={() => apercuLot("suppression")} disabled={lotBusy || selNb > 500}>Supprimer la selection...</button>
              {selNb > 500 && <span className="err">500 materiels au plus par suppression.</span>}
            </>}
          </div>
        )}
        {lot && (
          <div className="card" role="alertdialog" aria-label="Recapitulatif de la suppression">
            <h3>{lot.action === "reforme" ? "Reformer" : "Supprimer"} {lot.ok.length} materiel(s) ?</h3>
            <p className="muted">{lot.action === "reforme"
              ? "Le materiel passe au statut reforme et sort des previsions et des rappels ; son historique de remise est conserve. Un materiel actuellement remis est refuse."
              : "Cette suppression est definitive. Un materiel deja remis n'est jamais supprime : passez-le au statut reforme."}</p>
            {lot.refuses.length > 0 && (
              <div>
                <strong>{lot.refuses.length} refuse(s) :</strong>
                <ul>{lot.refuses.map((r) => <li key={r.id}>{r.identifiant ? `${r.identifiant} (n ${r.id})` : `n ${r.id}`} : {r.raison}</li>)}</ul>
              </div>
            )}
            {lot.apercu.length > 0 && (
              <div className="table-scroll" style={{ maxHeight: 260, overflowY: "auto" }}>
                <table>
                  <thead><tr><th>Id interne</th><th>Type</th><th>Marque</th><th>Modele</th><th>N serie</th></tr></thead>
                  <tbody>{lot.apercu.map((a) => (
                    <tr key={a.id}><td>{a.identifiant || "-"}</td><td>{a.type || "-"}</td><td>{a.marque || "-"}</td><td>{a.modele || "-"}</td><td>{a.numero_serie || "-"}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            <div className="row" style={{ marginTop: 8 }}>
              {lot.ok.length > 0 && <ConfirmButton confirmLabel={`Confirmer : ${lot.action === "reforme" ? "reformer" : "supprimer"} ${lot.ok.length} materiel(s)`} onConfirm={appliquerLot}>{lot.action === "reforme" ? "Reformer" : "Supprimer"} {lot.ok.length} materiel(s)</ConfirmButton>}
              <button type="button" className="ghost" onClick={() => setLot(null)}>Annuler</button>
            </div>
          </div>
        )}
        {items === null ? <Loading label="Chargement du materiel" />
          : items.length === 0 ? <Empty title="Aucun materiel enregistre" hint={writable ? "Ajoutez un equipement avec le formulaire ci-dessus ou importez un fichier." : "Le materiel est saisi par l'informatique."} />
          : visibles.length === 0 ? (
            <Empty title="Aucun materiel ne correspond" hint="Verifiez l'orthographe ou retirez un filtre.">
              <button type="button" className="ghost" onClick={clearFilters}>Effacer les filtres</button>
            </Empty>
          ) : (
        <>
        <div className="table-scroll vue-tableau">
        <table>
          <thead><tr>
            {writable && <th><input type="checkbox" aria-label="Selectionner les lignes de la page" checked={pageToute} onChange={() => cocher(pag.tranche, !pageToute)} /></th>}
            {COLONNES.map(([cle, libelle]) => <ThTri key={cle} cle={cle} tri={tri} sens={sens} onTri={changerTri}>{libelle}</ThTri>)}
            {writable && <th></th>}
          </tr></thead>
          <tbody>
            {pag.tranche.map((a) => (
              <tr key={a.id} id={`actif-${a.id}`} className={a.id === idCible ? "row-cible" : undefined} aria-current={a.id === idCible ? "true" : undefined}>
                {writable && <td><input type="checkbox" aria-label={`Selectionner ${a.identifiant_interne || a.numero_serie || a.id}`} checked={sel.has(a.id)} onChange={() => basculer(a.id)} /></td>}
                <td>{a.identifiant_interne || "-"}</td>
                <td>{a.type || "-"}</td>
                <td>{a.marque || "-"}</td>
                <td>{a.modele || "-"}</td>
                <td>{a.numero_serie || "-"}</td>
                <td><span className="badge">{a.statut}</span>{retours[a.id] && <span className="badge" title="Deja remis puis restitue, de nouveau en stock">{" "}Deja remis, retour du {String(retours[a.id]).slice(0, 10).split("-").reverse().join("/")}</span>}</td>
                {writable && <td>{actionsDe(a)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {/* Meme liste en cartes sur petit ecran (le tableau est alors masque par le CSS). */}
        <div className="tri-cartes">
          <label>Trier par
            <select value={tri} onChange={(e) => choisirTri(e.target.value)}>
              <option value="">Derniers ajoutes</option>
              {COLONNES.map(([cle, libelle]) => <option key={cle} value={cle}>{libelle}</option>)}
            </select>
          </label>
          {tri && (
            <button type="button" className="ghost" onClick={inverserSens}
                    aria-label={sens === "asc" ? "Tri croissant, cliquer pour inverser" : "Tri decroissant, cliquer pour inverser"}>
              {sens === "asc" ? "\u25B2 Croissant" : "\u25BC Decroissant"}
            </button>
          )}
        </div>
        <ul className="cartes">
          {pag.tranche.map((a) => (
            <li key={a.id} className={a.id === idCible ? "carte row-cible" : "carte"}>
              {writable && <label style={{ display: "flex", flexDirection: "row", gap: 8, alignItems: "center" }}><input type="checkbox" style={{ width: "auto" }} checked={sel.has(a.id)} onChange={() => basculer(a.id)} /> Selectionner</label>}
              <div className="carte-tete">
                <strong>{[a.marque, a.modele].filter(Boolean).join(" ") || a.type || "Materiel"}</strong>
                <span className="badge">{a.statut}</span>
              </div>
              {retours[a.id] && <div className="muted">Deja remis, retour du {String(retours[a.id]).slice(0, 10).split("-").reverse().join("/")}</div>}
              <div className="muted">{[a.type, a.identifiant_interne].filter(Boolean).join(" - ")}</div>
              {a.numero_serie && <code className="carte-serie">{a.numero_serie}</code>}
              {writable && actionsDe(a)}
            </li>
          ))}
        </ul>
        <Pagination pag={pag} taille={taille} objet="materiel(s)" onTaille={changerTaille}
                    onPage={changerPage} />
        </>
          )}
      </div>
    </div>
  );
}
