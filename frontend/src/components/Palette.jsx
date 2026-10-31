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

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { canWrite, useAuth } from "../auth.jsx";
import { ACCUEIL, ACTIONS, SECTIONS, visible } from "../nav.js";

// Recherche globale (Ctrl+K) : materiel et salaries via GET /search (portee du compte appliquee par le serveur),
// pages et actions construites ici selon le role. Fenetre <dialog> native : focus piege, Echap, retour du focus.
const PaletteContext = createContext({ ouvrir() {} });
export const usePalette = () => useContext(PaletteContext);

const VIDE = { materiel: [], utilisateurs: [] };
const fold = (v) => (v || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const correspond = (terme, texte) => fold(terme).split(/\s+/).filter(Boolean).every((t) => fold(texte).includes(t));

export function PaletteProvider({ children }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [ouverte, setOuverte] = useState(false);
  const [saisie, setSaisie] = useState("");
  const [serveur, setServeur] = useState(VIDE);
  const [actif, setActif] = useState(0);
  const dialogRef = useRef(null);
  const champRef = useRef(null);
  const requete = useRef(0);

  const ouvrir = useCallback(() => { setSaisie(""); setServeur(VIDE); setActif(0); setOuverte(true); }, []);
  const fermer = useCallback(() => { dialogRef.current?.close(); setOuverte(false); }, []);

  useEffect(() => {
    const surTouche = (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); ouvrir(); }
    };
    window.addEventListener("keydown", surTouche);
    return () => window.removeEventListener("keydown", surTouche);
  }, [ouvrir]);

  useEffect(() => {
    const d = dialogRef.current;
    if (ouverte && d && !d.open) { d.showModal(); champRef.current?.focus(); }
  }, [ouverte]);

  // Resultats du serveur, 200 ms apres la derniere frappe ; une reponse arrivee en retard est ignoree.
  useEffect(() => {
    if (!ouverte) return undefined;
    const terme = saisie.trim();
    if (terme.length < 2) { setServeur(VIDE); return undefined; }
    const n = ++requete.current;
    const minuteur = setTimeout(() => {
      api.get(`/search?q=${encodeURIComponent(terme)}&limit=5`)
        .then((r) => { if (n === requete.current) setServeur(r); })
        .catch(() => { if (n === requete.current) setServeur(VIDE); });
    }, 200);
    return () => clearTimeout(minuteur);
  }, [saisie, ouverte]);

  const groupes = useMemo(() => {
    const terme = saisie.trim();
    const g = [];
    const nomActif = (a) => `${a.marque || ""} ${a.modele || ""}`.trim() || a.type || a.numero_serie || a.identifiant_interne || "Materiel";
    if (serveur.materiel.length) {
      g.push({ label: "Materiel", items: serveur.materiel.map((a) => ({
        cle: "m" + a.id, titre: nomActif(a),
        sous: [a.numero_serie && `N de serie ${a.numero_serie}`, a.statut].filter(Boolean).join(" - "),
        indice: "Ouvre Materiel", vers: `/materiel?asset=${a.id}` })) });
    }
    if (serveur.utilisateurs.length) {
      g.push({ label: "Utilisateurs", items: serveur.utilisateurs.map((u) => ({
        cle: "u" + u.id, titre: `${u.prenom || ""} ${u.nom || ""}`.trim(),
        sous: [u.matricule && `Matricule ${u.matricule}`, u.statut].filter(Boolean).join(" - "),
        indice: "Ouvre Utilisateurs", vers: `/utilisateurs?q=${encodeURIComponent(u.matricule || u.nom || "")}` })) });
    }
    const pages = [{ ...ACCUEIL, section: "" },
      ...SECTIONS.flatMap((s) => s.items.map((i) => ({ ...i, section: s.label }))).filter((i) => visible(i, user.role)),
      { to: "/compte", label: "Mon compte", section: "" }]
      .filter((p) => !terme || correspond(terme, `${p.label} ${p.section}`)).slice(0, 6);
    if (pages.length) g.push({ label: "Pages", items: pages.map((p) => ({ cle: "p" + p.to, titre: p.label, sous: p.section, indice: "Aller a", vers: p.to })) });
    const actions = ACTIONS.filter((a) => canWrite(user.role, a.droit) && (!terme || correspond(terme, a.label)));
    if (actions.length) g.push({ label: "Actions", items: actions.map((a) => ({ cle: "a" + a.to + a.label, titre: a.label, sous: "", indice: "Action", vers: a.to })) });
    return g;
  }, [saisie, serveur, user.role]);

  const aplati = groupes.flatMap((g) => g.items);
  useEffect(() => { setActif(0); }, [saisie, serveur]);

  const choisir = (item) => { if (!item) return; fermer(); navigate(item.vers); };
  const surChamp = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActif((i) => (aplati.length ? (i + 1) % aplati.length : 0)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActif((i) => (aplati.length ? (i - 1 + aplati.length) % aplati.length : 0)); }
    else if (e.key === "Enter") { e.preventDefault(); choisir(aplati[actif]); }
  };

  useEffect(() => { document.getElementById("pal-opt-" + actif)?.scrollIntoView({ block: "nearest" }); }, [actif, aplati.length]);

  let compteur = -1;
  return (
    <PaletteContext.Provider value={{ ouvrir }}>
      {children}
      {ouverte && (
        <dialog ref={dialogRef} className="palette" aria-label="Recherche globale"
                onCancel={(e) => { e.preventDefault(); fermer(); }}
                onClick={(e) => { if (e.target === e.currentTarget) fermer(); }}>
          <div className="palette-champ">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            <input ref={champRef} type="text" role="combobox" aria-label="Rechercher dans Kikan" aria-expanded="true" aria-controls="pal-liste"
                   aria-activedescendant={aplati.length ? "pal-opt-" + actif : undefined} autoComplete="off" spellCheck="false"
                   placeholder="Materiel, salarie, page ou action" value={saisie}
                   onChange={(e) => setSaisie(e.target.value)} onKeyDown={surChamp} />
            <kbd>Echap</kbd>
          </div>
          <div id="pal-liste" role="listbox" aria-label="Resultats" className="palette-liste">
            {groupes.map((g) => (
              <div key={g.label} role="group" aria-label={g.label}>
                <div className="palette-groupe">{g.label}</div>
                {g.items.map((it) => {
                  compteur += 1;
                  const i = compteur;
                  return (
                    <div key={it.cle} id={"pal-opt-" + i} role="option" aria-selected={i === actif}
                         className={i === actif ? "palette-option actif" : "palette-option"}
                         onMouseMove={() => setActif(i)} onClick={() => choisir(it)}>
                      <span><strong>{it.titre}</strong>{it.sous && <small>{it.sous}</small>}</span>
                      <small>{it.indice}</small>
                    </div>
                  );
                })}
              </div>
            ))}
            {!aplati.length && <div className="palette-vide">{`Aucun resultat pour « ${saisie.trim()} »`}</div>}
          </div>
          <div className="palette-pied">
            <span><kbd>{"↑"}</kbd> <kbd>{"↓"}</kbd> naviguer</span>
            <span><kbd>Entree</kbd> ouvrir</span>
            {user.role !== "informatique" && <span className="palette-portee">Limite a votre perimetre d'entites</span>}
          </div>
        </dialog>
      )}
    </PaletteContext.Provider>
  );
}
