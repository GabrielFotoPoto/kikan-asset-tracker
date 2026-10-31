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

// Notifications en bas a droite. Succes et infos : annoncees poliment puis retirees apres 6 s.
// Erreurs : annoncees tout de suite (role alert) et conservees jusqu'a la fermeture.
const DUREE_MS = 6000;
const MAX = 4;
const ICONES = { ok: "✓", info: "i", err: "!" };

const NotifyContext = createContext(null);

export function NotificationsProvider({ children }) {
  const [items, setItems] = useState([]);
  const nextId = useRef(1);
  const timers = useRef(new Map());

  const close = useCallback((id) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setItems((liste) => liste.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((kind, text) => {
    if (!text) return;
    const id = nextId.current++;
    setItems((liste) => [...liste, { id, kind, text: String(text) }].slice(-MAX));
    if (kind !== "err") timers.current.set(id, setTimeout(() => close(id), DUREE_MS));
  }, [close]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const api = useMemo(() => ({
    ok: (text) => push("ok", text),
    info: (text) => push("info", text),
    err: (text) => push("err", text),
  }), [push]);

  const toast = (t) => (
    <div key={t.id} className={"toast " + t.kind}>
      <span className="toast-ico" aria-hidden="true">{ICONES[t.kind]}</span>
      <span className="toast-text">{t.text}</span>
      <button type="button" className="toast-close" aria-label="Fermer la notification" onClick={() => close(t.id)}>{"×"}</button>
    </div>
  );

  return (
    <NotifyContext.Provider value={api}>
      {children}
      <div className="toasts">
        <div role="status" aria-live="polite">{items.filter((t) => t.kind !== "err").map(toast)}</div>
        <div role="alert">{items.filter((t) => t.kind === "err").map(toast)}</div>
      </div>
    </NotifyContext.Provider>
  );
}

const SANS_FOURNISSEUR = { ok() {}, info() {}, err() {} };

export function useNotify() {
  return useContext(NotifyContext) || SANS_FOURNISSEUR;
}

// Remplace les deux lignes habituelles <p className="err"> et <p className="ok-msg"> : les messages
// que les pages posent dans leur etat deviennent des notifications. Un message identique redemande
// apres remise a zero (les pages font setMsg(null) avant chaque action) est annonce de nouveau.
export function Feedback({ err, msg }) {
  const notify = useNotify();
  const dernierMsg = useRef(null);
  const derniereErr = useRef(null);
  useEffect(() => {
    if (msg && msg !== dernierMsg.current) notify.ok(msg);
    dernierMsg.current = msg || null;
  }, [msg, notify]);
  useEffect(() => {
    if (err && err !== derniereErr.current) notify.err(err);
    derniereErr.current = err || null;
  }, [err, notify]);
  return null;
}
