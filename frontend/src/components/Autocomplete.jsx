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

import { useEffect, useId, useRef, useState } from "react";

// Meme cle de comparaison que le serveur : sans accents, sans casse, espaces uniques.
export const fold = (s) =>
  (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();

// Classement local (listes courtes) : commence par, puis contient ; a egalite, ordre alphabetique.
function rankLocal(items, value, limit = 20) {
  const q = fold(value);
  return items
    .map((nom) => ({ nom, key: fold(nom) }))
    .filter((x) => !q || x.key.includes(q))
    .sort((a, b) => (b.key.startsWith(q) - a.key.startsWith(q)) || a.nom.localeCompare(b.nom))
    .slice(0, limit)
    .map((x) => ({ nom: x.nom }));
}

/**
 * Saisie assistee. Source des suggestions : `fetcher(q)` (serveur, renvoie [{nom, count}])
 * ou `items` (liste locale de noms). La valeur reste libre : une valeur inedite est acceptee.
 */
export default function Autocomplete({ value, onChange, fetcher, items, placeholder, nouveau = "Nouvelle valeur", required, disabled }) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [list, setList] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [active, setActive] = useState(-1);
  const focused = useRef(false);
  const timer = useRef(null);
  const seq = useRef(0);
  const latest = useRef({ fetcher, items });
  latest.current = { fetcher, items };

  const search = (q, delay = 150) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const mine = ++seq.current;
      try {
        const { fetcher: f, items: local } = latest.current;
        const res = f ? await f(q) : rankLocal(local || [], q);
        if (mine === seq.current) { setList(res); setLoaded(true); setActive(-1); }
      } catch { if (mine === seq.current) { setList([]); setLoaded(true); } }
    }, delay);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  // Les listes locales changent quand le serveur repond : on recalcule si le champ est actif.
  useEffect(() => { if (focused.current) search(value, 0); }, [items]);

  const pick = (nom) => { onChange(nom); setOpen(false); setActive(-1); };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) { setOpen(true); search(value, 0); return; }
      setActive((a) => Math.min(a + 1, list.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && open && active >= 0 && list[active]) {
      e.preventDefault();  // ne valide pas le formulaire : on choisit la suggestion
      pick(list[active].nom);
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  };

  const typed = value || "";
  const near = typed.trim() && loaded ? list.find((s) => fold(s.nom) === fold(typed) && s.nom !== typed) : null;
  const isNew = typed.trim() && loaded && !list.some((s) => fold(s.nom) === fold(typed));

  return (
    <div className="ac-wrap">
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        value={typed}
        placeholder={placeholder}
        required={required}
        disabled={disabled}
        onFocus={() => { focused.current = true; setOpen(true); search(typed, 0); }}
        onBlur={() => { focused.current = false; setTimeout(() => setOpen(false), 120); }}
        onChange={(e) => { onChange(e.target.value); setOpen(true); search(e.target.value); }}
        onKeyDown={onKeyDown}
      />
      {open && list.length > 0 && (
        <ul id={listId} role="listbox" className="ac-list">
          {list.map((s, i) => (
            <li
              key={s.nom}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className="ac-item"
              onMouseDown={(e) => { e.preventDefault(); pick(s.nom); }}
              onClick={(e) => e.preventDefault()}  // dans un <label>, un clic redonnerait le focus au champ et rouvrirait la liste
              onMouseEnter={() => setActive(i)}
            >
              <span>{s.nom}</span>
              {s.count != null && <span className="muted">{s.count} materiel(s)</span>}
            </li>
          ))}
        </ul>
      )}
      {near && !open && (
        <small className="muted">Proche de <b>{near.nom}</b> : <a href="#" onClick={(e) => { e.preventDefault(); pick(near.nom); }}>utiliser {near.nom}</a></small>
      )}
      {isNew && !open && <small className="muted">{nouveau} : elle sera ajoutee au catalogue.</small>}
    </div>
  );
}
