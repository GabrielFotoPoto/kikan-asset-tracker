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

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

// Fenetre de confirmation sur l'element natif <dialog> : le navigateur piege le focus, rend le reste
// de la page inerte, gere Echap et rend le focus au declencheur. Remplace window.confirm.
//   const confirm = useConfirm();
//   if (!(await confirm({ title, message, details, confirmLabel, danger, requireText }))) return;
// requireText : mot a taper pour debloquer le bouton (actions irreversibles).
const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [req, setReq] = useState(null);
  const [saisie, setSaisie] = useState("");
  const dialogRef = useRef(null);

  const confirm = useCallback((opts) => new Promise((resolve) => {
    setSaisie("");
    setReq({ opts, resolve });
  }), []);

  useEffect(() => {
    const d = dialogRef.current;
    if (!req || !d || d.open) return;
    d.showModal();
    // Le focus demarre sur Annuler, jamais sur l'action destructive.
    d.querySelector("[data-initial]")?.focus();
  }, [req]);

  const finish = (valeur) => {
    if (!req) return;
    dialogRef.current?.close();
    const { resolve } = req;
    setReq(null);
    resolve(valeur);
  };

  const opts = req?.opts;
  const autorise = !opts?.requireText || saisie.trim() === opts.requireText;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {req && (
        <dialog
          ref={dialogRef}
          className="confirm"
          role={opts.danger ? "alertdialog" : "dialog"}
          aria-labelledby="confirm-titre"
          aria-describedby="confirm-detail"
          onCancel={(e) => { e.preventDefault(); finish(false); }}
        >
          <form onSubmit={(e) => { e.preventDefault(); if (autorise) finish(true); }}>
            <h2 id="confirm-titre">{opts.title}</h2>
            <div id="confirm-detail" className="confirm-detail">{opts.message}</div>
            {opts.details}
            {opts.requireText && (
              <label>
                <span>Pour confirmer, tapez <code>{opts.requireText}</code></span>
                <input value={saisie} onChange={(e) => setSaisie(e.target.value)} autoComplete="off" aria-describedby="confirm-aide" />
                <span id="confirm-aide" className="muted">Le bouton se debloque quand le mot est exact.</span>
              </label>
            )}
            <div className="row confirm-actions">
              <button type="button" className="ghost" data-initial onClick={() => finish(false)}>Annuler</button>
              <button type="submit" className={opts.danger ? "danger" : ""} disabled={!autorise}>{opts.confirmLabel || "Confirmer"}</button>
            </div>
          </form>
        </dialog>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext) || ((opts) => Promise.resolve(window.confirm(opts.title)));
}
